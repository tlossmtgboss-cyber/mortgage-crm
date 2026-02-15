"""
Seed Script: Generate 100 MUM Clients with Realistic Loan Data
"""
import os
import sys
import random
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# First names pool
FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Barbara", "William", "Elizabeth", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Charles", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Andrew", "Emily", "Paul", "Donna", "Joshua", "Michelle",
    "Kenneth", "Carol", "Kevin", "Amanda", "Brian", "Dorothy", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Jason", "Rebecca", "Edward", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
    "Nicholas", "Angela", "Eric", "Shirley", "Jonathan", "Brenda", "Stephen", "Emma",
    "Larry", "Anna", "Justin", "Pamela", "Scott", "Nicole", "Brandon", "Samantha",
    "Benjamin", "Katherine", "Samuel", "Christine", "Raymond", "Debra", "Gregory", "Rachel",
    "Frank", "Carolyn", "Alexander", "Janet", "Patrick", "Catherine", "Jack", "Maria"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Thompson", "White", "Harris",
    "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen",
    "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
    "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter",
    "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker", "Cruz",
    "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy", "Cook",
    "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey", "Reed",
    "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson", "Watson",
    "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz",
    "Hughes", "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long"
]

LOAN_TYPES = [
    "30-Year Fixed", "15-Year Fixed", "20-Year Fixed",
    "FHA 30-Year", "VA 30-Year", "Jumbo 30-Year", "Jumbo 15-Year"
]

SERVICERS = [
    "Wells Fargo", "Rocket Mortgage", "Chase", "Bank of America",
    "US Bank", "PNC Bank", "Caliber Home Loans", "Mr. Cooper",
    "Pennymac", "Freedom Mortgage", "Lakeview Loan Servicing", "Carrington Mortgage"
]

def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL')

def generate_phone():
    """Generate realistic phone number"""
    return f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"

def generate_loan_number(prefix="LN"):
    """Generate realistic loan number"""
    return f"{prefix}{random.randint(100000000, 999999999)}"

def get_interest_rate_for_date(closing_date):
    """
    Get realistic interest rate based on closing date
    Older loans = lower rates, recent loans = higher rates
    """
    years_ago = (date.today() - closing_date).days / 365.25

    # Rate ranges by year
    if years_ago >= 5:  # 2019-2020
        return round(random.uniform(3.5, 4.5), 4)
    elif years_ago >= 4:  # 2020-2021
        return round(random.uniform(2.75, 3.5), 4)
    elif years_ago >= 3:  # 2021-2022
        return round(random.uniform(3.0, 4.0), 4)
    elif years_ago >= 2:  # 2022-2023
        return round(random.uniform(5.0, 6.5), 4)
    elif years_ago >= 1:  # 2023-2024
        return round(random.uniform(6.5, 7.5), 4)
    else:  # 2024-2025
        return round(random.uniform(6.0, 7.25), 4)

def calculate_monthly_piti(loan_amount, rate, loan_type, property_value):
    """Calculate monthly payment including PITI"""
    # Determine loan term
    if '15' in loan_type:
        months = 180
    elif '20' in loan_type:
        months = 240
    else:
        months = 360

    # Calculate P&I
    monthly_rate = rate / 100 / 12
    if monthly_rate == 0:
        principal_interest = loan_amount / months
    else:
        principal_interest = loan_amount * (monthly_rate * pow(1 + monthly_rate, months)) / \
                           (pow(1 + monthly_rate, months) - 1)

    # Estimate taxes (1.2% of property value per year)
    monthly_taxes = (property_value * 0.012) / 12

    # Estimate insurance ($800-$1500 per year)
    monthly_insurance = random.uniform(800, 1500) / 12

    # PMI if LTV > 80%
    ltv = loan_amount / property_value
    monthly_pmi = (loan_amount * 0.005 / 12) if ltv > 0.80 else 0

    return {
        'principal_interest': round(principal_interest, 2),
        'monthly_taxes': round(monthly_taxes, 2),
        'monthly_insurance': round(monthly_insurance, 2),
        'monthly_pmi': round(monthly_pmi, 2) if monthly_pmi > 0 else None
    }

def determine_opportunities(rate, equity_pct, equity_amt, ltv, is_veteran):
    """Determine refinance/HELOC opportunities"""
    current_market_rate = 6.5

    refinance_opp = rate >= (current_market_rate + 0.75)
    rate_rebound_opp = rate >= 6.5 and equity_pct >= 0.20
    heloc_opp = equity_pct >= 0.25 and equity_amt >= 50000
    high_equity_opp = equity_pct >= 0.50 or equity_amt >= 150000

    return {
        'refinance': refinance_opp,
        'rate_rebound': rate_rebound_opp,
        'heloc': heloc_opp,
        'high_equity': high_equity_opp
    }

def generate_mum_clients():
    """Generate 100 MUM clients with realistic data"""
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()

    print("🏠 Generating 100 MUM clients...")

    for i in range(100):
        # Generate client info
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        client_name = f"{first_name} {last_name}"
        email = f"{first_name.lower()}.{last_name.lower()}@email.com"
        phone = generate_phone()

        # Generate loan details
        loan_type = random.choice(LOAN_TYPES)
        is_veteran = 'VA' in loan_type

        # Determine loan amount range based on type
        if 'Jumbo' in loan_type:
            original_amount = round(random.uniform(550000, 950000), 2)
        elif 'FHA' in loan_type:
            original_amount = round(random.uniform(200000, 450000), 2)
        else:
            original_amount = round(random.uniform(250000, 650000), 2)

        # Generate dates (spread over past 5 years)
        days_ago = random.randint(30, 1825)  # 1 month to 5 years
        closing_date = date.today() - timedelta(days=days_ago)
        first_payment_date = closing_date + timedelta(days=45)  # ~45 days after closing

        # Get appropriate interest rate for that time period
        interest_rate = get_interest_rate_for_date(closing_date)

        # Property value (loan amount / random LTV between 75-95%)
        ltv_at_closing = random.uniform(0.75, 0.95)
        appraisal_value = round(original_amount / ltv_at_closing, 2)

        # Calculate payments
        payments = calculate_monthly_piti(original_amount, interest_rate, loan_type, appraisal_value)

        # Servicer info
        servicer = random.choice(SERVICERS)
        has_escrow = random.choice([True, True, True, False])  # 75% have escrow

        # Loan numbers
        servicing_number = generate_loan_number("SVC")
        origination_number = generate_loan_number("ORG")

        # Calculate current values (would be done by API, but we'll store initial estimates)
        current_balance = original_amount  # Simplified for now
        current_value = appraisal_value  # Simplified for now
        ltv = round(current_balance / current_value, 4)

        # Engagement data
        last_contact = closing_date + timedelta(days=random.randint(30, days_ago))
        next_touchpoint = date.today() + timedelta(days=random.randint(1, 30))
        engagement_score = random.randint(50, 100)
        referrals = random.choices([0, 0, 0, 1, 1, 2, 2, 3, 4, 5], k=1)[0]

        # Calculate equity (simplified)
        equity_amt = current_value - current_balance
        equity_pct = round(equity_amt / current_value, 4)

        # Determine opportunities
        opps = determine_opportunities(interest_rate, equity_pct, equity_amt, ltv, is_veteran)

        # Insert into database
        insert_query = text("""
            INSERT INTO mum_clients (
                client_name, email, phone,
                original_loan_amount, current_loan_amount, interest_rate,
                servicing_loan_number, origination_loan_number,
                appraisal_value_at_closing, current_property_value,
                current_servicer, has_escrow,
                current_principal_payment, monthly_taxes, monthly_insurance, monthly_pmi,
                loan_type, is_veteran, ltv,
                closing_date, first_payment_date,
                last_contact_date, next_touchpoint_date, engagement_score,
                refinance_opportunity, heloc_opportunity, rate_rebound_opportunity, high_equity_opportunity,
                referrals_sent, status, equity_amount, equity_percentage
            ) VALUES (
                :client_name, :email, :phone,
                :original_amount, :current_balance, :interest_rate,
                :servicing_number, :origination_number,
                :appraisal_value, :current_value,
                :servicer, :has_escrow,
                :principal_payment, :monthly_taxes, :monthly_insurance, :monthly_pmi,
                :loan_type, :is_veteran, :ltv,
                :closing_date, :first_payment_date,
                :last_contact, :next_touchpoint, :engagement_score,
                :refinance_opp, :heloc_opp, :rate_rebound_opp, :high_equity_opp,
                :referrals, 'active', :equity_amt, :equity_pct
            )
        """)

        session.execute(insert_query, {
            'client_name': client_name,
            'email': email,
            'phone': phone,
            'original_amount': original_amount,
            'current_balance': current_balance,
            'interest_rate': interest_rate,
            'servicing_number': servicing_number,
            'origination_number': origination_number,
            'appraisal_value': appraisal_value,
            'current_value': current_value,
            'servicer': servicer,
            'has_escrow': has_escrow,
            'principal_payment': payments['principal_interest'],
            'monthly_taxes': payments['monthly_taxes'],
            'monthly_insurance': payments['monthly_insurance'],
            'monthly_pmi': payments['monthly_pmi'],
            'loan_type': loan_type,
            'is_veteran': is_veteran,
            'ltv': ltv,
            'closing_date': closing_date,
            'first_payment_date': first_payment_date,
            'last_contact': last_contact,
            'next_touchpoint': next_touchpoint,
            'engagement_score': engagement_score,
            'refinance_opp': opps['refinance'],
            'heloc_opp': opps['heloc'],
            'rate_rebound_opp': opps['rate_rebound'],
            'high_equity_opp': opps['high_equity'],
            'referrals': referrals,
            'equity_amt': equity_amt,
            'equity_pct': equity_pct
        })

        if (i + 1) % 10 == 0:
            print(f"  Created {i + 1} clients...")

    session.commit()
    session.close()

    print("✅ Successfully generated 100 MUM clients!")
    print(f"   - Loan types: {', '.join(set(LOAN_TYPES))}")
    print(f"   - Closing dates: {(date.today() - timedelta(days=1825)).isoformat()} to {date.today().isoformat()}")
    print(f"   - Interest rates: 2.75% to 7.5%")

if __name__ == "__main__":
    generate_mum_clients()
