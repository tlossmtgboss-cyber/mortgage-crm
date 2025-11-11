#!/usr/bin/env python3
"""
Comprehensive Error Check
Checks backend, Twilio, and SMS delivery for any errors
"""
import requests
import json
import sys

BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

def print_section(title, char="="):
    print("\n" + char*70)
    print(f"  {title}")
    print(char*70)

def check_backend_health():
    """Check if backend is responding"""
    print_section("🏥 BACKEND HEALTH CHECK")

    try:
        # Check docs endpoint
        response = requests.get(f"{BACKEND_URL}/docs", timeout=10)
        print(f"✅ Backend is online")
        print(f"   Status: {response.status_code}")
        print(f"   URL: {BACKEND_URL}")
        return True
    except Exception as e:
        print(f"❌ Backend error: {e}")
        return False

def check_twilio_configuration():
    """Check Twilio configuration on backend"""
    print_section("🔧 TWILIO CONFIGURATION CHECK")

    try:
        # Login
        login_response = requests.post(
            f"{BACKEND_URL}/token",
            data={"username": "demo@example.com", "password": "demo123"},
            timeout=10
        )

        if login_response.status_code != 200:
            print(f"❌ Authentication failed: {login_response.status_code}")
            return False

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Check SMS history to verify Twilio setup
        history_response = requests.get(
            f"{BACKEND_URL}/api/v1/sms/history",
            headers=headers,
            timeout=10
        )

        if history_response.status_code != 200:
            print(f"❌ SMS history endpoint error: {history_response.status_code}")
            return False

        history = history_response.json()
        print(f"✅ SMS endpoint accessible")
        print(f"   Total SMS records: {len(history)}")

        # Check recent messages
        if history:
            recent = history[0]
            print(f"\n📊 Most Recent SMS:")
            print(f"   ID: {recent.get('id')}")
            print(f"   To: {recent.get('to_number')}")
            print(f"   From: {recent.get('from_number')}")
            print(f"   Status: {recent.get('status')}")
            print(f"   Twilio SID: {recent.get('twilio_sid')}")

            # Check if from_number looks correct
            from_num = recent.get('from_number', '')
            if from_num.startswith('+1') and len(from_num) >= 12:
                print(f"   ✅ From number format looks correct")
            else:
                print(f"   ⚠️  From number format may be incorrect: {from_num}")
                return False

            # Check if we have Twilio SID
            if recent.get('twilio_sid'):
                print(f"   ✅ Twilio SID present - Twilio is working")
            else:
                print(f"   ❌ No Twilio SID - Message not sent via Twilio")
                return False

        return True

    except Exception as e:
        print(f"❌ Error checking Twilio: {e}")
        return False

def check_sms_failures():
    """Check for failed SMS messages"""
    print_section("📉 FAILED SMS ANALYSIS")

    try:
        # Login
        login_response = requests.post(
            f"{BACKEND_URL}/token",
            data={"username": "demo@example.com", "password": "demo123"},
            timeout=10
        )

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Get SMS history
        history_response = requests.get(
            f"{BACKEND_URL}/api/v1/sms/history",
            headers=headers,
            timeout=10
        )

        history = history_response.json()

        # Find failed messages
        failed = [msg for msg in history if msg.get('status') == 'failed']
        sent = [msg for msg in history if msg.get('status') == 'sent']

        print(f"📊 SMS Statistics:")
        print(f"   Total: {len(history)}")
        print(f"   Sent: {len(sent)}")
        print(f"   Failed: {len(failed)}")

        if failed:
            print(f"\n⚠️  Found {len(failed)} failed messages:")
            for msg in failed[:3]:  # Show first 3 failed
                print(f"\n   Message ID: {msg.get('id')}")
                print(f"   To: {msg.get('to_number')}")
                print(f"   From: {msg.get('from_number')}")
                print(f"   Created: {msg.get('created_at')}")
                print(f"   Reason: No Twilio SID - Twilio not configured at time of send")
        else:
            print(f"\n✅ No failed messages")

        if sent:
            print(f"\n✅ Recent successful sends:")
            for msg in sent[:2]:  # Show 2 recent successful
                print(f"\n   Message ID: {msg.get('id')}")
                print(f"   To: {msg.get('to_number')}")
                print(f"   Twilio SID: {msg.get('twilio_sid')}")
                print(f"   Created: {msg.get('created_at')}")

        return len(sent) > 0

    except Exception as e:
        print(f"❌ Error analyzing SMS: {e}")
        return False

def test_live_send():
    """Send a live test message and check for errors"""
    print_section("🧪 LIVE SMS TEST")

    try:
        # Login
        login_response = requests.post(
            f"{BACKEND_URL}/token",
            data={"username": "demo@example.com", "password": "demo123"},
            timeout=10
        )

        token = login_response.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Send test SMS
        print("📤 Sending test SMS...")
        print("   To: +18438344997")
        print("   Message: Test message - checking for errors")

        send_response = requests.post(
            f"{BACKEND_URL}/api/v1/sms/send",
            json={
                "to_number": "+18438344997",
                "message": "Test message - checking for errors"
            },
            headers=headers,
            timeout=15
        )

        print(f"\n📊 Response Status: {send_response.status_code}")

        if send_response.status_code == 201:
            result = send_response.json()
            print(f"✅ API accepted the request")
            print(f"\n📄 Response:")
            print(json.dumps(result, indent=2))

            # Analyze response
            status = result.get('status')
            twilio_sid = result.get('twilio_sid')
            from_number = result.get('from_number')

            print(f"\n🔍 Analysis:")
            print(f"   Status: {status}")
            print(f"   Twilio SID: {twilio_sid}")
            print(f"   From: {from_number}")

            if status == 'sent' and twilio_sid:
                print(f"\n✅ Message sent successfully via Twilio")
                print(f"   No errors detected in sending process")
                return True
            elif status == 'failed':
                print(f"\n❌ Message failed to send")
                print(f"   Error: Twilio credentials not configured properly")
                return False
            else:
                print(f"\n⚠️  Unexpected status: {status}")
                return False

        elif send_response.status_code == 503:
            print(f"❌ Service unavailable - Twilio not configured")
            print(f"   Response: {send_response.text}")
            return False
        else:
            print(f"❌ Send failed with status {send_response.status_code}")
            print(f"   Response: {send_response.text}")
            return False

    except Exception as e:
        print(f"❌ Error in live test: {e}")
        import traceback
        print(f"\n🔍 Full error trace:")
        traceback.print_exc()
        return False

def check_twilio_delivery():
    """Check Twilio delivery status via console link"""
    print_section("🔍 TWILIO DELIVERY CHECK")

    print("To check actual delivery status:")
    print("\n1. Go to: https://console.twilio.com/us1/monitor/logs/sms")
    print("2. Log in with your Twilio account")
    print("3. Look for recent messages to +18438344997")
    print("4. Check the 'Status' column:")
    print("   - 'delivered' = Message reached phone")
    print("   - 'sent' = Sent to carrier, pending delivery")
    print("   - 'undelivered' = Carrier couldn't deliver")
    print("   - 'failed' = Failed to send")
    print("\n5. Click on a message to see:")
    print("   - Error codes (if any)")
    print("   - Carrier response")
    print("   - Delivery timestamp")
    print("\nCommon Error Codes:")
    print("   30003 - Unreachable destination")
    print("   30004 - Message blocked by carrier")
    print("   30005 - Unknown destination")
    print("   30006 - Landline or unreachable carrier")

def main():
    print_section("🔍 COMPREHENSIVE ERROR CHECK", "=")
    print("Checking all systems for errors...")

    results = {}

    # Run all checks
    results['Backend Health'] = check_backend_health()
    results['Twilio Configuration'] = check_twilio_configuration()
    results['SMS Failures'] = check_sms_failures()
    results['Live Send Test'] = test_live_send()

    # Show delivery check info
    check_twilio_delivery()

    # Summary
    print_section("📊 ERROR CHECK SUMMARY", "=")

    all_passed = True
    for check, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status} - {check}")
        if not passed:
            all_passed = False

    print(f"\n{'='*70}")

    if all_passed:
        print("\n✅ NO ERRORS FOUND!")
        print("\nSystem Status: All systems operational")
        print("\nTwilio Integration: ✅ Working correctly")
        print("\n💡 If you're not receiving messages:")
        print("   1. Check Twilio console for delivery status")
        print("   2. Verify your phone can receive SMS from other services")
        print("   3. Check if number is on carrier blocklist")
        print("   4. Try sending to a different number")
        return 0
    else:
        print("\n⚠️  ERRORS DETECTED!")
        print("\nFailed Checks:")
        for check, passed in results.items():
            if not passed:
                print(f"   ❌ {check}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
