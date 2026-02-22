#!/usr/bin/env python3
"""
QA Report Generator
Generates comprehensive QA test reports with pass/fail status
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@dataclass
class TestCase:
    """Individual test case result"""
    id: str
    name: str
    category: str
    status: str  # "pass", "fail", "skip", "pending"
    duration: float = 0
    error: Optional[str] = None
    screenshot: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class TestCategory:
    """Category of tests"""
    name: str
    description: str
    tests: List[TestCase] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return len([t for t in self.tests if t.status == "pass"])

    @property
    def failed(self) -> int:
        return len([t for t in self.tests if t.status == "fail"])

    @property
    def skipped(self) -> int:
        return len([t for t in self.tests if t.status == "skip"])

    @property
    def pending(self) -> int:
        return len([t for t in self.tests if t.status == "pending"])

    @property
    def total(self) -> int:
        return len(self.tests)

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0
        return (self.passed / self.total) * 100


class QAReportGenerator:
    """Generate comprehensive QA reports"""

    def __init__(self):
        self.categories: List[TestCategory] = []
        self.start_time = datetime.now()
        self.environment = {}

    def set_environment(self, **kwargs):
        """Set environment information"""
        self.environment.update(kwargs)

    def add_category(self, name: str, description: str) -> TestCategory:
        """Add a test category"""
        category = TestCategory(name=name, description=description)
        self.categories.append(category)
        return category

    def add_test(
        self,
        category_name: str,
        test_id: str,
        test_name: str,
        status: str,
        duration: float = 0,
        error: str = None,
        notes: str = None
    ):
        """Add a test result"""
        category = next((c for c in self.categories if c.name == category_name), None)
        if not category:
            category = self.add_category(category_name, "")

        test = TestCase(
            id=test_id,
            name=test_name,
            category=category_name,
            status=status,
            duration=duration,
            error=error,
            notes=notes
        )
        category.tests.append(test)

    def generate_html_report(self, output_path: str) -> str:
        """Generate HTML report"""
        total_passed = sum(c.passed for c in self.categories)
        total_failed = sum(c.failed for c in self.categories)
        total_skipped = sum(c.skipped for c in self.categories)
        total_pending = sum(c.pending for c in self.categories)
        total_tests = sum(c.total for c in self.categories)

        overall_pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        overall_status = "PASS" if overall_pass_rate >= 95 else "FAIL"
        status_color = "#28a745" if overall_status == "PASS" else "#dc3545"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QA Test Report - {datetime.now().strftime('%Y-%m-%d')}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{ background: {status_color}; color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header .status {{ font-size: 48px; font-weight: bold; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .summary-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .summary-card h3 {{ font-size: 14px; color: #666; margin-bottom: 5px; }}
        .summary-card .value {{ font-size: 32px; font-weight: bold; }}
        .summary-card .value.pass {{ color: #28a745; }}
        .summary-card .value.fail {{ color: #dc3545; }}
        .category {{ background: white; border-radius: 8px; margin-bottom: 20px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .category-header {{ padding: 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }}
        .category-header h2 {{ font-size: 18px; }}
        .category-header .badge {{ padding: 4px 12px; border-radius: 20px; font-size: 14px; font-weight: 500; }}
        .badge.pass {{ background: #d4edda; color: #155724; }}
        .badge.fail {{ background: #f8d7da; color: #721c24; }}
        .tests {{ padding: 10px 0; }}
        .test-item {{ padding: 12px 20px; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; }}
        .test-item:last-child {{ border-bottom: none; }}
        .test-status {{ width: 24px; height: 24px; border-radius: 50%; margin-right: 15px; display: flex; align-items: center; justify-content: center; font-size: 14px; }}
        .test-status.pass {{ background: #d4edda; color: #28a745; }}
        .test-status.fail {{ background: #f8d7da; color: #dc3545; }}
        .test-status.skip {{ background: #fff3cd; color: #856404; }}
        .test-status.pending {{ background: #e2e3e5; color: #383d41; }}
        .test-info {{ flex: 1; }}
        .test-name {{ font-weight: 500; }}
        .test-id {{ font-size: 12px; color: #999; }}
        .test-duration {{ color: #666; font-size: 14px; }}
        .test-error {{ background: #f8d7da; padding: 10px 15px; margin: 10px 20px; border-radius: 4px; font-size: 13px; color: #721c24; }}
        .environment {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .environment h3 {{ margin-bottom: 15px; }}
        .environment table {{ width: 100%; border-collapse: collapse; }}
        .environment td {{ padding: 8px 0; border-bottom: 1px solid #eee; }}
        .environment td:first-child {{ font-weight: 500; width: 200px; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>QA Test Report</h1>
            <div>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            <div class="status">{overall_status}</div>
        </div>

        <div class="summary">
            <div class="summary-card">
                <h3>Total Tests</h3>
                <div class="value">{total_tests}</div>
            </div>
            <div class="summary-card">
                <h3>Passed</h3>
                <div class="value pass">{total_passed}</div>
            </div>
            <div class="summary-card">
                <h3>Failed</h3>
                <div class="value fail">{total_failed}</div>
            </div>
            <div class="summary-card">
                <h3>Pass Rate</h3>
                <div class="value {'pass' if overall_pass_rate >= 95 else 'fail'}">{overall_pass_rate:.1f}%</div>
            </div>
        </div>

        <div class="environment">
            <h3>Environment</h3>
            <table>
                {''.join(f'<tr><td>{k}</td><td>{v}</td></tr>' for k, v in self.environment.items())}
            </table>
        </div>

        {''.join(self._render_category(c) for c in self.categories)}

        <div class="footer">
            Report generated by QA Report Generator
        </div>
    </div>
</body>
</html>"""

        with open(output_path, 'w') as f:
            f.write(html)

        return output_path

    def _render_category(self, category: TestCategory) -> str:
        """Render a category section"""
        badge_class = "pass" if category.pass_rate >= 95 else "fail"

        tests_html = ""
        for test in category.tests:
            status_icon = {
                "pass": "✓",
                "fail": "✗",
                "skip": "○",
                "pending": "?"
            }.get(test.status, "?")

            error_html = f'<div class="test-error">{test.error}</div>' if test.error else ""

            tests_html += f"""
            <div class="test-item">
                <div class="test-status {test.status}">{status_icon}</div>
                <div class="test-info">
                    <div class="test-name">{test.name}</div>
                    <div class="test-id">{test.id}</div>
                </div>
                <div class="test-duration">{test.duration:.2f}s</div>
            </div>
            {error_html}
            """

        return f"""
        <div class="category">
            <div class="category-header">
                <h2>{category.name}</h2>
                <span class="badge {badge_class}">{category.passed}/{category.total} passed ({category.pass_rate:.1f}%)</span>
            </div>
            <div class="tests">
                {tests_html}
            </div>
        </div>
        """

    def generate_json_report(self, output_path: str) -> str:
        """Generate JSON report"""
        report = {
            "generated_at": datetime.now().isoformat(),
            "environment": self.environment,
            "summary": {
                "total": sum(c.total for c in self.categories),
                "passed": sum(c.passed for c in self.categories),
                "failed": sum(c.failed for c in self.categories),
                "skipped": sum(c.skipped for c in self.categories),
                "pending": sum(c.pending for c in self.categories),
            },
            "categories": [
                {
                    "name": c.name,
                    "description": c.description,
                    "passed": c.passed,
                    "failed": c.failed,
                    "total": c.total,
                    "pass_rate": c.pass_rate,
                    "tests": [
                        {
                            "id": t.id,
                            "name": t.name,
                            "status": t.status,
                            "duration": t.duration,
                            "error": t.error,
                            "notes": t.notes,
                        }
                        for t in c.tests
                    ]
                }
                for c in self.categories
            ]
        }

        report["summary"]["pass_rate"] = (
            report["summary"]["passed"] / report["summary"]["total"] * 100
            if report["summary"]["total"] > 0 else 0
        )
        report["summary"]["status"] = "PASS" if report["summary"]["pass_rate"] >= 95 else "FAIL"

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)

        return output_path


def create_qa_checklist_report() -> QAReportGenerator:
    """Create report structure based on QA Challenge checklist"""
    report = QAReportGenerator()

    report.set_environment(
        application="Mortgage CRM - Borrower Application",
        version="1.0.0",
        environment="QA/Staging",
        browser="Chrome 120+",
        tester="Automated",
        date=datetime.now().strftime("%Y-%m-%d")
    )

    # Challenge 1: Borrower Journey
    journey = report.add_category("Challenge 1: Borrower Journey", "End-to-end borrower application flow")

    journey_tests = [
        ("1.1", "Landing page loads"),
        ("1.2", "Social login (Google) redirect"),
        ("1.3", "Social login callback creates profile"),
        ("1.4", "Mode selection screen displays"),
        ("1.5", "Form mode starts application"),
        ("1.6", "Personal info auto-populated"),
        ("1.7", "Personal info saves (auto-save)"),
        ("1.8", "Data persists after refresh"),
        ("1.9", "Address autocomplete response (<1s)"),
        ("1.10", "Address selection auto-populates fields"),
        ("1.11", "Employer autocomplete works"),
        ("1.12", "Income info saves"),
        ("1.13", "PDF document uploads"),
        ("1.14", "AI document analysis completes"),
        ("1.15", "Oversized file rejected (>10MB)"),
        ("1.16", "Co-borrower invitation sent"),
        ("1.17", "Available slots API returns data"),
        ("1.18", "Review call scheduled"),
        ("1.19", "Summary review displays all data"),
        ("1.20", "Edit in summary works"),
        ("1.21", "Completion percentage accurate"),
        ("1.22", "Application submits"),
        ("1.23", "MISMO XML exports correctly"),
    ]

    for test_id, test_name in journey_tests:
        report.add_test("Challenge 1: Borrower Journey", test_id, test_name, "pending")

    # Challenge 2: AI Concierge
    concierge = report.add_category("Challenge 2: AI Concierge", "AI-powered conversational application")

    concierge_tests = [
        ("2.1", "Concierge mode starts"),
        ("2.2", "AI greeting message appears"),
        ("2.3", "Voice input processing works"),
        ("2.4", "Text input extracts data"),
        ("2.5", "Switch to form preserves data"),
    ]

    for test_id, test_name in concierge_tests:
        report.add_test("Challenge 2: AI Concierge", test_id, test_name, "pending")

    # Challenge 3: Mobile
    mobile = report.add_category("Challenge 3: Mobile", "Mobile device testing")

    mobile_tests = [
        ("3.1", "iPhone SE - content fits"),
        ("3.2", "iPhone 12 - navigation works"),
        ("3.3", "Android Pixel - touch-friendly"),
        ("3.4", "iPad - landscape adapts"),
        ("3.5", "No zoom on input focus"),
        ("3.6", "Swipe navigation works"),
        ("3.7", "Voice input on mobile"),
        ("3.8", "Page load <3s on 4G"),
    ]

    for test_id, test_name in mobile_tests:
        report.add_test("Challenge 3: Mobile", test_id, test_name, "pending")

    # Challenge 4: Edge Cases
    edge = report.add_category("Challenge 4: Edge Cases", "Input validation and error handling")

    edge_tests = [
        ("4.1", "Special character names accepted"),
        ("4.2", "Emoji in name handled"),
        ("4.3", "SQL injection prevented"),
        ("4.4", "XSS prevented"),
        ("4.5", "Extreme income values handled"),
        ("4.6", "Network failure graceful"),
        ("4.7", "Session expiration handled"),
        ("4.8", "Browser back button works"),
        ("4.9", "Multiple tabs conflict handled"),
    ]

    for test_id, test_name in edge_tests:
        report.add_test("Challenge 4: Edge Cases", test_id, test_name, "pending")

    # Challenge 5: Integrations
    integrations = report.add_category("Challenge 5: Integrations", "Third-party service integrations")

    integration_tests = [
        ("5.1", "Google Places API works"),
        ("5.2", "Google Places rate limiting"),
        ("5.3", "SendGrid email delivery"),
        ("5.4", "Telnyx SMS delivery"),
        ("5.5", "Claude document analysis"),
        ("5.6", "AI name mismatch detection"),
    ]

    for test_id, test_name in integration_tests:
        report.add_test("Challenge 5: Integrations", test_id, test_name, "pending")

    # Challenge 6: Performance
    perf = report.add_category("Challenge 6: Performance", "Performance and load testing")

    perf_tests = [
        ("6.1", "FCP < 1.5s"),
        ("6.2", "LCP < 2.5s"),
        ("6.3", "API response < 500ms"),
        ("6.4", "50 concurrent users supported"),
        ("6.5", "Error rate < 1% under load"),
        ("6.6", "No memory leaks"),
    ]

    for test_id, test_name in perf_tests:
        report.add_test("Challenge 6: Performance", test_id, test_name, "pending")

    # Challenge 7: Security
    security = report.add_category("Challenge 7: Security", "Security testing")

    security_tests = [
        ("7.1", "Access without token rejected"),
        ("7.2", "Invalid token rejected"),
        ("7.3", "Expired token rejected"),
        ("7.4", "Token manipulation detected"),
        ("7.5", "Borrower can't access LO endpoints"),
        ("7.6", "Can't access other's data"),
        ("7.7", "File path traversal prevented"),
        ("7.8", "Executable files rejected"),
        ("7.9", "SSN masked in response"),
        ("7.10", "Rate limiting active"),
    ]

    for test_id, test_name in security_tests:
        report.add_test("Challenge 7: Security", test_id, test_name, "pending")

    return report


def main():
    """Generate sample QA report"""
    report = create_qa_checklist_report()

    # Simulate some test results
    import random
    for category in report.categories:
        for test in category.tests:
            test.status = random.choices(
                ["pass", "fail", "skip"],
                weights=[0.85, 0.10, 0.05]
            )[0]
            test.duration = random.uniform(0.1, 2.0)
            if test.status == "fail":
                test.error = f"Expected condition not met for {test.name}"

    # Generate reports
    output_dir = Path(__file__).parent
    html_path = report.generate_html_report(str(output_dir / "qa_report.html"))
    json_path = report.generate_json_report(str(output_dir / "qa_report.json"))

    print(f"HTML Report: {html_path}")
    print(f"JSON Report: {json_path}")

    # Print summary
    total_passed = sum(c.passed for c in report.categories)
    total_tests = sum(c.total for c in report.categories)
    print(f"\nSummary: {total_passed}/{total_tests} tests passed")


if __name__ == "__main__":
    main()
