#!/usr/bin/env python3
"""Clear all dummy data from the CRM"""
import os
import urllib.request
import urllib.parse
import json
import sys

API_URL = os.environ.get("API_URL", "https://app.perenniaai.com")

# Login - set credentials via environment variables
username = os.environ.get("CRM_USERNAME", "")
password = os.environ.get("CRM_PASSWORD", "")
if not username or not password:
    print("ERROR: Set CRM_USERNAME and CRM_PASSWORD environment variables")
    sys.exit(1)

print("Logging in...")
login_data = urllib.parse.urlencode({
    "username": username,
    "password": password
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
