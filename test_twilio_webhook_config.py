#!/usr/bin/env python3
"""
Test if Twilio webhook is configured correctly
This will help diagnose why calls hang up immediately
"""
import subprocess
import json
import requests

print("=" * 80)
print("DIAGNOSING TWILIO WEBHOOK ISSUE")
print("=" * 80)

# Get Twilio credentials from Railway
print("\n1. Getting Twilio credentials...")
result = subprocess.run(
    ['railway', 'variables', '--json'],
    capture_output=True,
    text=True
)

vars_data = json.loads(result.stdout)
account_sid = vars_data.get('TWILIO_ACCOUNT_SID')
auth_token = vars_data.get('TWILIO_AUTH_TOKEN')
phone_number = vars_data.get('TWILIO_PHONE_NUMBER')

print(f"   Account SID: {account_sid}")
print(f"   Phone Number: {phone_number}")

# Check if we can query Twilio API
print("\n2. Checking Twilio phone number configuration...")
try:
    from twilio.rest import Client
    client = Client(account_sid, auth_token)

    # Get phone number details
    incoming_numbers = client.incoming_phone_numbers.list(phone_number=phone_number)

    if incoming_numbers:
        number = incoming_numbers[0]
        print(f"   ✅ Found phone number: {number.phone_number}")
        print(f"\n   Current Voice Webhook Configuration:")
        print(f"   Voice URL: {number.voice_url}")
        print(f"   Voice Method: {number.voice_method}")
        print(f"   Status Callback: {number.status_callback}")

        expected_url = "https://api.perenniaai.com/api/v1/voice/incoming"

        if number.voice_url == expected_url:
            print(f"\n   ✅ Webhook URL is CORRECT")
        elif number.voice_url:
            print(f"\n   ❌ Webhook URL is WRONG!")
            print(f"   Expected: {expected_url}")
            print(f"   Current:  {number.voice_url}")
            print(f"\n   This is why calls hang up immediately!")
        else:
            print(f"\n   ❌ NO WEBHOOK URL CONFIGURED!")
            print(f"   This is why you hear 'application error'")

        # Check if we can update it programmatically
        print(f"\n3. Attempting to update webhook URL...")
        try:
            number.update(
                voice_url=expected_url,
                voice_method='POST'
            )
            print(f"   ✅ Webhook URL updated successfully!")
            print(f"   New URL: {expected_url}")
            print(f"\n   Try calling the number again now!")
        except Exception as e:
            print(f"   ⚠️  Could not update automatically: {e}")
            print(f"\n   Please update manually in Twilio Console:")
            print(f"   https://console.twilio.com/us1/develop/phone-numbers/manage/incoming")
    else:
        print(f"   ❌ Phone number not found in Twilio account")

except ImportError:
    print("   ⚠️  Twilio library not available")
    print("   Install with: pip install twilio")
except Exception as e:
    print(f"   ❌ Error checking Twilio: {e}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("""
If the webhook URL was WRONG or MISSING:
- That's why the call hangs up immediately
- Twilio doesn't know where to send the call
- This script tried to fix it automatically

Next steps:
1. If update succeeded: Call the number again to test
2. If update failed: Update manually at:
   https://console.twilio.com/us1/develop/phone-numbers/manage/incoming

   Set Voice URL to:
   https://api.perenniaai.com/api/v1/voice/incoming
   Method: POST

3. After updating, call the number
4. You should hear: "Thank you for calling CMG Home Loans..."
""")
