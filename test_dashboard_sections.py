#!/usr/bin/env python3
"""
Test individual sections of dashboard to isolate the 500 error
"""
import requests
from datetime import date, timedelta

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get token
response = requests.post(
    f"{API_BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("Testing individual data queries that dashboard uses...")
print("="*80)

# Test 1: Get loans
print("\n1. Testing basic loans query...")
try:
    response = requests.get(f"{API_BASE_URL}/api/v1/loans/", headers=headers)
    if response.status_code == 200:
        loans = response.json()
        print(f"✓ Got {len(loans)} loans")

        # Check for loans in each stage
        from collections import defaultdict
        stages = defaultdict(int)
        for loan in loans:
            stages[loan.get('stage')] += 1

        print(f"  Loan stages: {dict(stages)}")

        # Check if any loan has problematic data
        for loan in loans:
            if loan.get('stage') == 'UW_RECEIVED':
                print(f"  Found UW loan: ID={loan['id']}, has status field: {'status' in loan}")
                if 'status' in loan:
                    print(f"    Status value: {loan['status']}")
                break
    else:
        print(f"✗ Failed: {response.status_code}")
except Exception as e:
    print(f"✗ Exception: {e}")

# Test 2: Get leads
print("\n2. Testing basic leads query...")
try:
    response = requests.get(f"{API_BASE_URL}/api/v1/leads/", headers=headers)
    if response.status_code == 200:
        leads = response.json()
        print(f"✓ Got {len(leads)} leads")

        # Check for high AI scores
        high_score = [l for l in leads if l.get('ai_score', 0) >= 80]
        print(f"  Leads with AI score >= 80: {len(high_score)}")
    else:
        print(f"✗ Failed: {response.status_code}")
except Exception as e:
    print(f"✗ Exception: {e}")

# Test 3: Check for loans with NULL values that might cause issues
print("\n3. Checking for potentially problematic loan data...")
try:
    response = requests.get(f"{API_BASE_URL}/api/v1/loans/", headers=headers)
    if response.status_code == 200:
        loans = response.json()

        # Check funded loans
        funded = [l for l in loans if l.get('stage') == 'Funded']
        print(f"  Funded loans: {len(funded)}")

        # Check for NULL amounts
        null_amounts = [l for l in funded if l.get('amount') is None]
        print(f"  Funded loans with NULL amount: {len(null_amounts)}")

        # Check for NULL funded_date
        null_dates = [l for l in funded if l.get('funded_date') is None]
        print(f"  Funded loans with NULL funded_date: {len(null_dates)}")

        # Check processing loans
        processing = [l for l in loans if l.get('stage') == 'Processing']
        print(f"  Processing loans: {len(processing)}")

        # Check UW loans
        uw = [l for l in loans if l.get('stage') == 'UW_RECEIVED']
        print(f"  UW_RECEIVED loans: {len(uw)}")
        if uw:
            # Check if they have days_in_stage
            sample = uw[0]
            print(f"  Sample UW loan fields: {sample.keys()}")

except Exception as e:
    print(f"✗ Exception: {e}")

print("\n" + "="*80)
print("Analysis complete. If all queries work, the issue is in dashboard aggregation logic.")
print("="*80)
