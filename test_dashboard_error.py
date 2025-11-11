#!/usr/bin/env python3
"""
Test dashboard with error details
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

print("Testing Dashboard with error capture...")
print("="*80)
response = requests.get(f"{API_BASE_URL}/api/v1/dashboard", headers=headers)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    if "error" in data:
        print("\nERROR CAPTURED:")
        print(f"Type: {data.get('type')}")
        print(f"Error: {data.get('error')}")
        print(f"\nTraceback:")
        print(data.get('traceback'))
    else:
        print("\n✓ Dashboard working!")
        print(f"Keys returned: {list(data.keys())}")
else:
    print(f"HTTP Error: {response.text}")
