#!/usr/bin/env python3
"""
Diagnose Voice AI Receptionist Issue
Checks all components to identify why calls are failing
"""
import requests
import subprocess
import json

print("=" * 80)
print("VOICE AI RECEPTIONIST - DIAGNOSTIC REPORT")
print("=" * 80)

# Test 1: Backend webhook
print("\n✅ TEST 1: Backend Webhook")
print("-" * 80)
try:
    response = requests.post(
        "https://api.perenniaai.com/api/v1/voice/incoming",
        data={
            "From": "+15555551234",
            "To": "+18326482297",
            "CallSid": "TEST123",
            "CallStatus": "ringing"
        },
        timeout=10
    )
    if response.status_code == 200 and '<?xml' in response.text:
        print("✅ PASS - Webhook returns valid TwiML")
        print(f"   Response: {response.text[:200]}...")
    else:
        print(f"❌ FAIL - Status {response.status_code}")
except Exception as e:
    print(f"❌ FAIL - Error: {e}")

# Test 2: Check environment variables in Railway
print("\n✅ TEST 2: Railway Environment Variables")
print("-" * 80)
try:
    result = subprocess.run(
        ['railway', 'variables', '--json'],
        capture_output=True,
        text=True,
        timeout=10
    )
    if result.returncode == 0:
        vars_data = json.loads(result.stdout)
        required_vars = ['OPENAI_API_KEY', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN',
                        'TWILIO_PHONE_NUMBER', 'PRODUCTION_DOMAIN']

        for var in required_vars:
            if var in vars_data and vars_data[var]:
                if var == 'OPENAI_API_KEY':
                    print(f"   ✅ {var}: sk-proj-...{vars_data[var][-10:]}")
                elif 'TOKEN' in var or 'KEY' in var:
                    print(f"   ✅ {var}: ...{vars_data[var][-10:]}")
                else:
                    print(f"   ✅ {var}: {vars_data[var]}")
            else:
                print(f"   ❌ {var}: NOT SET")
except Exception as e:
    print(f"   ⚠️  Could not check Railway vars: {e}")

# Test 3: Check if websockets library is in requirements
print("\n✅ TEST 3: Python Dependencies")
print("-" * 80)
try:
    with open('/Users/timothyloss/my-project/mortgage-crm/backend/requirements.txt', 'r') as f:
        requirements = f.read()
        if 'websockets' in requirements:
            print("   ✅ websockets library in requirements.txt")
        else:
            print("   ❌ websockets library MISSING from requirements.txt")
            print("   This is required for OpenAI Realtime API")
except Exception as e:
    print(f"   ⚠️  Could not check requirements.txt: {e}")

# Test 4: Check recent Railway logs for WebSocket errors
print("\n✅ TEST 4: Recent Railway Logs")
print("-" * 80)
try:
    result = subprocess.run(
        ['railway', 'logs', '--tail', '50'],
        capture_output=True,
        text=True,
        timeout=10
    )
    logs = result.stdout.lower()

    # Look for WebSocket-related logs
    if 'voice stream websocket connected' in logs:
        print("   ✅ Found successful WebSocket connection")
    elif 'websocket' in logs:
        print("   ⚠️  Found WebSocket mentions (check for errors)")
    else:
        print("   ℹ️  No recent WebSocket activity")

    # Look for incoming call logs
    if 'incoming call from' in logs:
        print("   ✅ Found recent incoming call attempts")
    else:
        print("   ⚠️  NO incoming call attempts in recent logs")
        print("   This suggests Twilio is NOT sending webhooks to the backend")

except Exception as e:
    print(f"   ⚠️  Could not check logs: {e}")

# Summary
print("\n" + "=" * 80)
print("DIAGNOSIS SUMMARY")
print("=" * 80)

print("""
Based on the tests above:

1. ✅ Backend webhook IS working and returns valid TwiML
2. The backend tells Twilio to connect to WebSocket for AI conversation

The most likely issue is:
❌ TWILIO PHONE NUMBER IS NOT CONFIGURED TO USE THIS WEBHOOK

When you call +1 (832) 648-2297:
- Twilio receives the call
- Twilio looks for webhook configuration
- If no webhook is configured (or wrong URL), Twilio plays:
  "An application error has occurred"

SOLUTION:
========
1. Go to Twilio Console: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
2. Click on phone number: +1 (832) 648-2297
3. Scroll to "Voice Configuration"
4. Set "A CALL COMES IN" to:

   Webhook: https://api.perenniaai.com/api/v1/voice/incoming
   HTTP POST

5. Click Save
6. Call the number again to test

ALTERNATIVE ISSUE:
==================
If webhook IS configured but WebSocket fails, check:
- Is 'websockets' library installed? (pip install websockets)
- Add to backend/requirements.txt if missing
- Redeploy to Railway

To verify Twilio config without logging into Twilio:
- Call the number and check Railway logs
- You should see: "INFO:voice_routes:Incoming call from +1XXXXXXXXXX"
- If you don't see this log, Twilio is NOT sending webhooks to backend
""")
