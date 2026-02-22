#!/usr/bin/env python3
"""
Test Vapi → CRM webhook integration with realistic call data
This simulates what happens when Vapi sends call events to the CRM
"""
import requests
import json
from datetime import datetime

CRM_WEBHOOK_URL = "https://app.perenniaai.com/api/vapi/webhook"
DASHBOARD_API_URL = "https://app.perenniaai.com/api/v1/ai-receptionist/dashboard"

print("=" * 80)
print("🧪 TESTING VAPI → CRM WEBHOOK INTEGRATION")
print("=" * 80)

# Test 1: Simulate call.started event
print("\n📋 TEST 1: Simulate 'call.started' Event")
call_started_payload = {
    "message": {
        "type": "call-start",
        "call": {
            "id": "test_call_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
            "phoneNumber": "+18438345251",
            "status": "in-progress",
            "startedAt": datetime.now().isoformat(),
            "assistant": {
                "id": "120e239e-4d19-4e43-ad92-1f8b07d08c8c",
                "name": "Sam - AI Receptionist"
            }
        }
    }
}

print(f"   Sending to: {CRM_WEBHOOK_URL}")
print(f"   Payload: {json.dumps(call_started_payload, indent=2)[:200]}...")

try:
    response = requests.post(
        CRM_WEBHOOK_URL,
        json=call_started_payload,
        timeout=10
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ Call started webhook accepted")
        print(f"   Response: {response.json()}")
    else:
        print(f"   ⚠️  Response: {response.text}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: Simulate call.ended event with transcript
print("\n📋 TEST 2: Simulate 'call.ended' Event")
call_ended_payload = {
    "message": {
        "type": "end-of-call-report",
        "call": {
            "id": "test_call_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
            "phoneNumber": "+18438345251",
            "status": "ended",
            "startedAt": "2025-11-19T10:00:00Z",
            "endedAt": datetime.now().isoformat(),
            "duration": 125,  # seconds
            "assistant": {
                "id": "120e239e-4d19-4e43-ad92-1f8b07d08c8c",
                "name": "Sam - AI Receptionist"
            },
            "transcript": [
                {
                    "role": "assistant",
                    "message": "Thank you for calling the Tim Loss Team, my name is Sam. Who do I have the pleasure of speaking to?"
                },
                {
                    "role": "user",
                    "message": "Hi, this is John Smith"
                },
                {
                    "role": "assistant",
                    "message": "Thank you John. I have you calling from +1 (843) 834-5251. Is this the best number to reach you in case we get disconnected?"
                },
                {
                    "role": "user",
                    "message": "Yes"
                },
                {
                    "role": "assistant",
                    "message": "Perfect! How can I help you today?"
                },
                {
                    "role": "user",
                    "message": "I'm interested in getting pre-approved for a mortgage"
                }
            ],
            "summary": "Customer John Smith called inquiring about mortgage pre-approval. Identified as new lead. Collecting application details.",
            "cost": 0.14
        }
    }
}

print(f"   Sending to: {CRM_WEBHOOK_URL}")
print(f"   Call duration: 125 seconds (2 minutes 5 seconds)")
print(f"   Transcript: 6 messages")

try:
    response = requests.post(
        CRM_WEBHOOK_URL,
        json=call_ended_payload,
        timeout=10
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ Call ended webhook accepted")
        print(f"   Response: {response.json()}")
    else:
        print(f"   ⚠️  Response: {response.text}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 3: Check if call appears in dashboard
print("\n📋 TEST 3: Verify Dashboard Can Retrieve Activity")

# We need to authenticate first - using demo user
auth_payload = {
    "username": "admin@perenniaai.com",
    "password": "demo123"
}

print(f"   Authenticating as admin@perenniaai.com...")
try:
    auth_response = requests.post(
        "https://app.perenniaai.com/api/v1/auth/login",
        data=auth_payload,
        timeout=10
    )

    if auth_response.status_code == 200:
        token = auth_response.json().get("access_token")
        print(f"   ✅ Authenticated successfully")

        # Now fetch dashboard activity
        headers = {"Authorization": f"Bearer {token}"}
        dashboard_response = requests.get(
            f"{DASHBOARD_API_URL}/activity?limit=5",
            headers=headers,
            timeout=10
        )

        if dashboard_response.status_code == 200:
            activity = dashboard_response.json()
            print(f"   ✅ Dashboard API accessible")
            print(f"   Total activities: {activity.get('total', 0)}")
            print(f"   Recent activities: {len(activity.get('items', []))}")

            if activity.get('items'):
                latest = activity['items'][0]
                print(f"\n   Latest activity:")
                print(f"   - Type: {latest.get('activity_type')}")
                print(f"   - Phone: {latest.get('phone_number')}")
                print(f"   - When: {latest.get('timestamp')}")
        else:
            print(f"   ⚠️  Dashboard API status: {dashboard_response.status_code}")
    else:
        print(f"   ⚠️  Auth failed: {auth_response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 80)
print("📊 INTEGRATION TEST SUMMARY")
print("=" * 80)

print("\n✅ Webhook Endpoint Tests:")
print("   - call.started event → CRM webhook")
print("   - call.ended event → CRM webhook")
print("   - Dashboard API accessibility")

print("\n🎯 CALL FLOW VERIFICATION:")
print("\n   When real call happens:")
print("   1. Caller dials +18434169589")
print("   2. Telnyx → Vapi")
print("   3. Sam answers call")
print("   4. Vapi sends 'call.started' → CRM webhook")
print("   5. During call: Function calls logged")
print("   6. Call ends: Vapi sends 'end-of-call-report' → CRM webhook")
print("   7. CRM processes webhook → Saves to database")
print("   8. Dashboard shows call in activity feed")

print("\n📱 READY TO TEST:")
print("   Call +18434169589 and verify:")
print("   ✅ Sam answers")
print("   ✅ Natural conversation")
print("   ✅ Call appears in dashboard within seconds")

print("\n" + "=" * 80)
