#!/usr/bin/env python3
"""Test incoming call webhook endpoint"""
import requests
import time

API_URL = "https://api.perenniaai.com"

print("=" * 70)
print("TEST: Incoming Call Webhook")
print("=" * 70)

# Test 1: Check if endpoint is reachable
print("\n1. Testing /api/v1/voice/incoming endpoint...")
test_data = {
    "From": "+15555551234",
    "To": "+18326482297",
    "CallSid": f"TEST_CALL_{int(time.time())}",
    "CallStatus": "ringing"
}

try:
    response = requests.post(
        f"{API_URL}/api/v1/voice/incoming",
        data=test_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10
    )

    print(f"   Status Code: {response.status_code}")
    print(f"   Content-Type: {response.headers.get('content-type')}")

    if response.status_code == 200:
        print(f"   ✅ SUCCESS - Webhook is working!")
        print(f"\n   Response (first 500 chars):")
        print(f"   {response.text[:500]}")

        # Check if it's valid TwiML
        if '<?xml' in response.text or '<Response>' in response.text:
            print(f"\n   ✅ Valid TwiML response")
        else:
            print(f"\n   ⚠️  Response is not TwiML")
    else:
        print(f"   ❌ ERROR - Status {response.status_code}")
        print(f"   Response: {response.text[:500]}")

except requests.exceptions.Timeout:
    print(f"   ❌ TIMEOUT - Webhook took too long to respond")
    print(f"   Twilio requires response in < 10 seconds")
except requests.exceptions.ConnectionError as e:
    print(f"   ❌ CONNECTION ERROR - Cannot reach webhook")
    print(f"   Error: {e}")
except Exception as e:
    print(f"   ❌ ERROR - {e}")

# Test 2: Check Railway deployment
print("\n2. Checking if Railway service is running...")
try:
    health_response = requests.get(f"{API_URL}/docs", timeout=5)
    if health_response.status_code == 200:
        print(f"   ✅ Backend is running")
    else:
        print(f"   ⚠️  Unexpected status: {health_response.status_code}")
except Exception as e:
    print(f"   ❌ Backend not reachable: {e}")

print("\n" + "=" * 70)
print("DIAGNOSIS")
print("=" * 70)

print("""
If the webhook test succeeded:
  - The endpoint is working correctly
  - The issue is likely with Twilio webhook configuration

If the webhook test failed:
  - Check Railway deployment status
  - Check if voice_routes.py is included in main.py
  - Check environment variables (OPENAI_API_KEY, etc.)

To fix Twilio configuration:
1. Go to: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
2. Click on +1 (832) 648-2297
3. Set 'A CALL COMES IN' webhook to:
   https://api.perenniaai.com/api/v1/voice/incoming
4. Method: HTTP POST
5. Save
""")
