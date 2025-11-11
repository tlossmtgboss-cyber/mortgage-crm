#!/usr/bin/env python3
"""
Direct SMS Test using Twilio SDK
Sends SMS directly via Twilio (not through backend API)
"""
import os
import sys

# Load environment variables from backend .env
from pathlib import Path
env_file = Path(__file__).parent / "backend" / ".env"

if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# Now import and use Twilio
try:
    from twilio.rest import Client
    print("✅ Twilio SDK installed")
except ImportError:
    print("❌ Twilio SDK not installed")
    print("\nInstalling twilio package...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "twilio", "-q"])
    from twilio.rest import Client
    print("✅ Twilio SDK installed successfully")

def send_sms():
    """Send SMS using Twilio SDK"""
    print("\n" + "="*70)
    print("  📱 SENDING TEST SMS VIA TWILIO")
    print("="*70)

    # Get credentials from environment
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")

    print(f"\n📋 Twilio Configuration:")
    print(f"   Account SID: {account_sid[:10]}..." if account_sid else "   Account SID: Not set")
    print(f"   Auth Token: {auth_token[:10]}..." if auth_token else "   Auth Token: Not set")
    print(f"   From Number: {from_number}")

    if not all([account_sid, auth_token, from_number]):
        print("\n❌ Twilio credentials not found in backend/.env")
        print("   Please add them to backend/.env file")
        return False

    # Recipient info
    to_number = "+18438344997"
    message = "Hello! This is a test message from your Mortgage CRM. The Verizon phone integration is working! 🎉"

    print(f"\n📤 Sending SMS:")
    print(f"   To: {to_number}")
    print(f"   From: {from_number}")
    print(f"   Message: {message[:50]}...")

    try:
        # Create Twilio client
        client = Client(account_sid, auth_token)

        # Send message
        message_obj = client.messages.create(
            body=message,
            from_=from_number,
            to=to_number
        )

        print(f"\n✅ SMS SENT SUCCESSFULLY!")
        print(f"\n📬 Message Details:")
        print(f"   SID: {message_obj.sid}")
        print(f"   Status: {message_obj.status}")
        print(f"   To: {message_obj.to}")
        print(f"   From: {message_obj.from_}")
        print(f"   Date Created: {message_obj.date_created}")

        print(f"\n🎉 SUCCESS! Check your phone at {to_number}")
        print(f"\n💡 You should receive the text within 1-2 minutes.")
        print(f"   If not, check your Twilio console for delivery status:")
        print(f"   https://console.twilio.com/us1/monitor/logs/sms")

        return True

    except Exception as e:
        print(f"\n❌ Error sending SMS: {e}")
        print(f"\n🔍 Troubleshooting:")
        print(f"   1. Check Twilio account has credits")
        print(f"   2. Verify phone number {to_number} is not blocked")
        print(f"   3. Check Twilio console for errors")
        print(f"   4. Verify from_number {from_number} is verified in Twilio")
        return False

def main():
    success = send_sms()

    if success:
        print("\n" + "="*70)
        print("  ✅ TEST COMPLETE - SMS SENT!")
        print("="*70)
        return 0
    else:
        print("\n" + "="*70)
        print("  ❌ TEST FAILED")
        print("="*70)
        return 1

if __name__ == "__main__":
    sys.exit(main())
