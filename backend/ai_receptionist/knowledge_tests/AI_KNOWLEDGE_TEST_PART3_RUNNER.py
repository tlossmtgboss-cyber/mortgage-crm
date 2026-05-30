#!/usr/bin/env python3
"""
================================================================================
PERENNIA AI - KNOWLEDGE & CAPABILITY TEST SUITE
================================================================================
Part 3: Test Runner & Report Generator

Runs all tests against the AI and generates comprehensive reports:
- Category scores and coverage
- Weak areas identification
- Recommendations for improvement
- Exportable results (JSON, HTML, Markdown)

================================================================================
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, asdict

# Import framework and tests
from AI_KNOWLEDGE_TEST_PART1_FRAMEWORK import (
    TestStatus,
    KnowledgeCategory,
    TestResult,
    CategoryReport,
    FullReport,
    MortgageKnowledgeBase,
)
from AI_KNOWLEDGE_TEST_PART2_TESTCASES import (
    ALL_TESTS,
    get_tests_by_category,
    get_test_count,
    get_category_counts,
)

logger = logging.getLogger(__name__)


# =============================================================================
# AI ADAPTERS
# =============================================================================

class AIAdapter:
    """Base adapter for AI systems"""

    async def query(
        self,
        prompt: str,
        return_tools: bool = False,
        return_data: bool = False,
    ) -> Any:
        raise NotImplementedError


# Alias for backwards compatibility
BaseAdapter = AIAdapter


class ClaudeAdapter(AIAdapter):
    """Adapter for Claude API"""

    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-6"):
        try:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
            self.model = model
        except ImportError:
            raise ImportError("anthropic package not installed")

    async def query(
        self,
        prompt: str,
        return_tools: bool = False,
        return_data: bool = False,
    ) -> Any:
        system = """You are an AI assistant for Perennia Mortgage CRM.
You have deep knowledge of mortgage lending, CRM systems, and the Perennia platform.
Answer questions accurately and concisely."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else ""

        if return_tools:
            # Extract tool calls from response
            tools = []
            # Simple extraction - in production, use proper tool calling
            if "get_" in text.lower() or "check_" in text.lower():
                import re
                tool_pattern = r'(get_\w+|check_\w+|create_\w+|send_\w+|book_\w+|schedule_\w+)'
                tools = re.findall(tool_pattern, text.lower())
            return text, tools

        return text


class OpenAIAdapter(AIAdapter):
    """Adapter for OpenAI API"""

    def __init__(self, api_key: str = None, model: str = "gpt-4-turbo-preview"):
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
            self.model = model
        except ImportError:
            raise ImportError("openai package not installed")

    async def query(
        self,
        prompt: str,
        return_tools: bool = False,
        return_data: bool = False,
    ) -> Any:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI assistant for Perennia Mortgage CRM with deep knowledge of mortgage lending.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        text = response.choices[0].message.content

        if return_tools:
            import re
            tools = re.findall(r'(get_\w+|check_\w+|create_\w+|send_\w+|book_\w+)', text.lower())
            return text, tools

        return text


class ConversationEngineAdapter(AIAdapter):
    """Adapter for our own conversation engine"""

    def __init__(self, engine):
        self.engine = engine
        self.call_sid = "TEST-KNOWLEDGE"

    async def query(
        self,
        prompt: str,
        return_tools: bool = False,
        return_data: bool = False,
    ) -> Any:
        # Ensure conversation exists
        if self.call_sid not in self.engine.conversations:
            await self.engine.start_conversation(
                call_sid=self.call_sid,
                caller_phone="+15551234567",
            )

        response = await self.engine.process_input(
            call_sid=self.call_sid,
            caller_input=prompt,
        )

        if return_tools:
            state = self.engine.get_conversation_state(self.call_sid)
            tools = [a.get("tool") for a in state.actions_taken] if state else []
            return response, tools

        return response


class MockAdapter(AIAdapter):
    """Mock adapter for testing the test framework"""

    def __init__(self, responses: Dict[str, str] = None):
        self.responses = responses or {}
        self.default_response = "I understand your question about mortgage lending."

    async def query(
        self,
        prompt: str,
        return_tools: bool = False,
        return_data: bool = False,
    ) -> Any:
        # Check for matching response
        for key, response in self.responses.items():
            if key.lower() in prompt.lower():
                if return_tools:
                    return response, []
                return response

        if return_tools:
            return self.default_response, []
        return self.default_response


# =============================================================================
# TEST RUNNER
# =============================================================================

class TestRunner:
    """
    Runs tests and collects results.
    """

    def __init__(
        self,
        ai_adapter: AIAdapter,
        parallel: bool = False,
        max_concurrent: int = 5,
    ):
        self.ai = ai_adapter
        self.parallel = parallel
        self.max_concurrent = max_concurrent
        self.results: List[TestResult] = []

    async def _run_single_test(self, test) -> TestResult:
        """Run a single test"""
        try:
            # Create handler function
            async def handler(prompt, return_tools=False, return_data=False):
                return await self.ai.query(prompt, return_tools, return_data)

            result = await test.run(handler)
            return result
        except Exception as e:
            logger.error(f"Error running test {test.test_id}: {e}")
            return TestResult(
                test_id=test.test_id,
                category=test.category,
                name=test.name,
                status=TestStatus.ERROR,
                score=0.0,
                expected="N/A",
                actual=str(e),
                details=f"Test execution error: {str(e)}",
            )

    async def run_tests(
        self,
        tests: List = None,
        categories: List[KnowledgeCategory] = None,
        progress_callback: Callable = None,
    ) -> List[TestResult]:
        """
        Run specified tests.

        Args:
            tests: Specific tests to run (or ALL_TESTS)
            categories: Filter by categories
            progress_callback: Called with (current, total, test_id)
        """
        if tests is None:
            tests = ALL_TESTS

        if categories:
            tests = [t for t in tests if t.category in categories]

        self.results = []
        total = len(tests)

        if self.parallel:
            # Run tests in parallel with semaphore
            semaphore = asyncio.Semaphore(self.max_concurrent)

            async def run_with_semaphore(test, index):
                async with semaphore:
                    result = await self._run_single_test(test)
                    if progress_callback:
                        progress_callback(index + 1, total, test.test_id)
                    return result

            tasks = [run_with_semaphore(t, i) for i, t in enumerate(tests)]
            self.results = await asyncio.gather(*tasks)
        else:
            # Run tests sequentially
            for i, test in enumerate(tests):
                result = await self._run_single_test(test)
                self.results.append(result)
                if progress_callback:
                    progress_callback(i + 1, total, test.test_id)

        return self.results

    async def run_category(
        self,
        category: KnowledgeCategory,
        progress_callback: Callable = None,
    ) -> List[TestResult]:
        """Run all tests for a category"""
        tests = get_tests_by_category(category)
        return await self.run_tests(tests, progress_callback=progress_callback)

    async def run_all(
        self,
        progress_callback: Callable = None,
    ) -> List[TestResult]:
        """Run all tests"""
        return await self.run_tests(ALL_TESTS, progress_callback=progress_callback)


# =============================================================================
# REPORT GENERATOR
# =============================================================================

class ReportGenerator:
    """
    Generates comprehensive reports from test results.
    """

    def __init__(self, results: List[TestResult]):
        self.results = results

    def generate_category_report(self, category: KnowledgeCategory) -> CategoryReport:
        """Generate report for a single category"""
        category_results = [r for r in self.results if r.category == category]

        if not category_results:
            return CategoryReport(
                category=category,
                total_tests=0,
                passed=0,
                failed=0,
                partial=0,
                skipped=0,
                errors=0,
                average_score=0.0,
                coverage_percentage=0.0,
            )

        passed = sum(1 for r in category_results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in category_results if r.status == TestStatus.FAILED)
        partial = sum(1 for r in category_results if r.status == TestStatus.PARTIAL)
        skipped = sum(1 for r in category_results if r.status == TestStatus.SKIPPED)
        errors = sum(1 for r in category_results if r.status == TestStatus.ERROR)

        total = len(category_results)
        avg_score = sum(r.score for r in category_results) / total if total > 0 else 0
        coverage = (passed + partial * 0.5) / total * 100 if total > 0 else 0

        # Identify weak and strong areas
        weak = [r.name for r in category_results if r.score < 0.5]
        strong = [r.name for r in category_results if r.score >= 0.8]

        return CategoryReport(
            category=category,
            total_tests=total,
            passed=passed,
            failed=failed,
            partial=partial,
            skipped=skipped,
            errors=errors,
            average_score=round(avg_score, 3),
            coverage_percentage=round(coverage, 1),
            weak_areas=weak[:5],  # Top 5 weak areas
            strong_areas=strong[:5],  # Top 5 strong areas
        )

    def generate_full_report(self, execution_time: float = 0) -> FullReport:
        """Generate complete test report"""
        # Category reports
        categories = {}
        for category in KnowledgeCategory:
            categories[category.value] = self.generate_category_report(category)

        # Overall stats
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == TestStatus.PASSED)
        overall_score = sum(r.score for r in self.results) / total if total > 0 else 0

        # Generate recommendations
        recommendations = self._generate_recommendations(categories)

        return FullReport(
            timestamp=datetime.now(),
            total_tests=total,
            overall_score=round(overall_score, 3),
            categories=categories,
            results=self.results,
            recommendations=recommendations,
            execution_time_seconds=round(execution_time, 2),
        )

    def _generate_recommendations(self, categories: Dict[str, CategoryReport]) -> List[str]:
        """Generate improvement recommendations based on results"""
        recommendations = []

        # Check each category
        for name, report in categories.items():
            if report.average_score < 0.5:
                recommendations.append(
                    f"CRITICAL: {name.upper()} knowledge is below 50%. "
                    f"Focus training on: {', '.join(report.weak_areas[:3])}"
                )
            elif report.average_score < 0.7:
                recommendations.append(
                    f"IMPROVE: {name.upper()} could use improvement. "
                    f"Weak areas: {', '.join(report.weak_areas[:3])}"
                )

        # Overall recommendations
        overall_passed = sum(r.passed for r in categories.values())
        overall_total = sum(r.total_tests for r in categories.values())

        if overall_passed / overall_total < 0.7 if overall_total > 0 else True:
            recommendations.append(
                "Consider additional training on mortgage fundamentals "
                "and CRM operations."
            )

        if not recommendations:
            recommendations.append(
                "Good overall knowledge. Continue monitoring for updates "
                "to compliance requirements and new features."
            )

        return recommendations

    def to_json(self, report: FullReport = None) -> str:
        """Export report as JSON"""
        if report is None:
            report = self.generate_full_report()

        def convert(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, KnowledgeCategory):
                return obj.value
            if isinstance(obj, TestStatus):
                return obj.value
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            return str(obj)

        data = {
            "timestamp": report.timestamp.isoformat(),
            "total_tests": report.total_tests,
            "overall_score": report.overall_score,
            "execution_time_seconds": report.execution_time_seconds,
            "categories": {
                k: {
                    "total_tests": v.total_tests,
                    "passed": v.passed,
                    "failed": v.failed,
                    "partial": v.partial,
                    "average_score": v.average_score,
                    "coverage_percentage": v.coverage_percentage,
                    "weak_areas": v.weak_areas,
                    "strong_areas": v.strong_areas,
                }
                for k, v in report.categories.items()
            },
            "recommendations": report.recommendations,
            "results": [r.to_dict() for r in report.results],
        }

        return json.dumps(data, indent=2, default=str)

    def to_markdown(self, report: FullReport = None) -> str:
        """Export report as Markdown"""
        if report is None:
            report = self.generate_full_report()

        lines = [
            "# Perennia AI Knowledge Test Report",
            "",
            f"**Generated:** {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Execution Time:** {report.execution_time_seconds}s",
            "",
            "---",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Tests | {report.total_tests} |",
            f"| Overall Score | {report.overall_score:.1%} |",
            "",
        ]

        # Category breakdown
        lines.extend([
            "## Category Breakdown",
            "",
            "| Category | Tests | Passed | Score | Coverage |",
            "|----------|-------|--------|-------|----------|",
        ])

        for name, cat in report.categories.items():
            lines.append(
                f"| {name.title()} | {cat.total_tests} | {cat.passed} | "
                f"{cat.average_score:.1%} | {cat.coverage_percentage:.1f}% |"
            )

        # Recommendations
        lines.extend([
            "",
            "## Recommendations",
            "",
        ])
        for rec in report.recommendations:
            lines.append(f"- {rec}")

        # Weak Areas
        weak_all = []
        for cat in report.categories.values():
            weak_all.extend(cat.weak_areas)

        if weak_all:
            lines.extend([
                "",
                "## Weak Areas (Need Improvement)",
                "",
            ])
            for area in weak_all[:10]:
                lines.append(f"- {area}")

        # Detailed Results (failures only)
        failures = [r for r in report.results if r.status == TestStatus.FAILED]
        if failures:
            lines.extend([
                "",
                "## Failed Tests",
                "",
                "| Test ID | Name | Score | Details |",
                "|---------|------|-------|---------|",
            ])
            for r in failures[:20]:
                lines.append(f"| {r.test_id} | {r.name} | {r.score:.1%} | {r.details[:50]} |")

        return "\n".join(lines)

    def to_html(self, report: FullReport = None) -> str:
        """Export report as HTML"""
        if report is None:
            report = self.generate_full_report()

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Perennia AI Knowledge Test Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; }}
        h1 {{ color: #1a1a2e; }}
        h2 {{ color: #16213e; margin-top: 30px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #4a4e69; color: white; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .score-high {{ color: #27ae60; font-weight: bold; }}
        .score-mid {{ color: #f39c12; font-weight: bold; }}
        .score-low {{ color: #e74c3c; font-weight: bold; }}
        .summary-box {{ background: #f0f0f0; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .recommendation {{ background: #fff3cd; padding: 10px; margin: 5px 0; border-left: 4px solid #ffc107; }}
        .progress {{ background: #e0e0e0; border-radius: 4px; height: 20px; }}
        .progress-bar {{ background: #4a4e69; height: 100%; border-radius: 4px; }}
    </style>
</head>
<body>
    <h1>🧠 Perennia AI Knowledge Test Report</h1>

    <div class="summary-box">
        <p><strong>Generated:</strong> {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Total Tests:</strong> {report.total_tests}</p>
        <p><strong>Overall Score:</strong> <span class="{'score-high' if report.overall_score >= 0.8 else 'score-mid' if report.overall_score >= 0.5 else 'score-low'}">{report.overall_score:.1%}</span></p>
        <div class="progress">
            <div class="progress-bar" style="width: {report.overall_score * 100}%"></div>
        </div>
    </div>

    <h2>📊 Category Breakdown</h2>
    <table>
        <tr>
            <th>Category</th>
            <th>Tests</th>
            <th>Passed</th>
            <th>Failed</th>
            <th>Score</th>
            <th>Coverage</th>
        </tr>
"""

        for name, cat in report.categories.items():
            score_class = 'score-high' if cat.average_score >= 0.8 else 'score-mid' if cat.average_score >= 0.5 else 'score-low'
            html += f"""
        <tr>
            <td><strong>{name.title()}</strong></td>
            <td>{cat.total_tests}</td>
            <td>{cat.passed}</td>
            <td>{cat.failed}</td>
            <td class="{score_class}">{cat.average_score:.1%}</td>
            <td>{cat.coverage_percentage:.1f}%</td>
        </tr>
"""

        html += """
    </table>

    <h2>💡 Recommendations</h2>
"""

        for rec in report.recommendations:
            html += f'    <div class="recommendation">{rec}</div>\n'

        # Failed tests
        failures = [r for r in report.results if r.status == TestStatus.FAILED]
        if failures:
            html += """
    <h2>❌ Failed Tests</h2>
    <table>
        <tr>
            <th>Test ID</th>
            <th>Name</th>
            <th>Category</th>
            <th>Score</th>
            <th>Details</th>
        </tr>
"""
            for r in failures[:20]:
                html += f"""
        <tr>
            <td>{r.test_id}</td>
            <td>{r.name}</td>
            <td>{r.category.value}</td>
            <td class="score-low">{r.score:.1%}</td>
            <td>{r.details[:100]}</td>
        </tr>
"""
            html += "    </table>\n"

        html += """
</body>
</html>
"""
        return html


# =============================================================================
# CLI INTERFACE
# =============================================================================

async def run_cli():
    """Command line interface for running tests"""
    import argparse

    parser = argparse.ArgumentParser(description="Perennia AI Knowledge Test Suite")
    parser.add_argument("--provider", choices=["claude", "openai", "mock"], default="claude",
                       help="AI provider to test")
    parser.add_argument("--category", type=str, help="Test specific category only")
    parser.add_argument("--output", type=str, default="report", help="Output file prefix")
    parser.add_argument("--format", choices=["json", "md", "html", "all"], default="all",
                       help="Output format")
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("--verbose", action="store_true", help="Show detailed progress")

    args = parser.parse_args()

    # Create adapter
    print(f"\n{'='*60}")
    print("PERENNIA AI KNOWLEDGE TEST SUITE")
    print(f"{'='*60}\n")

    if args.provider == "claude":
        adapter = ClaudeAdapter()
        print("Using Claude API")
    elif args.provider == "openai":
        adapter = OpenAIAdapter()
        print("Using OpenAI API")
    else:
        adapter = MockAdapter()
        print("Using Mock Adapter (for testing)")

    # Create runner
    runner = TestRunner(adapter, parallel=args.parallel)

    # Progress callback
    def progress(current, total, test_id):
        if args.verbose:
            print(f"  [{current}/{total}] {test_id}")
        else:
            print(f"\rProgress: {current}/{total} ({current/total*100:.0f}%)", end="")

    # Run tests
    print(f"\nRunning {get_test_count()} tests...")
    print("-" * 40)

    start_time = datetime.now()

    if args.category:
        category = KnowledgeCategory(args.category.lower())
        results = await runner.run_category(category, progress_callback=progress)
    else:
        results = await runner.run_all(progress_callback=progress)

    execution_time = (datetime.now() - start_time).total_seconds()

    print(f"\n\nCompleted in {execution_time:.1f}s")

    # Generate report
    generator = ReportGenerator(results)
    report = generator.generate_full_report(execution_time)

    # Print summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"\nOverall Score: {report.overall_score:.1%}")
    print(f"Tests Passed: {sum(1 for r in results if r.status == TestStatus.PASSED)}/{len(results)}")
    print("\nCategory Scores:")
    for name, cat in report.categories.items():
        bar = "█" * int(cat.average_score * 20) + "░" * (20 - int(cat.average_score * 20))
        print(f"  {name:15} {bar} {cat.average_score:.1%}")

    # Save reports
    if args.format in ["json", "all"]:
        with open(f"{args.output}.json", "w") as f:
            f.write(generator.to_json(report))
        print(f"\nSaved: {args.output}.json")

    if args.format in ["md", "all"]:
        with open(f"{args.output}.md", "w") as f:
            f.write(generator.to_markdown(report))
        print(f"Saved: {args.output}.md")

    if args.format in ["html", "all"]:
        with open(f"{args.output}.html", "w") as f:
            f.write(generator.to_html(report))
        print(f"Saved: {args.output}.html")

    print("\n" + "=" * 60)

    return report


# =============================================================================
# QUICK TEST FUNCTION
# =============================================================================

async def quick_test(
    provider: str = "claude",
    categories: List[str] = None,
    verbose: bool = True,
) -> FullReport:
    """
    Quick function to run tests programmatically.

    Usage:
        from AI_KNOWLEDGE_TEST_PART3_RUNNER import quick_test

        report = await quick_test(provider="claude")
        print(f"Score: {report.overall_score:.1%}")
    """
    # Create adapter
    if provider == "claude":
        adapter = ClaudeAdapter()
    elif provider == "openai":
        adapter = OpenAIAdapter()
    else:
        adapter = MockAdapter()

    runner = TestRunner(adapter)

    # Filter categories if specified
    category_filter = None
    if categories:
        category_filter = [KnowledgeCategory(c) for c in categories]

    # Run
    if verbose:
        print(f"Running {get_test_count()} tests...")

    start = datetime.now()

    if category_filter:
        results = []
        for cat in category_filter:
            results.extend(await runner.run_category(cat))
    else:
        results = await runner.run_all()

    execution_time = (datetime.now() - start).total_seconds()

    # Generate report
    generator = ReportGenerator(results)
    report = generator.generate_full_report(execution_time)

    if verbose:
        print(f"\nOverall Score: {report.overall_score:.1%}")
        print(f"Completed in {execution_time:.1f}s")

    return report


async def test_category(
    category: str,
    provider: str = "claude",
    verbose: bool = True,
) -> FullReport:
    """
    Test a single category.

    Usage:
        from AI_KNOWLEDGE_TEST_PART3_RUNNER import test_category

        report = await test_category("pipeline", provider="claude")
    """
    return await quick_test(provider=provider, categories=[category], verbose=verbose)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    asyncio.run(run_cli())
