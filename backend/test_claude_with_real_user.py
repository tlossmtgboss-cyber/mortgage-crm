#!/usr/bin/env python
"""Test Claude email processing with real user account"""
import requests
import json


def main():
    # Railway production URL
    BASE_URL = "https://api.perenniaai.com"

    # Your credentials
    EMAIL = "tloss@cmgfi.com"
    PASSWORD = input("Enter password for tloss@cmgfi.com: ")

    print("="*80)
    print("TESTING CLAUDE WITH REAL USER ACCOUNT")
    print("="*80)

    # Step 1: Login
    print(f"\n1️⃣  Logging in as {EMAIL}...")
    login_response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={
            "username": EMAIL,
            "password": PASSWORD
        }
    )

    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.status_code}")
        print(f"   Response: {login_response.text}")
        exit(1)

    token = login_response.json().get("access_token")
    print(f"✅ Login successful! Token: {token[:20]}...")

    headers = {
        "Authorization": f"Bearer {token}"
    }

    # Step 2: Check for unprocessed emails
    print(f"\n2️⃣  Checking for unprocessed emails...")
    response = requests.get(
        f"{BASE_URL}/api/v1/reconciliation/pending",
        headers=headers
    )

    if response.status_code == 200:
        pending = response.json()
        print(f"✅ Found {len(pending)} pending emails for review")
    else:
        print(f"⚠️  Could not fetch pending emails: {response.status_code}")

    # Step 3: Trigger email reprocessing to use Claude
    print(f"\n3️⃣  Triggering email reprocessing with Claude...")
    response = requests.post(
        f"{BASE_URL}/api/v1/microsoft/reprocess-emails",
        headers=headers
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ Reprocessing complete!")
        print(f"   Status: {result.get('status')}")
        print(f"   Emails found: {result.get('total_found', 0)}")
        print(f"   Reprocessed: {result.get('reprocessed_count', 0)}")
        print(f"   Message: {result.get('message')}")

        if result.get('reprocessed_count', 0) > 0:
            print(f"\n🎉 Claude should have processed {result.get('reprocessed_count')} emails!")
            print(f"   Check Railway logs for:")
            print(f"   - '🤖 Using Claude parser for email...'")
            print(f"   - '✅ Claude extracted X fields with Y% confidence'")
    else:
        print(f"❌ Reprocessing failed: {response.status_code}")
        print(f"   Response: {response.text}")

    # Step 4: Trigger Microsoft email sync
    print(f"\n4️⃣  Triggering Microsoft 365 email sync...")
    response = requests.post(
        f"{BASE_URL}/api/v1/microsoft/sync-emails",
        headers=headers
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ Sync complete!")
        print(f"   Status: {result.get('status')}")
        print(f"   New emails: {result.get('new_count', 0)}")
        print(f"   Message: {result.get('message')}")

        if result.get('new_count', 0) > 0:
            print(f"\n🎉 Claude processed {result.get('new_count')} new emails!")
            print(f"   Check Railway logs for Claude parsing activity")
    elif response.status_code == 404:
        print(f"⚠️  Microsoft OAuth not connected for this account")
        print(f"   Please connect Microsoft 365 in the CRM settings first")
    else:
        print(f"❌ Sync failed: {response.status_code}")
        print(f"   Response: {response.text}")

    print(f"\n" + "="*80)
    print("✅ TEST COMPLETE")
    print("="*80)
    print("\n💡 Next steps:")
    print("   1. Check Railway logs: railway logs --tail 50")
    print("   2. Look for: '🤖 Using Claude parser'")
    print("   3. Or send a test email to your connected inbox")


if __name__ == "__main__":
    main()
