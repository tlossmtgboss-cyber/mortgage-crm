#!/usr/bin/env python3
"""
Clear all MUM clients (portfolio borrowers) from PRODUCTION database.
Run this script to remove all portfolio clients.
"""
import requests

# Your production backend URL
BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

print("🧹 Clear Portfolio Clients")
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

# Step 2: Get all MUM clients
print("Step 2: Fetching all portfolio clients...")
get_response = requests.get(
    f"{BACKEND_URL}/api/v1/mum-clients/",
    headers=headers
)

if get_response.status_code != 200:
    print(f"❌ Failed to fetch clients: {get_response.text}")
    exit(1)

clients = get_response.json()
print(f"Found {len(clients)} portfolio clients")
print()

if len(clients) == 0:
    print("✅ No clients to delete. Portfolio is already empty.")
    exit(0)

# Step 3: Confirm deletion
print("⚠️  WARNING: This will delete ALL portfolio clients:")
for client in clients[:10]:  # Show first 10
    print(f"   - {client.get('name', 'Unknown')} (Loan #{client.get('loan_number', 'N/A')})")
if len(clients) > 10:
    print(f"   ... and {len(clients) - 10} more")
print()

confirm = input(f"Type 'YES' to delete all {len(clients)} portfolio clients: ")
if confirm != "YES":
    print("❌ Cancelled. No data was deleted.")
    exit(0)

# Step 4: Delete all clients
print()
print("🗑️  Deleting portfolio clients...")
deleted_count = 0
failed_count = 0

for client in clients:
    client_id = client.get('id')
    try:
        delete_response = requests.delete(
            f"{BACKEND_URL}/api/v1/mum-clients/{client_id}",
            headers=headers
        )
        if delete_response.status_code in [200, 204]:
            deleted_count += 1
            print(f"✓ Deleted: {client.get('name', 'Unknown')}")
        else:
            failed_count += 1
            print(f"✗ Failed to delete {client.get('name', 'Unknown')}: {delete_response.status_code}")
    except Exception as e:
        failed_count += 1
        print(f"✗ Error deleting {client.get('name', 'Unknown')}: {e}")

print()
print("=" * 50)
print(f"✅ Deletion complete!")
print(f"   Successfully deleted: {deleted_count}")
if failed_count > 0:
    print(f"   Failed: {failed_count}")
print()
print("🎉 Your portfolio is now empty!")
print("   Refresh your portfolio page to see the changes.")
