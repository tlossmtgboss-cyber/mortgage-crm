#!/usr/bin/env python3
"""
Run A/B Testing Tables Migration on Production
Calls the migration endpoint to create all necessary tables
"""
import requests
import os
import sys

# Production URL
BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

def run_migration():
    """Run the A/B testing tables migration"""

    print("🚀 A/B Testing Migration Runner")
    print("=" * 60)

    # Get credentials
    email = input("Enter your email: ").strip()
    password = input("Enter your password: ").strip()

    if not email or not password:
        print("❌ Email and password are required")
        return False

    # Step 1: Login
    print(f"\n1. Logging in as {email}...")
    login_url = f"{BACKEND_URL}/token"
    login_data = {
        "username": email,
        "password": password
    }

    try:
        response = requests.post(login_url, data=login_data)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            print("❌ Failed to get access token")
            return False

        print("✅ Login successful")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return False

    # Step 2: Run migration
    print("\n2. Running A/B testing migration...")
    migration_url = f"{BACKEND_URL}/api/v1/migrations/add-ab-testing-tables"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(migration_url, headers=headers)
        response.raise_for_status()
        result = response.json()

        print("\n" + "=" * 60)
        print("MIGRATION RESULT:")
        print("=" * 60)

        if result.get("success"):
            print("✅ SUCCESS!")
            print(f"\nMessage: {result.get('message')}")

            if result.get("already_exists"):
                print("\n📌 Tables already exist - no changes made")
            else:
                tables = result.get("tables_created", [])
                print(f"\n📊 Tables created ({len(tables)}):")
                for table in tables:
                    print(f"   - {table}")
        else:
            print("❌ FAILED!")
            print(f"\nMessage: {result.get('message')}")
            if result.get("error"):
                print(f"Error: {result.get('error')}")

        print("=" * 60)

        return result.get("success", False)

    except requests.exceptions.HTTPError as e:
        print(f"❌ Migration failed with HTTP error: {e}")
        print(f"Response: {e.response.text if hasattr(e.response, 'text') else 'N/A'}")
        return False
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    print("\n")
    success = run_migration()
    print("\n")

    if success:
        print("🎉 A/B testing migration completed successfully!")
        print("\n📝 Next steps:")
        print("   1. Test A/B testing endpoints at:")
        print(f"      {BACKEND_URL}/docs#/A/B%20Testing")
        print("   2. Create your first experiment")
        print("   3. Integrate A/B testing with AI services")
        sys.exit(0)
    else:
        print("💥 Migration failed. Please check the error messages above.")
        sys.exit(1)
