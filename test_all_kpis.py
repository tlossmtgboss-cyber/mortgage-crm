#!/usr/bin/env python3
"""
Comprehensive KPI test across all endpoints
"""
import requests
import json

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get token
response = requests.post(
    f"{API_BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("="*80)
print("COMPREHENSIVE KPI TEST")
print("="*80)

endpoints = [
    ("Dashboard", "/api/v1/dashboard"),
    ("Pipeline", "/api/v1/analytics/pipeline"),
    ("Monthly Performance", "/api/v1/analytics/monthly-performance"),
    ("Loan Efficiency", "/api/v1/analytics/loan-efficiency"),
    ("Scorecard", "/api/v1/analytics/scorecard"),
    ("Portfolio Stats", "/api/v1/portfolio/stats"),
    ("Portfolio Loans", "/api/v1/portfolio/"),
    ("Leads", "/api/v1/leads/"),
    ("Loans", "/api/v1/loans/"),
]

results = {}

for name, endpoint in endpoints:
    print(f"\n{name}:")
    print("-" * 80)
    try:
        response = requests.get(f"{API_BASE_URL}{endpoint}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                print(f"✓ Status: 200 | Type: list | Count: {len(data)}")
            elif isinstance(data, dict):
                print(f"✓ Status: 200 | Type: dict | Keys: {len(data.keys())}")
                # Show key metrics
                if name == "Portfolio Stats":
                    print(f"  Total Loans: {data.get('total_loans')}")
                    print(f"  Total Volume: ${data.get('total_volume'):,.0f}")
                elif name == "Pipeline":
                    print(f"  Total Loans: {data.get('total_loans')}")
                    print(f"  Total Volume: ${data.get('total_volume'):,.0f}")
            results[name] = "✓ PASS"
        else:
            print(f"✗ Status: {response.status_code}")
            if response.status_code == 500:
                print(f"  Error: {response.text[:200]}")
            results[name] = f"✗ FAIL ({response.status_code})"
    except Exception as e:
        print(f"✗ Exception: {str(e)}")
        results[name] = f"✗ ERROR ({str(e)[:50]})"

print("\n" + "="*80)
print("SUMMARY")
print("="*80)
for name, result in results.items():
    print(f"{name:30} {result}")

passed = sum(1 for r in results.values() if "PASS" in r)
total = len(results)
print(f"\n{passed}/{total} endpoints working ({int(passed/total*100)}%)")
print("="*80 + "\n")
