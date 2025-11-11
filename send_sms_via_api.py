#!/usr/bin/env python3
"""
Send Test SMS via Backend API
Uses the deployed backend to send SMS through Twilio
"""
import requests
import sys

BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

def main():
    print("="*70)
    print("  📱 SENDING TEST SMS VIA BACKEND API")
    print("="*70)

    # Step 1: Login to get token
    print("\n🔐 Step 1: Authenticating...")
    login_data = {
        "username": "demo@example.com",
        "password": "demo123"
    }

    try:
        login_response = requests.post(
            f"{BACKEND_URL}/token",
            data=login_data,
            timeout=10
        )

        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.status_code}")
            print(f"   Response: {login_response.text}")
            return 1

        token = login_response.json().get("access_token")
        print("✅ Authenticated successfully")

    except Exception as e:
        print(f"❌ Authentication error: {e}")
        return 1

    # Step 2: Check if SMS endpoint exists
    print("\n🔍 Step 2: Checking SMS endpoint...")
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # Try to check API docs for SMS endpoint
        docs_response = requests.get(f"{BACKEND_URL}/openapi.json", timeout=10)
        if docs_response.ok:
            openapi = docs_response.json()
            paths = openapi.get("paths", {})
            sms_endpoints = [path for path in paths.keys() if "sms" in path.lower()]

            if sms_endpoints:
                print(f"✅ Found SMS endpoints: {sms_endpoints}")
            else:
                print("⚠️  No SMS endpoints found in API")
                print("   The SMS API may not be deployed yet")
                return 1
        else:
            print("⚠️  Could not access API documentation")

    except Exception as e:
        print(f"⚠️  Could not check endpoints: {e}")

    # Step 3: Send SMS
    print("\n📤 Step 3: Sending SMS...")
    phone_number = "+18438344997"
    message = "Hello! This is a test message from your Mortgage CRM phone integration. 📱"

    sms_data = {
        "to_number": phone_number,
        "message": message
    }

    print(f"   To: {phone_number}")
    print(f"   Message: {message}")

    try:
        sms_response = requests.post(
            f"{BACKEND_URL}/api/v1/sms/send",
            json=sms_data,
            headers={
                **headers,
                "Content-Type": "application/json"
            },
            timeout=15
        )

        print(f"\n📊 Response Status: {sms_response.status_code}")

        if sms_response.status_code == 201:
            result = sms_response.json()
            print("\n" + "="*70)
            print("  ✅ SMS SENT SUCCESSFULLY!")
            print("="*70)
            print(f"\n✨ Message Details:")
            print(f"   Twilio SID: {result.get('twilio_sid', 'N/A')}")
            print(f"   Status: {result.get('status', 'N/A')}")
            print(f"   To: {phone_number}")
            print(f"\n📬 Check your phone for the message!")
            return 0

        elif sms_response.status_code == 404:
            print("\n❌ SMS endpoint not found (404)")
            print("   The endpoint /api/v1/sms/send is not available")
            print("\n🔍 Possible reasons:")
            print("   1. Backend code may not be deployed yet")
            print("   2. SMS routes may not be registered")
            print("   3. Endpoint path may be different")
            return 1

        elif sms_response.status_code == 503:
            print("\n⚠️  SMS service not configured (503)")
            print("   Twilio credentials are not set on the backend")
            print("\n📋 To configure:")
            print("   1. Add TWILIO_ACCOUNT_SID to Railway")
            print("   2. Add TWILIO_AUTH_TOKEN to Railway")
            print("   3. Add TWILIO_PHONE_NUMBER to Railway")
            print("   4. Restart the backend service")
            return 1

        else:
            print(f"\n❌ SMS sending failed: {sms_response.status_code}")
            try:
                error_detail = sms_response.json()
                print(f"   Error: {error_detail}")
            except:
                print(f"   Response: {sms_response.text}")
            return 1

    except Exception as e:
        print(f"\n❌ Error sending SMS: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
