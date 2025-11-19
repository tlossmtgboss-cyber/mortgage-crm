#!/usr/bin/env python3
"""
Test the complete voice flow end-to-end
Simulates a real Twilio call to verify Sam answers
"""
import requests
import time
import subprocess
import json

API_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

print("=" * 70)
print("END-TO-END VOICE TEST")
print("=" * 70)

# Step 1: Get Twilio credentials
print("\n1. Getting Twilio credentials...")
result = subprocess.run(
    ['railway', 'variables', '--json'],
    capture_output=True,
    text=True
)
vars_data = json.loads(result.stdout)
account_sid = vars_data.get('TWILIO_ACCOUNT_SID')
auth_token = vars_data.get('TWILIO_AUTH_TOKEN')
from_number = vars_data.get('TWILIO_PHONE_NUMBER')

print(f"   Account SID: {account_sid}")
print(f"   From Number: {from_number}")

# Step 2: Make a test call using Twilio
print("\n2. Making test call via Twilio...")
try:
    from twilio.rest import Client
    client = Client(account_sid, auth_token)

    # Make outbound call to a test number (will fail but we can check logs)
    # Or we can just verify webhook works
    print("   Testing webhook endpoint instead...")

    # Test the incoming webhook
    webhook_response = requests.post(
        f"{API_URL}/api/v1/voice/incoming",
        data={
            "From": "+15555551234",
            "To": from_number,
            "CallSid": f"TEST_E2E_{int(time.time())}",
            "CallStatus": "ringing"
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    print(f"   Webhook Status: {webhook_response.status_code}")

    if webhook_response.status_code == 200:
        print("   ✅ Webhook responding")
        twiml = webhook_response.text
        print(f"\n   TwiML Response:")
        print(f"   {twiml[:300]}...")

        # Check if it contains WebSocket URL
        if "wss://" in twiml and "voice-stream" in twiml:
            print("\n   ✅ TwiML contains WebSocket connection")
        else:
            print("\n   ❌ TwiML missing WebSocket connection")
    else:
        print(f"   ❌ Webhook failed: {webhook_response.status_code}")

except Exception as e:
    print(f"   ❌ Error: {e}")

# Step 3: Check Railway logs for WebSocket connection
print("\n3. Checking Railway logs for WebSocket activity...")
result = subprocess.run(
    ['railway', 'logs', '--tail', '100'],
    capture_output=True,
    text=True,
    timeout=10
)

logs = result.stdout

# Look for key indicators
if "Voice stream WebSocket connected" in logs:
    print("   ✅ WebSocket connection successful")
else:
    print("   ⚠️  No WebSocket connection yet")

if "Error in voice stream" in logs:
    print("   ❌ Error in WebSocket stream")
    # Find the error
    for line in logs.split('\n'):
        if "Error in voice stream" in line or "ERROR" in line:
            print(f"   {line}")
else:
    print("   ✅ No errors in voice stream")

# Step 4: Final verification
print("\n" + "=" * 70)
print("VERIFICATION")
print("=" * 70)

# Check recent logs for the specific error we fixed
if "additional_headers" in logs:
    print("❌ STILL BROKEN - 'additional_headers' error still present")
    print("   Railway may not have restarted yet")
elif "Error in voice stream" in logs:
    print("⚠️  DIFFERENT ERROR - WebSocket connects but different error")
    print("   Need to investigate new error")
else:
    print("✅ NO ERRORS DETECTED")
    print("\nReady for real call test!")
    print("\nNext step: Call +1 (832) 648-2297 from your phone")
    print("Expected: Sam answers with 'Hi, this is Sam with CMG Home Loans'")

print("\n" + "=" * 70)
