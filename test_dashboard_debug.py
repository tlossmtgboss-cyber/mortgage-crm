#!/usr/bin/env python3
import requests

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get token
response = requests.post(
    f"{API_BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("Testing dashboard-debug endpoint...")
response = requests.get(f"{API_BASE_URL}/api/v1/dashboard-debug", headers=headers)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print(f"\nStatus: {data.get('status')}")
    print(f"Results: {data.get('results')}")
    if data.get('status') == 'error':
        print(f"\n❌ Error: {data.get('error')}")
        print(f"Type: {data.get('type')}")
        print(f"\nTraceback:")
        print(data.get('traceback'))
else:
    print(f"Response: {response.text}")
