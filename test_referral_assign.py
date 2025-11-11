#!/usr/bin/env python3
"""Test assigning a lead to a referral partner"""
import requests

BASE_URL = "http://localhost:8000"

# Step 1: Login
print("Logging in...")
login_response = requests.post(
    f"{BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)

if login_response.status_code != 200:
    print(f"Login failed: {login_response.text}")
    exit(1)

token = login_response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("✅ Logged in successfully\n")

# Step 2: Get all leads
print("Fetching leads...")
leads_response = requests.get(f"{BASE_URL}/api/v1/leads", headers=headers)
leads = leads_response.json()
print(f"Found {len(leads)} leads\n")

if len(leads) == 0:
    print("No leads found to test with")
    exit(1)

test_lead = leads[0]
print(f"Test lead: {test_lead['name']} (ID: {test_lead['id']})")
print(f"Current referral_partner_id: {test_lead.get('referral_partner_id')}\n")

# Step 3: Get all referral partners
print("Fetching referral partners...")
partners_response = requests.get(f"{BASE_URL}/api/v1/referral-partners", headers=headers)
partners = partners_response.json()
print(f"Found {len(partners)} partners\n")

if len(partners) == 0:
    print("No partners found to test with")
    exit(1)

test_partner = partners[0]
print(f"Test partner: {test_partner['name']} (ID: {test_partner['id']})")
print(f"Partner type: {test_partner.get('type')}\n")

# Step 4: Assign lead to partner
print(f"Assigning lead '{test_lead['name']}' to partner '{test_partner['name']}'...")
update_data = {
    "referral_partner_id": test_partner['id'],
    "stage": "New"
}

update_response = requests.patch(
    f"{BASE_URL}/api/v1/leads/{test_lead['id']}",
    json=update_data,
    headers=headers
)

if update_response.status_code == 200:
    updated_lead = update_response.json()
    print("✅ UPDATE SUCCESSFUL!")
    print(f"   Lead ID: {updated_lead['id']}")
    print(f"   Lead Name: {updated_lead['name']}")
    print(f"   Referral Partner ID: {updated_lead.get('referral_partner_id')}")
    print(f"   Stage: {updated_lead.get('stage')}")

    if updated_lead.get('referral_partner_id') == test_partner['id']:
        print("\n✅✅✅ SUCCESS! Lead was assigned to partner correctly!")
    else:
        print(f"\n❌❌❌ FAILED! referral_partner_id is {updated_lead.get('referral_partner_id')}, expected {test_partner['id']}")
else:
    print(f"❌ UPDATE FAILED!")
    print(f"   Status: {update_response.status_code}")
    print(f"   Error: {update_response.text}")

# Step 5: Verify by fetching the lead again
print("\nVerifying by fetching lead again...")
verify_response = requests.get(f"{BASE_URL}/api/v1/leads/{test_lead['id']}", headers=headers)
if verify_response.status_code == 200:
    verified_lead = verify_response.json()
    print(f"Verified referral_partner_id: {verified_lead.get('referral_partner_id')}")
    if verified_lead.get('referral_partner_id') == test_partner['id']:
        print("✅ VERIFICATION PASSED!")
    else:
        print(f"❌ VERIFICATION FAILED! Expected {test_partner['id']}, got {verified_lead.get('referral_partner_id')}")
