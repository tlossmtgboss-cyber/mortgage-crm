#!/usr/bin/env python3
"""Test creating and retrieving team partners"""
import requests
import json

BASE_URL = "http://localhost:8000"

# Step 1: Login to get token
print("Step 1: Logging in...")
login_response = requests.post(
    f"{BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
print(f"Login Status: {login_response.status_code}")
if login_response.status_code != 200:
    print(f"Login failed: {login_response.text}")
    exit(1)

token = login_response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print(f"✅ Logged in successfully")

# Step 2: Create a team partner
print("\nStep 2: Creating a team partner...")
team_partner_data = {
    "name": "Elite Real Estate Team",
    "company": "Elite Realty Group",
    "type": "Real Estate Agent",
    "phone": "555-0199",
    "email": "team@eliterealty.com",
    "partner_category": "team"
}
create_response = requests.post(
    f"{BASE_URL}/api/v1/referral-partners/",
    json=team_partner_data,
    headers=headers
)
print(f"Create Status: {create_response.status_code}")
if create_response.status_code == 201:
    created_partner = create_response.json()
    print(f"✅ Team partner created successfully!")
    print(f"   ID: {created_partner['id']}")
    print(f"   Name: {created_partner['name']}")
    print(f"   Partner Category: {created_partner.get('partner_category', 'NOT FOUND')}")
    partner_id = created_partner['id']
else:
    print(f"❌ Failed to create team partner: {create_response.text}")
    exit(1)

# Step 3: Create an individual partner for comparison
print("\nStep 3: Creating an individual partner...")
individual_partner_data = {
    "name": "John Smith",
    "company": "Smith Realty",
    "type": "Real Estate Agent",
    "phone": "555-0188",
    "email": "john@smithrealty.com",
    "partner_category": "individual"
}
create_response2 = requests.post(
    f"{BASE_URL}/api/v1/referral-partners/",
    json=individual_partner_data,
    headers=headers
)
print(f"Create Status: {create_response2.status_code}")
if create_response2.status_code == 201:
    created_partner2 = create_response2.json()
    print(f"✅ Individual partner created successfully!")
    print(f"   ID: {created_partner2['id']}")
    print(f"   Name: {created_partner2['name']}")
    print(f"   Partner Category: {created_partner2.get('partner_category', 'NOT FOUND')}")
else:
    print(f"❌ Failed to create individual partner: {create_response2.text}")

# Step 4: Retrieve the team partner
print(f"\nStep 4: Retrieving team partner by ID {partner_id}...")
get_response = requests.get(
    f"{BASE_URL}/api/v1/referral-partners/{partner_id}",
    headers=headers
)
print(f"Get Status: {get_response.status_code}")
if get_response.status_code == 200:
    retrieved_partner = get_response.json()
    print(f"✅ Team partner retrieved successfully!")
    print(f"   Name: {retrieved_partner['name']}")
    print(f"   Partner Category: {retrieved_partner.get('partner_category', 'NOT FOUND')}")

    if retrieved_partner.get('partner_category') == 'team':
        print(f"\n🎉 SUCCESS! Team partner category is correctly saved as 'team'")
    else:
        print(f"\n❌ FAILED! Expected 'team', got '{retrieved_partner.get('partner_category')}'")
else:
    print(f"❌ Failed to retrieve team partner: {get_response.text}")

# Step 5: Get all partners and check categorization
print(f"\nStep 5: Retrieving all partners...")
all_response = requests.get(
    f"{BASE_URL}/api/v1/referral-partners/",
    headers=headers
)
print(f"Get All Status: {all_response.status_code}")
if all_response.status_code == 200:
    all_partners = all_response.json()
    team_count = sum(1 for p in all_partners if p.get('partner_category') == 'team')
    individual_count = sum(1 for p in all_partners if p.get('partner_category') == 'individual')
    print(f"✅ Retrieved {len(all_partners)} total partners")
    print(f"   Team partners: {team_count}")
    print(f"   Individual partners: {individual_count}")

    print("\nPartner details:")
    for p in all_partners:
        category = p.get('partner_category', 'NONE')
        print(f"   - {p['name']}: {category}")
else:
    print(f"❌ Failed to retrieve all partners: {all_response.text}")

print("\n" + "="*60)
print("Test completed!")
