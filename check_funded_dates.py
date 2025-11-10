#!/usr/bin/env python3
import requests

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get token
response = requests.post(
    f"{API_BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)
token = response.json()["access_token"]

headers = {"Authorization": f"Bearer {token}"}

# Get all loans
response = requests.get(f"{API_BASE_URL}/api/v1/loans/", headers=headers)
loans = response.json()

funded_loans = [l for l in loans if l.get('stage') == 'Funded']

print(f"Total loans: {len(loans)}")
print(f"Funded loans: {len(funded_loans)}")

# Check funded_date
loans_with_funded_date = [l for l in funded_loans if l.get('funded_date')]
loans_without_funded_date = [l for l in funded_loans if not l.get('funded_date')]

print(f"\nFunded loans WITH funded_date: {len(loans_with_funded_date)}")
print(f"Funded loans WITHOUT funded_date: {len(loans_without_funded_date)}")

if loans_without_funded_date:
    print(f"\nLoans missing funded_date:")
    for loan in loans_without_funded_date[:5]:
        print(f"  ID {loan['id']}: {loan.get('borrower_name')} - {loan.get('loan_number')}")
