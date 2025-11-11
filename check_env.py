#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, '/Users/timothyloss/my-project/mortgage-crm/backend')

# Check environment variables directly
print("Direct OS environment check:")
print(f"TWILIO_ACCOUNT_SID: {os.getenv('TWILIO_ACCOUNT_SID', 'NOT SET')}")
print(f"TWILIO_AUTH_TOKEN: {os.getenv('TWILIO_AUTH_TOKEN', 'NOT SET')[:10]}...")
print(f"TWILIO_PHONE_NUMBER: {os.getenv('TWILIO_PHONE_NUMBER', 'NOT SET')}")

# Load with dotenv
from dotenv import load_dotenv
load_dotenv('/Users/timothyloss/my-project/mortgage-crm/backend/.env')

print("\nAfter loading .env:")
print(f"TWILIO_ACCOUNT_SID: {os.getenv('TWILIO_ACCOUNT_SID', 'NOT SET')}")
print(f"TWILIO_AUTH_TOKEN: {os.getenv('TWILIO_AUTH_TOKEN', 'NOT SET')[:10]}...")
print(f"TWILIO_PHONE_NUMBER: {os.getenv('TWILIO_PHONE_NUMBER', 'NOT SET')}")

# Try to import the service
print("\nTrying to import twilio_service...")
try:
    from integrations.twilio_service import sms_client
    print(f"SMS Client enabled: {sms_client.enabled}")
    print(f"SMS Client account_sid: {sms_client.account_sid[:10] if sms_client.account_sid else 'None'}...")
    print(f"SMS Client from_number: {sms_client.from_number}")
except Exception as e:
    print(f"Error: {e}")
