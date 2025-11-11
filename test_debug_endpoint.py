#!/usr/bin/env python3
"""
Test dashboard-debug endpoint
"""
import requests
import json

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get token
response = requests.post(
    f"{API_BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("Testing Dashboard-Debug endpoint...")
print("="*80)
response = requests.get(f"{API_BASE_URL}/api/v1/dashboard-debug", headers=headers)
print(f"Status: {response.status_code}\n")

if response.status_code == 200:
    data = response.json()
    print(f"Status: {data.get('status')}")
    print(f"\nResults:")
    for key, value in data.get('results', {}).items():
        print(f"  {key}: {value}")

    if data.get('status') == 'error':
        print(f"\nError Type: {data.get('type')}")
        print(f"Error Message: {data.get('error')}")
        print(f"\nTraceback:")
        print(data.get('traceback'))
else:
    print(f"HTTP Error: {response.text}")
