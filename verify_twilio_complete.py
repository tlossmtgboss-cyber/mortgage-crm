#!/usr/bin/env python3
"""
Complete Twilio Verification
Checks integration status and sends test SMS
"""
import requests
import json
import time

BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

def print_section(title):
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

# Login
print_section("🔐 AUTHENTICATING")
login_response = requests.post(
    f"{BACKEND_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"},
    timeout=10
)

if login_response.status_code != 200:
    print(f"❌ Login failed: {login_response.status_code}")
    exit(1)

token = login_response.json()["access_token"]
print("✅ Authenticated successfully")

headers = {"Authorization": f"Bearer {token}"}

# Check Integration Status
print_section("📊 CHECKING INTEGRATION STATUS")
try:
    status_response = requests.get(
        f"{BACKEND_URL}/api/v1/integrations/status",
        headers=headers,
        timeout=10
    )

    if status_response.ok:
        status_data = status_response.json()
        print("✅ Integration status endpoint responded")
        print("\n📄 Full Status:")
        print(json.dumps(status_data, indent=2))

        # Find Twilio integration
        integrations = status_data.get('integrations', [])
        twilio = next((i for i in integrations if 'Twilio' in i.get('name', '')), None)

        if twilio:
            print("\n📱 Twilio Integration:")
            print(f"   Name: {twilio.get('name')}")
            print(f"   Status: {twilio.get('status')}")
            print(f"   Details: {json.dumps(twilio.get('details', {}), indent=2)}")
        else:
            print("\n⚠️  Twilio integration not found in status response")
    else:
        print(f"❌ Status check failed: {status_response.status_code}")
        print(f"   Response: {status_response.text}")
except Exception as e:
    print(f"❌ Error checking status: {e}")

# Check SMS History
print_section("📜 CHECKING SMS HISTORY")
try:
    history_response = requests.get(
        f"{BACKEND_URL}/api/v1/sms/history",
        headers=headers,
        timeout=10
    )

    if history_response.ok:
        history = history_response.json()
        print(f"✅ Found {len(history)} SMS records")
        print("\n📨 Recent SMS Messages:")
        for msg in history[:5]:  # Show last 5
            print(f"\n   ID: {msg.get('id')}")
            print(f"   To: {msg.get('to_number')}")
            print(f"   From: {msg.get('from_number')}")
            print(f"   Message: {msg.get('message')}")
            print(f"   Status: {msg.get('status')}")
            print(f"   Twilio SID: {msg.get('twilio_sid')}")
            print(f"   Created: {msg.get('created_at')}")
    else:
        print(f"⚠️  History check failed: {history_response.status_code}")
except Exception as e:
    print(f"⚠️  Error checking history: {e}")

# Send Test SMS
print_section("📤 SENDING NEW TEST SMS")
print("\n📱 Sending to: +18438344997")
print("💬 Message: Hello from Twilio! This is a test message from your Mortgage CRM.")

send_response = requests.post(
    f"{BACKEND_URL}/api/v1/sms/send",
    json={
        "to_number": "+18438344997",
        "message": "Hello from Twilio! This is a test message from your Mortgage CRM."
    },
    headers={
        **headers,
        "Content-Type": "application/json"
    },
    timeout=15
)

print(f"\n📊 Response Status: {send_response.status_code}")

if send_response.ok:
    result = send_response.json()
    print("\n✅ SMS API responded successfully")
    print("\n📄 Response:")
    print(json.dumps(result, indent=2))

    # Analyze result
    print_section("🔍 ANALYSIS")

    status = result.get('status')
    twilio_sid = result.get('twilio_sid')
    from_number = result.get('from_number')

    print(f"\n📊 Message Status: {status}")
    print(f"📱 From Number: {from_number}")
    print(f"🆔 Twilio SID: {twilio_sid}")

    if status == 'sent' and twilio_sid:
        print("\n" + "="*70)
        print("  ✅ SUCCESS! TWILIO IS WORKING!")
        print("="*70)
        print(f"\n✨ SMS sent successfully via Twilio")
        print(f"   Twilio SID: {twilio_sid}")
        print(f"   From: {from_number}")
        print(f"   To: +18438344997")
        print(f"\n⏰ Message should arrive within 5-30 seconds")
        print(f"\n📬 Check your phone!")

        print("\n💡 If you don't receive it:")
        print("   1. Check if your phone can receive SMS")
        print("   2. Check Twilio console for delivery status:")
        print("      https://console.twilio.com/us1/monitor/logs/sms")
        print(f"   3. Search for SID: {twilio_sid}")
        print("   4. Verify phone number is not blocked")

    elif status == 'failed':
        print("\n" + "="*70)
        print("  ❌ TWILIO NOT CONFIGURED PROPERLY")
        print("="*70)
        print(f"\n⚠️  Message saved but not sent")
        print(f"   From Number: {from_number}")

        if 'ac2558bd' in from_number.lower() or len(from_number) > 15:
            print("\n🔍 Issue: Phone number is showing as hash/ID")
            print("   This means TWILIO_PHONE_NUMBER is not set correctly")

        print("\n📋 To fix:")
        print("   1. Go to https://railway.app/dashboard")
        print("   2. Select backend service")
        print("   3. Go to Variables tab")
        print("   4. Check TWILIO_PHONE_NUMBER:")
        print("      - Must be in format: +15551234567")
        print("      - No spaces, dashes, or parentheses")
        print("      - Must start with + and country code")
        print("   5. Verify TWILIO_ACCOUNT_SID starts with 'AC'")
        print("   6. Verify TWILIO_AUTH_TOKEN is 32 characters")
        print("   7. Save and restart backend")
    else:
        print(f"\n⚠️  Unexpected status: {status}")
        print(f"   Twilio SID: {twilio_sid or 'None'}")

else:
    print(f"\n❌ SMS send failed: {send_response.status_code}")
    print(f"   Response: {send_response.text}")

print("\n" + "="*70)
print("  VERIFICATION COMPLETE")
print("="*70 + "\n")
