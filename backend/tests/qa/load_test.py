#!/usr/bin/env python3
"""
Load Testing Script
Simulates concurrent users for performance testing
"""

import asyncio
import aiohttp
import time
import statistics
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import threading
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@dataclass
class RequestMetrics:
    """Metrics for a single request"""
    endpoint: str
    method: str
    status_code: int
    response_time: float
    timestamp: datetime
    error: Optional[str] = None
    success: bool = True


@dataclass
class LoadTestResult:
    """Results from a load test run"""
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_duration: float
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    p50_response_time: float
    p95_response_time: float
    p99_response_time: float
    requests_per_second: float
    error_rate: float
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "total_duration": round(self.total_duration, 2),
            "avg_response_time": round(self.avg_response_time, 3),
            "min_response_time": round(self.min_response_time, 3),
            "max_response_time": round(self.max_response_time, 3),
            "p50_response_time": round(self.p50_response_time, 3),
            "p95_response_time": round(self.p95_response_time, 3),
            "p99_response_time": round(self.p99_response_time, 3),
            "requests_per_second": round(self.requests_per_second, 2),
            "error_rate": round(self.error_rate, 2),
            "errors": self.errors[:10],  # First 10 errors
        }


class LoadTester:
    """Load testing utility"""

    def __init__(self, base_url: str, auth_token: str = None):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.metrics: List[RequestMetrics] = []
        self.lock = threading.Lock()

    def _get_headers(self) -> Dict:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    async def _make_request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        endpoint: str,
        data: Dict = None
    ) -> RequestMetrics:
        """Make a single HTTP request"""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()

        try:
            async with session.request(
                method,
                url,
                json=data,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                await response.text()
                elapsed = time.time() - start_time

                metric = RequestMetrics(
                    endpoint=endpoint,
                    method=method,
                    status_code=response.status,
                    response_time=elapsed,
                    timestamp=datetime.now(),
                    success=200 <= response.status < 400
                )

        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            metric = RequestMetrics(
                endpoint=endpoint,
                method=method,
                status_code=0,
                response_time=elapsed,
                timestamp=datetime.now(),
                error="Timeout",
                success=False
            )
        except Exception as e:
            elapsed = time.time() - start_time
            metric = RequestMetrics(
                endpoint=endpoint,
                method=method,
                status_code=0,
                response_time=elapsed,
                timestamp=datetime.now(),
                error=str(e),
                success=False
            )

        with self.lock:
            self.metrics.append(metric)

        return metric

    async def run_concurrent_requests(
        self,
        endpoint: str,
        method: str = "GET",
        data: Dict = None,
        num_requests: int = 100,
        concurrency: int = 10
    ) -> LoadTestResult:
        """Run concurrent requests to an endpoint"""
        self.metrics = []
        start_time = time.time()

        connector = aiohttp.TCPConnector(limit=concurrency)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self._make_request(session, method, endpoint, data)
                for _ in range(num_requests)
            ]
            await asyncio.gather(*tasks)

        total_duration = time.time() - start_time
        return self._calculate_results(total_duration)

    def _calculate_results(self, total_duration: float) -> LoadTestResult:
        """Calculate aggregate results"""
        successful = [m for m in self.metrics if m.success]
        failed = [m for m in self.metrics if not m.success]

        response_times = sorted([m.response_time for m in self.metrics])

        if not response_times:
            return LoadTestResult(
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                total_duration=total_duration,
                avg_response_time=0,
                min_response_time=0,
                max_response_time=0,
                p50_response_time=0,
                p95_response_time=0,
                p99_response_time=0,
                requests_per_second=0,
                error_rate=0
            )

        def percentile(data: List[float], p: float) -> float:
            k = (len(data) - 1) * p / 100
            f = int(k)
            c = f + 1 if f + 1 < len(data) else f
            return data[f] + (k - f) * (data[c] - data[f])

        return LoadTestResult(
            total_requests=len(self.metrics),
            successful_requests=len(successful),
            failed_requests=len(failed),
            total_duration=total_duration,
            avg_response_time=statistics.mean(response_times),
            min_response_time=min(response_times),
            max_response_time=max(response_times),
            p50_response_time=percentile(response_times, 50),
            p95_response_time=percentile(response_times, 95),
            p99_response_time=percentile(response_times, 99),
            requests_per_second=len(self.metrics) / total_duration,
            error_rate=(len(failed) / len(self.metrics)) * 100,
            errors=[m.error for m in failed if m.error][:10]
        )


class BorrowerJourneyLoadTest:
    """Simulate multiple borrowers completing applications"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.results = []

    async def simulate_borrower(self, session: aiohttp.ClientSession, borrower_id: int) -> Dict:
        """Simulate a single borrower journey"""
        metrics = {
            "borrower_id": borrower_id,
            "steps": [],
            "success": True,
            "total_time": 0
        }

        start = time.time()

        try:
            # Step 1: Start application
            step_start = time.time()
            async with session.post(
                f"{self.base_url}/api/v1/borrower/applications",
                json={"loan_purpose": "purchase"},
                headers={"Authorization": f"Bearer test_token_{borrower_id}"}
            ) as resp:
                metrics["steps"].append({
                    "name": "start_application",
                    "status": resp.status,
                    "time": time.time() - step_start
                })
                if resp.status != 201:
                    metrics["success"] = False
                    return metrics
                data = await resp.json()
                app_id = data.get("id", data.get("application_id", 1))

            # Step 2: Save personal info
            step_start = time.time()
            async with session.put(
                f"{self.base_url}/api/v1/borrower/applications/{app_id}/personal",
                json={
                    "first_name": f"Test{borrower_id}",
                    "last_name": "User",
                    "email": f"test{borrower_id}@example.com",
                    "phone": f"+1555{borrower_id:07d}"
                },
                headers={"Authorization": f"Bearer test_token_{borrower_id}"}
            ) as resp:
                metrics["steps"].append({
                    "name": "save_personal_info",
                    "status": resp.status,
                    "time": time.time() - step_start
                })

            # Step 3: Save property info
            step_start = time.time()
            async with session.put(
                f"{self.base_url}/api/v1/borrower/applications/{app_id}/property",
                json={
                    "property_address": f"{100 + borrower_id} Test Street",
                    "city": "Test City",
                    "state": "CA",
                    "zip_code": "90210",
                    "purchase_price": 500000
                },
                headers={"Authorization": f"Bearer test_token_{borrower_id}"}
            ) as resp:
                metrics["steps"].append({
                    "name": "save_property_info",
                    "status": resp.status,
                    "time": time.time() - step_start
                })

            # Step 4: Save income info
            step_start = time.time()
            async with session.put(
                f"{self.base_url}/api/v1/borrower/applications/{app_id}/income",
                json={
                    "employer_name": "Test Company",
                    "monthly_income": 10000
                },
                headers={"Authorization": f"Bearer test_token_{borrower_id}"}
            ) as resp:
                metrics["steps"].append({
                    "name": "save_income_info",
                    "status": resp.status,
                    "time": time.time() - step_start
                })

        except Exception as e:
            metrics["success"] = False
            metrics["error"] = str(e)

        metrics["total_time"] = time.time() - start
        return metrics

    async def run_load_test(self, num_borrowers: int = 50, concurrency: int = 10) -> Dict:
        """Run load test with multiple concurrent borrowers"""
        print(f"\n{'=' * 60}")
        print(f"BORROWER JOURNEY LOAD TEST")
        print(f"{'=' * 60}")
        print(f"Simulating {num_borrowers} borrowers with {concurrency} concurrent")
        print()

        start_time = time.time()

        connector = aiohttp.TCPConnector(limit=concurrency)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self.simulate_borrower(session, i)
                for i in range(num_borrowers)
            ]
            self.results = await asyncio.gather(*tasks)

        total_duration = time.time() - start_time

        # Analyze results
        successful = [r for r in self.results if r["success"]]
        failed = [r for r in self.results if not r["success"]]

        step_times = {}
        for result in successful:
            for step in result["steps"]:
                name = step["name"]
                if name not in step_times:
                    step_times[name] = []
                step_times[name].append(step["time"])

        report = {
            "total_borrowers": num_borrowers,
            "successful": len(successful),
            "failed": len(failed),
            "total_duration": total_duration,
            "borrowers_per_second": num_borrowers / total_duration,
            "success_rate": (len(successful) / num_borrowers) * 100,
            "avg_journey_time": statistics.mean([r["total_time"] for r in successful]) if successful else 0,
            "step_performance": {
                name: {
                    "avg": statistics.mean(times),
                    "max": max(times),
                    "min": min(times),
                }
                for name, times in step_times.items()
            }
        }

        self._print_report(report)
        return report

    def _print_report(self, report: Dict):
        """Print formatted report"""
        print(f"\n{'=' * 60}")
        print("RESULTS")
        print(f"{'=' * 60}")
        print(f"Total Borrowers: {report['total_borrowers']}")
        print(f"Successful: {report['successful']}")
        print(f"Failed: {report['failed']}")
        print(f"Success Rate: {report['success_rate']:.1f}%")
        print(f"Total Duration: {report['total_duration']:.2f}s")
        print(f"Throughput: {report['borrowers_per_second']:.2f} borrowers/second")
        print(f"Avg Journey Time: {report['avg_journey_time']:.2f}s")

        print(f"\n{'=' * 60}")
        print("STEP PERFORMANCE")
        print(f"{'=' * 60}")
        for step, perf in report.get("step_performance", {}).items():
            print(f"\n{step}:")
            print(f"  Avg: {perf['avg']*1000:.0f}ms")
            print(f"  Min: {perf['min']*1000:.0f}ms")
            print(f"  Max: {perf['max']*1000:.0f}ms")

        # Pass/Fail assessment
        print(f"\n{'=' * 60}")
        print("ASSESSMENT")
        print(f"{'=' * 60}")

        passed = True
        if report["success_rate"] < 95:
            print("❌ FAIL: Success rate below 95%")
            passed = False
        else:
            print("✅ PASS: Success rate above 95%")

        if report["avg_journey_time"] > 30:
            print("❌ FAIL: Average journey time above 30 seconds")
            passed = False
        else:
            print("✅ PASS: Average journey time acceptable")

        slow_steps = [
            s for s, p in report.get("step_performance", {}).items()
            if p["avg"] > 2
        ]
        if slow_steps:
            print(f"⚠️ WARNING: Slow steps (>2s avg): {', '.join(slow_steps)}")

        print(f"\n{'=' * 60}")
        print(f"OVERALL: {'✅ PASS' if passed else '❌ FAIL'}")
        print(f"{'=' * 60}")


async def run_api_load_test(base_url: str, token: str):
    """Run load test on API endpoints"""
    tester = LoadTester(base_url, token)

    endpoints = [
        ("/api/v1/borrower/applications", "GET"),
        ("/api/v1/lo/dashboard/stats", "GET"),
        ("/api/v1/lo/applications", "GET"),
    ]

    print(f"\n{'=' * 60}")
    print("API ENDPOINT LOAD TEST")
    print(f"{'=' * 60}")

    for endpoint, method in endpoints:
        print(f"\nTesting {method} {endpoint}...")
        result = await tester.run_concurrent_requests(
            endpoint=endpoint,
            method=method,
            num_requests=100,
            concurrency=20
        )

        print(f"  Requests: {result.total_requests}")
        print(f"  Success: {result.successful_requests}")
        print(f"  Failed: {result.failed_requests}")
        print(f"  Avg Response: {result.avg_response_time*1000:.0f}ms")
        print(f"  P95 Response: {result.p95_response_time*1000:.0f}ms")
        print(f"  Error Rate: {result.error_rate:.1f}%")
        print(f"  RPS: {result.requests_per_second:.1f}")

        if result.avg_response_time > 0.5:
            print("  ❌ FAIL: Response time > 500ms")
        else:
            print("  ✅ PASS")


def main():
    parser = argparse.ArgumentParser(description="Load Testing Tool")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--token", default="test_token", help="Auth token")
    parser.add_argument("--users", type=int, default=50, help="Number of simulated users")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent users")
    parser.add_argument("--test", choices=["api", "journey", "both"], default="both")

    args = parser.parse_args()

    if args.test in ["api", "both"]:
        asyncio.run(run_api_load_test(args.url, args.token))

    if args.test in ["journey", "both"]:
        journey_test = BorrowerJourneyLoadTest(args.url)
        asyncio.run(journey_test.run_load_test(args.users, args.concurrency))


if __name__ == "__main__":
    main()
