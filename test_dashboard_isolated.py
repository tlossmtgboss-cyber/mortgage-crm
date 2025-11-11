#!/usr/bin/env python3
"""
Test dashboard components in isolation to find the 500 error
"""
import requests

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get token
response = requests.post(
    f"{API_BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("Testing dashboard-related endpoints...")

# Test tasks endpoint
print("\n1. Testing /api/v1/tasks/...")
response = requests.get(f"{API_BASE_URL}/api/v1/tasks/", headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    tasks = response.json()
    print(f"  Tasks count: {len(tasks)}")
else:
    print(f"  Error: {response.text[:200]}")

# Test referral partners
print("\n2. Testing /api/v1/referral-partners/...")
response = requests.get(f"{API_BASE_URL}/api/v1/referral-partners/", headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    partners = response.json()
    print(f"  Partners count: {len(partners)}")
else:
    print(f"  Error: {response.text[:200]}")

# Test activities
print("\n3. Testing /api/v1/activities/...")
response = requests.get(f"{API_BASE_URL}/api/v1/activities/", headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    activities = response.json()
    print(f"  Activities count: {len(activities)}")
else:
    print(f"  Error: {response.text[:200]}")

print("\n" + "="*80)
print("If all above endpoints work, the dashboard issue is in the logic, not the data")
print("="*80)
