#!/bin/bash
#
# optimize.sh - CLAUDE.md Optimization Script
#
# Usage:
#   ./optimize.sh CLAUDE.md           # Split and test
#   ./optimize.sh demo                # Run demo with sample file
#   ./optimize.sh benchmark           # Run performance benchmark
#   ./optimize.sh test                # Run test suite
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default output directory
OUTPUT_DIR="./prompts"

print_header() {
    echo -e "\n${BLUE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_dependencies() {
    print_header "Checking Dependencies"

    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed."
        exit 1
    fi
    print_success "Python 3 found: $(python3 --version)"

    # Check for required files
    if [ ! -f "prompt_splitter.py" ]; then
        print_error "prompt_splitter.py not found in current directory"
        exit 1
    fi
    print_success "prompt_splitter.py found"

    if [ ! -f "prompt_loader.py" ]; then
        print_error "prompt_loader.py not found in current directory"
        exit 1
    fi
    print_success "prompt_loader.py found"

    if [ ! -f "prompt_integration.py" ]; then
        print_error "prompt_integration.py not found in current directory"
        exit 1
    fi
    print_success "prompt_integration.py found"
}

create_demo_file() {
    print_header "Creating Demo CLAUDE.md"

    cat > demo_claude.md << 'EOF'
# Perennia AI - Core Identity

You are Perennia AI, an intelligent assistant for mortgage loan officers. Your primary goal is to help loan officers manage their pipeline efficiently and close more loans.

## Core Principles

1. Always prioritize accuracy over speed
2. Provide actionable insights
3. Maintain compliance with regulations
4. Support the loan officer's workflow

## Safety Instructions

- Never share sensitive borrower information inappropriately
- Always verify identity before providing loan details
- Follow RESPA and TRID guidelines
- Protect personally identifiable information (PII)

## Communication Style

- Be professional yet friendly
- Use clear, concise language
- Avoid jargon when possible
- Provide context for recommendations

## Tool Usage Guidelines

When using tools, follow these principles:

### Pipeline Tools
- get_pipeline_metrics: Use for dashboard views
- get_loans_by_status: Use for status filtering
- calculate_conversion_rates: Use for performance analysis

### Lead Management Tools
- get_lead_details: Retrieve complete lead profiles
- score_lead: Calculate lead quality scores
- suggest_followup: Recommend next actions

### Document Tools
- get_missing_documents: Check for incomplete files
- get_loan_conditions: Track outstanding conditions
- send_document_reminder: Automate follow-ups

## Memory and Context

Maintain context throughout conversations:
- Remember current loan being discussed
- Track user preferences
- Reference previous recommendations
- Build on established context

## Search Capabilities

When searching for information:
- Query the knowledge base first
- Use appropriate filters
- Rank results by relevance
- Provide source citations

## Agent Orchestration

For complex tasks, delegate to specialized agents:
- Pipeline Analyst: Performance metrics
- Compliance Checker: Regulatory verification
- Lead Nurturer: Lead engagement
- Document Tracker: File management

## Domain Knowledge - Mortgage Industry

### Loan Types
- Conventional: Standard mortgages
- FHA: Government-insured for first-time buyers
- VA: For veterans and military
- Jumbo: Above conforming limits

### Pipeline Stages
- Application → Processing → Underwriting → Approval → Closing

### Key Metrics
- Pull-through rate
- Cycle time
- Conversion rate
- Volume and units

## Workflow Procedures

### Daily Priorities
1. Check urgent tasks
2. Review pipeline alerts
3. Follow up with borrowers
4. Update loan statuses

### Weekly Reviews
1. Pipeline health check
2. Lead scoring updates
3. Document collection status
4. Performance metrics

## Optional: Advanced Features

### Rate Lock Management
Monitor rate lock expirations and alert proactively.

### Competitive Analysis
Compare rates and terms with market data.

### Predictive Analytics
Forecast closing probabilities based on historical patterns.
EOF

    print_success "Created demo_claude.md ($(wc -c < demo_claude.md | tr -d ' ') chars)"
}

split_file() {
    local input_file="$1"

    print_header "Splitting $input_file"

    if [ ! -f "$input_file" ]; then
        print_error "File not found: $input_file"
        exit 1
    fi

    local char_count=$(wc -c < "$input_file" | tr -d ' ')
    echo "Input file: $input_file ($char_count characters)"
    echo "Output directory: $OUTPUT_DIR"
    echo ""

    python3 prompt_splitter.py "$input_file" "$OUTPUT_DIR"

    print_success "Split complete!"

    # Show results
    echo ""
    echo "Generated files:"
    find "$OUTPUT_DIR" -type f -name "*.md" -o -name "*.json" | while read file; do
        local size=$(wc -c < "$file" | tr -d ' ')
        echo "  $file ($size chars)"
    done
}

run_benchmark() {
    print_header "Running Performance Benchmark"

    if [ ! -d "$OUTPUT_DIR" ]; then
        print_error "Prompts directory not found. Run split first."
        exit 1
    fi

    python3 prompt_integration.py "$OUTPUT_DIR" --benchmark
}

run_tests() {
    print_header "Running Test Suite"

    if [ -f "test_suite.py" ]; then
        python3 test_suite.py
    else
        print_warning "test_suite.py not found. Running basic validation..."

        echo "Testing prompt_splitter.py..."
        python3 -c "import prompt_splitter; print('  ✓ Import successful')"

        echo "Testing prompt_loader.py..."
        python3 -c "import prompt_loader; print('  ✓ Import successful')"

        echo "Testing prompt_integration.py..."
        python3 -c "import prompt_integration; print('  ✓ Import successful')"

        print_success "Basic validation passed"
    fi
}

run_demo() {
    print_header "Running Full Demo"

    # Create demo file
    create_demo_file

    # Split it
    OUTPUT_DIR="./demo_prompts"
    split_file "demo_claude.md"

    # Run benchmark
    run_benchmark

    # Summary
    print_header "Demo Complete"

    echo "Files created:"
    echo "  - demo_claude.md (sample input)"
    echo "  - demo_prompts/ (split output)"
    echo ""
    echo "To use in your code:"
    echo ""
    echo "  from prompt_integration import OptimizedPromptService, ContextPresets"
    echo ""
    echo "  service = OptimizedPromptService('./demo_prompts')"
    echo "  prompt = service.get_system_prompt(ContextPresets.conversational())"
    echo ""

    print_success "Ready to integrate!"
}

show_help() {
    echo "CLAUDE.md Optimization Script"
    echo ""
    echo "Usage:"
    echo "  ./optimize.sh <command> [options]"
    echo ""
    echo "Commands:"
    echo "  <file.md>     Split the specified CLAUDE.md file"
    echo "  demo          Create and split a demo file, run benchmark"
    echo "  benchmark     Run performance benchmark on existing prompts"
    echo "  test          Run the test suite"
    echo "  help          Show this help message"
    echo ""
    echo "Options:"
    echo "  -o, --output  Specify output directory (default: ./prompts)"
    echo ""
    echo "Examples:"
    echo "  ./optimize.sh CLAUDE.md"
    echo "  ./optimize.sh CLAUDE.md -o ./my_prompts"
    echo "  ./optimize.sh demo"
    echo "  ./optimize.sh benchmark"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        help|--help|-h)
            show_help
            exit 0
            ;;
        demo)
            check_dependencies
            run_demo
            exit 0
            ;;
        benchmark)
            check_dependencies
            run_benchmark
            exit 0
            ;;
        test)
            check_dependencies
            run_tests
            exit 0
            ;;
        *.md)
            check_dependencies
            split_file "$1"
            exit 0
            ;;
        *)
            print_error "Unknown command: $1"
            echo "Run './optimize.sh help' for usage"
            exit 1
            ;;
    esac
done

# No arguments - show help
show_help
