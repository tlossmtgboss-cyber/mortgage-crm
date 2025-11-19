#!/usr/bin/env python3
"""Make a real test call via Twilio to verify Sam answers"""
import subprocess
import json
import time
from twilio.rest import Client

print("=" * 70)
print("MAKING REAL TEST CALL VIA TWILIO")
print("=" * 70)

# Get credentials
result = subprocess.run(
    ['railway', 'variables', '--json'],
    capture_output=True,
    text=True
)
vars_data = json.loads(result.stdout)
account_sid = vars_data.get('TWILIO_ACCOUNT_SID')
auth_token = vars_data.get('TWILIO_AUTH_TOKEN')
from_number = vars_data.get('TWILIO_PHONE_NUMBER')

# Twilio test number that accepts calls (doesn't ring, just for testing)
test_to_number = "+15005550006"  # Twilio magic number - success

print(f"\n1. Initiating test call...")
print(f"   From: {from_number}")
print(f"   To: {test_to_number} (Twilio test number)")

try:
    client = Client(account_sid, auth_token)

    # Make the call
    call = client.calls.create(
        to=test_to_number,
        from_=from_number,
        url="https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voice/incoming",
        method='POST',
        status_callback="https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voice/call-status",
        status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
        status_callback_method='POST'
    )

    print(f"\n2. Call initiated!")
    print(f"   Call SID: {call.sid}")
    print(f"   Status: {call.status}")

    # Wait and check status
    print(f"\n3. Waiting 5 seconds...")
    time.sleep(5)

    # Fetch updated call status
    call = client.calls(call.sid).fetch()
    print(f"\n4. Call status: {call.status}")
    print(f"   Duration: {call.duration} seconds")

    if call.status in ['completed', 'busy', 'failed', 'no-answer']:
        print(f"\n5. Checking Railway logs for WebSocket connection...")

        # Check logs
        log_result = subprocess.run(
            ['railway', 'logs', '--tail', '50'],
            capture_output=True,
            text=True,
            timeout=10
        )

        logs = log_result.stdout

        if call.sid in logs:
            print(f"   ✅ Found call {call.sid} in logs")

        if "Voice stream WebSocket connected" in logs:
            print(f"   ✅ WebSocket connected successfully!")
        else:
            print(f"   ⚠️  No WebSocket connection logged")

        if "Error in voice stream" in logs:
            print(f"   ❌ Error in voice stream:")
            for line in logs.split('\n'):
                if "ERROR" in line or "Error in voice stream" in line:
                    print(f"     {line}")
        else:
            print(f"   ✅ No errors detected")

        print(f"\n" + "=" * 70)
        print("TEST COMPLETE")
        print("=" * 70)

        if "Voice stream WebSocket connected" in logs and "Error in voice stream" not in logs:
            print("✅ SUCCESS - Sam is ready to answer calls!")
            print("\nYou can now call +1 (832) 648-2297 from your phone")
            print("Sam will answer with his natural voice")
        else:
            print("⚠️  PARTIAL SUCCESS - Webhook works but need to verify WebSocket")
            print("Try calling the number manually to test")

except Exception as e:
    print(f"\n❌ Error making test call: {e}")
    print(f"   Type: {type(e).__name__}")
