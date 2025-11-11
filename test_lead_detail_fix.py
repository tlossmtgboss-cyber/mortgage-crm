#!/usr/bin/env python3
"""
Test script to verify the lead detail fix is working.
This tests that we can view lead details regardless of ownership.
"""
import requests
import sys

# API configuration
API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

def test_lead_detail_access():
    """Test that we can access lead details"""

    # First, login to get a token
    print("🔐 Logging in...")
    login_data = {
        "username": "demo@example.com",
        "password": "demo123"
    }

    response = requests.post(
        f"{API_BASE_URL}/token",
        data=login_data
    )

    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code}")
        print(response.text)
        return False

    token = response.json()["access_token"]
    print("✅ Login successful")

    # Get list of leads
    print("\n📋 Fetching leads list...")
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(
        f"{API_BASE_URL}/api/v1/leads/",
        headers=headers,
        params={"show_all": True, "limit": 10}
    )

    if response.status_code != 200:
        print(f"❌ Failed to fetch leads: {response.status_code}")
        print(response.text)
        return False

    leads = response.json()
    print(f"✅ Found {len(leads)} leads")

    if not leads:
        print("⚠️  No leads found to test with")
        return True

    # Test accessing each lead's detail page
    print("\n🔍 Testing lead detail access...")
    success_count = 0
    fail_count = 0

    for lead in leads[:5]:  # Test first 5 leads
        lead_id = lead["id"]
        lead_name = lead.get("name", "Unknown")
        owner_id = lead.get("owner_id", "Unknown")

        response = requests.get(
            f"{API_BASE_URL}/api/v1/leads/{lead_id}",
            headers=headers
        )

        if response.status_code == 200:
            print(f"✅ Lead {lead_id} ({lead_name}) - Owner: {owner_id} - Accessible")
            success_count += 1
        else:
            print(f"❌ Lead {lead_id} ({lead_name}) - Owner: {owner_id} - Failed: {response.status_code}")
            fail_count += 1

    print(f"\n📊 Results: {success_count} successful, {fail_count} failed")

    return fail_count == 0

if __name__ == "__main__":
    print("🧪 Testing Lead Detail Access Fix\n")
    print("=" * 60)

    try:
        success = test_lead_detail_access()

        print("\n" + "=" * 60)
        if success:
            print("✅ All tests passed! Lead detail access is working correctly.")
            sys.exit(0)
        else:
            print("❌ Some tests failed. Please check the output above.")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
