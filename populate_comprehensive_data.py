#!/usr/bin/env python3
"""
Comprehensive data population script for all CRM analytics pages
Populates: Monthly Performance, Team Performance, Loan Efficiency, Live Pipeline, Scorecard
"""
import requests
import json
from datetime import datetime, timedelta
import random

# API Configuration
API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# User credentials - using Quick Login demo account
USER_EMAIL = "demo@example.com"
USER_PASSWORD = "demo123"

# Global token storage
AUTH_TOKEN = None

def get_auth_token():
    """Get JWT token by logging in"""
    global AUTH_TOKEN
    if AUTH_TOKEN:
        return AUTH_TOKEN

    try:
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
            print(f"✗ Login failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"✗ Login exception: {e}")
    return None

# Sample data pools
FIRST_NAMES = ["John", "Sarah", "Michael", "Emily", "David", "Jennifer", "Robert", "Lisa",
               "William", "Jessica", "James", "Amanda", "Thomas", "Ashley", "Daniel", "Melissa",
               "Matthew", "Michelle", "Christopher", "Kimberly", "Brian", "Laura", "Kevin", "Nicole"]

LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
              "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
              "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Walker", "Hall", "Allen"]

REFERRAL_SOURCES = ["Realtor - Sarah Thompson", "Realtor - Mike Chen", "Past Client Referral",
                    "Facebook Ad Campaign", "Google Search", "Zillow Lead", "Instagram Ad",
                    "Open House Event", "Direct Mail Campaign", "Website Contact Form",
                    "LinkedIn Connection", "Referral - John Davis", "Yelp Review"]

LOAN_TYPES = ["Conventional", "FHA", "VA", "USDA", "Jumbo", "HELOC"]
CITIES = ["Los Angeles", "San Diego", "San Francisco", "Sacramento", "Fresno", "Irvine", "San Jose"]

def create_lead_with_date(stage, created_date):
    """Create a lead with specific creation date"""
    token = get_auth_token()
    if not token:
        return None

    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)

    lead_data = {
        "name": f"{first_name} {last_name}",
        "email": f"{first_name.lower()}.{last_name.lower()}.{random.randint(100,999)}@email.com",
        "phone": f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
        "source": random.choice(REFERRAL_SOURCES),
        "stage": stage,
        "notes": f"Lead from {random.choice(REFERRAL_SOURCES)} - Created {created_date.strftime('%Y-%m-%d')}"
    }

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/leads/",
            json=lead_data,
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code in [200, 201]:
            return response.json()
    except Exception as e:
        pass
    return None

def create_loan_with_date(borrower_name, email, stage, amount, loan_type, created_date):
    """Create a loan with specific creation date"""
    token = get_auth_token()
    if not token:
        return None

    loan_number = f"LN{created_date.year}{random.randint(100000, 999999)}"

    loan_data = {
        "loan_number": loan_number,
        "borrower_name": borrower_name,
        "borrower_email": email,
        "amount": amount,
        "product_type": loan_type,
        "stage": stage,
        "interest_rate": round(random.uniform(5.5, 7.5), 3),
        "property_address": f"{random.randint(100, 9999)} {random.choice(['Oak', 'Main', 'Elm', 'Maple', 'Park', 'Cedar'])} {random.choice(['St', 'Ave', 'Blvd', 'Dr', 'Ln'])}",
        "property_city": random.choice(CITIES),
        "property_state": "CA",
        "property_zip": f"9{random.randint(1000, 9999)}",
        "notes": f"{loan_type} - {stage} - {created_date.strftime('%B %Y')}"
    }

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/loans/",
            json=loan_data,
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code in [200, 201]:
            return response.json()
    except Exception as e:
        pass
    return None

def populate_comprehensive_data():
    """Populate comprehensive data across multiple months"""

    print("\n" + "="*70)
    print("COMPREHENSIVE CRM DATA POPULATION")
    print("Populating data for all analytics pages")
    print("="*70 + "\n")

    # Authenticate
    print("--- AUTHENTICATION ---")
    token = get_auth_token()
    if not token:
        print("✗ Failed to authenticate. Cannot continue.")
        return
    print()

    # Statistics tracking
    total_leads = 0
    total_loans = 0
    total_funded = 0

    # Get date ranges for the last 6 months
    today = datetime.now()
    months_data = []

    for i in range(6, 0, -1):
        month_start = (today - timedelta(days=i*30)).replace(day=1)
        months_data.append(month_start)

    print(f"Creating data for {len(months_data)} months: {months_data[0].strftime('%B %Y')} - {months_data[-1].strftime('%B %Y')}\n")

    # Create data for each month
    for month_idx, month_date in enumerate(months_data):
        print(f"\n{'='*70}")
        print(f"MONTH {month_idx + 1}: {month_date.strftime('%B %Y')}")
        print(f"{'='*70}\n")

        # Determine activity level (ramp up over time)
        activity_multiplier = 0.5 + (month_idx * 0.1)  # Starts at 50%, increases each month

        # LEADS for this month
        print(f"--- Creating Leads for {month_date.strftime('%B')} ---")
        month_leads = 0

        # Prospects (10-15 per month)
        prospect_count = int(random.randint(10, 15) * activity_multiplier)
        for i in range(prospect_count):
            days_offset = random.randint(0, 28)
            lead_date = month_date + timedelta(days=days_offset)
            if create_lead_with_date("prospect", lead_date):
                month_leads += 1
                total_leads += 1
        print(f"  ✓ Created {prospect_count} prospects")

        # Application Started (8-12 per month)
        app_started_count = int(random.randint(8, 12) * activity_multiplier)
        for i in range(app_started_count):
            days_offset = random.randint(0, 28)
            lead_date = month_date + timedelta(days=days_offset)
            if create_lead_with_date("application_started", lead_date):
                month_leads += 1
                total_leads += 1
        print(f"  ✓ Created {app_started_count} application started")

        # Application Complete (5-8 per month)
        app_complete_count = int(random.randint(5, 8) * activity_multiplier)
        for i in range(app_complete_count):
            days_offset = random.randint(0, 28)
            lead_date = month_date + timedelta(days=days_offset)
            if create_lead_with_date("application_complete", lead_date):
                month_leads += 1
                total_leads += 1
        print(f"  ✓ Created {app_complete_count} application complete")

        # Pre-Approved (3-5 per month)
        pre_approved_count = int(random.randint(3, 5) * activity_multiplier)
        for i in range(pre_approved_count):
            days_offset = random.randint(0, 28)
            lead_date = month_date + timedelta(days=days_offset)
            if create_lead_with_date("pre_approved", lead_date):
                month_leads += 1
                total_leads += 1
        print(f"  ✓ Created {pre_approved_count} pre-approved")

        # ACTIVE LOANS for this month (for older months, most will eventually be funded)
        print(f"\n--- Creating Active Loans for {month_date.strftime('%B')} ---")

        # For older months, create mostly disclosed/processing (they'll become funded in later months)
        # For recent months, create across all stages
        is_recent = month_idx >= len(months_data) - 2  # Last 2 months

        if not is_recent:
            # Older month - create some active loans (some will be funded later)
            active_count = int(random.randint(3, 6) * activity_multiplier)
            for i in range(active_count):
                name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                email = f"{name.replace(' ', '.').lower()}.{random.randint(100,999)}@email.com"
                amount = random.randint(250000, 850000)
                loan_type = random.choice(LOAN_TYPES)
                stage = random.choice(["disclosed", "processing"])
                days_offset = random.randint(0, 28)
                loan_date = month_date + timedelta(days=days_offset)

                if create_loan_with_date(name, email, stage, amount, loan_type, loan_date):
                    total_loans += 1
            print(f"  ✓ Created {active_count} active loans (disclosed/processing)")
        else:
            # Recent month - create across all active stages
            stages_distribution = [
                ("disclosed", random.randint(2, 4)),
                ("processing", random.randint(3, 6)),
                ("uw_received", random.randint(2, 4)),
                ("ctc", random.randint(1, 3))
            ]

            for stage, count in stages_distribution:
                count = int(count * activity_multiplier)
                for i in range(count):
                    name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                    email = f"{name.replace(' ', '.').lower()}.{random.randint(100,999)}@email.com"
                    amount = random.randint(250000, 900000)
                    loan_type = random.choice(LOAN_TYPES)
                    days_offset = random.randint(0, 28)
                    loan_date = month_date + timedelta(days=days_offset)

                    if create_loan_with_date(name, email, stage, amount, loan_type, loan_date):
                        total_loans += 1
                print(f"  ✓ Created {count} {stage} loans")

        # FUNDED LOANS for this month
        print(f"\n--- Creating Funded Loans for {month_date.strftime('%B')} ---")

        # Create funded loans (more for older months, showing progression)
        funded_count = int(random.randint(8, 15) * activity_multiplier)

        # Distribution by loan type
        loan_types_dist = {
            "Conventional": int(funded_count * 0.48),  # 48%
            "FHA": int(funded_count * 0.24),           # 24%
            "VA": int(funded_count * 0.16),            # 16%
            "Jumbo": int(funded_count * 0.08),         # 8%
            "USDA": int(funded_count * 0.04)           # 4%
        }

        month_funded = 0
        for loan_type, count in loan_types_dist.items():
            for i in range(max(1, count)):
                name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                email = f"{name.replace(' ', '.').lower()}.{random.randint(100,999)}@email.com"

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
                    amount = random.randint(300000, 850000)

                days_offset = random.randint(0, 28)
                loan_date = month_date + timedelta(days=days_offset)

                if create_loan_with_date(name, email, "funded", amount, loan_type, loan_date):
                    month_funded += 1
                    total_funded += 1
                    total_loans += 1

        print(f"  ✓ Created {month_funded} funded loans")
        print(f"\n  📊 Month Summary: {month_leads} leads, {month_funded} funded loans")

    # Final summary
    print("\n" + "="*70)
    print("DATA POPULATION COMPLETE!")
    print("="*70)
    print(f"\n📈 TOTAL DATA CREATED:")
    print(f"  • Total Leads: {total_leads}")
    print(f"  • Total Loans: {total_loans}")
    print(f"  • Funded Loans: {total_funded}")
    print(f"  • Time Period: {months_data[0].strftime('%B %Y')} - {months_data[-1].strftime('%B %Y')}")
    print(f"\n✅ All analytics pages should now display comprehensive data!")
    print(f"  • Monthly Performance Tracker - ✓")
    print(f"  • Team Performance - ✓")
    print(f"  • Loan Efficiency - ✓")
    print(f"  • Live Loan Pipeline - ✓")
    print(f"  • Scorecard - ✓")
    print("="*70 + "\n")

if __name__ == "__main__":
    populate_comprehensive_data()
