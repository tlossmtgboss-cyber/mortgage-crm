#!/usr/bin/env python3
"""
Send Hello SMS to User's Phone
"""
import requests
import json

BACKEND_URL = "https://app.perenniaai.com"

print("="*70)
print("  📱 SENDING TEST SMS")
print("="*70)

# Login
print("\n🔐 Logging in...")
login_response = requests.post(
    f"{BACKEND_URL}/token",
    data={"username": "admin@perenniaai.com", "password": "demo123"},
    timeout=10
)

if login_response.status_code != 200:
    print(f"❌ Login failed: {login_response.status_code}")
    exit(1)

token = login_response.json()["access_token"]
print("✅ Logged in successfully")

# Send SMS
print("\n📤 Sending SMS...")
print("   To: +18438344997")
print("   Message: Hello!")

response = requests.post(
    f"{BACKEND_URL}/api/v1/sms/send",
    json={
        "to_number": "+18438344997",
        "message": "Hello!"
    },
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    },
    timeout=15
)

print(f"\n📊 Response Status: {response.status_code}")
print("\n📄 Full Response:")
print(json.dumps(response.json(), indent=2))

data = response.json()

if response.status_code == 201:
    if data.get('status') == 'sent' or data.get('twilio_sid'):
        print("\n" + "="*70)
        print("  ✅ SUCCESS! SMS SENT!")
        print("="*70)
        print(f"\n✨ Message delivered to +18438344997")
        print(f"   Twilio SID: {data.get('twilio_sid')}")
        print(f"   Status: {data.get('status')}")
        print(f"\n📬 Check your phone for the message!")
    else:
        print("\n" + "="*70)
        print("  ⚠️  SMS SAVED BUT NOT SENT")
        print("="*70)
        print(f"\n❌ Status: {data.get('status')}")
        print(f"   From Number: {data.get('from_number')}")
        print(f"\n🔍 Issue: Twilio credentials not properly configured on Railway")
        print("\n📋 To fix:")
        print("   1. Go to Railway dashboard")
        print("   2. Select backend service")
        print("   3. Go to Variables tab")
        print("   4. Verify these variables:")
        print("      - TWILIO_ACCOUNT_SID (starts with AC)")
        print("      - TWILIO_AUTH_TOKEN (32 characters)")
        print("      - TWILIO_PHONE_NUMBER (format: +15551234567)")
        print("   5. Restart backend if needed")
else:
    print(f"\n❌ Failed with status {response.status_code}")
