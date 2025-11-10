#!/usr/bin/env python3
import requests

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

print("Testing backend health...")

# Try token endpoint
print("\n1. Testing /token endpoint...")
response = requests.post(
    f"{API_BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
print(f"Status: {response.status_code}")
print(f"Response: {response.text[:500]}")

# Try a simple endpoint
print("\n2. Testing /api/v1/portfolio/stats...")
if response.status_code == 200:
    token = response.json().get("access_token")
    if token:
        headers = {"Authorization": f"Bearer {token}"}
        response2 = requests.get(f"{API_BASE_URL}/api/v1/portfolio/stats", headers=headers)
        print(f"Status: {response2.status_code}")
        print(f"Response: {response2.text[:500]}")
