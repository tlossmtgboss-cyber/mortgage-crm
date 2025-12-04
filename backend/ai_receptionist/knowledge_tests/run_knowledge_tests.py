#!/usr/bin/env python3
"""
================================================================================
PERENNIA AI - KNOWLEDGE TEST RUNNER
================================================================================
Run this script to test what the AI knows about your pipeline and CRM.

Usage:
    python run_knowledge_tests.py                    # Run all tests
    python run_knowledge_tests.py --category pipeline  # Test pipeline only
    python run_knowledge_tests.py --interactive      # Interactive mode
    python run_knowledge_tests.py --quick            # Quick summary only

================================================================================
"""

import os
import sys
import asyncio
import argparse
from datetime import datetime


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║     🧠 PERENNIA AI - KNOWLEDGE & CAPABILITY TEST SUITE                       ║
║                                                                              ║
║     Test what the AI knows about:                                            ║
║       • Pipeline stages and workflows                                        ║
║       • CRM entities and relationships                                       ║
║       • Loan types and requirements                                          ║
║       • Compliance rules (TRID, RESPA, ECOA)                                 ║
║       • 160 tools and their usage                                            ║
║       • Business metrics and reporting                                       ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)


def check_dependencies():
    """Check if required packages are installed"""
    missing = []

    try:
        import anthropic
    except ImportError:
        missing.append("anthropic")

    try:
        import openai
    except ImportError:
        missing.append("openai (optional)")

    if "anthropic" in missing:
        print("Missing required package: anthropic")
        print("Install with: pip install anthropic")
        print("\nOr set OPENAI_API_KEY to use OpenAI instead")
        return False

    return True


def check_api_keys():
    """Check for API keys"""
    claude_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not claude_key and not openai_key:
        print("❌ No API keys found!")
        print("\nSet one of these environment variables:")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        print("  export OPENAI_API_KEY='sk-...'")
        return None

    if claude_key:
        print("✓ Using Claude API")
        return "claude"
    else:
        print("✓ Using OpenAI API")
        return "openai"


async def run_interactive():
    """Interactive testing mode"""
    from AI_KNOWLEDGE_TEST_PART1_FRAMEWORK import KnowledgeCategory, MortgageKnowledgeBase
    from AI_KNOWLEDGE_TEST_PART2_TESTCASES import ALL_TESTS, get_tests_by_category
    from AI_KNOWLEDGE_TEST_PART3_RUNNER import ClaudeAdapter, OpenAIAdapter, TestRunner, ReportGenerator

    provider = check_api_keys()
    if not provider:
        return

    adapter = ClaudeAdapter() if provider == "claude" else OpenAIAdapter()

    while True:
        print("\n" + "=" * 50)
        print("INTERACTIVE TEST MODE")
        print("=" * 50)
        print("\nCategories:")
        print("  1. Pipeline     - Stages, flows, metrics")
        print("  2. CRM          - Entities, relationships")
        print("  3. Loans        - Types, requirements")
        print("  4. Compliance   - TRID, RESPA, Fair Lending")
        print("  5. Tools        - Tool usage tests")
        print("  6. Workflows    - Process knowledge")
        print("  7. All          - Run all tests")
        print("  8. Custom       - Ask a custom question")
        print("  0. Exit")

        choice = input("\nSelect [0-8]: ").strip()

        if choice == "0":
            break
        elif choice == "8":
            # Custom question
            question = input("\nEnter your question: ")
            response = await adapter.query(question)
            print(f"\nAI Response:\n{response}")
        else:
            # Map choice to category
            category_map = {
                "1": KnowledgeCategory.PIPELINE,
                "2": KnowledgeCategory.CRM,
                "3": KnowledgeCategory.LOANS,
                "4": KnowledgeCategory.COMPLIANCE,
                "5": KnowledgeCategory.TOOLS,
                "6": KnowledgeCategory.WORKFLOWS,
            }

            if choice == "7":
                tests = ALL_TESTS
            elif choice in category_map:
                tests = get_tests_by_category(category_map[choice])
            else:
                print("Invalid choice")
                continue

            # Run tests
            runner = TestRunner(adapter)
            print(f"\nRunning {len(tests)} tests...")

            results = await runner.run_tests(tests)

            # Show results
            passed = sum(1 for r in results if r.status.value == "passed")
            print(f"\n✓ Passed: {passed}/{len(results)}")

            # Show failures
            failures = [r for r in results if r.status.value == "failed"]
            if failures:
                print("\n❌ Failed tests:")
                for r in failures[:5]:
                    print(f"  - {r.name}: {r.details}")

    print("\nGoodbye!")


async def run_full_test(
    provider: str,
    category: str = None,
    output_dir: str = ".",
    verbose: bool = True,
):
    """Run full test suite"""
    from AI_KNOWLEDGE_TEST_PART1_FRAMEWORK import KnowledgeCategory
    from AI_KNOWLEDGE_TEST_PART2_TESTCASES import ALL_TESTS, get_tests_by_category, get_test_count
    from AI_KNOWLEDGE_TEST_PART3_RUNNER import (
        ClaudeAdapter, OpenAIAdapter, MockAdapter,
        TestRunner, ReportGenerator
    )

    # Create adapter
    if provider == "claude":
        adapter = ClaudeAdapter()
    elif provider == "openai":
        adapter = OpenAIAdapter()
    else:
        adapter = MockAdapter()

    # Select tests
    if category:
        cat = KnowledgeCategory(category.lower())
        tests = get_tests_by_category(cat)
        print(f"\nRunning {len(tests)} tests for category: {category}")
    else:
        tests = ALL_TESTS
        print(f"\nRunning all {len(tests)} tests...")

    # Progress display
    def progress(current, total, test_id):
        pct = current / total * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"\r  {bar} {pct:.0f}% ({current}/{total})", end="", flush=True)

    # Run
    runner = TestRunner(adapter)
    start = datetime.now()

    results = await runner.run_tests(tests, progress_callback=progress if verbose else None)

    execution_time = (datetime.now() - start).total_seconds()
    print(f"\n\n  Completed in {execution_time:.1f}s")

    # Generate report
    generator = ReportGenerator(results)
    report = generator.generate_full_report(execution_time)

    # Print summary
    print("\n" + "=" * 60)
    print("KNOWLEDGE TEST RESULTS")
    print("=" * 60)

    # Overall score with visual
    score_pct = report.overall_score * 100
    if score_pct >= 80:
        grade = "🌟 EXCELLENT"
        color = "\033[92m"  # Green
    elif score_pct >= 60:
        grade = "✓ GOOD"
        color = "\033[93m"  # Yellow
    elif score_pct >= 40:
        grade = "⚠ NEEDS WORK"
        color = "\033[93m"  # Yellow
    else:
        grade = "❌ POOR"
        color = "\033[91m"  # Red

    print(f"\n{color}Overall Score: {score_pct:.1f}% - {grade}\033[0m")

    # Category breakdown
    print("\nCategory Breakdown:")
    print("-" * 45)

    for name, cat in report.categories.items():
        score = cat.average_score * 100
        bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
        status = "✓" if score >= 70 else "⚠" if score >= 50 else "❌"
        print(f"  {name:15} {bar} {score:5.1f}% {status}")

    # Test counts
    passed = sum(1 for r in results if r.status.value == "passed")
    failed = sum(1 for r in results if r.status.value == "failed")
    partial = sum(1 for r in results if r.status.value == "partial")

    print("\n" + "-" * 45)
    print(f"  ✓ Passed:  {passed}")
    print(f"  ~ Partial: {partial}")
    print(f"  ❌ Failed:  {failed}")

    # Recommendations
    if report.recommendations:
        print("\n💡 Recommendations:")
        for rec in report.recommendations[:3]:
            print(f"  • {rec}")

    # Save reports
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_file = os.path.join(output_dir, f"knowledge_report_{timestamp}.json")
    with open(json_file, "w") as f:
        f.write(generator.to_json(report))

    html_file = os.path.join(output_dir, f"knowledge_report_{timestamp}.html")
    with open(html_file, "w") as f:
        f.write(generator.to_html(report))

    md_file = os.path.join(output_dir, f"knowledge_report_{timestamp}.md")
    with open(md_file, "w") as f:
        f.write(generator.to_markdown(report))

    print(f"\n📄 Reports saved:")
    print(f"  • {json_file}")
    print(f"  • {html_file}")
    print(f"  • {md_file}")

    print("\n" + "=" * 60)

    return report


async def run_quick_test(provider: str):
    """Run quick test with just summary"""
    from AI_KNOWLEDGE_TEST_PART2_TESTCASES import PIPELINE_TESTS, CRM_TESTS, LOAN_TESTS
    from AI_KNOWLEDGE_TEST_PART3_RUNNER import ClaudeAdapter, OpenAIAdapter, TestRunner, ReportGenerator

    adapter = ClaudeAdapter() if provider == "claude" else OpenAIAdapter()
    runner = TestRunner(adapter)

    # Just run a few key tests
    quick_tests = PIPELINE_TESTS[:3] + CRM_TESTS[:3] + LOAN_TESTS[:3]

    print(f"\nRunning quick test ({len(quick_tests)} tests)...")

    results = await runner.run_tests(quick_tests)

    passed = sum(1 for r in results if r.status.value == "passed")
    score = sum(r.score for r in results) / len(results)

    print(f"\n✓ Quick Score: {score:.1%}")
    print(f"  Passed: {passed}/{len(results)}")

    if score >= 0.7:
        print("\n🌟 AI has good knowledge of your system!")
    else:
        print("\n⚠ AI may need additional context or training.")


def main():
    parser = argparse.ArgumentParser(
        description="Test what the AI knows about your pipeline and CRM"
    )
    parser.add_argument("--category", type=str,
                       choices=["pipeline", "crm", "loans", "compliance", "tools", "workflows"],
                       help="Test specific category only")
    parser.add_argument("--interactive", "-i", action="store_true",
                       help="Interactive testing mode")
    parser.add_argument("--quick", "-q", action="store_true",
                       help="Quick test (subset of tests)")
    parser.add_argument("--output", "-o", type=str, default=".",
                       help="Output directory for reports")
    parser.add_argument("--provider", type=str, choices=["claude", "openai", "auto"],
                       default="auto", help="AI provider")

    args = parser.parse_args()

    print_banner()

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Determine provider
    if args.provider == "auto":
        provider = check_api_keys()
        if not provider:
            sys.exit(1)
    else:
        provider = args.provider

    # Run appropriate mode
    if args.interactive:
        asyncio.run(run_interactive())
    elif args.quick:
        asyncio.run(run_quick_test(provider))
    else:
        asyncio.run(run_full_test(
            provider=provider,
            category=args.category,
            output_dir=args.output,
        ))


if __name__ == "__main__":
    main()
