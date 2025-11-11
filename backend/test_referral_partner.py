#!/usr/bin/env python3
"""
Test script to verify referral partner creation works with proper authentication
"""

import requests
import json

BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

def test_referral_partner_creation():
    """Test creating a referral partner with authentication"""

    # Step 1: Login to get token
    print("🔐 Step 1: Logging in...")
    login_data = {
        "username": "demo@example.com",  # Change to your test user
        "password": "demo123"  # Change to your test password
    }

    response = requests.post(f"{BASE_URL}/token", data=login_data)

    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return

    token = response.json()["access_token"]
    print(f"✅ Login successful! Token: {token[:20]}...")

    # Step 2: Create referral partner
    print("\n📝 Step 2: Creating referral partner...")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    partner_data = {
        "name": "Test Partner",
        "company": "Test Realty",
        "type": "Real Estate Agent",
        "email": "test@example.com",
        "phone": "555-1234",
        "partner_category": "individual"
    }

    response = requests.post(
        f"{BASE_URL}/api/v1/referral-partners/",
        json=partner_data,
        headers=headers
    )

    if response.status_code == 201:
        partner = response.json()
        print(f"✅ Partner created successfully!")
        print(f"   ID: {partner['id']}")
        print(f"   Name: {partner['name']}")
        print(f"   Company: {partner.get('company', 'N/A')}")
    else:
        print(f"❌ Failed to create partner: {response.status_code}")
        print(f"   Response: {response.text}")

    # Step 3: List referral partners to verify
    print("\n📋 Step 3: Listing referral partners...")
    response = requests.get(f"{BASE_URL}/api/v1/referral-partners/", headers=headers)

    if response.status_code == 200:
        partners = response.json()
        print(f"✅ Found {len(partners)} referral partners")
        for partner in partners[-3:]:  # Show last 3
            print(f"   - {partner['name']} ({partner.get('company', 'No company')})")
    else:
        print(f"❌ Failed to list partners: {response.status_code}")

if __name__ == "__main__":
    test_referral_partner_creation()
