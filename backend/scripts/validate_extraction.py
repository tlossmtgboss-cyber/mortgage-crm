#!/usr/bin/env python3
"""
Extraction Validation CLI

Compares unified extraction vs parallel agents to validate quality.

Usage:
    # Validate sample transcripts
    python scripts/validate_extraction.py

    # Validate with custom transcript file
    python scripts/validate_extraction.py --file transcript.txt

    # Validate multiple files
    python scripts/validate_extraction.py --dir ./transcripts/

    # Output JSON report
    python scripts/validate_extraction.py --json --output report.json

Requirements:
    - ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable
    - pip install anthropic (or openai)
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.call_intelligence.extraction_validator import (
    ExtractionValidator,
    ValidationReport,
    AggregateReport,
    SAMPLE_TRANSCRIPTS,
)
from services.call_intelligence.llm_client import create_llm_client, LLMConfig


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def print_status(text: str, status: str = "info"):
    """Print a status message."""
    symbols = {
        "info": "ℹ️ ",
        "success": "✅",
        "warning": "⚠️ ",
        "error": "❌",
        "running": "🔄",
    }
    print(f"{symbols.get(status, '')} {text}")


async def validate_samples(validator: ExtractionValidator, args) -> AggregateReport:
    """Validate the built-in sample transcripts."""
    print_header("Validating Sample Transcripts")
    print(f"Found {len(SAMPLE_TRANSCRIPTS)} sample transcripts\n")

    aggregate = await validator.validate_batch(SAMPLE_TRANSCRIPTS)
    return aggregate


async def validate_file(validator: ExtractionValidator, filepath: str) -> ValidationReport:
    """Validate a single transcript file."""
    print_status(f"Reading {filepath}", "info")

    with open(filepath, "r") as f:
        transcript = f.read()

    call_id = Path(filepath).stem
    print_status(f"Validating {call_id} ({len(transcript):,} chars)", "running")

    report = await validator.validate_transcript(transcript, call_id)
    return report


async def validate_directory(validator: ExtractionValidator, dirpath: str) -> AggregateReport:
    """Validate all transcript files in a directory."""
    print_header(f"Validating Transcripts in {dirpath}")

    transcripts = []
    for filepath in Path(dirpath).glob("*.txt"):
        with open(filepath, "r") as f:
            transcript = f.read()
        call_id = filepath.stem
        transcripts.append((call_id, transcript))

    if not transcripts:
        print_status("No .txt files found in directory", "warning")
        return AggregateReport()

    print(f"Found {len(transcripts)} transcript files\n")
    aggregate = await validator.validate_batch(transcripts)
    return aggregate


def save_report(report, output_path: str):
    """Save report to JSON file."""
    with open(output_path, "w") as f:
        if isinstance(report, AggregateReport):
            data = report.to_dict()
            data["individual_reports"] = [r.to_dict() for r in report.reports]
        else:
            data = report.to_dict()
        json.dump(data, f, indent=2, default=str)
    print_status(f"Report saved to {output_path}", "success")


def print_report(report):
    """Print report summary."""
    if isinstance(report, AggregateReport):
        print("\n" + report.summary())

        # Print individual failures if any
        if report.failing_count > 0:
            print_header("Detailed Failure Analysis")
            for r in report.reports:
                if r.quality_score < report.passing_threshold:
                    print(f"\n--- {r.call_id} ---")
                    print(r.summary())
    else:
        print("\n" + report.summary())


def check_api_keys() -> bool:
    """Check if required API keys are set."""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not anthropic_key and not openai_key:
        print_status("No API key found!", "error")
        print("\nPlease set one of these environment variables:")
        print("  export ANTHROPIC_API_KEY=your-key-here")
        print("  export OPENAI_API_KEY=your-key-here")
        return False

    if anthropic_key:
        print_status("Using Anthropic API", "info")
    else:
        print_status("Using OpenAI API", "info")

    return True


async def main():
    parser = argparse.ArgumentParser(
        description="Validate extraction quality: unified vs parallel agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Validate sample transcripts
  %(prog)s --file call.txt          # Validate single file
  %(prog)s --dir ./transcripts/     # Validate directory
  %(prog)s --json -o report.json    # Output JSON report
  %(prog)s --threshold 90           # Set passing threshold to 90
        """,
    )

    parser.add_argument(
        "--file", "-f",
        help="Path to a single transcript file to validate",
    )
    parser.add_argument(
        "--dir", "-d",
        help="Directory containing transcript files (.txt)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=85.0,
        help="Quality score threshold for passing (default: 85)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Minimal output (just pass/fail)",
    )

    args = parser.parse_args()

    # Print header
    if not args.quiet:
        print_header("Extraction Validation Tool")
        print("Compares unified extraction vs parallel agents")

    # Check API keys
    if not check_api_keys():
        sys.exit(1)

    # Create LLM client and validator
    try:
        print_status("Initializing LLM client...", "running")
        llm_client = create_llm_client()
        validator = ExtractionValidator(llm_client)
        print_status("Validator ready", "success")
    except Exception as e:
        print_status(f"Failed to initialize: {e}", "error")
        sys.exit(1)

    # Run validation
    try:
        if args.file:
            report = await validate_file(validator, args.file)
        elif args.dir:
            report = await validate_directory(validator, args.dir)
            report.passing_threshold = args.threshold
        else:
            report = await validate_samples(validator, args)
            report.passing_threshold = args.threshold

        # Output results
        if args.json:
            if args.output:
                save_report(report, args.output)
            else:
                if isinstance(report, AggregateReport):
                    data = report.to_dict()
                else:
                    data = report.to_dict()
                print(json.dumps(data, indent=2, default=str))
        else:
            print_report(report)

        # Exit code based on pass/fail
        if isinstance(report, AggregateReport):
            if report.failing_count > 0:
                print_status(
                    f"\n{report.failing_count}/{report.total_transcripts} transcripts FAILED",
                    "warning"
                )
                sys.exit(1)
            else:
                print_status(
                    f"\nAll {report.total_transcripts} transcripts PASSED",
                    "success"
                )
        else:
            if report.quality_score < args.threshold:
                print_status(f"\nFAILED (score: {report.quality_score:.0f} < {args.threshold})", "error")
                sys.exit(1)
            else:
                print_status(f"\nPASSED (score: {report.quality_score:.0f})", "success")

    except KeyboardInterrupt:
        print_status("\nValidation cancelled", "warning")
        sys.exit(130)
    except Exception as e:
        print_status(f"Validation failed: {e}", "error")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
