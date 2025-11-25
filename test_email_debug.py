#!/usr/bin/env python3
"""Debug email sending"""

import requests

API_URL = "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/ai/send-daily-priorities-email"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZW1vQGV4YW1wbGUuY29tIiwiZXhwIjoxNzY0MDE2OTcxfQ.DvKjpG2FOrpR_g8XHZ1ETk7bEFKRaABHW0D25csrdxA"
TARGET_EMAIL = "tloss@cmgfi.com"

print("Testing email endpoint...")

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "email_address": TARGET_EMAIL
}

response = requests.post(API_URL, json=payload, headers=headers, timeout=30)

print(f"Status Code: {response.status_code}")
print(f"Headers: {dict(response.headers)}")
print(f"\nRaw Response Text:")
print(response.text)
print("\n" + "="*80)

try:
    data = response.json()
    print("JSON Response:")
    print(data)
except:
    print("Response is not JSON")
