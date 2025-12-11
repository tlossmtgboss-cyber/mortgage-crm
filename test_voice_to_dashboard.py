#!/usr/bin/env python3
"""
Test that voice calls get logged to AI Receptionist Dashboard
This simulates what happens when someone calls +1 (832) 648-2297
"""
import requests
import time

API_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

print("=" * 70)
print("TEST: Voice Call → AI Receptionist Dashboard")
print("=" * 70)

# Get auth token
print("\n1. Getting auth token...")
token_response = requests.post(
    f"{API_URL}/token",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={"username": "admin@perenniaai.com", "password": "demo123"}
)
token = token_response.json()["access_token"]
print(f"   ✅ Got token")

headers = {"Authorization": f"Bearer {token}"}

# Get current activity count
print("\n2. Checking current activity count...")
response = requests.get(f"{API_URL}/api/v1/ai-receptionist/dashboard/activity/feed?limit=1", headers=headers)
before_count_response = requests.get(f"{API_URL}/api/v1/ai-receptionist/dashboard/activity/count", headers=headers)
before_count = before_count_response.json().get('count', 0)
print(f"   📊 Current activities: {before_count}")

# Simulate incoming call (what Twilio sends)
print("\n3. Simulating incoming call to +1 (832) 648-2297...")
print("   (This is what Twilio sends when someone calls)")
webhook_data = {
    "From": "+15555551234",  # Test caller number
    "To": "+18326482297",    # Your number
    "CallSid": f"TEST_CALL_{int(time.time())}",
    "CallStatus": "ringing"
}

webhook_response = requests.post(
    f"{API_URL}/api/v1/voice/incoming",
    data=webhook_data,
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

if webhook_response.status_code == 200:
    print(f"   ✅ Webhook accepted (status {webhook_response.status_code})")
    print(f"   📞 Call logged with SID: {webhook_data['CallSid']}")
else:
    print(f"   ❌ Webhook failed (status {webhook_response.status_code})")
    print(f"   Response: {webhook_response.text[:200]}")

# Wait a moment for database write
print("\n4. Waiting 2 seconds for database to update...")
time.sleep(2)

# Check if activity increased
print("\n5. Checking if call appeared in dashboard...")
after_count_response = requests.get(f"{API_URL}/api/v1/ai-receptionist/dashboard/activity/count", headers=headers)
after_count = after_count_response.json().get('count', 0)
print(f"   📊 Activities after call: {after_count}")

if after_count > before_count:
    print(f"   ✅ SUCCESS! Call logged to dashboard (+{after_count - before_count} activities)")

    # Get the latest activity
    activity_response = requests.get(f"{API_URL}/api/v1/ai-receptionist/dashboard/activity/feed?limit=1", headers=headers)
    latest = activity_response.json()[0] if activity_response.json() else None

    if latest:
        print(f"\n   Latest Activity:")
        print(f"   - Type: {latest.get('action_type')}")
        print(f"   - Phone: {latest.get('client_phone')}")
        print(f"   - Time: {latest.get('timestamp')}")
        print(f"   - Status: {latest.get('outcome_status')}")
else:
    print(f"   ⚠️  No new activity detected")
    print(f"   This might mean the webhook didn't write to database")

print("\n" + "=" * 70)
print("CONCLUSION")
print("=" * 70)

if after_count > before_count:
    print("✅ CONFIRMED: Calls to +1 (832) 648-2297 WILL appear in dashboard!")
    print("\nWhat happens when you call:")
    print("1. Twilio receives call to +1 (832) 648-2297")
    print("2. Twilio sends webhook to Railway backend")
    print("3. Backend logs call to production database")
    print("4. Dashboard reads from same database")
    print("5. You see the call in AI Receptionist Dashboard")
else:
    print("⚠️  WARNING: Webhook may not be logging to database properly")
    print("Need to check Twilio configuration and database connection")
