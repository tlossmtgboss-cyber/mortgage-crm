#!/usr/bin/env python3
"""
Final verification test with fresh data (no duplicates)
"""

import requests
import json
import random

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

def get_auth_token():
    """Login and get authentication token"""
    login_data = {"username": "demo@example.com", "password": "demo123"}
    response = requests.post(
        f"{API_BASE_URL}/token",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    return None

def test_upload(token, destination, csv_content, mappings):
    """Test upload"""
    answers = {"destination": destination}
    files = {'file': (f'test_{destination}.csv', csv_content, 'text/csv')}
    data = {
        'mappings': json.dumps(mappings),
        'answers': json.dumps(answers)
    }
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.post(
        f"{API_BASE_URL}/api/v1/data-import/execute",
        files=files,
        data=data,
        headers=headers
    )

    return response.status_code == 200 and response.json().get('imported', 0) > 0

def main():
    print("\n" + "="*70)
    print("FINAL VERIFICATION TEST - Fresh Data Upload")
    print("="*70)

    token = get_auth_token()
    if not token:
        print("❌ Login failed")
        return

    print("\n✅ Authenticated")

    # Generate unique identifiers for this test
    unique_id = random.randint(10000, 99999)

    results = []

    # Test Leads
    csv = f"""first_name,last_name,email,phone
TestLead{unique_id}A,Smith,testlead{unique_id}a@example.com,555-1111
TestLead{unique_id}B,Jones,testlead{unique_id}b@example.com,555-2222
"""
    mappings = {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "phone": "phone"
    }
    result = test_upload(token, 'leads', csv, mappings)
    results.append(("Leads", result))
    print(f"{'✅' if result else '❌'} Leads: {'Passed' if result else 'Failed'}")

    # Test Loans
    csv = f"""first_name,last_name,loan_amount,property_value
TestLoan{unique_id}A,Client,400000,500000
TestLoan{unique_id}B,Borrower,300000,375000
"""
    mappings = {
        "first_name": "first_name",
        "last_name": "last_name",
        "loan_amount": "loan_amount",
        "property_value": "property_value"
    }
    result = test_upload(token, 'loans', csv, mappings)
    results.append(("Loans", result))
    print(f"{'✅' if result else '❌'} Loans: {'Passed' if result else 'Failed'}")

    # Test Portfolio
    csv = f"""first_name,last_name,loan_amount,interest_rate
TestMUM{unique_id}A,Client,450000,3.75
TestMUM{unique_id}B,Customer,350000,4.00
"""
    mappings = {
        "first_name": "first_name",
        "last_name": "last_name",
        "loan_amount": "loan_amount",
        "interest_rate": "interest_rate"
    }
    result = test_upload(token, 'portfolio', csv, mappings)
    results.append(("Portfolio", result))
    print(f"{'✅' if result else '❌'} Portfolio: {'Passed' if result else 'Failed'}")

    # Test Realtors
    csv = f"""first_name,last_name,email,phone,company
TestRealtor{unique_id}A,Agent,testrealtor{unique_id}a@realty.com,555-7777,Test Realty
TestRealtor{unique_id}B,Partner,testrealtor{unique_id}b@loans.com,555-8888,Test Lending
"""
    mappings = {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "phone": "phone",
        "company": "company"
    }
    result = test_upload(token, 'realtors', csv, mappings)
    results.append(("Realtors", result))
    print(f"{'✅' if result else '❌'} Realtors: {'Passed' if result else 'Failed'}")

    # Test Team Members with unique emails
    csv = f"""first_name,last_name,email,role
TestUser{unique_id}A,Officer,testuser{unique_id}a@mortgage.com,loan_officer
TestUser{unique_id}B,Admin,testuser{unique_id}b@mortgage.com,admin
"""
    mappings = {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "role": "role"
    }
    result = test_upload(token, 'team_members', csv, mappings)
    results.append(("Team Members", result))
    print(f"{'✅' if result else '❌'} Team Members: {'Passed' if result else 'Failed'}")

    # Summary
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)

    all_passed = all(r[1] for r in results)

    for name, passed in results:
        print(f"{'✅' if passed else '❌'} {name}")

    print("\n" + "="*70)
    if all_passed:
        print("🎉 SUCCESS! ALL UPLOAD TYPES WORKING!")
        print("\nAll 5 destination types successfully uploaded fresh data:")
        print("  ✅ Leads")
        print("  ✅ Active Loans")
        print("  ✅ Portfolio (MUM Clients)")
        print("  ✅ Realtors / Referral Partners")
        print("  ✅ Team Members")
        print("\n✨ Data upload is FULLY FUNCTIONAL!")
    else:
        print("⚠️  Some tests failed - check errors above")

    print("="*70 + "\n")

if __name__ == "__main__":
    main()
