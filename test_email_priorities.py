#!/usr/bin/env python3
"""Test sending daily priorities email"""

import os
import requests
import json
import sys

# API endpoint - set AUTH_TOKEN and TARGET_EMAIL via environment variables
API_URL = os.environ.get("API_URL", "https://app.perenniaai.com/api/v1/ai/send-daily-priorities-email")
TOKEN = os.environ.get("AUTH_TOKEN", "")

# Target email
TARGET_EMAIL = os.environ.get("TARGET_EMAIL", "")

print("="* 80)
print("Testing Daily Priorities Email Functionality")
print("="* 80)
print(f"\nTarget Email: {TARGET_EMAIL}")
print(f"API Endpoint: {API_URL}\n")

# Test the endpoint
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "email_address": TARGET_EMAIL
}

print("Sending request...")
try:
    response = requests.post(API_URL, json=payload, headers=headers, timeout=30)

    print(f"Status Code: {response.status_code}")
    print(f"\nResponse:")
    print(json.dumps(response.json(), indent=2))

    if response.status_code == 200:
        print("\n✓ SUCCESS: Email sent successfully!")
        print(f"Check your inbox at {TARGET_EMAIL}")
    else:
        print(f"\n✗ FAILED: {response.json().get('detail', 'Unknown error')}")
        sys.exit(1)

except requests.exceptions.ConnectionError:
    print("\n✗ ERROR: Could not connect to API")
    print("Make sure the backend server is running")
    sys.exit(1)
except requests.exceptions.Timeout:
    print("\n✗ ERROR: Request timed out")
    sys.exit(1)
except Exception as e:
    print(f"\n✗ ERROR: {str(e)}")
    sys.exit(1)
