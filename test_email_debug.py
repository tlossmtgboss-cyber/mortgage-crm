#!/usr/bin/env python3
"""Debug email sending"""

import os
import requests

API_URL = os.environ.get("API_URL", "https://app.perenniaai.com/api/v1/ai/send-daily-priorities-email")
TOKEN = os.environ.get("AUTH_TOKEN", "")
TARGET_EMAIL = os.environ.get("TARGET_EMAIL", "")

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
