#!/usr/bin/env python3
"""
Comprehensive test for all data upload destinations
Tests: leads, loans, portfolio, realtors, team_members
"""

import requests
import json
import time

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

def get_auth_token():
    """Login and get authentication token"""
    login_data = {"username": "demo@example.com", "password": "demo123"}

    try:
        response = requests.post(
            f"{API_BASE_URL}/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            print(f"❌ Login failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Login error: {e}")
        return None

def test_upload(token, destination, csv_content, mappings, test_name):
    """Test upload for a specific destination"""
    print(f"\n{'='*70}")
    print(f"TESTING: {test_name}")
    print(f"Destination: {destination}")
    print(f"{'='*70}")

    answers = {"destination": destination}

    files = {'file': (f'test_{destination}.csv', csv_content, 'text/csv')}
    data = {
        'mappings': json.dumps(mappings),
        'answers': json.dumps(answers)
    }
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/data-import/execute",
            files=files,
            data=data,
            headers=headers
        )

        print(f"\n📊 Status Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Upload successful!")
            print(f"   Total rows: {result.get('total', 0)}")
            print(f"   Imported: {result.get('imported', 0)}")
            print(f"   Failed: {result.get('failed', 0)}")

            if result.get('errors'):
                print(f"\n⚠️  Errors:")
                for error in result.get('errors', [])[:3]:
                    print(f"      {error}")

            return result.get('failed', 0) == 0
        else:
            print(f"❌ Upload failed!")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "🔷"*35)
    print("COMPREHENSIVE DATA UPLOAD TEST")
    print("Testing all 5 destination types")
    print("🔷"*35)

    # Get auth token
    token = get_auth_token()
    if not token:
        print("\n❌ Cannot proceed without authentication")
        return

    print(f"\n✅ Authentication successful")

    # Wait for Railway deployment
    print(f"\n⏳ Waiting 2 minutes for Railway deployment...")
    time.sleep(120)

    results = {}

    # Test 1: Leads
    csv_leads = """first_name,last_name,email,phone,address,city,state,zip
John,Doe,john.doe@example.com,555-1111,123 Main St,Austin,TX,78701
Jane,Smith,jane.smith@example.com,555-2222,456 Oak Ave,Dallas,TX,75201
"""
    mappings_leads = {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "phone": "phone",
        "address": "address",
        "city": "city",
        "state": "state",
        "zip": "zip_code"
    }
    results['leads'] = test_upload(token, 'leads', csv_leads, mappings_leads, "Leads Upload")

    # Test 2: Active Loans
    csv_loans = """first_name,last_name,email,phone,loan_amount,property_value
Bob,Johnson,bob.j@example.com,555-3333,350000,450000
Alice,Williams,alice.w@example.com,555-4444,275000,325000
"""
    mappings_loans = {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "phone": "phone",
        "loan_amount": "loan_amount",
        "property_value": "property_value"
    }
    results['loans'] = test_upload(token, 'loans', csv_loans, mappings_loans, "Active Loans Upload")

    # Test 3: Portfolio (MUM Clients)
    csv_portfolio = """first_name,last_name,email,phone,loan_amount,interest_rate
Charlie,Brown,charlie.b@example.com,555-5555,400000,3.5
Diana,Prince,diana.p@example.com,555-6666,300000,4.0
"""
    mappings_portfolio = {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "phone": "phone",
        "loan_amount": "loan_amount",
        "interest_rate": "interest_rate"
    }
    results['portfolio'] = test_upload(token, 'portfolio', csv_portfolio, mappings_portfolio, "Portfolio (MUM) Upload")

    # Test 4: Realtors / Referral Partners
    csv_realtors = """first_name,last_name,email,phone,company,type
Emily,Realtor,emily.r@realty.com,555-7777,Premier Realty,realtor
Frank,Lender,frank.l@lending.com,555-8888,Quick Loans Inc,lender
"""
    mappings_realtors = {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "phone": "phone",
        "company": "company",
        "type": "type"
    }
    results['realtors'] = test_upload(token, 'realtors', csv_realtors, mappings_realtors, "Realtors/Partners Upload")

    # Test 5: Team Members
    csv_team = """first_name,last_name,email,role
Grace,Officer,grace.o@mortgage.com,loan_officer
Henry,Admin,henry.a@mortgage.com,admin
"""
    mappings_team = {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "role": "role"
    }
    results['team_members'] = test_upload(token, 'team_members', csv_team, mappings_team, "Team Members Upload")

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    all_passed = True
    for dest, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status} - {dest}")
        if not passed:
            all_passed = False

    print("\n" + "="*70)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("\nData upload functionality is working for all destination types:")
        print("  ✅ Leads")
        print("  ✅ Active Loans")
        print("  ✅ Portfolio (MUM Clients)")
        print("  ✅ Realtors / Referral Partners")
        print("  ✅ Team Members")
        print("\n✨ You can now upload data from the CRM UI!")
    else:
        print("⚠️  SOME TESTS FAILED")
        print("\nPlease check the errors above for details.")

    print("="*70 + "\n")

if __name__ == "__main__":
    main()
