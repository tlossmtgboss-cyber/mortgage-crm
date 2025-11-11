#!/usr/bin/env python3
"""Test Twilio authentication methods"""
import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv('/Users/timothyloss/my-project/mortgage-crm/backend/.env')

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
api_key_sid = os.getenv("TWILIO_API_KEY_SID")
api_key_secret = os.getenv("TWILIO_API_KEY_SECRET")

print("Testing Twilio Authentication Methods")
print("="*60)

# Test 1: Auth Token
print("\nTest 1: Using Auth Token...")
try:
    client = Client(account_sid, auth_token)
    account = client.api.accounts(account_sid).fetch()
    print(f"✅ AUTH TOKEN WORKS!")
    print(f"   Account: {account.friendly_name}")
    print(f"   Status: {account.status}")
except Exception as e:
    print(f"❌ Auth Token failed: {e}")

# Test 2: API Key
print("\nTest 2: Using API Key...")
try:
    client = Client(api_key_sid, api_key_secret, account_sid)
    account = client.api.accounts(account_sid).fetch()
    print(f"✅ API KEY WORKS!")
    print(f"   Account: {account.friendly_name}")
    print(f"   Status: {account.status}")
except Exception as e:
    print(f"❌ API Key failed: {e}")

print("\n" + "="*60)
