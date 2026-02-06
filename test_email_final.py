#!/usr/bin/env python3
"""Final email test with detailed logging"""

import os
import requests
import json

API_URL = os.environ.get("API_URL", "https://app.perenniaai.com/api/v1/ai/send-daily-priorities-email")
TOKEN = os.environ.get("AUTH_TOKEN", "")
TARGET_EMAIL = os.environ.get("TARGET_EMAIL", "")

print("="*80)
print("FINAL EMAIL TEST")
print("="*80)
print(f"Target: {TARGET_EMAIL}")
print(f"API: {API_URL}")
print()

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "email_address": TARGET_EMAIL
}

print("Payload:")
print(json.dumps(payload, indent=2))
print()

print("Sending request...")
try:
    response = requests.post(API_URL, json=payload, headers=headers, timeout=60)

    print(f"Status: {response.status_code}")
    print()

    if response.status_code == 200:
        data = response.json()
        print("✅ SUCCESS!")
        print(json.dumps(data, indent=2))
        print()
        print(f"📧 Email sent to: {data.get('email')}")
        print(f"📊 Items included: {data.get('items_count')}")
        print()
        print("Check your inbox at tloss@cmgfi.com!")
    else:
        print(f"❌ ERROR: {response.status_code}")
        print("Response:")
        print(response.text)

        try:
            error_data = response.json()
            print()
            print("Error details:")
            print(json.dumps(error_data, indent=2))
        except:
            pass

except Exception as e:
    print(f"❌ EXCEPTION: {e}")
    import traceback
    traceback.print_exc()
