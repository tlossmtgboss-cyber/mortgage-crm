#!/usr/bin/env python3
"""
Script to populate the CRM with dummy data for scorecard testing
"""
import requests
import json
from datetime import datetime, timedelta
import random

# API Configuration
API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"
API_KEY = "185b7101-9435-44da-87ab-b7582c4e4607"

# User credentials - using Quick Login demo account
USER_EMAIL = "demo@example.com"
USER_PASSWORD = "demo123"

# Global token storage
AUTH_TOKEN = None

def get_auth_token():
    """Get JWT token by logging in or registering"""
    global AUTH_TOKEN

    if AUTH_TOKEN:
        return AUTH_TOKEN

    # Try to login first
    try:
        login_data = {
            "username": USER_EMAIL,
            "password": USER_PASSWORD
        }
        response = requests.post(
            f"{API_BASE_URL}/token",
            data=login_data  # Form data for OAuth2
        )
        if response.status_code == 200:
            AUTH_TOKEN = response.json()["access_token"]
            print(f"✓ Logged in successfully as {USER_EMAIL}")
            return AUTH_TOKEN
        else:
            print(f"Login failed with status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Login exception: {e}")

    # If login fails, try to register
    print("Attempting to register new user...")
    try:
        register_data = {
            "email": USER_EMAIL,
            "password": USER_PASSWORD,
            "full_name": "Demo User"
        }
        response = requests.post(
            f"{API_BASE_URL}/api/v1/register",
            json=register_data
        )
        if response.status_code in [200, 201]:
            print(f"✓ Registration successful")
            # Now login with new account
            login_data = {
                "username": USER_EMAIL,
                "password": USER_PASSWORD
            }
            response = requests.post(
                f"{API_BASE_URL}/token",
                data=login_data
            )
            if response.status_code == 200:
                AUTH_TOKEN = response.json()["access_token"]
                print(f"✓ Logged in successfully as {USER_EMAIL}")
                return AUTH_TOKEN
            else:
                print(f"✗ Login after registration failed: {response.status_code} - {response.text}")
        else:
            print(f"✗ Registration failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"✗ Registration exception: {e}")

    return None

# Sample data
FIRST_NAMES = ["John", "Sarah", "Michael", "Emily", "David", "Jennifer", "Robert", "Lisa", "William", "Jessica",
               "James", "Amanda", "Thomas", "Ashley", "Daniel", "Melissa", "Matthew", "Michelle", "Christopher", "Kimberly"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
              "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]

REFERRAL_SOURCES = ["Realtor Partner", "Past Client Referral", "Facebook Ad", "Google Search", "Zillow",
                    "Instagram", "Open House", "Direct Mail", "Website Contact", "LinkedIn"]

LOAN_TYPES = ["Conventional", "FHA", "VA", "USDA", "Jumbo", "Construction"]

LEAD_STAGES = ["prospect", "application_started", "application_complete", "pre_approved"]
LOAN_STAGES = ["disclosed", "processing", "uw_received", "ctc", "funded"]

def create_lead(stage, days_ago=0):
    """Create a single lead"""
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)

    lead_data = {
        "name": f"{first_name} {last_name}",
        "email": f"{first_name.lower()}.{last_name.lower()}@email.com",
        "phone": f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
        "source": random.choice(REFERRAL_SOURCES),
        "stage": stage,
        "notes": f"Lead from {random.choice(REFERRAL_SOURCES)}"
    }

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/leads/",
            json=lead_data,
            headers={"X-API-Key": API_KEY}
        )
        if response.status_code in [200, 201]:
            print(f"✓ Created lead: {lead_data['name']} ({stage})")
            return response.json()
        else:
            print(f"✗ Failed to create lead: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error creating lead: {e}")
        return None

def create_loan(borrower_name, email, stage, amount, loan_type, days_ago=0):
    """Create a single loan"""

    token = get_auth_token()
    if not token:
        print(f"✗ Cannot create loan - no auth token")
        return None

    # Generate unique loan number
    loan_number = f"LN{datetime.now().year}{random.randint(100000, 999999)}"

    loan_data = {
        "loan_number": loan_number,
        "borrower_name": borrower_name,
        "borrower_email": email,
        "amount": amount,
        "product_type": loan_type,
        "stage": stage,
        "interest_rate": round(random.uniform(5.5, 7.5), 3),
        "property_address": f"{random.randint(100, 9999)} {random.choice(['Oak', 'Main', 'Elm', 'Maple', 'Park'])} {random.choice(['St', 'Ave', 'Blvd', 'Dr', 'Ln'])}",
        "property_city": random.choice(["Los Angeles", "San Diego", "San Francisco", "Sacramento", "Fresno"]),
        "property_state": "CA",
        "property_zip": f"9{random.randint(1000, 9999)}",
        "notes": f"{loan_type} loan in {stage} stage"
    }

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/loans/",
            json=loan_data,
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code in [200, 201]:
            print(f"✓ Created loan: {borrower_name} - ${amount:,} ({stage})")
            return response.json()
        else:
            print(f"✗ Failed to create loan: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error creating loan: {e}")
        return None

def populate_data():
    """Main function to populate all dummy data"""

    print("\n" + "="*60)
    print("POPULATING SCORECARD DATA")
    print("="*60 + "\n")

    # Authenticate first
    print("--- AUTHENTICATION ---")
    token = get_auth_token()
    if not token:
        print("✗ Failed to authenticate. Cannot continue.")
        return
    print()

    # Track created leads for conversion to loans
    created_leads = []

    # Create Leads (50 total)
    print("\n--- CREATING LEADS ---")

    # 20 Prospects
    print("\nProspects (20):")
    for i in range(20):
        lead = create_lead("prospect", days_ago=random.randint(1, 60))
        if lead:
            created_leads.append(lead)

    # 15 Application Started
    print("\nApplication Started (15):")
    for i in range(15):
        lead = create_lead("application_started", days_ago=random.randint(1, 45))
        if lead:
            created_leads.append(lead)

    # 10 Application Complete
    print("\nApplication Complete (10):")
    for i in range(10):
        lead = create_lead("application_complete", days_ago=random.randint(1, 30))
        if lead:
            created_leads.append(lead)

    # 5 Pre-Approved
    print("\nPre-Approved (5):")
    for i in range(5):
        lead = create_lead("pre_approved", days_ago=random.randint(1, 20))
        if lead:
            created_leads.append(lead)

    # Create Active Loans (various stages)
    print("\n\n--- CREATING ACTIVE LOANS ---")

    # 8 Disclosed
    print("\nDisclosed (8):")
    for i in range(8):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        email = f"{name.replace(' ', '.').lower()}@email.com"
        amount = random.randint(250000, 800000)
        loan_type = random.choice(LOAN_TYPES)
        create_loan(name, email, "disclosed", amount, loan_type, days_ago=random.randint(1, 15))

    # 12 Processing
    print("\nProcessing (12):")
    for i in range(12):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        email = f"{name.replace(' ', '.').lower()}@email.com"
        amount = random.randint(250000, 850000)
        loan_type = random.choice(LOAN_TYPES)
        create_loan(name, email, "processing", amount, loan_type, days_ago=random.randint(1, 25))

    # 6 UW Received
    print("\nUnderwriting (6):")
    for i in range(6):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        email = f"{name.replace(' ', '.').lower()}@email.com"
        amount = random.randint(300000, 900000)
        loan_type = random.choice(LOAN_TYPES)
        create_loan(name, email, "uw_received", amount, loan_type, days_ago=random.randint(1, 20))

    # 4 Clear to Close
    print("\nClear to Close (4):")
    for i in range(4):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        email = f"{name.replace(' ', '.').lower()}@email.com"
        amount = random.randint(350000, 950000)
        loan_type = random.choice(LOAN_TYPES)
        create_loan(name, email, "ctc", amount, loan_type, days_ago=random.randint(1, 10))

    # Create Funded Loans (Portfolio) - 25 total
    print("\n\n--- CREATING FUNDED LOANS (PORTFOLIO) ---")
    print("\nFunded Loans (25):")

    # Distribution by loan type
    loan_type_counts = {
        "Conventional": 12,
        "FHA": 6,
        "VA": 4,
        "Jumbo": 2,
        "USDA": 1
    }

    for loan_type, count in loan_type_counts.items():
        for i in range(count):
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            email = f"{name.replace(' ', '.').lower()}@email.com"

            # Vary amounts by loan type
            if loan_type == "Jumbo":
                amount = random.randint(900000, 2500000)
            elif loan_type == "VA":
                amount = random.randint(250000, 600000)
            elif loan_type == "FHA":
                amount = random.randint(200000, 500000)
            elif loan_type == "USDA":
                amount = random.randint(150000, 400000)
            else:  # Conventional
                amount = random.randint(300000, 800000)

            create_loan(name, email, "funded", amount, loan_type, days_ago=random.randint(1, 300))

    print("\n" + "="*60)
    print("DATA POPULATION COMPLETE!")
    print("="*60)
    print(f"\nTotal Leads Created: ~50")
    print(f"Total Active Loans Created: ~30")
    print(f"Total Funded Loans Created: 25")
    print(f"\nYour scorecard should now show realistic data!")
    print("="*60 + "\n")

if __name__ == "__main__":
    populate_data()
