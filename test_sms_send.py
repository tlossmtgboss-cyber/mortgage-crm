#!/usr/bin/env python3
"""
Test SMS Sending to User's Cell Phone
Sends a test SMS message via Twilio
"""
import requests
import sys

BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

def login():
    """Login to get auth token"""
    print("🔐 Logging in to backend...")

    # Try with demo credentials
    login_data = {
        "username": "demo@example.com",
        "password": "demo123"
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/token",
            data=login_data,
            timeout=10
        )

        if response.status_code == 200:
            token = response.json().get("access_token")
            print(f"✅ Logged in successfully")
            return token
        else:
            print(f"❌ Login failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Login error: {e}")
        return None

def send_sms(token, phone_number, message):
    """Send SMS via backend API"""
    print(f"\n📱 Sending SMS to {phone_number}...")
    print(f"💬 Message: {message}")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "to_number": phone_number,
        "message": message
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/v1/sms/send",
            json=payload,
            headers=headers,
            timeout=15
        )

        if response.status_code == 201:
            result = response.json()
            print(f"\n✅ SMS SENT SUCCESSFULLY!")
            print(f"   Twilio SID: {result.get('twilio_sid', 'N/A')}")
            print(f"   Status: {result.get('status', 'N/A')}")
            print(f"\n📬 Check your phone for the message!")
            return True
        else:
            print(f"\n❌ SMS sending failed: {response.status_code}")
            print(f"   Response: {response.text}")

            # Check if Twilio is configured
            if response.status_code == 503:
                print("\n⚠️  Twilio SMS service is not configured on the backend.")
                print("   Please add these environment variables to Railway:")
                print("   - TWILIO_ACCOUNT_SID")
                print("   - TWILIO_AUTH_TOKEN")
                print("   - TWILIO_PHONE_NUMBER")

            return False
    except Exception as e:
        print(f"\n❌ Error sending SMS: {e}")
        return False

def main():
    print("="*70)
    print("  📱 SMS TEST - Sending Message to Your Cell Phone")
    print("="*70)

    # Get auth token
    token = login()
    if not token:
        print("\n❌ Cannot proceed without authentication")
        return 1

    # Send SMS
    phone_number = "+18438344997"
    message = "Hello! This is a test message from your Mortgage CRM. The Verizon phone integration is working! 🎉"

    success = send_sms(token, phone_number, message)

    if success:
        print("\n" + "="*70)
        print("  🎉 SUCCESS!")
        print("="*70)
        print("\n✅ Test SMS sent successfully!")
        print("📱 Check your phone (843) 834-4997")
        print("\nIf you don't receive it within 1 minute:")
        print("  1. Check your Twilio console for delivery status")
        print("  2. Verify phone number format is correct")
        print("  3. Check Railway logs for any errors")
        return 0
    else:
        print("\n" + "="*70)
        print("  ❌ FAILED")
        print("="*70)
        print("\nTroubleshooting:")
        print("  1. Verify Twilio credentials are added to Railway")
        print("  2. Check Railway backend logs for errors")
        print("  3. Confirm Twilio phone number is verified")
        print("  4. Check Twilio account has credits")
        return 1

if __name__ == "__main__":
    sys.exit(main())
