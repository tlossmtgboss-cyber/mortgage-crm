#!/usr/bin/env python3
"""
QA Test Data Generator
Creates realistic test data for comprehensive QA testing scenarios
"""

import random
import string
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from decimal import Decimal
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestDataGenerator:
    """Generate realistic test data for QA scenarios"""

    # Sample data pools
    FIRST_NAMES = [
        "John", "Jane", "Michael", "Sarah", "David", "Emily", "Robert", "Jessica",
        "William", "Jennifer", "James", "Amanda", "Joseph", "Ashley", "Charles",
        "Stephanie", "Thomas", "Nicole", "Christopher", "Elizabeth", "Daniel",
        "Maria", "Matthew", "Patricia", "Anthony", "Linda", "Mark", "Barbara"
    ]

    LAST_NAMES = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
        "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
        "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
        "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez",
        "O'Brien", "O'Connor", "McDonald", "Von Schmidt", "De La Cruz"  # Edge cases
    ]

    STREET_NAMES = [
        "Main Street", "Oak Avenue", "Maple Drive", "Cedar Lane", "Pine Road",
        "Elm Street", "Washington Boulevard", "Lincoln Avenue", "Park Place",
        "Lake View Drive", "Highland Avenue", "Sunset Boulevard", "River Road",
        "Mountain View Lane", "Forest Drive", "Valley Road", "Spring Street"
    ]

    CITIES = [
        ("New York", "NY", "10001"), ("Los Angeles", "CA", "90001"),
        ("Chicago", "IL", "60601"), ("Houston", "TX", "77001"),
        ("Phoenix", "AZ", "85001"), ("Philadelphia", "PA", "19101"),
        ("San Antonio", "TX", "78201"), ("San Diego", "CA", "92101"),
        ("Dallas", "TX", "75201"), ("San Jose", "CA", "95101"),
        ("Austin", "TX", "78701"), ("Jacksonville", "FL", "32099"),
        ("San Juan", "PR", "00901"),  # Puerto Rico
        ("Honolulu", "HI", "96801"),  # Hawaii
    ]

    EMPLOYERS = [
        ("Google LLC", "1600 Amphitheatre Parkway", "Mountain View", "CA", "94043"),
        ("Microsoft Corporation", "One Microsoft Way", "Redmond", "WA", "98052"),
        ("Apple Inc.", "One Apple Park Way", "Cupertino", "CA", "95014"),
        ("Amazon.com Inc.", "410 Terry Ave N", "Seattle", "WA", "98109"),
        ("Meta Platforms Inc.", "1 Hacker Way", "Menlo Park", "CA", "94025"),
        ("Acme Corporation", "123 Business Park", "Anytown", "CA", "90210"),
        ("First National Bank", "100 Finance Street", "New York", "NY", "10005"),
        ("General Hospital", "500 Medical Center Drive", "Boston", "MA", "02101"),
    ]

    JOB_TITLES = [
        "Software Engineer", "Product Manager", "Sales Manager", "Accountant",
        "Nurse", "Teacher", "Marketing Director", "Operations Manager",
        "Financial Analyst", "Project Manager", "HR Manager", "Data Scientist",
        "Registered Nurse", "Attorney", "Physician", "Consultant"
    ]

    LOAN_PURPOSES = ["purchase", "refinance", "cash_out_refinance"]
    PROPERTY_TYPES = ["single_family", "condo", "townhouse", "multi_family"]
    OCCUPANCY_TYPES = ["primary_residence", "second_home", "investment"]

    def __init__(self, seed: int = None):
        """Initialize with optional seed for reproducibility"""
        if seed:
            random.seed(seed)

    def generate_ssn(self) -> str:
        """Generate fake SSN (format only, not valid)"""
        # Use obviously fake area numbers (900-999 are not assigned)
        area = random.randint(900, 999)
        group = random.randint(10, 99)
        serial = random.randint(1000, 9999)
        return f"{area}-{group}-{serial}"

    def generate_phone(self) -> str:
        """Generate fake phone number"""
        # Use 555 exchange (reserved for fiction)
        area = random.choice(["212", "310", "415", "512", "702", "813"])
        return f"+1{area}555{random.randint(1000, 9999)}"

    def generate_email(self, first_name: str, last_name: str) -> str:
        """Generate email based on name"""
        domains = ["gmail.com", "yahoo.com", "outlook.com", "example.com"]
        separator = random.choice([".", "_", ""])
        num = random.randint(1, 99) if random.random() > 0.5 else ""
        return f"{first_name.lower()}{separator}{last_name.lower()}{num}@{random.choice(domains)}"

    def generate_address(self) -> Dict:
        """Generate realistic address"""
        street_num = random.randint(100, 9999)
        street = random.choice(self.STREET_NAMES)
        city, state, zip_code = random.choice(self.CITIES)

        # Add unit number sometimes
        unit = ""
        if random.random() > 0.7:
            unit = f"Apt {random.randint(1, 999)}"

        return {
            "street": f"{street_num} {street}",
            "unit": unit,
            "city": city,
            "state": state,
            "zip_code": zip_code,
            "county": f"{city} County"
        }

    def generate_dob(self, min_age: int = 25, max_age: int = 65) -> str:
        """Generate date of birth"""
        today = datetime.now()
        age = random.randint(min_age, max_age)
        birth_year = today.year - age
        birth_month = random.randint(1, 12)
        birth_day = random.randint(1, 28)  # Safe for all months
        return f"{birth_year}-{birth_month:02d}-{birth_day:02d}"

    def generate_income(self, profile: str = "standard") -> Dict:
        """Generate income data based on profile"""
        profiles = {
            "low": (3000, 5000),
            "standard": (5000, 10000),
            "high": (10000, 25000),
            "very_high": (25000, 100000),
        }
        min_income, max_income = profiles.get(profile, profiles["standard"])
        monthly = random.randint(min_income, max_income)

        employer = random.choice(self.EMPLOYERS)

        return {
            "employment_status": "employed",
            "employer_name": employer[0],
            "employer_address": employer[1],
            "employer_city": employer[2],
            "employer_state": employer[3],
            "employer_zip": employer[4],
            "job_title": random.choice(self.JOB_TITLES),
            "monthly_income": monthly,
            "annual_income": monthly * 12,
            "years_employed": random.randint(1, 15),
            "months_employed": random.randint(0, 11),
        }

    def generate_assets(self, income_level: str = "standard") -> Dict:
        """Generate asset data"""
        multipliers = {
            "low": (0.5, 2),
            "standard": (2, 5),
            "high": (5, 15),
            "very_high": (15, 50),
        }
        min_mult, max_mult = multipliers.get(income_level, (2, 5))

        base = random.randint(50000, 200000)

        return {
            "checking_balance": round(base * random.uniform(0.1, 0.3)),
            "savings_balance": round(base * random.uniform(0.3, 0.5)),
            "investment_balance": round(base * random.uniform(0.2, 0.8)),
            "retirement_balance": round(base * random.uniform(0.5, 2.0)),
            "other_assets": round(base * random.uniform(0, 0.3)),
            "gift_funds": round(base * random.uniform(0, 0.2)) if random.random() > 0.7 else 0,
        }

    def generate_loan_details(self, income: Dict) -> Dict:
        """Generate loan details based on income"""
        annual_income = income["annual_income"]
        # Typical DTI around 35-45%
        max_loan = annual_income * random.uniform(3, 5)

        property_value = round(max_loan / random.uniform(0.75, 0.95), -3)
        down_payment_pct = random.choice([0.03, 0.05, 0.10, 0.15, 0.20, 0.25])
        down_payment = round(property_value * down_payment_pct)
        loan_amount = property_value - down_payment

        return {
            "loan_purpose": random.choice(self.LOAN_PURPOSES),
            "property_type": random.choice(self.PROPERTY_TYPES),
            "occupancy_type": random.choice(self.OCCUPANCY_TYPES),
            "property_value": property_value,
            "purchase_price": property_value,
            "down_payment": down_payment,
            "down_payment_percentage": down_payment_pct * 100,
            "loan_amount": loan_amount,
            "ltv": round((loan_amount / property_value) * 100, 2),
        }

    def generate_borrower(self, profile: str = "standard") -> Dict:
        """Generate complete borrower profile"""
        first_name = random.choice(self.FIRST_NAMES)
        last_name = random.choice(self.LAST_NAMES)

        income = self.generate_income(profile)
        assets = self.generate_assets(profile)
        loan = self.generate_loan_details(income)
        address = self.generate_address()
        property_address = self.generate_address()

        return {
            "id": str(uuid.uuid4()),
            "personal_info": {
                "first_name": first_name,
                "last_name": last_name,
                "email": self.generate_email(first_name, last_name),
                "phone": self.generate_phone(),
                "ssn": self.generate_ssn(),
                "date_of_birth": self.generate_dob(),
                "citizenship_status": "us_citizen",
            },
            "current_address": address,
            "property_info": {
                **property_address,
                "property_type": loan["property_type"],
                "occupancy_type": loan["occupancy_type"],
                "purchase_price": loan["purchase_price"],
            },
            "income_info": income,
            "assets_info": assets,
            "loan_info": loan,
            "declarations": {
                "outstanding_judgments": False,
                "bankruptcy": False,
                "foreclosure": False,
                "party_to_lawsuit": False,
                "loan_delinquency": False,
                "alimony_obligation": False,
                "down_payment_borrowed": False,
                "co_maker_note": False,
                "us_citizen": True,
                "permanent_resident": False,
                "primary_residence": loan["occupancy_type"] == "primary_residence",
            },
            "created_at": datetime.now().isoformat(),
        }

    def generate_co_borrower(self, primary: Dict) -> Dict:
        """Generate co-borrower related to primary"""
        co_borrower = self.generate_borrower()

        # Share address with primary
        co_borrower["current_address"] = primary["current_address"]

        # Different last name sometimes
        if random.random() > 0.7:
            co_borrower["personal_info"]["last_name"] = random.choice(self.LAST_NAMES)

        co_borrower["relationship_to_primary"] = random.choice([
            "spouse", "domestic_partner", "relative", "other"
        ])

        return co_borrower

    def generate_application_batch(self, count: int, statuses: List[str] = None) -> List[Dict]:
        """Generate batch of applications with various statuses"""
        if statuses is None:
            statuses = [
                "draft", "in_progress", "documents_pending",
                "submitted", "under_review", "approved", "funded"
            ]

        applications = []
        for i in range(count):
            profile = random.choice(["low", "standard", "high", "very_high"])
            borrower = self.generate_borrower(profile)

            # Add co-borrower sometimes
            if random.random() > 0.6:
                borrower["co_borrower"] = self.generate_co_borrower(borrower)

            # Add status
            borrower["status"] = random.choice(statuses)

            # Add timestamps based on status
            created = datetime.now() - timedelta(days=random.randint(1, 90))
            borrower["created_at"] = created.isoformat()

            if borrower["status"] != "draft":
                borrower["submitted_at"] = (created + timedelta(days=random.randint(1, 7))).isoformat()

            if borrower["status"] in ["approved", "funded"]:
                borrower["approved_at"] = (created + timedelta(days=random.randint(7, 30))).isoformat()

            if borrower["status"] == "funded":
                borrower["funded_at"] = (created + timedelta(days=random.randint(30, 60))).isoformat()

            applications.append(borrower)

        return applications


class EdgeCaseGenerator:
    """Generate edge case test data"""

    @staticmethod
    def special_character_names() -> List[Dict]:
        """Names with special characters"""
        return [
            {"first_name": "O'Brien", "last_name": "McDonald-Smith"},
            {"first_name": "José", "last_name": "García"},
            {"first_name": "François", "last_name": "Müller"},
            {"first_name": "Björk", "last_name": "Guðmundsdóttir"},
            {"first_name": "Mary Jane", "last_name": "Watson Jr."},
            {"first_name": "X Æ A-12", "last_name": "Musk"},  # Extreme edge case
        ]

    @staticmethod
    def extreme_values() -> Dict:
        """Extreme numerical values"""
        return {
            "max_income": 999999999,
            "min_income": 0,
            "max_property_value": 50000000,
            "min_property_value": 10000,
            "max_loan_amount": 25000000,
            "oldest_dob": "1920-01-01",
            "youngest_valid_dob": (datetime.now() - timedelta(days=18*365)).strftime("%Y-%m-%d"),
            "future_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        }

    @staticmethod
    def invalid_inputs() -> Dict:
        """Invalid inputs for validation testing"""
        return {
            "invalid_emails": [
                "notanemail",
                "@nodomain.com",
                "no@domain",
                "spaces in@email.com",
                "",
            ],
            "invalid_phones": [
                "123",
                "abc-def-ghij",
                "+999999999999999",
                "",
            ],
            "invalid_ssns": [
                "000-00-0000",
                "123-45-678",
                "12-345-6789",
                "aaa-bb-cccc",
            ],
            "sql_injection_attempts": [
                "'; DROP TABLE applications; --",
                "1' OR '1'='1",
                "admin'--",
                "1; SELECT * FROM users",
            ],
            "xss_attempts": [
                "<script>alert('xss')</script>",
                "<img src=x onerror=alert('xss')>",
                "javascript:alert('xss')",
                "<svg/onload=alert('xss')>",
            ],
            "path_traversal_attempts": [
                "../../etc/passwd",
                "..\\..\\windows\\system32",
                "%2e%2e%2f%2e%2e%2f",
            ],
        }

    @staticmethod
    def file_edge_cases() -> List[Dict]:
        """File upload edge cases"""
        return [
            {"name": "empty.pdf", "size": 0, "type": "application/pdf"},
            {"name": "huge.pdf", "size": 100 * 1024 * 1024, "type": "application/pdf"},  # 100MB
            {"name": "no_extension", "size": 1024, "type": "application/octet-stream"},
            {"name": "fake.pdf.exe", "size": 1024, "type": "application/x-executable"},
            {"name": "special chars $#@!.pdf", "size": 1024, "type": "application/pdf"},
            {"name": "unicode_名前.pdf", "size": 1024, "type": "application/pdf"},
            {"name": "../../etc/passwd", "size": 1024, "type": "text/plain"},
        ]


class ConversationTestGenerator:
    """Generate test conversations for AI Concierge"""

    @staticmethod
    def standard_conversations() -> List[List[Dict]]:
        """Standard conversation flows"""
        return [
            # Happy path
            [
                {"role": "user", "content": "Hi, I want to apply for a mortgage"},
                {"role": "user", "content": "My name is John Smith"},
                {"role": "user", "content": "I want to buy a house at 123 Main St, New York, NY 10001"},
                {"role": "user", "content": "The price is $500,000 and I have $100,000 for down payment"},
                {"role": "user", "content": "I work at Google and make $150,000 per year"},
            ],
            # Voice-like input (natural speech)
            [
                {"role": "user", "content": "yeah so like i wanna buy a house"},
                {"role": "user", "content": "um my name is jane doe and i live in california"},
                {"role": "user", "content": "i make about a hundred k a year working at microsoft"},
            ],
            # Multiple info in one message
            [
                {"role": "user", "content": "I'm Sarah Johnson, I want to buy a $600k house in Austin TX with 20% down, I make $12k/month at Apple"},
            ],
        ]

    @staticmethod
    def edge_case_conversations() -> List[List[Dict]]:
        """Edge case conversations"""
        return [
            # Ambiguous input
            [
                {"role": "user", "content": "I make 8000"},  # Monthly or annual?
                {"role": "user", "content": "The house is worth around 400"},  # 400k?
            ],
            # Off-topic
            [
                {"role": "user", "content": "What's the weather like today?"},
                {"role": "user", "content": "Can you tell me a joke?"},
                {"role": "user", "content": "Who won the Super Bowl?"},
            ],
            # Contradictory info
            [
                {"role": "user", "content": "I want to buy a house"},
                {"role": "user", "content": "Actually, I want to refinance"},
                {"role": "user", "content": "Wait, maybe I should do a cash-out refi"},
            ],
            # Very long input
            [
                {"role": "user", "content": "So basically what happened is that my wife and I have been renting for about 5 years now and we've saved up a good amount of money and we think it's finally time to buy our first home. We've been looking in the Austin area because that's where we both work - I'm a software engineer at Dell and she's a nurse at the hospital downtown. Combined we make about $180,000 a year and we have about $80,000 saved for a down payment. We're hoping to find something in the $400-500k range, preferably a single family home with at least 3 bedrooms because we're planning to start a family soon. We've already been pre-approved by another lender but we wanted to shop around and see if we could get a better rate."},
            ],
        ]


def main():
    """Generate sample test data"""
    generator = TestDataGenerator(seed=42)

    # Generate sample borrower
    print("=" * 60)
    print("SAMPLE BORROWER")
    print("=" * 60)
    borrower = generator.generate_borrower("standard")
    print(json.dumps(borrower, indent=2, default=str))

    # Generate batch
    print("\n" + "=" * 60)
    print("APPLICATION BATCH (5 samples)")
    print("=" * 60)
    batch = generator.generate_application_batch(5)
    for i, app in enumerate(batch):
        print(f"\n{i+1}. {app['personal_info']['first_name']} {app['personal_info']['last_name']}")
        print(f"   Status: {app['status']}")
        print(f"   Loan: ${app['loan_info']['loan_amount']:,.0f}")

    # Edge cases
    print("\n" + "=" * 60)
    print("EDGE CASES")
    print("=" * 60)
    edge = EdgeCaseGenerator()
    print("\nSpecial Names:")
    for name in edge.special_character_names():
        print(f"  - {name['first_name']} {name['last_name']}")

    print("\nExtreme Values:")
    for key, value in edge.extreme_values().items():
        print(f"  - {key}: {value}")

    # Save to file
    output = {
        "generated_at": datetime.now().isoformat(),
        "sample_borrower": borrower,
        "batch_applications": batch,
        "edge_cases": {
            "special_names": edge.special_character_names(),
            "extreme_values": edge.extreme_values(),
            "invalid_inputs": edge.invalid_inputs(),
            "file_edge_cases": edge.file_edge_cases(),
        },
        "conversation_tests": {
            "standard": ConversationTestGenerator.standard_conversations(),
            "edge_cases": ConversationTestGenerator.edge_case_conversations(),
        }
    }

    output_file = os.path.join(os.path.dirname(__file__), "test_data.json")
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n\nTest data saved to: {output_file}")


if __name__ == "__main__":
    main()
