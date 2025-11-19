#!/usr/bin/env python3
"""Test AI Receptionist Dashboard API endpoints"""
import requests
import json

API_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get auth token
print("Getting auth token...")
token_response = requests.post(
    f"{API_URL}/token",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={"username": "demo@example.com", "password": "demo123"}
)
token = token_response.json()["access_token"]
print(f"Got token: {token[:30]}...")

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json"
}

# Test endpoints
print("\n=== Test 1: Realtime Metrics ===")
response = requests.get(f"{API_URL}/api/v1/ai-receptionist/dashboard/metrics/realtime", headers=headers)
print(f"Status: {response.status_code}")
print(json.dumps(response.json(), indent=2))

print("\n=== Test 2: Activity Feed ===")
response = requests.get(f"{API_URL}/api/v1/ai-receptionist/dashboard/activity/feed?limit=5", headers=headers)
print(f"Status: {response.status_code}")
data = response.json()
if isinstance(data, list):
    print(f"Returned {len(data)} activities")
    for i, item in enumerate(data[:3]):
        print(f"\nActivity {i+1}:")
        print(f"  Type: {item.get('action_type')}")
        print(f"  Name: {item.get('client_name')}")
        print(f"  Phone: {item.get('client_phone')}")
        print(f"  Time: {item.get('timestamp')}")
else:
    print(json.dumps(data, indent=2))

print("\n=== Test 3: Skills ===")
response = requests.get(f"{API_URL}/api/v1/ai-receptionist/dashboard/skills", headers=headers)
print(f"Status: {response.status_code}")
data = response.json()
if isinstance(data, list):
    print(f"Returned {len(data)} skills")
    for skill in data[:5]:
        print(f"  - {skill.get('skill_name')}: {skill.get('accuracy_score', 0)*100:.1f}%")
else:
    print(json.dumps(data, indent=2))
