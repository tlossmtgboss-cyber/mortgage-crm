#!/usr/bin/env python3
"""
Perennia AI - Production Test Runner

This script runs tests in the correct order with proper gating:
1. Unit tests (fast, always run first)
2. Contract tests (API schema validation)
3. Golden flow tests (critical business paths)
4. Integration tests (external services)
5. AI harness tests (agent behavior)

Exit codes:
- 0: All tests passed
- 1: Critical tests failed (blocks deployment)
- 2: Non-critical tests failed (warning only)
"""
import subprocess
import sys
import os
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
import json


@dataclass
class TestSuite:
    """Configuration for a test suite"""
    name: str
    markers: List[str]
    critical: bool = False
    timeout: int = 300  # 5 minutes default
    description: str = ""


@dataclass
class TestResult:
    """Result from running a test suite"""
    suite_name: str
    passed: bool
    exit_code: int
    duration: float
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    output: str = ""


# Define test suites in execution order
TEST_SUITES = [
    TestSuite(
        name="unit",
        markers=["unit"],
        critical=True,
        timeout=120,
        description="Fast isolated tests with mocked dependencies"
    ),
    TestSuite(
        name="contract",
        markers=["contract"],
        critical=True,
        timeout=180,
        description="API contract validation tests"
    ),
    TestSuite(
        name="golden",
        markers=["golden", "critical"],
        critical=True,
        timeout=300,
        description="Critical business flow tests"
    ),
    TestSuite(
        name="integration",
        markers=["integration"],
        critical=False,
        timeout=300,
        description="Integration tests with external services"
    ),
    TestSuite(
        name="ai_harness",
        markers=["ai", "agents"],
        critical=False,
        timeout=300,
        description="AI agent behavior tests"
    ),
    TestSuite(
        name="regression",
        markers=["regression"],
        critical=False,
        timeout=300,
        description="Golden response regression tests"
    ),
]


def get_project_root() -> Path:
    """Get the project root directory"""
    return Path(__file__).parent.parent


def run_test_suite(suite: TestSuite, verbose: bool = True) -> TestResult:
    """Run a single test suite"""
    start_time = time.time()

    # Build pytest command
    cmd = [
        sys.executable, "-m", "pytest",
        "-v" if verbose else "-q",
        "--tb=short",
        f"--timeout={suite.timeout}",
    ]

    # Add markers
    if suite.markers:
        marker_expr = " or ".join(suite.markers)
        cmd.extend(["-m", marker_expr])

    # Add test path
    cmd.append(str(get_project_root() / "tests"))

    print(f"\n{'='*60}")
    print(f"Running: {suite.name}")
    print(f"Description: {suite.description}")
    print(f"Critical: {'Yes' if suite.critical else 'No'}")
    print(f"{'='*60}\n")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=suite.timeout,
            cwd=get_project_root()
        )

        duration = time.time() - start_time

        # Parse output for test counts
        output = result.stdout + result.stderr
        tests_run, tests_passed, tests_failed = parse_pytest_output(output)

        return TestResult(
            suite_name=suite.name,
            passed=result.returncode == 0,
            exit_code=result.returncode,
            duration=duration,
            tests_run=tests_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            output=output
        )

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return TestResult(
            suite_name=suite.name,
            passed=False,
            exit_code=-1,
            duration=duration,
            output=f"Test suite timed out after {suite.timeout} seconds"
        )


def parse_pytest_output(output: str) -> tuple[int, int, int]:
    """Parse pytest output to extract test counts"""
    import re

    # Look for summary line like "5 passed, 2 failed, 1 skipped"
    patterns = [
        r'(\d+) passed',
        r'(\d+) failed',
        r'(\d+) error',
    ]

    passed = 0
    failed = 0

    for match in re.finditer(r'(\d+) passed', output):
        passed = int(match.group(1))
    for match in re.finditer(r'(\d+) (failed|error)', output):
        failed += int(match.group(1))

    total = passed + failed
    return total, passed, failed


def print_summary(results: List[TestResult]):
    """Print test summary"""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    total_duration = sum(r.duration for r in results)
    total_tests = sum(r.tests_run for r in results)
    total_passed = sum(r.tests_passed for r in results)
    total_failed = sum(r.tests_failed for r in results)

    for result in results:
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"{status} | {result.suite_name:15} | "
              f"{result.tests_passed}/{result.tests_run} tests | "
              f"{result.duration:.1f}s")

    print("-"*60)
    print(f"Total: {total_passed}/{total_tests} tests passed in {total_duration:.1f}s")
    print("="*60)


def save_results(results: List[TestResult], output_path: Optional[Path] = None):
    """Save test results to JSON file"""
    if output_path is None:
        output_path = get_project_root() / "tests" / "test_results.json"

    data = {
        "timestamp": datetime.now().isoformat(),
        "suites": [
            {
                "name": r.suite_name,
                "passed": r.passed,
                "exit_code": r.exit_code,
                "duration": r.duration,
                "tests_run": r.tests_run,
                "tests_passed": r.tests_passed,
                "tests_failed": r.tests_failed,
            }
            for r in results
        ],
        "summary": {
            "total_tests": sum(r.tests_run for r in results),
            "total_passed": sum(r.tests_passed for r in results),
            "total_failed": sum(r.tests_failed for r in results),
            "total_duration": sum(r.duration for r in results),
            "all_critical_passed": all(
                r.passed for r, s in zip(results, TEST_SUITES) if s.critical
            ),
        }
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nResults saved to: {output_path}")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Run Perennia AI test suites")
    parser.add_argument(
        "--suite", "-s",
        choices=[s.name for s in TEST_SUITES] + ["all"],
        default="all",
        help="Test suite to run"
    )
    parser.add_argument(
        "--critical-only", "-c",
        action="store_true",
        help="Only run critical test suites"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=True,
        help="Verbose output"
    )
    parser.add_argument(
        "--save-results",
        action="store_true",
        help="Save results to JSON file"
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip slow tests"
    )

    args = parser.parse_args()

    # Filter suites
    suites_to_run = TEST_SUITES

    if args.suite != "all":
        suites_to_run = [s for s in TEST_SUITES if s.name == args.suite]

    if args.critical_only:
        suites_to_run = [s for s in suites_to_run if s.critical]

    if not suites_to_run:
        print("No test suites to run")
        sys.exit(0)

    print("="*60)
    print("PERENNIA AI - PRODUCTION TEST RUNNER")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Suites: {[s.name for s in suites_to_run]}")
    print("="*60)

    # Run suites
    results = []
    critical_failure = False

    for suite in suites_to_run:
        result = run_test_suite(suite, verbose=args.verbose)
        results.append(result)

        if args.verbose:
            print(result.output)

        # Check for critical failure
        if not result.passed and suite.critical:
            critical_failure = True
            print(f"\n⚠️  CRITICAL TEST SUITE FAILED: {suite.name}")
            print("Stopping test run - critical tests must pass for deployment")
            break

    # Print summary
    print_summary(results)

    # Save results if requested
    if args.save_results:
        save_results(results)

    # Exit with appropriate code
    if critical_failure:
        print("\n❌ DEPLOYMENT BLOCKED: Critical tests failed")
        sys.exit(1)
    elif any(not r.passed for r in results):
        print("\n⚠️  WARNING: Some non-critical tests failed")
        sys.exit(2)
    else:
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
