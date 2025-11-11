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
print(f"   ✓ Token obtained: {token[:20]}...")

# Test Dashboard endpoint
print("\n2. Testing Dashboard endpoint...")
response = requests.get(f"{API_BASE_URL}/api/v1/dashboard", headers=headers)
print(f"   Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print(f"\n   ✅ SUCCESS! Dashboard is working!")
    print(f"\n   Response keys: {list(data.keys())}")
    if 'pipeline_stats' in data:
        print(f"   Pipeline stats: {len(data['pipeline_stats'])} stages")
    if 'lead_metrics' in data:
        print(f"   Lead metrics: {data['lead_metrics']}")
    if 'referral_stats' in data:
        print(f"   Referral partners: {len(data['referral_stats'].get('top_partners', []))} partners")
else:
    print(f"\n   ❌ FAILED with status {response.status_code}")
    print(f"   Response: {response.text[:500]}")
