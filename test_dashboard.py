#!/usr/bin/env python3
import requests

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get token
response = requests.post(
    f"{API_BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
token = response.json()["access_token"]
print(f"✓ Got token")

headers = {"Authorization": f"Bearer {token}"}

# Test dashboard
print("\nTesting Dashboard...")
response = requests.get(f"{API_BASE_URL}/api/v1/dashboard", headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print("Dashboard data:", data)
else:
    print("Error:", response.text)

# Test pipeline
print("\nTesting Pipeline...")
response = requests.get(f"{API_BASE_URL}/api/v1/analytics/pipeline", headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"Pipeline type: {type(data)}")
    if isinstance(data, list) and len(data) > 0:
        print(f"First item: {data[0]}")
    elif isinstance(data, dict):
        print(f"Keys: {data.keys()}")
else:
    print("Error:", response.text)

# Test leads count
print("\nTesting Leads...")
response = requests.get(f"{API_BASE_URL}/api/v1/leads/", headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    leads = response.json()
    print(f"Total leads: {len(leads)}")

# Test loans count
print("\nTesting Loans...")
response = requests.get(f"{API_BASE_URL}/api/v1/loans/", headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    loans = response.json()
    print(f"Total loans: {len(loans)}")
    funded = [l for l in loans if l.get('stage') == 'Funded']
    print(f"Funded loans: {len(funded)}")

# Test portfolio
print("\nTesting Portfolio...")
response = requests.get(f"{API_BASE_URL}/api/v1/portfolio/stats", headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    stats = response.json()
    print(f"Portfolio stats: {stats}")
