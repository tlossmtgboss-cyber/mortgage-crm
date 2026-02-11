#!/usr/bin/env python3
"""
QA Suite Runner
Runs all QA tests and generates comprehensive report
"""

import subprocess
import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.qa.qa_report_generator import QAReportGenerator, create_qa_checklist_report


class QASuiteRunner:
    """Run all QA test suites"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.qa_dir = Path(__file__).parent
        self.results = {}
        self.report = create_qa_checklist_report()

    def run_pytest_suite(self, test_file: str, category_name: str) -> Dict:
        """Run a pytest test file"""
        print(f"\n{'=' * 60}")
        print(f"Running: {test_file}")
        print('=' * 60)

        test_path = self.qa_dir / test_file

        if not test_path.exists():
            print(f"  ⚠️ Test file not found: {test_path}")
            return {"success": False, "error": "File not found"}

        cmd = [
            sys.executable, "-m", "pytest",
            str(test_path),
            "-v",
            "--tb=short",
            "-q",
            "--json-report",
            f"--json-report-file={self.qa_dir}/pytest_result.json"
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(self.qa_dir.parent.parent)
            )

            # Read pytest JSON report
            json_report_path = self.qa_dir / "pytest_result.json"
            if json_report_path.exists():
                with open(json_report_path) as f:
                    pytest_report = json.load(f)

                # Update our report with results
                self._update_report_from_pytest(pytest_report, category_name)

                # Clean up
                json_report_path.unlink()

                return {
                    "success": result.returncode == 0,
                    "passed": pytest_report.get("summary", {}).get("passed", 0),
                    "failed": pytest_report.get("summary", {}).get("failed", 0),
                    "output": result.stdout[-2000:] if result.stdout else ""
                }

            return {
                "success": result.returncode == 0,
                "output": result.stdout[-2000:] if result.stdout else "",
                "error": result.stderr[-500:] if result.stderr else ""
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Test timed out after 10 minutes"}
        except Exception as e:
            return {"success": False, "error": "Internal server error"}

    def _update_report_from_pytest(self, pytest_report: Dict, category_name: str):
        """Update QA report from pytest results"""
        category = next(
            (c for c in self.report.categories if category_name in c.name),
            None
        )

        if not category:
            return

        tests_by_name = {t.name.lower(): t for t in category.tests}

        for test in pytest_report.get("tests", []):
            test_name = test.get("nodeid", "").split("::")[-1].lower()
            outcome = test.get("outcome", "passed")

            # Try to match test name
            for name, test_obj in tests_by_name.items():
                if any(word in test_name for word in name.split()):
                    test_obj.status = "pass" if outcome == "passed" else "fail"
                    test_obj.duration = test.get("duration", 0)
                    if outcome == "failed":
                        test_obj.error = test.get("call", {}).get("longrepr", "Test failed")
                    break

    def run_load_test(self) -> Dict:
        """Run load tests"""
        print(f"\n{'=' * 60}")
        print("Running: Load Tests")
        print('=' * 60)

        from tests.qa.load_test import LoadTester, BorrowerJourneyLoadTest
        import asyncio

        try:
            # Run API load test
            tester = LoadTester(self.base_url, "test_token")
            result = asyncio.run(tester.run_concurrent_requests(
                endpoint="/api/v1/borrower/applications",
                method="GET",
                num_requests=50,
                concurrency=10
            ))

            # Update report
            perf_category = next(
                (c for c in self.report.categories if "Performance" in c.name),
                None
            )

            if perf_category:
                for test in perf_category.tests:
                    if "concurrent" in test.name.lower():
                        test.status = "pass" if result.error_rate < 1 else "fail"
                        test.duration = result.total_duration
                    elif "error rate" in test.name.lower():
                        test.status = "pass" if result.error_rate < 1 else "fail"

            return {
                "success": result.error_rate < 5,
                "avg_response": result.avg_response_time,
                "error_rate": result.error_rate
            }

        except Exception as e:
            return {"success": False, "error": "Internal server error"}

    def run_security_tests(self) -> Dict:
        """Run security test suite"""
        return self.run_pytest_suite("security_tests.py", "Security")

    def run_journey_tests(self) -> Dict:
        """Run E2E journey tests"""
        return self.run_pytest_suite("e2e_journey_tests.py", "Borrower Journey")

    def run_all(self) -> Dict:
        """Run all test suites"""
        print("\n" + "=" * 70)
        print("QA SUITE RUNNER - COMPREHENSIVE TESTING")
        print("=" * 70)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Target: {self.base_url}")

        results = {}

        # Run each test suite
        print("\n" + "-" * 70)
        print("1. E2E JOURNEY TESTS")
        print("-" * 70)
        results["journey"] = self.run_journey_tests()

        print("\n" + "-" * 70)
        print("2. SECURITY TESTS")
        print("-" * 70)
        results["security"] = self.run_security_tests()

        print("\n" + "-" * 70)
        print("3. LOAD TESTS")
        print("-" * 70)
        results["load"] = self.run_load_test()

        # Generate reports
        print("\n" + "-" * 70)
        print("GENERATING REPORTS")
        print("-" * 70)

        report_dir = self.qa_dir
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        html_path = report_dir / f"qa_report_{timestamp}.html"
        json_path = report_dir / f"qa_report_{timestamp}.json"

        self.report.generate_html_report(str(html_path))
        self.report.generate_json_report(str(json_path))

        print(f"  HTML Report: {html_path}")
        print(f"  JSON Report: {json_path}")

        # Print summary
        self._print_summary(results)

        return results

    def _print_summary(self, results: Dict):
        """Print test summary"""
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)

        total_passed = sum(c.passed for c in self.report.categories)
        total_failed = sum(c.failed for c in self.report.categories)
        total_tests = sum(c.total for c in self.report.categories)
        pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

        print(f"\nTotal Tests: {total_tests}")
        print(f"Passed: {total_passed}")
        print(f"Failed: {total_failed}")
        print(f"Pass Rate: {pass_rate:.1f}%")

        print("\nBy Category:")
        for category in self.report.categories:
            status = "✅" if category.pass_rate >= 95 else "❌"
            print(f"  {status} {category.name}: {category.passed}/{category.total} ({category.pass_rate:.1f}%)")

        print("\n" + "=" * 70)
        overall = "✅ READY FOR LAUNCH" if pass_rate >= 95 else "❌ NOT READY - FIX FAILURES"
        print(f"OVERALL: {overall}")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="QA Suite Runner")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL to test")
    parser.add_argument(
        "--suite",
        choices=["all", "journey", "security", "load"],
        default="all",
        help="Which test suite to run"
    )

    args = parser.parse_args()

    runner = QASuiteRunner(base_url=args.url)

    if args.suite == "all":
        runner.run_all()
    elif args.suite == "journey":
        runner.run_journey_tests()
    elif args.suite == "security":
        runner.run_security_tests()
    elif args.suite == "load":
        runner.run_load_test()


if __name__ == "__main__":
    main()
