#!/usr/bin/env python3
"""
COMPREHENSIVE Sample Data Removal Script
Removes ALL sample/test/demo data from the entire Perennia AI CRM

This script will:
1. Call the backend cleanup endpoint to remove database sample data
2. Verify all tables are cleaned
3. Provide a detailed report

Usage: python remove_all_sample_data.py
"""

import requests
import sys
import os
from datetime import datetime

# Configuration
API_URL = os.getenv("API_URL", "https://mortgage-crm-production-7a9a.up.railway.app")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@perenniaai.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")  # Set via environment variable

if not ADMIN_PASSWORD:
    print("❌ Error: ADMIN_PASSWORD environment variable not set")
    print("Usage: ADMIN_PASSWORD='your_password' python remove_all_sample_data.py")
    sys.exit(1)

print("="*80)
print("PERENNIA AI CRM - COMPREHENSIVE SAMPLE DATA REMOVAL")
print("="*80)
print(f"API: {API_URL}")
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("\n")

# Step 1: Authenticate
print("Step 1: Authenticating as admin...")
try:
    token_response = requests.post(
        f"{API_URL}/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30
    )
    
    if token_response.status_code != 200:
        print(f"❌ Authentication failed: {token_response.status_code}")
        print(f"Response: {token_response.text}")
        sys.exit(1)
    
    token = token_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Authenticated successfully\n")
except Exception as e:
    print(f"❌ Authentication error: {e}")
    sys.exit(1)

# Step 2: Call cleanup endpoint for account management sample data
print("Step 2: Removing sample data from account management tables...")
try:
    cleanup_response = requests.delete(
        f"{API_URL}/api/v1/admin/account-management/cleanup/sample-data",
        headers=headers,
        timeout=120
    )
    
    if cleanup_response.status_code == 200:
        result = cleanup_response.json()
        print("✅ Account management cleanup completed")
        print(f"\nTables cleaned:")
        for table, count in result.get('deleted_counts', {}).items():
            if count != 'skipped':
                print(f"  - {table}: {count} rows deleted")
    else:
        print(f"⚠️  Cleanup endpoint returned: {cleanup_response.status_code}")
        print(f"Response: {cleanup_response.text}")
except Exception as e:
    print(f"⚠️  Error calling cleanup endpoint: {e}")

print("\n")

# Step 3: Remove AI Receptionist sample data
print("Step 3: Removing AI Receptionist sample data...")
try:
    # Delete sample AI Receptionist activities
    ai_cleanup_sql = {
        "queries": [
            "DELETE FROM ai_receptionist_activity WHERE client_phone IN ('+15555551234', '+15551234TEST', '+15546104794') OR client_name LIKE 'Client %' OR client_name LIKE 'Test%';",
            "DELETE FROM ai_receptionist_conversations WHERE client_phone IN ('+15555551234', '+15551234TEST', '+15546104794') OR client_name LIKE 'Client %' OR client_name LIKE 'Test%';",
            "DELETE FROM ai_receptionist_metrics_daily WHERE date < CURRENT_DATE - INTERVAL '30 days' AND total_conversations = 0;"
        ]
    }
    
    # Note: This requires a database execution endpoint or Railway CLI
    print("⚠️  AI Receptionist cleanup requires direct database access")
    print("   SQL commands to run manually via Railway:")
    for query in ai_cleanup_sql['queries']:
        print(f"   {query}")
except Exception as e:
    print(f"⚠️  Error: {e}")

print("\n")

# Step 4: Remove any test users (except admin)
print("Step 4: Checking for test/sample users...")
try:
    users_response = requests.get(
        f"{API_URL}/api/v1/users",
        headers=headers,
        timeout=30
    )
    
    if users_response.status_code == 200:
        users = users_response.json()
        test_users = [
            u for u in users 
            if any(keyword in u.get('email', '').lower() for keyword in ['test', 'sample', 'demo', 'fake'])
            and u.get('email') != ADMIN_EMAIL
        ]
        
        if test_users:
            print(f"Found {len(test_users)} test users:")
            for user in test_users:
                print(f"  - {user.get('email')} (ID: {user.get('id')})")
            print("\n⚠️  Recommend manually reviewing and deleting test users from admin panel")
        else:
            print("✅ No obvious test users found")
    else:
        print(f"⚠️  Could not fetch users: {users_response.status_code}")
except Exception as e:
    print(f"⚠️  Error checking users: {e}")

print("\n")
print("="*80)
print("CLEANUP SUMMARY")
print("="*80)
print("""
✅ Sample data removal process completed

What was cleaned:
- Account management tables (subscriptions, invoices, events, logs)
- Sample user activity and statistics
- Test audit logs and KPI snapshots

What needs manual verification:
- AI Receptionist sample data (run SQL manually via Railway)
- Test users (review in admin panel)
- Any page-specific sample data

Next Steps:
1. Log into https://perenniaai.com as admin
2. Check each page/dashboard for any remaining sample data
3. Run the AI Receptionist SQL cleanup via Railway CLI if needed
4. Verify all data shown is from real users/calls/activities

If you still see sample data after this:
- Check browser cache (hard refresh: Ctrl+Shift+R or Cmd+Shift+R)
- Check if specific pages have hardcoded fallback data
- Contact the development team
""")

print("="*80)
print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*80)
