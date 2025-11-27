#!/usr/bin/env python3
"""
Pipeline360 Load Testing Script
================================
Simulates concurrent users making API requests to test system performance.

Usage:
    python tests/load_test.py [API_URL] [--users N] [--requests N] [--api-key KEY]

Environment Variables:
    TEST_API_KEY - API key to bypass IP restrictions (set in server .env)

Examples:
    python tests/load_test.py https://mortgage-crm-production-7a9a.up.railway.app
    python tests/load_test.py --users 50 --requests 10
    TEST_API_KEY=your-key python tests/load_test.py https://api.example.com
    python tests/load_test.py --api-key your-key https://api.example.com
"""

import asyncio
import aiohttp
import argparse
import os
import sys
import time
from dataclasses import dataclass
from statistics import mean, median, stdev
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class RequestResult:
    """Result of a single API request"""
    endpoint: str
    status: int
    duration: float
    success: bool
    error: Optional[str] = None


class LoadTester:
    """Load testing utility for Pipeline360 API"""

    def __init__(self, api_url: str, token: str = None, test_api_key: str = None):
        self.api_url = api_url.rstrip('/')
        self.token = token
        self.test_api_key = test_api_key or os.getenv("TEST_API_KEY", "")
        self.results: List[RequestResult] = []

    async def get_token(self, session: aiohttp.ClientSession) -> str:
        """Get authentication token"""
        try:
            headers = {}
            if self.test_api_key:
                headers["X-Test-API-Key"] = self.test_api_key

            async with session.post(
                f"{self.api_url}/token",
                headers=headers,
                data={
                    "username": "demo@example.com",
                    "password": "demo123"
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("access_token")
        except Exception as e:
            print(f"Failed to get token: {e}")
        return None

    async def make_request(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        method: str = "GET",
        data: dict = None
    ) -> RequestResult:
        """Make a single API request and measure performance"""
        url = f"{self.api_url}{endpoint}"
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.test_api_key:
            headers["X-Test-API-Key"] = self.test_api_key

        start = time.time()
        try:
            if method == "GET":
                async with session.get(url, headers=headers, timeout=30) as response:
                    await response.text()  # Consume response
                    duration = time.time() - start
                    return RequestResult(
                        endpoint=endpoint,
                        status=response.status,
                        duration=duration,
                        success=response.status == 200
                    )
            elif method == "POST":
                async with session.post(url, headers=headers, json=data, timeout=30) as response:
                    await response.text()
                    duration = time.time() - start
                    return RequestResult(
                        endpoint=endpoint,
                        status=response.status,
                        duration=duration,
                        success=response.status in (200, 201)
                    )
        except asyncio.TimeoutError:
            return RequestResult(
                endpoint=endpoint,
                status=0,
                duration=30.0,
                success=False,
                error="Timeout"
            )
        except Exception as e:
            return RequestResult(
                endpoint=endpoint,
                status=0,
                duration=time.time() - start,
                success=False,
                error=str(e)
            )

    async def run_test(
        self,
        endpoints: List[Dict],
        concurrent_users: int = 50,
        requests_per_user: int = 10
    ) -> Dict:
        """Run load test with simulated concurrent users"""

        print(f"\n{'='*60}")
        print(f"  Pipeline360 Load Test")
        print(f"{'='*60}")
        print(f"API URL: {self.api_url}")
        print(f"Concurrent Users: {concurrent_users}")
        print(f"Requests per User: {requests_per_user}")
        print(f"Total Requests: {concurrent_users * requests_per_user * len(endpoints)}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        connector = aiohttp.TCPConnector(limit=100)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Get auth token
            if not self.token:
                print("Getting authentication token...")
                self.token = await self.get_token(session)
                if not self.token:
                    print("❌ Failed to get authentication token")
                    return {"error": "Authentication failed"}
                print("✅ Token acquired\n")

            # Create all tasks
            tasks = []
            for user in range(concurrent_users):
                for req in range(requests_per_user):
                    for endpoint_config in endpoints:
                        task = self.make_request(
                            session,
                            endpoint_config["path"],
                            endpoint_config.get("method", "GET"),
                            endpoint_config.get("data")
                        )
                        tasks.append(task)

            # Execute all tasks
            print(f"Executing {len(tasks)} requests...")
            start_time = time.time()

            # Run in batches to avoid overwhelming the server
            batch_size = 100
            all_results = []
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i+batch_size]
                batch_results = await asyncio.gather(*batch)
                all_results.extend(batch_results)
                print(f"  Completed {min(i+batch_size, len(tasks))}/{len(tasks)} requests...")

            total_time = time.time() - start_time
            self.results = all_results

            return self._analyze_results(total_time)

    def _analyze_results(self, total_time: float) -> Dict:
        """Analyze test results and generate report"""

        if not self.results:
            return {"error": "No results to analyze"}

        # Calculate metrics
        durations = [r.duration for r in self.results]
        success_count = sum(1 for r in self.results if r.success)
        error_count = len(self.results) - success_count

        # Group by endpoint
        endpoint_stats = {}
        for result in self.results:
            if result.endpoint not in endpoint_stats:
                endpoint_stats[result.endpoint] = {
                    "durations": [],
                    "successes": 0,
                    "errors": 0
                }
            endpoint_stats[result.endpoint]["durations"].append(result.duration)
            if result.success:
                endpoint_stats[result.endpoint]["successes"] += 1
            else:
                endpoint_stats[result.endpoint]["errors"] += 1

        # Generate report
        print(f"\n{'='*60}")
        print(f"  Load Test Results")
        print(f"{'='*60}\n")

        print(f"Overall Statistics:")
        print(f"  Total Requests:     {len(self.results)}")
        print(f"  Successful:         {success_count} ({success_count/len(self.results)*100:.1f}%)")
        print(f"  Failed:             {error_count} ({error_count/len(self.results)*100:.1f}%)")
        print(f"  Total Time:         {total_time:.2f}s")
        print(f"  Requests/Second:    {len(self.results)/total_time:.2f}")
        print()

        print(f"Response Time (seconds):")
        print(f"  Average:            {mean(durations):.3f}s")
        print(f"  Median:             {median(durations):.3f}s")
        print(f"  Std Dev:            {stdev(durations):.3f}s" if len(durations) > 1 else "  Std Dev:            N/A")
        print(f"  Min:                {min(durations):.3f}s")
        print(f"  Max:                {max(durations):.3f}s")
        print()

        # Percentiles
        sorted_durations = sorted(durations)
        p95_idx = int(len(sorted_durations) * 0.95)
        p99_idx = int(len(sorted_durations) * 0.99)
        print(f"Percentiles:")
        print(f"  P95:                {sorted_durations[p95_idx]:.3f}s")
        print(f"  P99:                {sorted_durations[p99_idx]:.3f}s")
        print()

        print(f"Per-Endpoint Statistics:")
        for endpoint, stats in endpoint_stats.items():
            ep_durations = stats["durations"]
            print(f"\n  {endpoint}:")
            print(f"    Requests:         {len(ep_durations)}")
            print(f"    Success Rate:     {stats['successes']/len(ep_durations)*100:.1f}%")
            print(f"    Avg Time:         {mean(ep_durations):.3f}s")
            print(f"    Max Time:         {max(ep_durations):.3f}s")

        print(f"\n{'='*60}")

        # Performance assessment
        avg_time = mean(durations)
        success_rate = success_count / len(self.results) * 100

        print("\nPerformance Assessment:")

        if avg_time < 0.5 and success_rate > 99:
            print("  ✅ EXCELLENT - System is performing well")
        elif avg_time < 1.0 and success_rate > 95:
            print("  ✅ GOOD - System meets performance targets")
        elif avg_time < 2.0 and success_rate > 90:
            print("  ⚠️  ACCEPTABLE - Some optimization may help")
        else:
            print("  ❌ NEEDS IMPROVEMENT - Performance issues detected")

        print(f"\n{'='*60}")

        # Return summary for programmatic use
        return {
            "total_requests": len(self.results),
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": success_rate,
            "total_time": total_time,
            "requests_per_second": len(self.results) / total_time,
            "avg_response_time": avg_time,
            "median_response_time": median(durations),
            "min_response_time": min(durations),
            "max_response_time": max(durations),
            "p95_response_time": sorted_durations[p95_idx],
            "p99_response_time": sorted_durations[p99_idx],
            "endpoint_stats": endpoint_stats
        }


async def main():
    parser = argparse.ArgumentParser(description="Pipeline360 Load Testing")
    parser.add_argument(
        "api_url",
        nargs="?",
        default="https://mortgage-crm-production-7a9a.up.railway.app",
        help="API URL to test"
    )
    parser.add_argument(
        "--users",
        type=int,
        default=20,
        help="Number of concurrent users (default: 20)"
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=5,
        help="Requests per user (default: 5)"
    )
    parser.add_argument(
        "--token",
        type=str,
        help="Auth token (will fetch if not provided)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="Test API key to bypass IP restrictions (or set TEST_API_KEY env var)"
    )

    args = parser.parse_args()

    # Define endpoints to test
    endpoints = [
        {"path": "/api/v1/loans/", "method": "GET"},
        {"path": "/api/v1/tasks/", "method": "GET"},
        {"path": "/api/v1/contacts/", "method": "GET"},
        {"path": "/api/v1/leads/", "method": "GET"},
        {"path": "/health", "method": "GET"},
    ]

    # Get API key from argument or environment
    api_key = args.api_key or os.getenv("TEST_API_KEY", "")

    tester = LoadTester(args.api_url, args.token, api_key)
    results = await tester.run_test(
        endpoints=endpoints,
        concurrent_users=args.users,
        requests_per_user=args.requests
    )

    # Exit with appropriate code
    if results.get("error"):
        sys.exit(1)
    elif results.get("success_rate", 0) < 95 or results.get("avg_response_time", 999) > 2.0:
        print("\n⚠️  Performance targets not met")
        sys.exit(1)
    else:
        print("\n✅ Load test passed")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
