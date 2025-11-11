#!/usr/bin/env python3
"""
Clear all sample data from PRODUCTION database.
Run this script to remove all the fake team members and sample data.
"""
import requests

# Your production backend URL
BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

print("🧹 Clear Production Sample Data")
print("=" * 50)
print(f"Backend: {BACKEND_URL}")
print()

# Step 1: Login
print("Step 1: Logging in...")
username = input("Enter your email (demo@example.com): ") or "demo@example.com"
password = input("Enter your password (demo123): ") or "demo123"

login_response = requests.post(
    f"{BACKEND_URL}/token",
    data={"username": username, "password": password}
)

if login_response.status_code != 200:
    print(f"❌ Login failed: {login_response.text}")
    exit(1)

token = login_response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("✅ Logged in successfully")
print()

# Step 2: Confirm deletion
print("⚠️  WARNING: This will delete ALL of the following:")
print("   - All loans (including sample data)")
print("   - All leads")
print("   - All tasks")
print("   - All referral partners")
print("   - All MUM clients")
print()
print("✅ Your user account and company settings will be kept.")
print()
print("The 'Team Members' list will be completely empty after this.")
print()

confirm = input("Type 'YES' to confirm deletion: ")
if confirm != "YES":
    print("❌ Cancelled. No data was deleted.")
    exit(0)

# Step 3: Clear data
print()
print("🗑️  Clearing sample data from production...")
clear_response = requests.post(
    f"{BACKEND_URL}/api/v1/admin/clear-sample-data",
    headers=headers
)

if clear_response.status_code == 200:
    result = clear_response.json()
    print("\n✅ SUCCESS! Sample data has been cleared.")
    print()
    print("Deleted:")
    for key, value in result["deleted"].items():
        print(f"  - {value} {key}")
    print()
    print("Remaining:")
    for key, value in result["remaining"].items():
        print(f"  - {value} {key}")
    print()
    print("🎉 Your Team Members list is now empty!")
    print("   Refresh your settings page to see the changes.")
else:
    print(f"\n❌ Failed to clear data")
    print(f"Status: {clear_response.status_code}")
    print(f"Error: {clear_response.text}")
