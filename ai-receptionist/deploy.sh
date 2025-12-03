#!/bin/bash
#===============================================================================
# PERENNIA AI RECEPTIONIST - DEPLOYMENT SCRIPT
#===============================================================================
# One-command deployment for the AI Receptionist system
#
# Usage:
#   ./deploy.sh              # Interactive setup
#   ./deploy.sh --docker     # Deploy with Docker
#   ./deploy.sh --local      # Run locally
#   ./deploy.sh --check      # Check configuration
#   ./deploy.sh --ngrok      # Start with ngrok tunnel
#===============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"

#===============================================================================
# HELPER FUNCTIONS
#===============================================================================

print_banner() {
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                                                                  ║"
    echo "║           🎙️  PERENNIA AI RECEPTIONIST DEPLOYMENT  🎙️            ║"
    echo "║                                                                  ║"
    echo "║     Intelligent Voice AI for Mortgage Companies                  ║"
    echo "║                                                                  ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

check_command() {
    if command -v "$1" &> /dev/null; then
        log_success "$1 is installed"
        return 0
    else
        log_error "$1 is not installed"
        return 1
    fi
}

#===============================================================================
# ENVIRONMENT SETUP
#===============================================================================

check_prerequisites() {
    log_info "Checking prerequisites..."

    local all_ok=true

    # Required
    check_command "python3" || all_ok=false
    check_command "pip" || check_command "pip3" || all_ok=false

    # Optional but recommended
    check_command "docker" || log_warning "Docker not found (optional)"
    check_command "ngrok" || log_warning "ngrok not found (optional for local dev)"

    if [ "$all_ok" = false ]; then
        log_error "Missing required prerequisites"
        exit 1
    fi

    log_success "All required prerequisites met"
}

create_env_file() {
    local env_file="${PROJECT_ROOT}/.env"

    if [ -f "$env_file" ]; then
        log_warning ".env file already exists"
        read -p "Overwrite? (y/N): " overwrite
        if [ "$overwrite" != "y" ] && [ "$overwrite" != "Y" ]; then
            log_info "Keeping existing .env file"
            return
        fi
    fi

    echo -e "${CYAN}"
    echo "═══════════════════════════════════════════════════════════════"
    echo "                    ENVIRONMENT SETUP"
    echo "═══════════════════════════════════════════════════════════════"
    echo -e "${NC}"

    # Twilio
    echo -e "${YELLOW}TWILIO CONFIGURATION${NC}"
    echo "Get credentials from: https://console.twilio.com"
    echo ""
    read -p "Twilio Account SID: " TWILIO_ACCOUNT_SID
    read -p "Twilio Auth Token: " TWILIO_AUTH_TOKEN
    read -p "Twilio Phone Number (e.g., +15551234567): " TWILIO_PHONE_NUMBER
    read -p "Webhook Base URL (e.g., https://your-domain.com): " TWILIO_WEBHOOK_BASE_URL

    echo ""
    echo -e "${YELLOW}LLM CONFIGURATION${NC}"
    echo "Choose your LLM provider (Claude recommended)"
    echo ""
    read -p "Anthropic API Key (or press Enter to skip): " ANTHROPIC_API_KEY
    read -p "OpenAI API Key (or press Enter to skip): " OPENAI_API_KEY

    echo ""
    echo -e "${YELLOW}SPEECH SERVICES${NC}"
    echo "Get Deepgram key from: https://console.deepgram.com"
    echo "Get ElevenLabs key from: https://elevenlabs.io"
    echo ""
    read -p "Deepgram API Key: " DEEPGRAM_API_KEY
    read -p "ElevenLabs API Key: " ELEVENLABS_API_KEY

    echo ""
    echo -e "${YELLOW}DATABASE (Optional)${NC}"
    read -p "Database URL (or press Enter to skip): " DATABASE_URL

    # Write .env file
    cat > "$env_file" << EOF
#===============================================================================
# PERENNIA AI RECEPTIONIST - ENVIRONMENT CONFIGURATION
#===============================================================================
# Generated on: $(date)
#===============================================================================

#-------------------------------------------------------------------------------
# TWILIO VOICE
#-------------------------------------------------------------------------------
TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID}
TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN}
TWILIO_PHONE_NUMBER=${TWILIO_PHONE_NUMBER}
TWILIO_WEBHOOK_BASE_URL=${TWILIO_WEBHOOK_BASE_URL}

#-------------------------------------------------------------------------------
# LLM PROVIDERS
#-------------------------------------------------------------------------------
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
OPENAI_API_KEY=${OPENAI_API_KEY}

#-------------------------------------------------------------------------------
# SPEECH SERVICES
#-------------------------------------------------------------------------------
DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}
ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}

#-------------------------------------------------------------------------------
# DATABASE
#-------------------------------------------------------------------------------
DATABASE_URL=${DATABASE_URL}

#-------------------------------------------------------------------------------
# SERVER
#-------------------------------------------------------------------------------
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
EOF

    log_success "Created .env file"
}

load_env() {
    local env_file="${PROJECT_ROOT}/.env"

    if [ -f "$env_file" ]; then
        export $(grep -v '^#' "$env_file" | xargs)
        log_success "Loaded environment from .env"
    else
        log_warning "No .env file found"
    fi
}

#===============================================================================
# PYTHON SETUP
#===============================================================================

setup_python_env() {
    log_info "Setting up Python environment..."

    # Create virtual environment if it doesn't exist
    if [ ! -d "${PROJECT_ROOT}/venv" ]; then
        log_info "Creating virtual environment..."
        python3 -m venv "${PROJECT_ROOT}/venv"
    fi

    # Activate virtual environment
    source "${PROJECT_ROOT}/venv/bin/activate"

    # Upgrade pip
    pip install --upgrade pip

    # Install dependencies
    log_info "Installing dependencies..."
    pip install -r "${PROJECT_ROOT}/requirements.txt"

    log_success "Python environment ready"
}

#===============================================================================
# CONFIGURATION CHECK
#===============================================================================

check_configuration() {
    echo -e "${CYAN}"
    echo "═══════════════════════════════════════════════════════════════"
    echo "                 CONFIGURATION CHECK"
    echo "═══════════════════════════════════════════════════════════════"
    echo -e "${NC}"

    load_env

    local all_ok=true

    # Required
    echo -e "${YELLOW}Required Services:${NC}"

    if [ -n "$TWILIO_ACCOUNT_SID" ] && [ "$TWILIO_ACCOUNT_SID" != "" ]; then
        log_success "Twilio Account SID: ${TWILIO_ACCOUNT_SID:0:10}..."
    else
        log_error "Twilio Account SID: NOT SET"
        all_ok=false
    fi

    if [ -n "$TWILIO_AUTH_TOKEN" ] && [ "$TWILIO_AUTH_TOKEN" != "" ]; then
        log_success "Twilio Auth Token: ****${TWILIO_AUTH_TOKEN: -4}"
    else
        log_error "Twilio Auth Token: NOT SET"
        all_ok=false
    fi

    if [ -n "$TWILIO_PHONE_NUMBER" ] && [ "$TWILIO_PHONE_NUMBER" != "" ]; then
        log_success "Twilio Phone: $TWILIO_PHONE_NUMBER"
    else
        log_error "Twilio Phone: NOT SET"
        all_ok=false
    fi

    # LLM
    echo ""
    echo -e "${YELLOW}LLM Provider:${NC}"

    if [ -n "$ANTHROPIC_API_KEY" ] && [ "$ANTHROPIC_API_KEY" != "" ]; then
        log_success "Anthropic API Key: ****${ANTHROPIC_API_KEY: -4}"
    elif [ -n "$OPENAI_API_KEY" ] && [ "$OPENAI_API_KEY" != "" ]; then
        log_success "OpenAI API Key: ****${OPENAI_API_KEY: -4}"
    else
        log_error "No LLM API key set (need Anthropic or OpenAI)"
        all_ok=false
    fi

    # Speech
    echo ""
    echo -e "${YELLOW}Speech Services:${NC}"

    if [ -n "$DEEPGRAM_API_KEY" ] && [ "$DEEPGRAM_API_KEY" != "" ]; then
        log_success "Deepgram API Key: ****${DEEPGRAM_API_KEY: -4}"
    else
        log_warning "Deepgram API Key: NOT SET (STT will be limited)"
    fi

    if [ -n "$ELEVENLABS_API_KEY" ] && [ "$ELEVENLABS_API_KEY" != "" ]; then
        log_success "ElevenLabs API Key: ****${ELEVENLABS_API_KEY: -4}"
    else
        log_warning "ElevenLabs API Key: NOT SET (TTS will use Twilio)"
    fi

    # Database
    echo ""
    echo -e "${YELLOW}Database:${NC}"

    if [ -n "$DATABASE_URL" ] && [ "$DATABASE_URL" != "" ]; then
        log_success "Database URL: configured"
    else
        log_warning "Database URL: NOT SET (CRM features disabled)"
    fi

    # Webhook URL
    echo ""
    echo -e "${YELLOW}Webhook Configuration:${NC}"

    if [ -n "$TWILIO_WEBHOOK_BASE_URL" ] && [ "$TWILIO_WEBHOOK_BASE_URL" != "" ]; then
        log_success "Webhook URL: $TWILIO_WEBHOOK_BASE_URL"
        echo ""
        echo -e "${CYAN}Configure in Twilio Console:${NC}"
        echo "  Voice URL: ${TWILIO_WEBHOOK_BASE_URL}/voice/inbound"
        echo "  Method: POST"
    else
        log_error "Webhook Base URL: NOT SET"
        all_ok=false
    fi

    echo ""
    if [ "$all_ok" = true ]; then
        log_success "Configuration check passed!"
        return 0
    else
        log_error "Configuration check failed - please fix errors above"
        return 1
    fi
}

#===============================================================================
# TWILIO WEBHOOK SETUP
#===============================================================================

setup_twilio_webhook() {
    log_info "Setting up Twilio webhook..."

    load_env

    if [ -z "$TWILIO_ACCOUNT_SID" ] || [ -z "$TWILIO_AUTH_TOKEN" ]; then
        log_error "Twilio credentials not configured"
        return 1
    fi

    if [ -z "$TWILIO_PHONE_NUMBER" ]; then
        log_error "Twilio phone number not configured"
        return 1
    fi

    if [ -z "$TWILIO_WEBHOOK_BASE_URL" ]; then
        log_error "Webhook base URL not configured"
        return 1
    fi

    # Get the phone number SID
    log_info "Looking up phone number..."

    PHONE_SID=$(curl -s -X GET "https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}/IncomingPhoneNumbers.json?PhoneNumber=${TWILIO_PHONE_NUMBER}" \
        -u "${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}" | \
        python3 -c "import sys, json; data = json.load(sys.stdin); print(data['incoming_phone_numbers'][0]['sid'] if data['incoming_phone_numbers'] else '')")

    if [ -z "$PHONE_SID" ]; then
        log_error "Could not find phone number in Twilio account"
        return 1
    fi

    log_info "Found phone number SID: $PHONE_SID"

    # Update webhook URL
    log_info "Updating webhook URL..."

    RESULT=$(curl -s -X POST "https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}/IncomingPhoneNumbers/${PHONE_SID}.json" \
        -u "${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}" \
        --data-urlencode "VoiceUrl=${TWILIO_WEBHOOK_BASE_URL}/voice/inbound" \
        --data-urlencode "VoiceMethod=POST" \
        --data-urlencode "StatusCallback=${TWILIO_WEBHOOK_BASE_URL}/voice/status" \
        --data-urlencode "StatusCallbackMethod=POST")

    if echo "$RESULT" | grep -q "voice_url"; then
        log_success "Twilio webhook configured!"
        echo ""
        echo -e "${CYAN}Webhook URLs set:${NC}"
        echo "  Voice URL: ${TWILIO_WEBHOOK_BASE_URL}/voice/inbound"
        echo "  Status Callback: ${TWILIO_WEBHOOK_BASE_URL}/voice/status"
    else
        log_error "Failed to update webhook"
        echo "$RESULT"
        return 1
    fi
}

#===============================================================================
# RUN LOCALLY
#===============================================================================

run_local() {
    log_info "Starting AI Receptionist locally..."

    load_env

    # Activate virtual environment if exists
    if [ -d "${PROJECT_ROOT}/venv" ]; then
        source "${PROJECT_ROOT}/venv/bin/activate"
    fi

    # Set defaults
    HOST=${HOST:-0.0.0.0}
    PORT=${PORT:-8000}

    echo ""
    echo -e "${GREEN}Starting server on http://${HOST}:${PORT}${NC}"
    echo ""
    echo "Endpoints:"
    echo "  POST /voice/inbound      - Twilio call webhook"
    echo "  POST /voice/process-speech - Speech processing"
    echo "  WS   /voice/stream       - Audio streaming"
    echo "  GET  /health             - Health check"
    echo ""
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    echo ""

    python3 "${PROJECT_ROOT}/main.py"
}

#===============================================================================
# NGROK TUNNEL
#===============================================================================

run_with_ngrok() {
    log_info "Starting with ngrok tunnel..."

    if ! command -v ngrok &> /dev/null; then
        log_error "ngrok is not installed"
        echo "Install from: https://ngrok.com/download"
        exit 1
    fi

    load_env
    PORT=${PORT:-8000}

    # Start ngrok in background
    log_info "Starting ngrok tunnel on port $PORT..."
    ngrok http $PORT > /dev/null &
    NGROK_PID=$!

    # Wait for ngrok to start
    sleep 3

    # Get ngrok URL
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'] if data['tunnels'] else '')")

    if [ -z "$NGROK_URL" ]; then
        log_error "Could not get ngrok URL"
        kill $NGROK_PID 2>/dev/null
        exit 1
    fi

    log_success "ngrok tunnel: $NGROK_URL"

    # Update environment
    export TWILIO_WEBHOOK_BASE_URL="$NGROK_URL"

    echo ""
    echo -e "${CYAN}Configure Twilio webhook:${NC}"
    echo "  Voice URL: ${NGROK_URL}/voice/inbound"
    echo ""

    # Ask if user wants to auto-configure Twilio
    read -p "Auto-configure Twilio webhook? (y/N): " auto_config
    if [ "$auto_config" = "y" ] || [ "$auto_config" = "Y" ]; then
        setup_twilio_webhook
    fi

    # Start server
    echo ""
    log_info "Starting server..."

    # Trap to kill ngrok on exit
    trap "kill $NGROK_PID 2>/dev/null" EXIT

    run_local
}

#===============================================================================
# DOCKER DEPLOYMENT
#===============================================================================

build_docker() {
    log_info "Building Docker image..."

    docker build -t perennia-receptionist:latest "${PROJECT_ROOT}"

    log_success "Docker image built: perennia-receptionist:latest"
}

run_docker() {
    log_info "Starting Docker container..."

    load_env

    docker run -d \
        --name perennia-receptionist \
        -p ${PORT:-8000}:8000 \
        -e TWILIO_ACCOUNT_SID \
        -e TWILIO_AUTH_TOKEN \
        -e TWILIO_PHONE_NUMBER \
        -e TWILIO_WEBHOOK_BASE_URL \
        -e ANTHROPIC_API_KEY \
        -e OPENAI_API_KEY \
        -e DEEPGRAM_API_KEY \
        -e ELEVENLABS_API_KEY \
        -e DATABASE_URL \
        perennia-receptionist:latest

    log_success "Container started: perennia-receptionist"
    echo ""
    echo "View logs: docker logs -f perennia-receptionist"
    echo "Stop: docker stop perennia-receptionist"
}

deploy_docker() {
    build_docker
    run_docker
}

#===============================================================================
# DOCKER COMPOSE
#===============================================================================

deploy_compose() {
    log_info "Starting with Docker Compose..."

    load_env

    docker-compose up -d

    log_success "Services started"
    echo ""
    echo "View logs: docker-compose logs -f"
    echo "Stop: docker-compose down"
}

#===============================================================================
# HEALTH CHECK
#===============================================================================

health_check() {
    load_env
    PORT=${PORT:-8000}

    log_info "Checking health at http://localhost:${PORT}/health..."

    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${PORT}/health" 2>/dev/null)

    if [ "$RESPONSE" = "200" ]; then
        log_success "Server is healthy!"
        curl -s "http://localhost:${PORT}/health" | python3 -m json.tool
    else
        log_error "Server is not responding (HTTP $RESPONSE)"
        return 1
    fi
}

#===============================================================================
# TEST CALL
#===============================================================================

test_call() {
    log_info "Making test call..."

    load_env

    if [ -z "$TWILIO_ACCOUNT_SID" ] || [ -z "$TWILIO_AUTH_TOKEN" ]; then
        log_error "Twilio credentials not configured"
        return 1
    fi

    read -p "Enter phone number to call (e.g., +15551234567): " TO_NUMBER

    log_info "Initiating call to $TO_NUMBER..."

    RESULT=$(curl -s -X POST "https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}/Calls.json" \
        -u "${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}" \
        --data-urlencode "To=${TO_NUMBER}" \
        --data-urlencode "From=${TWILIO_PHONE_NUMBER}" \
        --data-urlencode "Url=${TWILIO_WEBHOOK_BASE_URL}/voice/inbound")

    if echo "$RESULT" | grep -q "sid"; then
        CALL_SID=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['sid'])")
        log_success "Call initiated: $CALL_SID"
    else
        log_error "Failed to initiate call"
        echo "$RESULT"
    fi
}

#===============================================================================
# MAIN
#===============================================================================

main() {
    print_banner

    case "${1:-}" in
        --setup)
            check_prerequisites
            create_env_file
            setup_python_env
            check_configuration
            ;;
        --check)
            check_configuration
            ;;
        --local)
            run_local
            ;;
        --ngrok)
            run_with_ngrok
            ;;
        --docker)
            deploy_docker
            ;;
        --compose)
            deploy_compose
            ;;
        --build)
            build_docker
            ;;
        --webhook)
            setup_twilio_webhook
            ;;
        --health)
            health_check
            ;;
        --test-call)
            test_call
            ;;
        --help|-h)
            echo "Usage: ./deploy.sh [OPTION]"
            echo ""
            echo "Options:"
            echo "  --setup      Interactive setup (recommended first run)"
            echo "  --check      Check configuration"
            echo "  --local      Run locally"
            echo "  --ngrok      Run with ngrok tunnel (for development)"
            echo "  --docker     Deploy with Docker"
            echo "  --compose    Deploy with Docker Compose"
            echo "  --build      Build Docker image only"
            echo "  --webhook    Configure Twilio webhook"
            echo "  --health     Check server health"
            echo "  --test-call  Make a test call"
            echo "  --help       Show this help"
            echo ""
            echo "Examples:"
            echo "  ./deploy.sh --setup     # First time setup"
            echo "  ./deploy.sh --ngrok     # Development with tunnel"
            echo "  ./deploy.sh --docker    # Production deployment"
            ;;
        *)
            # Interactive mode
            echo "What would you like to do?"
            echo ""
            echo "  1) Initial Setup (first time)"
            echo "  2) Check Configuration"
            echo "  3) Run Locally"
            echo "  4) Run with ngrok (development)"
            echo "  5) Deploy with Docker"
            echo "  6) Configure Twilio Webhook"
            echo "  7) Health Check"
            echo "  8) Make Test Call"
            echo "  9) Exit"
            echo ""
            read -p "Choose [1-9]: " choice

            case $choice in
                1) check_prerequisites; create_env_file; setup_python_env; check_configuration ;;
                2) check_configuration ;;
                3) run_local ;;
                4) run_with_ngrok ;;
                5) deploy_docker ;;
                6) setup_twilio_webhook ;;
                7) health_check ;;
                8) test_call ;;
                9) exit 0 ;;
                *) log_error "Invalid choice" ;;
            esac
            ;;
    esac
}

main "$@"
