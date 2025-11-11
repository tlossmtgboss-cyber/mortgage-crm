#!/usr/bin/env python3
"""
Check SMS sending with detailed response
"""
import requests
import json

BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Login
login_response = requests.post(
    f"{BACKEND_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
token = login_response.json()["access_token"]

# Send SMS with full response
response = requests.post(
    f"{BACKEND_URL}/api/v1/sms/send",
    json={
        "to_number": "+18438344997",
        "message": "Hello! Test from Mortgage CRM 📱"
    },
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
)

print(f"Status Code: {response.status_code}")
print(f"\nFull Response:")
print(json.dumps(response.json(), indent=2))

# Check integration status
print("\n" + "="*60)
print("CHECKING INTEGRATION STATUS")
print("="*60)

status_response = requests.get(
    f"{BACKEND_URL}/api/v1/integrations/status",
    headers={"Authorization": f"Bearer {token}"}
)

if status_response.ok:
    status_data = status_response.json()
    print(json.dumps(status_data, indent=2))
