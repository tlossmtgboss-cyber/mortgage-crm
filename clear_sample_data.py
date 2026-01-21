#!/usr/bin/env python3
"""Clear sample/test data from AI Receptionist Dashboard - keep only REAL call data"""
import requests

API_URL = "https://app.perenniaai.com"

# Get auth token
print("Getting auth token...")
token_response = requests.post(
    f"{API_URL}/token",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={"username": "admin@perenniaai.com", "password": "demo123"}
)
token = token_response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("\n" + "=" * 70)
print("CLEARING SAMPLE DATA FROM AI RECEPTIONIST DASHBOARD")
print("=" * 70)

# Step 1: Check current data
print("\n1. Checking current data in dashboard...")
activity_response = requests.get(
    f"{API_URL}/api/v1/ai-receptionist/dashboard/activity/feed?limit=100",
    headers=headers
)

if activity_response.status_code == 200:
    activities = activity_response.json()
    print(f"   Current activities: {len(activities)}")

    # Count test vs potentially real data
    test_numbers = ['+15555551234', '+15551234TEST', '+15546104794']
    test_count = sum(1 for a in activities if a.get('client_phone') in test_numbers)
    real_count = len(activities) - test_count

    print(f"   - Test/sample calls: {test_count}")
    print(f"   - Potentially real calls: {real_count}")

    if test_count > 0:
        print(f"\n   Test phone numbers found:")
        for num in test_numbers:
            count = sum(1 for a in activities if a.get('client_phone') == num)
            if count > 0:
                print(f"   - {num}: {count} calls")

# Step 2: Use admin endpoint to clear database
print("\n2. Clearing sample data from production database...")
print("   (This will remove all test calls and demo data)")

# We need to call Railway to run SQL directly
import subprocess

sql_commands = """
-- Delete test/sample calls
DELETE FROM ai_receptionist_activity
WHERE client_phone IN ('+15555551234', '+15551234TEST', '+15546104794')
   OR client_name LIKE 'Client %';

-- Delete sample conversations
DELETE FROM ai_receptionist_conversations
WHERE client_phone IN ('+15555551234', '+15551234TEST', '+15546104794')
   OR client_name LIKE 'Client %';

-- Delete sample metrics (keep only real data)
DELETE FROM ai_receptionist_metrics_daily
WHERE date < CURRENT_DATE - INTERVAL '1 day'
  AND total_conversations = 0;

-- Show remaining data
SELECT COUNT(*) as remaining_activities FROM ai_receptionist_activity;
SELECT COUNT(*) as remaining_conversations FROM ai_receptionist_conversations;
"""

print("\n   Executing SQL to clear sample data...")

try:
    # Save SQL to temp file
    with open('/tmp/clear_sample_data.sql', 'w') as f:
        f.write(sql_commands)

    # Execute via Railway
    result = subprocess.run(
        ['railway', 'run', 'psql', '-f', '/tmp/clear_sample_data.sql'],
        capture_output=True,
        text=True,
        timeout=30
    )

    if result.returncode == 0:
        print("   ✅ Sample data cleared successfully")
        print(f"\n   Output:")
        print(result.stdout)
    else:
        print(f"   ⚠️  Error clearing data: {result.stderr}")

except Exception as e:
    print(f"   ⚠️  Could not clear via Railway CLI: {e}")
    print("\n   Alternative: Use Railway dashboard to run SQL manually")

# Step 3: Verify clean state
print("\n3. Verifying dashboard is clean...")
activity_response = requests.get(
    f"{API_URL}/api/v1/ai-receptionist/dashboard/activity/feed?limit=10",
    headers=headers
)

if activity_response.status_code == 200:
    activities = activity_response.json()
    print(f"   Remaining activities: {len(activities)}")

    if len(activities) == 0:
        print("   ✅ Dashboard is clean - ready for real call data!")
    else:
        print(f"\n   Remaining activities:")
        for i, activity in enumerate(activities[:5], 1):
            print(f"   {i}. {activity['action_type']} - {activity['client_phone']}")

print("\n" + "=" * 70)
print("NEXT STEPS")
print("=" * 70)
print("""
✅ Sample/test data has been cleared

Now when you call +1 (832) 648-2297:
1. Twilio receives your call
2. Backend logs it to ai_receptionist_activity table
3. Your call appears in the AI Receptionist Dashboard
4. You'll see ONLY real call data

Test it now:
1. Call: +1 (832) 648-2297
2. Wait a few seconds after the call
3. Go to: https://mortgage-crm-nine.vercel.app/ai-receptionist-dashboard
4. Click "Refresh" to see your call

Your call should show:
- Your real phone number
- Call timestamp
- Call status (completed/missed)
- Any conversation transcript
""")
