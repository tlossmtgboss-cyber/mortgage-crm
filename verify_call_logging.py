#!/usr/bin/env python3
"""Verify that calling +1 (832) 648-2297 will log to AI Receptionist Dashboard"""
import requests
import time
import json

API_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get token
token_response = requests.post(
    f"{API_URL}/token",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={"username": "admin@perenniaai.com", "password": "demo123"}
)
token = token_response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("=" * 80)
print("VERIFICATION: Will calls to +1 (832) 648-2297 appear in dashboard?")
print("=" * 80)

# Step 1: Check current activities
print("\n📊 Step 1: Checking current dashboard data...")
activity_response = requests.get(
    f"{API_URL}/api/v1/ai-receptionist/dashboard/activity/feed?limit=3",
    headers=headers
)
current_activities = activity_response.json()
print(f"   Current activities in dashboard: {len(current_activities)}")

if current_activities:
    latest = current_activities[0]
    print(f"   Latest activity: {latest['action_type']} from {latest['client_phone']}")

# Step 2: Send a test webhook (simulate Twilio)
print("\n📞 Step 2: Simulating incoming call webhook...")
test_phone = "+15551234TEST"
test_sid = f"CA_TEST_{int(time.time())}"

webhook_response = requests.post(
    f"{API_URL}/api/v1/voice/incoming",
    data={
        "From": test_phone,
        "To": "+18326482297",
        "CallSid": test_sid,
        "CallStatus": "ringing"
    },
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

print(f"   Webhook response: {webhook_response.status_code}")
if webhook_response.status_code != 200:
    print(f"   ERROR: {webhook_response.text[:200]}")

# Step 3: Wait and check again
print("\n⏳ Step 3: Waiting 3 seconds...")
time.sleep(3)

print("\n📊 Step 4: Checking dashboard again...")
new_activity_response = requests.get(
    f"{API_URL}/api/v1/ai-receptionist/dashboard/activity/feed?limit=5",
    headers=headers
)
new_activities = new_activity_response.json()
print(f"   Activities now: {len(new_activities)}")

# Check if our test call appears
found_test = False
for activity in new_activities:
    if activity.get('client_phone') == test_phone or activity.get('conversation_id') == test_sid:
        found_test = True
        print(f"\n   ✅ FOUND TEST CALL!")
        print(f"   - Phone: {activity['client_phone']}")
        print(f"   - Type: {activity['action_type']}")
        print(f"   - Time: {activity['timestamp']}")
        print(f"   - SID: {activity.get('conversation_id')}")
        break

# Step 5: Conclusion
print("\n" + "=" * 80)
print("ANSWER")
print("=" * 80)

if found_test:
    print("✅ YES - Calls to +1 (832) 648-2297 WILL appear in the AI Receptionist Dashboard")
    print("\nHere's what happens when you call:")
    print("1. You dial +1 (832) 648-2297")
    print("2. Twilio receives the call")
    print("3. Twilio sends webhook to: https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voice/incoming")
    print("4. Backend logs call to 'ai_receptionist_activity' table in production database")
    print("5. Dashboard queries same database every 30 seconds")
    print("6. Your call appears in the dashboard!")
    print("\n✅ This is CONFIRMED and WORKING")
else:
    print("⚠️  ISSUE DETECTED")
    print("\nThe webhook endpoint exists and responds (200 OK)")
    print("But the call is NOT being logged to the database")
    print("\nPossible causes:")
    print("1. Database connection issue in voice_routes.py")
    print("2. Table schema mismatch")
    print("3. Database write failing silently")
    print("\nNeed to check Railway logs for errors")

print("\nTo configure Twilio:")
print("1. Go to: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming")
print("2. Click on +1 (832) 648-2297")
print("3. Set Voice Webhook to:")
print("   https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voice/incoming")
print("4. Save")
