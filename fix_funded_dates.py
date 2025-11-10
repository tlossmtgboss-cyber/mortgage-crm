#!/usr/bin/env python3
"""
Fix funded_date for all funded loans
"""
import requests
from datetime import datetime, timedelta
import random

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get token
response = requests.post(
    f"{API_BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
token = response.json()["access_token"]

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

print("="*80)
print("FIXING FUNDED DATES FOR PORTFOLIO LOANS")
print("="*80)

# Get all loans
response = requests.get(f"{API_BASE_URL}/api/v1/loans/", headers=headers)
loans = response.json()

funded_loans = [l for l in loans if l.get('stage') == 'Funded']
print(f"\nFound {len(funded_loans)} funded loans")

# Update each one with a realistic funded date
today = datetime.now()
updated_count = 0
failed_count = 0

print("\nUpdating funded_date for each loan...")

for i, loan in enumerate(funded_loans):
    # Set funded_date to sometime in the past 12 months
    days_ago = random.randint(1, 365)
    funded_date = today - timedelta(days=days_ago)

    # Use closing_date if available, otherwise set to random date
    if loan.get('closing_date'):
        # Set funded_date a few days after closing
        closing_date = datetime.fromisoformat(loan['closing_date'].replace('Z', '+00:00'))
        funded_date = closing_date + timedelta(days=random.randint(1, 3))

    patch_data = {
        "funded_date": funded_date.strftime("%Y-%m-%dT00:00:00")
    }

    try:
        response = requests.patch(
            f"{API_BASE_URL}/api/v1/loans/{loan['id']}",
            json=patch_data,
            headers=headers
        )

        if response.status_code == 200:
            updated_count += 1
            if (i + 1) % 10 == 0:
                print(f"  ✓ Updated {i + 1}/{len(funded_loans)} loans...")
        else:
            failed_count += 1
            if failed_count <= 3:
                print(f"  ✗ Failed to update loan {loan['id']}: {response.status_code}")
    except Exception as e:
        failed_count += 1
        if failed_count <= 3:
            print(f"  ✗ Exception updating loan {loan['id']}: {str(e)}")

print(f"\n✓ Updated {updated_count} loans")
if failed_count > 0:
    print(f"✗ Failed to update {failed_count} loans")

# Verify
print("\nVerifying...")
response = requests.get(f"{API_BASE_URL}/api/v1/loans/", headers=headers)
loans = response.json()
funded_loans = [l for l in loans if l.get('stage') == 'Funded']
loans_with_funded_date = [l for l in funded_loans if l.get('funded_date')]

print(f"Funded loans with funded_date: {len(loans_with_funded_date)}/{len(funded_loans)}")

print("\n" + "="*80)
print("COMPLETE")
print("="*80 + "\n")
