#!/usr/bin/env python3
"""
Pre-Launch Test Runner
Executes all pre-launch tests and generates a comprehensive report
"""

import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path
import os

# Test categories with their files
TEST_SUITES = {
    "borrower_flow": {
        "file": "test_borrower_flow.py",
        "description": "Borrower Flow (End-to-End)",
        "checklist": [
            "Social login from all 4 providers",
            "Magic link email delivery",
            "Form application completion",
            "Conversational AI mode completion",
            "Document upload and AI verification",
            "Co-borrower invitation and acceptance",
            "Review call scheduling",
            "Final submission",
            "Confirmation emails/SMS",
        ]
    },
    "lo_dashboard": {
        "file": "test_lo_dashboard.py",
        "description": "LO Dashboard",
        "checklist": [
            "Application listing and filtering",
            "MISMO XML export",
            "Social content generation",
            "Analytics dashboard accuracy",
            "Application detail view",
        ]
    },
    "mobile": {
        "file": "../frontend/src/__tests__/MobileResponsiveness.test.js",
        "description": "Mobile Testing",
        "checklist": [
            "iOS Safari (iPhone 12+, SE)",
            "Android Chrome (Pixel, Samsung)",
            "Tablet landscape/portrait",
            "Touch gestures (swipe navigation)",
            "Voice input on mobile",
        ],
        "runner": "npm"
    },
    "notifications": {
        "file": "test_notifications.py",
        "description": "Notifications",
        "checklist": [
            "Welcome email on application start",
            "Document upload confirmation",
            "24h reminder for incomplete apps",
            "Submission confirmation to borrower",
            "New application alert to LO",
            "SMS delivery and formatting",
        ]
    },
    "ai_features": {
        "file": "test_ai_features.py",
        "description": "AI Features",
        "checklist": [
            "Document analysis accuracy",
            "Conversational mode data extraction",
            "Summary review completeness",
            "Social content quality",
        ]
    },
    "performance": {
        "file": "test_performance.py",
        "description": "Performance",
        "checklist": [
            "Page load times (<3s)",
            "Google Places autocomplete response",
            "Document upload speed (S3)",
            "AI response times (Claude API)",
            "Database query optimization",
        ]
    },
}


def run_pytest(test_file: str, verbose: bool = True) -> dict:
    """Run pytest on a specific file and return results"""
    cmd = [
        sys.executable, "-m", "pytest",
        test_file,
        "-v" if verbose else "",
        "--tb=short",
        "-q",
        "--json-report",
        "--json-report-file=test_results.json"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        # Try to read JSON report
        json_report = {}
        if Path("test_results.json").exists():
            with open("test_results.json") as f:
                json_report = json.load(f)
            os.remove("test_results.json")

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr,
            "report": json_report,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "errors": "Test timed out after 5 minutes",
            "report": {},
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "errors": str(e),
            "report": {},
            "returncode": -1
        }


def run_jest(test_file: str) -> dict:
    """Run Jest on a specific file and return results"""
    cmd = ["npm", "test", "--", test_file, "--json"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(Path(__file__).parent.parent.parent / "frontend")
        )

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr,
            "returncode": result.returncode
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "errors": str(e),
            "returncode": -1
        }


def generate_report(results: dict) -> str:
    """Generate a formatted test report"""
    report = []
    report.append("=" * 70)
    report.append("PRE-LAUNCH TEST REPORT")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 70)
    report.append("")

    total_passed = 0
    total_failed = 0

    for suite_name, suite_result in results.items():
        suite_info = TEST_SUITES.get(suite_name, {})
        description = suite_info.get("description", suite_name)

        status = "✅ PASSED" if suite_result["success"] else "❌ FAILED"
        report.append(f"\n{description}")
        report.append("-" * 40)
        report.append(f"Status: {status}")

        # Checklist items
        report.append("\nChecklist:")
        for item in suite_info.get("checklist", []):
            # Mark items based on test results (simplified)
            mark = "✓" if suite_result["success"] else "○"
            report.append(f"  [{mark}] {item}")

        if suite_result["success"]:
            total_passed += 1
        else:
            total_failed += 1
            if suite_result.get("errors"):
                report.append(f"\nErrors:\n{suite_result['errors'][:500]}")

    report.append("\n" + "=" * 70)
    report.append("SUMMARY")
    report.append("=" * 70)
    report.append(f"Total Suites: {total_passed + total_failed}")
    report.append(f"Passed: {total_passed}")
    report.append(f"Failed: {total_failed}")

    overall = "✅ READY FOR LAUNCH" if total_failed == 0 else "❌ NOT READY - FIX FAILURES"
    report.append(f"\nOverall Status: {overall}")
    report.append("")

    return "\n".join(report)


def main():
    """Run all pre-launch tests"""
    print("=" * 70)
    print("RUNNING PRE-LAUNCH TESTS")
    print("=" * 70)
    print()

    results = {}
    test_dir = Path(__file__).parent

    for suite_name, suite_info in TEST_SUITES.items():
        print(f"\n▶ Running {suite_info['description']}...")

        test_file = suite_info["file"]
        runner = suite_info.get("runner", "pytest")

        if runner == "pytest":
            test_path = test_dir / test_file
            if test_path.exists():
                results[suite_name] = run_pytest(str(test_path))
            else:
                results[suite_name] = {
                    "success": False,
                    "output": "",
                    "errors": f"Test file not found: {test_path}",
                    "returncode": -1
                }
        elif runner == "npm":
            results[suite_name] = run_jest(test_file)

        status = "✅" if results[suite_name]["success"] else "❌"
        print(f"  {status} {suite_info['description']}")

    # Generate and save report
    report = generate_report(results)
    print(report)

    # Save report to file
    report_file = test_dir / f"prelaunch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, "w") as f:
        f.write(report)

    print(f"\nReport saved to: {report_file}")

    # Exit with appropriate code
    all_passed = all(r["success"] for r in results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
