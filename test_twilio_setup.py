#!/usr/bin/env python3
"""Test Twilio setup and send a test SMS"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/Users/timothyloss/my-project/mortgage-crm/backend/.env')

print("="*60)
print("TWILIO CONFIGURATION TEST")
print("="*60)

# Check environment variables
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
api_key_sid = os.getenv("TWILIO_API_KEY_SID")
api_key_secret = os.getenv("TWILIO_API_KEY_SECRET")
from_number = os.getenv("TWILIO_PHONE_NUMBER")

print(f"\n✓ Account SID: {account_sid[:10]}... (length: {len(account_sid) if account_sid else 0})")
print(f"✓ Auth Token: {auth_token[:10] if auth_token else 'Not set'}... (length: {len(auth_token) if auth_token else 0})")
print(f"✓ API Key SID: {api_key_sid[:10] if api_key_sid else 'Not set'}... (length: {len(api_key_sid) if api_key_sid else 0})")
print(f"✓ API Secret: {api_key_secret[:10] if api_key_secret else 'Not set'}... (length: {len(api_key_secret) if api_key_secret else 0})")
print(f"✓ Phone Number: {from_number}")

# Check if we have minimum credentials
has_basic_creds = account_sid and from_number and (auth_token or (api_key_sid and api_key_secret))

if not has_basic_creds:
    print("\n❌ Missing required credentials!")
    print("Required: Account SID, Phone Number, and (Auth Token OR API Key)")
    sys.exit(1)

print("\n✅ All required credentials are present!")

# Try to initialize Twilio client
print("\n" + "="*60)
print("TESTING TWILIO CONNECTION")
print("="*60)

try:
    from twilio.rest import Client

    # Try with API Key first (more secure)
    if api_key_sid and api_key_secret:
        print("\nUsing API Key authentication...")
        client = Client(api_key_sid, api_key_secret, account_sid)
    else:
        print("\nUsing Auth Token authentication...")
        client = Client(account_sid, auth_token)

    # Test connection by fetching account info
    account = client.api.accounts(account_sid).fetch()
    print(f"✅ Successfully connected to Twilio!")
    print(f"   Account Status: {account.status}")
    print(f"   Account Name: {account.friendly_name}")

    # Get phone number details
    print(f"\n✅ Checking phone number {from_number}...")
    incoming_numbers = client.incoming_phone_numbers.list(phone_number=from_number, limit=1)

    if incoming_numbers:
        number = incoming_numbers[0]
        print(f"   Phone Number: {number.phone_number}")
        print(f"   Friendly Name: {number.friendly_name}")
        print(f"   SMS Enabled: {number.capabilities.get('sms', False)}")
    else:
        print(f"   ⚠️  Phone number {from_number} not found in your account")
        print("   This might be a trial number or not yet activated")

except Exception as e:
    print(f"\n❌ Error connecting to Twilio: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("SEND TEST SMS?")
print("="*60)
print("Would you like to send a test SMS to verify everything works?")
print("Enter a phone number to send to (format: +1234567890)")
print("Or press Enter to skip")

test_number = input("\nPhone number: ").strip()

if test_number:
    if not test_number.startswith('+'):
        test_number = f"+1{test_number}"

    try:
        print(f"\nSending test SMS to {test_number}...")
        message = client.messages.create(
            body="Test message from your Mortgage CRM! 🎉 Your Twilio integration is working!",
            from_=from_number,
            to=test_number
        )
        print(f"✅ SMS sent successfully!")
        print(f"   Message SID: {message.sid}")
        print(f"   Status: {message.status}")
        print(f"   To: {message.to}")
    except Exception as e:
        print(f"❌ Failed to send SMS: {e}")
else:
    print("\nSkipping test SMS.")

print("\n" + "="*60)
print("✅ TWILIO SETUP COMPLETE!")
print("="*60)
print("Your Twilio integration is ready to use in the CRM.")
