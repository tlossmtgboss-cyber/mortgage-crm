#!/usr/bin/env python3
import requests
import time

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

print("Waiting 30 seconds for Railway deployment...")
time.sleep(30)

# Get token
print("\n1. Getting authentication token...")
response = requests.post(
    f"{API_BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print(f"   ✓ Token obtained")

# Test Workflow Members endpoint
print("\n2. Testing Workflow Members endpoint...")
response = requests.get(f"{API_BASE_URL}/api/v1/team/workflow-members", headers=headers)
print(f"   Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print(f"\n   ✅ SUCCESS! Workflow team members retrieved!")

    print(f"\n   📊 Role Statistics:")
    if 'role_stats' in data:
        stats = data['role_stats']
        print(f"      - Processors: {stats.get('processors', 0)}")
        print(f"      - Underwriters: {stats.get('underwriters', 0)}")
        print(f"      - Loan Officers: {stats.get('loan_officers', 0)}")
        print(f"      - Realtors: {stats.get('realtors', 0)}")
        print(f"      - Title Companies: {stats.get('title_companies', 0)}")
        print(f"      - Total Members: {stats.get('total_members', 0)}")

    print(f"\n   👥 Team Members ({len(data.get('team_members', []))}):")
    for i, member in enumerate(data.get('team_members', [])[:5], 1):
        print(f"      {i}. {member['name']} - {member['role']} ({member['loan_count']} loans)")
        if i == 5 and len(data.get('team_members', [])) > 5:
            print(f"      ... and {len(data.get('team_members', [])) - 5} more")
            break

    print(f"\n   Total Loans: {data.get('total_loans', 0)}")
else:
    print(f"\n   ❌ FAILED with status {response.status_code}")
    print(f"   Response: {response.text[:500]}")
