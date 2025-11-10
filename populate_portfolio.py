#!/usr/bin/env python3
"""
Populate portfolio with dummy funded loans (borrowers)
"""
import requests
import random
from datetime import datetime, timedelta

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"
USER_EMAIL = "demo@example.com"
USER_PASSWORD = "demo123"

# Realistic borrower data
FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Barbara", "David", "Elizabeth", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White",
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young",
    "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"
]

CITIES_STATES = [
    ("Austin", "TX"), ("Dallas", "TX"), ("Houston", "TX"), ("San Antonio", "TX"),
    ("Phoenix", "AZ"), ("Scottsdale", "AZ"), ("Denver", "CO"), ("Boulder", "CO"),
    ("Los Angeles", "CA"), ("San Diego", "CA"), ("San Francisco", "CA"), ("Sacramento", "CA"),
    ("Seattle", "WA"), ("Portland", "OR"), ("Miami", "FL"), ("Tampa", "FL"),
    ("Atlanta", "GA"), ("Charlotte", "NC"), ("Nashville", "TN"), ("Raleigh", "NC")
]

STREETS = [
    "Oak", "Maple", "Pine", "Cedar", "Elm", "Willow", "Birch", "Cherry",
    "Walnut", "Ash", "Cypress", "Magnolia", "Hickory", "Poplar", "Spruce",
    "Main", "Park", "Lake", "Hill", "Valley", "River", "Mountain", "Sunset"
]

STREET_TYPES = ["St", "Ave", "Dr", "Ln", "Rd", "Blvd", "Ct", "Way", "Pl"]

PROPERTY_TYPES = ["Single Family", "Condo", "Townhouse", "Multi-Family"]
LOAN_PROGRAMS = ["Conventional", "FHA", "VA", "USDA", "Jumbo"]
LOAN_TYPES = ["Purchase", "Refinance", "Cash-Out Refi"]

PROCESSORS = ["Sarah Mitchell", "John Davis", "Emily Chen", "Michael Brown"]
UNDERWRITERS = ["Robert Wilson", "Lisa Anderson", "David Martinez", "Jennifer Taylor"]
REALTORS = ["Amanda Clark", "James Rodriguez", "Maria Garcia", "Christopher Lee"]
TITLE_COMPANIES = ["First American Title", "Chicago Title", "Stewart Title", "Fidelity National"]

def get_token():
    """Authenticate and get JWT token"""
    response = requests.post(
        f"{API_BASE_URL}/token",
        data={"username": USER_EMAIL, "password": USER_PASSWORD}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        print(f"✗ Login failed: {response.status_code}")
        return None

def generate_borrower_name():
    """Generate realistic borrower name"""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return f"{first} {last}", first, last

def generate_email(first, last):
    """Generate email from name"""
    domains = ["gmail.com", "yahoo.com", "outlook.com", "icloud.com", "email.com"]
    return f"{first.lower()}.{last.lower()}@{random.choice(domains)}"

def generate_phone():
    """Generate phone number"""
    return f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"

def generate_address():
    """Generate property address"""
    number = random.randint(100, 9999)
    street = random.choice(STREETS)
    street_type = random.choice(STREET_TYPES)
    city, state = random.choice(CITIES_STATES)
    zip_code = f"{random.randint(10000, 99999)}"

    return {
        "address": f"{number} {street} {street_type}",
        "city": city,
        "state": state,
        "zip": zip_code
    }

def generate_loan_number(index):
    """Generate loan number"""
    return f"LN{datetime.now().year}{str(index + 1000).zfill(4)}"

def populate_portfolio():
    """Create funded loans for portfolio"""

    print("\n" + "="*70)
    print("POPULATE PORTFOLIO WITH FUNDED LOANS")
    print("="*70 + "\n")

    # Authenticate
    print("1. AUTHENTICATING...")
    print("-" * 70)
    token = get_token()
    if not token:
        print("✗ Failed to authenticate")
        return
    print(f"✓ Successfully authenticated\n")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Create 50 funded loans (portfolio borrowers)
    print("2. CREATING FUNDED LOANS FOR PORTFOLIO...")
    print("-" * 70)

    created_count = 0
    failed_count = 0

    # Create loans from the past 12 months
    today = datetime.now()

    for i in range(50):
        # Generate borrower data
        full_name, first_name, last_name = generate_borrower_name()
        email = generate_email(first_name, last_name)
        phone = generate_phone()
        address = generate_address()

        # Random funded date in the past 12 months
        days_ago = random.randint(1, 365)
        funded_date = today - timedelta(days=days_ago)

        # Random closing date a few days before funded date
        closing_date = funded_date - timedelta(days=random.randint(1, 3))

        # Loan details
        loan_amount = random.randint(200000, 800000)
        property_value = int(loan_amount * random.uniform(1.15, 1.35))
        down_payment = int(property_value * random.uniform(0.05, 0.25))
        interest_rate = round(random.uniform(5.5, 7.5), 3)

        loan_data = {
            "loan_number": generate_loan_number(i),
            "borrower_name": full_name,
            "borrower_email": email,
            "borrower_phone": phone,
            "amount": loan_amount,
            "product_type": random.choice(LOAN_PROGRAMS),
            "loan_type": random.choice(LOAN_TYPES),
            "interest_rate": interest_rate,
            "term": random.choice([180, 240, 360]),
            "purchase_price": property_value,
            "down_payment": down_payment,
            "property_address": address["address"],
            "property_city": address["city"],
            "property_state": address["state"],
            "property_zip": address["zip"],
            "closing_date": closing_date.strftime("%Y-%m-%dT00:00:00"),
            "processor": random.choice(PROCESSORS),
            "underwriter": random.choice(UNDERWRITERS),
            "realtor_agent": random.choice(REALTORS),
            "title_company": random.choice(TITLE_COMPANIES),
            "stage": "Funded",  # This makes it appear in portfolio
            "notes": f"Portfolio loan funded on {funded_date.strftime('%m/%d/%Y')}"
        }

        try:
            response = requests.post(
                f"{API_BASE_URL}/api/v1/loans/",
                json=loan_data,
                headers=headers
            )

            if response.status_code in [200, 201]:
                created_loan = response.json()
                created_count += 1

                # Update the funded_date via PATCH (if the create doesn't set it)
                patch_data = {
                    "funded_date": funded_date.strftime("%Y-%m-%dT00:00:00")
                }
                requests.patch(
                    f"{API_BASE_URL}/api/v1/loans/{created_loan['id']}",
                    json=patch_data,
                    headers=headers
                )

                if (i + 1) % 10 == 0:
                    print(f"✓ Created {i + 1}/50 funded loans...")
            else:
                failed_count += 1
                print(f"✗ Failed to create loan {i + 1}: {response.status_code} - {response.text[:100]}")

        except Exception as e:
            failed_count += 1
            print(f"✗ Exception creating loan {i + 1}: {str(e)}")

    print(f"\n✓ Created {created_count} funded loans")
    if failed_count > 0:
        print(f"✗ Failed to create {failed_count} loans")
    print()

    # Verify portfolio
    print("3. VERIFYING PORTFOLIO...")
    print("-" * 70)

    try:
        portfolio_response = requests.get(
            f"{API_BASE_URL}/api/v1/portfolio/",
            headers=headers
        )

        if portfolio_response.status_code == 200:
            portfolio_loans = portfolio_response.json()
            print(f"✓ Portfolio now contains {len(portfolio_loans)} funded loans")

            # Get portfolio stats
            stats_response = requests.get(
                f"{API_BASE_URL}/api/v1/portfolio/stats",
                headers=headers
            )

            if stats_response.status_code == 200:
                stats = stats_response.json()
                print(f"  Total Loans: {stats['total_loans']}")
                print(f"  Total Volume: ${stats['total_volume']:,.2f}")
                print(f"  Active Loans: {stats['active_loans']}")
        else:
            print(f"✗ Failed to retrieve portfolio: {portfolio_response.status_code}")
    except Exception as e:
        print(f"✗ Exception verifying portfolio: {str(e)}")

    print()
    print("="*70)
    print("PORTFOLIO POPULATION COMPLETE")
    print("="*70)
    print(f"✅ Successfully created {created_count} funded loans (borrowers) in portfolio")
    print("="*70 + "\n")

if __name__ == "__main__":
    populate_portfolio()
