#!/usr/bin/env python3
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

print("Testing Dashboard with detailed error...")
response = requests.get(f"{API_BASE_URL}/api/v1/dashboard", headers=headers)
print(f"Status: {response.status_code}")
print(f"Headers: {response.headers}")
print(f"Content: {response.text[:1000]}")

# Try to get more error details from other endpoints that work
print("\n\nChecking leads with different stages...")
response = requests.get(f"{API_BASE_URL}/api/v1/leads/", headers=headers)
if response.status_code == 200:
    leads = response.json()
    stages = {}
    for lead in leads:
        stage = lead.get('stage', 'None')
        stages[stage] = stages.get(stage, 0) + 1
    print(f"Lead stages: {stages}")

print("\n\nChecking loans with stages...")
response = requests.get(f"{API_BASE_URL}/api/v1/loans/", headers=headers)
if response.status_code == 200:
    loans = response.json()
    stages = {}
    for loan in loans:
        stage = loan.get('stage', 'None')
        stages[stage] = stages.get(stage, 0) + 1
    print(f"Loan stages: {stages}")

    # Check funded loans have funded_date
    funded = [l for l in loans if l.get('stage') == 'Funded']
    with_date = [l for l in funded if l.get('funded_date')]
    print(f"\nFunded loans: {len(funded)}")
    print(f"With funded_date: {len(with_date)}")
    if with_date:
        print(f"Sample funded_date: {with_date[0]['funded_date']}")
