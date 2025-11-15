#!/usr/bin/env python3
"""Clear all dummy data from the CRM"""
import urllib.request
import urllib.parse
import json
import sys

API_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Login
print("Logging in...")
login_data = urllib.parse.urlencode({
    "username": "tloss@cmgfi.com",
    "password": "Woodwindow00!"
}).encode()

login_req = urllib.request.Request(
    f"{API_URL}/token",
    data=login_data,
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

try:
    with urllib.request.urlopen(login_req) as response:
        login_result = json.loads(response.read().decode())
        token = login_result["access_token"]
        print("Login successful!")
except Exception as e:
    print(f"Login failed: {e}")
    sys.exit(1)

# Clear sample data
print("\nClearing all dummy data...")
clear_req = urllib.request.Request(
    f"{API_URL}/api/v1/admin/clear-sample-data",
    method="POST",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
)

try:
    with urllib.request.urlopen(clear_req) as response:
        result = json.loads(response.read().decode())
        print("\n✅ Successfully cleared dummy data!")
        print(f"\nDeleted:")
        for key, value in result.items():
            if key.startswith("deleted_"):
                item_name = key.replace("deleted_", "").replace("_", " ").title()
                print(f"  - {item_name}: {value}")
except Exception as e:
    print(f"\n❌ Failed to clear data: {e}")
    sys.exit(1)
