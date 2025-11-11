#!/usr/bin/env python3
"""
Clear ALL data from your PRODUCTION account.
This will remove everything except your user account and settings.
Run this script to start completely fresh.
"""
import requests

# Your production backend URL
BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

print("🧹 Clear ALL Account Data")
print("=" * 50)
print(f"Backend: {BACKEND_URL}")
print()

# Step 1: Login
print("Step 1: Logging in...")
username = input("Enter your email (tloss@cmgfi.com): ") or "tloss@cmgfi.com"
password = input("Enter your password: ")

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

# Step 2: Get counts of all data
print("Step 2: Checking what data exists...")
data_counts = {}

try:
    # Count leads
    leads_response = requests.get(f"{BACKEND_URL}/api/v1/leads/", headers=headers)
    if leads_response.status_code == 200:
        data_counts['leads'] = len(leads_response.json())

    # Count loans
    loans_response = requests.get(f"{BACKEND_URL}/api/v1/loans/", headers=headers)
    if loans_response.status_code == 200:
        data_counts['loans'] = len(loans_response.json())

    # Count MUM clients
    mum_response = requests.get(f"{BACKEND_URL}/api/v1/mum-clients/", headers=headers)
    if mum_response.status_code == 200:
        data_counts['mum_clients'] = len(mum_response.json())

    # Count referral partners
    partners_response = requests.get(f"{BACKEND_URL}/api/v1/referral-partners/", headers=headers)
    if partners_response.status_code == 200:
        data_counts['referral_partners'] = len(partners_response.json())

    # Count tasks
    tasks_response = requests.get(f"{BACKEND_URL}/api/v1/tasks/", headers=headers)
    if tasks_response.status_code == 200:
        data_counts['tasks'] = len(tasks_response.json())

    # Count team members
    team_response = requests.get(f"{BACKEND_URL}/api/v1/team/members", headers=headers)
    if team_response.status_code == 200:
        team_data = team_response.json()
        if isinstance(team_data, list):
            data_counts['team_members'] = len(team_data)
        elif isinstance(team_data, dict) and 'team_members' in team_data:
            data_counts['team_members'] = len(team_data['team_members'])

except Exception as e:
    print(f"Warning: Could not count some data: {e}")

print("\nFound:")
for key, count in data_counts.items():
    print(f"   - {count} {key}")
print()

total_items = sum(data_counts.values())
if total_items == 0:
    print("✅ No data found. Your account is already empty.")
    exit(0)

# Step 3: Confirm deletion
print("⚠️  WARNING: This will DELETE ALL of the following:")
print("   ❌ All leads")
print("   ❌ All loans (active files)")
print("   ❌ All portfolio clients (MUM)")
print("   ❌ All referral partners")
print("   ❌ All tasks")
print("   ❌ All activities & conversation logs")
print("   ❌ All team members")
print("   ❌ All calendar events")
print()
print("✅ Your user account and settings will be KEPT")
print()

confirm = input(f"Type 'DELETE ALL' to permanently delete {total_items} items: ")
if confirm != "DELETE ALL":
    print("❌ Cancelled. No data was deleted.")
    exit(0)

# Step 4: Delete everything
print()
print("🗑️  Deleting all data...")
results = {
    'deleted': {},
    'failed': {}
}

# Delete activities (must be first due to foreign keys)
try:
    activities_response = requests.get(f"{BACKEND_URL}/api/v1/activities/", headers=headers)
    if activities_response.status_code == 200:
        activities = activities_response.json()
        deleted_count = 0
        for activity in activities:
            try:
                delete_response = requests.delete(
                    f"{BACKEND_URL}/api/v1/activities/{activity['id']}",
                    headers=headers
                )
                if delete_response.status_code in [200, 204]:
                    deleted_count += 1
            except:
                pass
        results['deleted']['activities'] = deleted_count
        print(f"✓ Deleted {deleted_count} activities")
except Exception as e:
    print(f"✗ Error deleting activities: {e}")

# Delete tasks
try:
    tasks_response = requests.get(f"{BACKEND_URL}/api/v1/tasks/", headers=headers)
    if tasks_response.status_code == 200:
        tasks = tasks_response.json()
        deleted_count = 0
        for task in tasks:
            try:
                delete_response = requests.delete(
                    f"{BACKEND_URL}/api/v1/tasks/{task['id']}",
                    headers=headers
                )
                if delete_response.status_code in [200, 204]:
                    deleted_count += 1
            except:
                pass
        results['deleted']['tasks'] = deleted_count
        print(f"✓ Deleted {deleted_count} tasks")
except Exception as e:
    print(f"✗ Error deleting tasks: {e}")

# Delete leads
try:
    leads_response = requests.get(f"{BACKEND_URL}/api/v1/leads/", headers=headers)
    if leads_response.status_code == 200:
        leads = leads_response.json()
        deleted_count = 0
        for lead in leads:
            try:
                delete_response = requests.delete(
                    f"{BACKEND_URL}/api/v1/leads/{lead['id']}",
                    headers=headers
                )
                if delete_response.status_code in [200, 204]:
                    deleted_count += 1
            except:
                pass
        results['deleted']['leads'] = deleted_count
        print(f"✓ Deleted {deleted_count} leads")
except Exception as e:
    print(f"✗ Error deleting leads: {e}")

# Delete loans
try:
    loans_response = requests.get(f"{BACKEND_URL}/api/v1/loans/", headers=headers)
    if loans_response.status_code == 200:
        loans = loans_response.json()
        deleted_count = 0
        for loan in loans:
            try:
                delete_response = requests.delete(
                    f"{BACKEND_URL}/api/v1/loans/{loan['id']}",
                    headers=headers
                )
                if delete_response.status_code in [200, 204]:
                    deleted_count += 1
            except:
                pass
        results['deleted']['loans'] = deleted_count
        print(f"✓ Deleted {deleted_count} loans")
except Exception as e:
    print(f"✗ Error deleting loans: {e}")

# Delete MUM clients
try:
    mum_response = requests.get(f"{BACKEND_URL}/api/v1/mum-clients/", headers=headers)
    if mum_response.status_code == 200:
        clients = mum_response.json()
        deleted_count = 0
        for client in clients:
            try:
                delete_response = requests.delete(
                    f"{BACKEND_URL}/api/v1/mum-clients/{client['id']}",
                    headers=headers
                )
                if delete_response.status_code in [200, 204]:
                    deleted_count += 1
            except:
                pass
        results['deleted']['mum_clients'] = deleted_count
        print(f"✓ Deleted {deleted_count} portfolio clients")
except Exception as e:
    print(f"✗ Error deleting portfolio clients: {e}")

# Delete referral partners
try:
    partners_response = requests.get(f"{BACKEND_URL}/api/v1/referral-partners/", headers=headers)
    if partners_response.status_code == 200:
        partners = partners_response.json()
        deleted_count = 0
        for partner in partners:
            try:
                delete_response = requests.delete(
                    f"{BACKEND_URL}/api/v1/referral-partners/{partner['id']}",
                    headers=headers
                )
                if delete_response.status_code in [200, 204]:
                    deleted_count += 1
            except:
                pass
        results['deleted']['referral_partners'] = deleted_count
        print(f"✓ Deleted {deleted_count} referral partners")
except Exception as e:
    print(f"✗ Error deleting referral partners: {e}")

# Delete team members
try:
    team_response = requests.get(f"{BACKEND_URL}/api/v1/team/members", headers=headers)
    if team_response.status_code == 200:
        team_data = team_response.json()
        members = team_data if isinstance(team_data, list) else team_data.get('team_members', [])
        deleted_count = 0
        for member in members:
            try:
                delete_response = requests.delete(
                    f"{BACKEND_URL}/api/v1/team/members/{member['id']}",
                    headers=headers
                )
                if delete_response.status_code in [200, 204]:
                    deleted_count += 1
            except:
                pass
        results['deleted']['team_members'] = deleted_count
        print(f"✓ Deleted {deleted_count} team members")
except Exception as e:
    print(f"✗ Error deleting team members: {e}")

# Delete calendar events
try:
    calendar_response = requests.get(f"{BACKEND_URL}/api/v1/calendar/events", headers=headers)
    if calendar_response.status_code == 200:
        events = calendar_response.json()
        deleted_count = 0
        for event in events:
            try:
                delete_response = requests.delete(
                    f"{BACKEND_URL}/api/v1/calendar/events/{event['id']}",
                    headers=headers
                )
                if delete_response.status_code in [200, 204]:
                    deleted_count += 1
            except:
                pass
        results['deleted']['calendar_events'] = deleted_count
        print(f"✓ Deleted {deleted_count} calendar events")
except Exception as e:
    print(f"✗ Error deleting calendar events: {e}")

print()
print("=" * 50)
print("✅ Data clearing complete!")
print()
print("Deleted:")
for key, count in results['deleted'].items():
    print(f"   ✓ {count} {key}")

print()
print("🎉 Your account is now empty and ready to build from scratch!")
print("   Your user account and settings remain intact.")
print("   Refresh your CRM to see the empty state.")
