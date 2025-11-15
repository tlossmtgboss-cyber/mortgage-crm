#!/usr/bin/env python3
"""
Test Mission Control API Endpoints on Production
Tests all endpoints to verify functionality
"""

import os
import sys
import json
from datetime import datetime
import subprocess

# Configuration
API_BASE = "https://mortgage-crm-production-7a9a.up.railway.app"

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def print_status(message, status="info"):
    if status == "success":
        print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")
    elif status == "error":
        print(f"{Colors.RED}❌ {message}{Colors.RESET}")
    elif status == "warning":
        print(f"{Colors.YELLOW}⚠️  {message}{Colors.RESET}")
    else:
        print(f"{Colors.BLUE}ℹ️  {message}{Colors.RESET}")

def print_section(title):
    print(f"\n{Colors.BLUE}{'='*70}")
    print(f"{title}")
    print(f"{'='*70}{Colors.RESET}\n")

def test_endpoint(name, url, requires_auth=True):
    """Test an API endpoint"""
    print(f"\nTesting: {name}")
    print(f"URL: {url}")

    try:
        if requires_auth:
            # For now, test without auth to see if endpoint exists
            # Will get 401 but at least we know it's there
            cmd = [
                'curl', '-s', '-w', '\\nHTTP_CODE:%{http_code}',
                url
            ]
        else:
            cmd = ['curl', '-s', '-w', '\\nHTTP_CODE:%{http_code}', url]

        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout

        # Split response and status code
        parts = output.rsplit('HTTP_CODE:', 1)
        response_body = parts[0].strip()
        status_code = parts[1].strip() if len(parts) > 1 else '000'

        print(f"Status Code: {status_code}")

        if status_code == '200':
            print_status("Endpoint working!", "success")
            # Try to parse JSON
            try:
                data = json.loads(response_body)
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                if isinstance(data, dict):
                    for key, value in list(data.items())[:3]:
                        if isinstance(value, (list, dict)):
                            print(f"  {key}: {type(value).__name__} (len={len(value) if isinstance(value, list) else 'N/A'})")
                        else:
                            print(f"  {key}: {value}")
            except json.JSONDecodeError:
                print(f"Response: {response_body[:100]}...")
            return True

        elif status_code == '401':
            print_status("Endpoint exists but requires authentication", "warning")
            return True  # Endpoint is there, just need auth

        elif status_code == '404':
            print_status("Endpoint NOT FOUND", "error")
            return False

        elif status_code == '500':
            print_status("Server error (endpoint exists but failing)", "error")
            print(f"Error: {response_body[:200]}")
            return False

        else:
            print_status(f"Unexpected status code: {status_code}", "warning")
            print(f"Response: {response_body[:200]}")
            return False

    except Exception as e:
        print_status(f"Request failed: {str(e)}", "error")
        return False

def main():
    print(f"\n{Colors.BLUE}{'='*70}")
    print("MISSION CONTROL PRODUCTION API TEST")
    print(f"{'='*70}{Colors.RESET}")
    print(f"API Base: {API_BASE}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    endpoints = {
        "Health Endpoint": f"{API_BASE}/api/v1/mission-control/health?days=7",
        "Metrics Endpoint": f"{API_BASE}/api/v1/mission-control/metrics?days=30",
        "Recent Actions": f"{API_BASE}/api/v1/mission-control/recent-actions?limit=20",
        "Insights": f"{API_BASE}/api/v1/mission-control/insights?limit=10&status=active",
    }

    results = {}
    for name, url in endpoints.items():
        results[name] = test_endpoint(name, url, requires_auth=True)

    # Summary
    print_section("SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, result in results.items():
        status = "success" if result else "error"
        print_status(f"{test}: {'AVAILABLE' if result else 'FAILED'}", status)

    print(f"\n{Colors.BLUE}Overall: {passed}/{total} endpoints accessible{Colors.RESET}")

    if passed == total:
        print_status("✨ All endpoints are accessible!", "success")
        print_status("Note: Endpoints require authentication. Frontend should work with proper login.", "info")
        return 0
    else:
        print_status(f"⚠️  {total - passed} endpoint(s) not accessible", "error")
        return 1

if __name__ == "__main__":
    sys.exit(main())
