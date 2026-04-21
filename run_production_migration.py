#!/usr/bin/env python3
"""
Run MUM client fields migration on production via API
"""

import requests
import sys
import os

API_BASE = "https://app.perenniaai.com"

# SECURITY: Password must be provided via environment variable
MIGRATION_USERNAME = os.environ.get("MIGRATION_USERNAME", "")
MIGRATION_PASSWORD = os.environ.get("MIGRATION_PASSWORD", "")

if not MIGRATION_USERNAME or not MIGRATION_PASSWORD:
    print("❌ Error: Set MIGRATION_USERNAME and MIGRATION_PASSWORD environment variables")
    print("Usage: MIGRATION_USERNAME='user@example.com' MIGRATION_PASSWORD='...' python run_production_migration.py")
    sys.exit(1)

credentials = [
    {"username": MIGRATION_USERNAME, "password": MIGRATION_PASSWORD},
]

print("🔑 Attempting to authenticate...")

token = None
for cred in credentials:
    try:
        response = requests.post(
            f"{API_BASE}/token",
            data=cred,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )

        if response.status_code == 200:
            token = response.json().get("access_token")
            print(f"✅ Authenticated as {cred['username']}")
            break
        else:
            print(f"⏭️  Failed with {cred['username']}: {response.status_code}")
    except Exception as e:
        print(f"⏭️  Error with {cred['username']}: {e}")

if not token:
    print("❌ Failed to authenticate with any credentials")
    print("\nPlease provide valid credentials:")
    print("You can run this manually in your browser console instead:")
    print("\nfetch('https://app.perenniaai.com/api/v1/migrations/add-mum-client-fields', {")
    print("  method: 'POST',")
    print("  headers: {")
    print("    'Authorization': 'Bearer ' + localStorage.getItem('token'),")
    print("    'Content-Type': 'application/json'")
    print("  }")
    print("}).then(r => r.json()).then(console.log);")
    sys.exit(1)

print("")
print("🔧 Running MUM client fields migration...")
print("")

try:
    response = requests.post(
        f"{API_BASE}/api/v1/migrations/add-mum-client-fields",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        timeout=30
    )

    result = response.json()

    print("=" * 60)
    print("📋 Migration Result:")
    print("=" * 60)
    print("")

    if result.get("success"):
        print("✅ Migration completed successfully!")
        print("")

        added = result.get("added_columns", [])
        existing = result.get("existing_columns", [])

        if added:
            print(f"✨ Added {len(added)} new columns:")
            for col in added:
                print(f"   - {col}")
            print("")

        if existing:
            print(f"📋 {len(existing)} columns already existed:")
            for col in existing:
                print(f"   - {col}")
            print("")
    else:
        print("⚠️  Migration result:")
        print(f"   {result.get('message', 'Unknown result')}")
        print("")
        if result.get("error"):
            print(f"Error details: {result['error']}")

    print("=" * 60)

    sys.exit(0 if result.get("success") else 1)

except Exception as e:
    print(f"❌ Failed to run migration: {e}")
    sys.exit(1)
