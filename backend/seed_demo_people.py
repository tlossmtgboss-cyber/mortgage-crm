#!/usr/bin/env python3
"""
Comprehensive Demo Data Generator
Creates realistic placeholder people across all CRM categories:
- Team members (employees, management, leadership, operations)
- Leads (prospects at various stages)
- Active loans (borrowers in pipeline)
- MUM clients (clients for life)
- Referral partners
"""

import sys
import os
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
import random
import json

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from database import SessionLocal
import bcrypt as _bcrypt

logger = logging.getLogger(__name__)


class _BcryptCompat:
    """Drop-in replacement providing .hash()/.verify() over raw bcrypt."""
    def hash(self, password: str) -> str:
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()
    def verify(self, plain: str, hashed: str) -> bool:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())

pwd_context = _BcryptCompat()

# ============================================================================
# DEMO PERSON DATA
# ============================================================================

# Team Members by Role
TEAM_MEMBERS = {
    "leadership": [
        {"name": "Sarah Mitchell", "email": "sarah.mitchell@company.com", "role": "admin", "department": "Leadership", "title": "Chief Lending Officer"},
        {"name": "Michael Chen", "email": "michael.chen@company.com", "role": "management", "department": "Leadership", "title": "VP of Operations"},
    ],
    "management": [
        {"name": "Jennifer Rodriguez", "email": "jennifer.rodriguez@company.com", "role": "management", "department": "Management", "title": "Sales Manager"},
        {"name": "David Thompson", "email": "david.thompson@company.com", "role": "management", "department": "Management", "title": "Operations Manager"},
        {"name": "Lisa Wong", "email": "lisa.wong@company.com", "role": "management", "department": "Management", "title": "Processing Manager"},
    ],
    "operations": [
        {"name": "Robert Garcia", "email": "robert.garcia@company.com", "role": "operations", "department": "Operations", "title": "Senior Processor"},
        {"name": "Amanda Foster", "email": "amanda.foster@company.com", "role": "operations", "department": "Operations", "title": "Loan Processor"},
        {"name": "Kevin Park", "email": "kevin.park@company.com", "role": "operations", "department": "Operations", "title": "Junior Processor"},
        {"name": "Rachel Stevens", "email": "rachel.stevens@company.com", "role": "operations", "department": "Operations", "title": "Underwriting Assistant"},
    ],
    "sales": [
        {"name": "Marcus Johnson", "email": "marcus.johnson@company.com", "role": "sales", "department": "Sales", "title": "Senior Loan Officer"},
        {"name": "Emily Patterson", "email": "emily.patterson@company.com", "role": "sales", "department": "Sales", "title": "Loan Officer"},
        {"name": "Brandon Lee", "email": "brandon.lee@company.com", "role": "sales", "department": "Sales", "title": "Loan Officer"},
        {"name": "Samantha Brooks", "email": "samantha.brooks@company.com", "role": "sales", "department": "Sales", "title": "Junior Loan Officer"},
        {"name": "Tyler Martinez", "email": "tyler.martinez@company.com", "role": "loan_officer", "department": "Sales", "title": "Loan Officer"},
        {"name": "Olivia Anderson", "email": "olivia.anderson@company.com", "role": "loan_officer", "department": "Sales", "title": "Loan Officer"},
    ]
}

# Leads - Prospects at various stages with referral scores
DEMO_LEADS = [
    {
        "name": "James Wilson",
        "email": "james.wilson@email.com",
        "phone": "(555) 234-5678",
        "stage": "New",
        "source": "Website",
        "loan_type": "Purchase - Conventional",
        "credit_score": 750,
        "annual_income": 125000,
        "property_value": 450000,
        "down_payment": 90000,
        "city": "Austin",
        "state": "TX",
        "employer_name": "Dell Technologies",
        "job_title": "Regional Sales Director",
        "referral_source_score": 92,
        "referral_source_rating": "Strong Referral Source"
    },
    {
        "name": "Maria Hernandez",
        "email": "maria.hernandez@email.com",
        "phone": "(555) 345-6789",
        "co_applicant_name": "Carlos Hernandez",
        "stage": "Prospect",
        "source": "Referral Partner",
        "loan_type": "Purchase - FHA",
        "credit_score": 680,
        "annual_income": 85000,
        "property_value": 325000,
        "down_payment": 11375,
        "city": "San Antonio",
        "state": "TX",
        "employer_name": "USAA",
        "job_title": "HR Manager",
        "referral_source_score": 78,
        "referral_source_rating": "Good Referral Source"
    },
    {
        "name": "Robert Taylor",
        "email": "robert.taylor@email.com",
        "phone": "(555) 456-7890",
        "stage": "Application Started",
        "source": "Zillow",
        "loan_type": "Refinance - Conventional",
        "credit_score": 720,
        "annual_income": 150000,
        "property_value": 550000,
        "city": "Dallas",
        "state": "TX",
        "employer_name": "Texas Instruments",
        "job_title": "Engineering Manager",
        "referral_source_score": 85,
        "referral_source_rating": "Strong Referral Source"
    },
    {
        "name": "Ashley Thompson",
        "email": "ashley.thompson@email.com",
        "phone": "(555) 567-8901",
        "co_applicant_name": "Brian Thompson",
        "stage": "Application Complete",
        "source": "Facebook Ad",
        "loan_type": "Purchase - VA",
        "credit_score": 695,
        "annual_income": 95000,
        "property_value": 380000,
        "down_payment": 0,
        "city": "Houston",
        "state": "TX",
        "employer_name": "Memorial Hermann",
        "job_title": "Nursing Supervisor",
        "referral_source_score": 71,
        "referral_source_rating": "Good Referral Source"
    },
    {
        "name": "Christopher Davis",
        "email": "chris.davis@email.com",
        "phone": "(555) 678-9012",
        "stage": "Pre-Approved",
        "source": "Realtor Referral",
        "loan_type": "Purchase - Jumbo",
        "credit_score": 780,
        "annual_income": 250000,
        "property_value": 850000,
        "down_payment": 170000,
        "preapproval_amount": 680000,
        "city": "Plano",
        "state": "TX",
        "employer_name": "Deloitte",
        "job_title": "Partner",
        "referral_source_score": 95,
        "referral_source_rating": "Strong Referral Source"
    },
    {
        "name": "Jessica Martinez",
        "email": "jessica.martinez@email.com",
        "phone": "(555) 789-0123",
        "stage": "New",
        "source": "Google",
        "loan_type": "Purchase - Conventional",
        "credit_score": 710,
        "annual_income": 105000,
        "property_value": 395000,
        "down_payment": 79000,
        "city": "Fort Worth",
        "state": "TX",
        "employer_name": "Lockheed Martin",
        "job_title": "Project Manager",
        "referral_source_score": 82,
        "referral_source_rating": "Strong Referral Source"
    },
    {
        "name": "Daniel Brown",
        "email": "daniel.brown@email.com",
        "phone": "(555) 890-1234",
        "stage": "Attempted Contact",
        "source": "Website",
        "loan_type": "Purchase - FHA",
        "credit_score": 665,
        "annual_income": 72000,
        "property_value": 285000,
        "down_payment": 9975,
        "first_time_buyer": True,
        "city": "Arlington",
        "state": "TX",
        "employer_name": "GM Financial",
        "job_title": "Financial Analyst",
        "referral_source_score": 58,
        "referral_source_rating": "Moderate Referral Source"
    },
    {
        "name": "Nicole Anderson",
        "email": "nicole.anderson@email.com",
        "phone": "(555) 901-2345",
        "co_applicant_name": "Steven Anderson",
        "stage": "Prospect",
        "source": "Past Client Referral",
        "loan_type": "Refinance - Cash Out",
        "credit_score": 735,
        "annual_income": 165000,
        "property_value": 625000,
        "city": "Frisco",
        "state": "TX",
        "employer_name": "Toyota North America",
        "job_title": "VP of Marketing",
        "referral_source_score": 88,
        "referral_source_rating": "Strong Referral Source"
    },
    # Additional leads for top 20 variety
    {
        "name": "Michael Chen",
        "email": "michael.chen@email.com",
        "phone": "(555) 111-2233",
        "stage": "Pre-Approved",
        "source": "LinkedIn",
        "loan_type": "Purchase - Conventional",
        "credit_score": 760,
        "annual_income": 185000,
        "property_value": 520000,
        "down_payment": 104000,
        "city": "Austin",
        "state": "TX",
        "employer_name": "Oracle",
        "job_title": "Senior Director",
        "referral_source_score": 90,
        "referral_source_rating": "Strong Referral Source"
    },
    {
        "name": "Sarah Williams",
        "email": "sarah.williams@email.com",
        "phone": "(555) 222-3344",
        "stage": "Application Started",
        "source": "Realtor Referral",
        "loan_type": "Purchase - Jumbo",
        "credit_score": 795,
        "annual_income": 320000,
        "property_value": 1200000,
        "down_payment": 240000,
        "city": "Highland Park",
        "state": "TX",
        "employer_name": "Goldman Sachs",
        "job_title": "Managing Director",
        "referral_source_score": 98,
        "referral_source_rating": "Strong Referral Source"
    },
    {
        "name": "David Rodriguez",
        "email": "david.rodriguez@email.com",
        "phone": "(555) 333-4455",
        "stage": "Prospect",
        "source": "Website",
        "loan_type": "Purchase - Conventional",
        "credit_score": 725,
        "annual_income": 135000,
        "property_value": 480000,
        "down_payment": 96000,
        "city": "Round Rock",
        "state": "TX",
        "employer_name": "Apple",
        "job_title": "Product Manager",
        "referral_source_score": 86,
        "referral_source_rating": "Strong Referral Source"
    },
    {
        "name": "Jennifer Lee",
        "email": "jennifer.lee@email.com",
        "phone": "(555) 444-5566",
        "stage": "New",
        "source": "Google",
        "loan_type": "Purchase - Conventional",
        "credit_score": 740,
        "annual_income": 145000,
        "property_value": 425000,
        "down_payment": 85000,
        "city": "Irving",
        "state": "TX",
        "employer_name": "ExxonMobil",
        "job_title": "Operations Manager",
        "referral_source_score": 79,
        "referral_source_rating": "Good Referral Source"
    },
    {
        "name": "Kevin Patel",
        "email": "kevin.patel@email.com",
        "phone": "(555) 555-6677",
        "stage": "Application Complete",
        "source": "Past Client Referral",
        "loan_type": "Refinance - Conventional",
        "credit_score": 770,
        "annual_income": 210000,
        "property_value": 750000,
        "city": "Southlake",
        "state": "TX",
        "employer_name": "McKinsey & Company",
        "job_title": "Senior Consultant",
        "referral_source_score": 91,
        "referral_source_rating": "Strong Referral Source"
    },
    {
        "name": "Amanda Foster",
        "email": "amanda.foster.client@email.com",
        "phone": "(555) 666-7788",
        "stage": "Pre-Approved",
        "source": "Zillow",
        "loan_type": "Purchase - VA",
        "credit_score": 705,
        "annual_income": 98000,
        "property_value": 365000,
        "down_payment": 0,
        "city": "Keller",
        "state": "TX",
        "employer_name": "Lockheed Martin",
        "job_title": "Systems Engineer",
        "referral_source_score": 74,
        "referral_source_rating": "Good Referral Source"
    },
    {
        "name": "Brian Jackson",
        "email": "brian.jackson@email.com",
        "phone": "(555) 777-8899",
        "stage": "Prospect",
        "source": "Website",
        "loan_type": "Purchase - Conventional",
        "credit_score": 715,
        "annual_income": 115000,
        "property_value": 410000,
        "down_payment": 82000,
        "city": "McKinney",
        "state": "TX",
        "employer_name": "Raytheon",
        "job_title": "Program Manager",
        "referral_source_score": 83,
        "referral_source_rating": "Strong Referral Source"
    },
    {
        "name": "Lisa Nguyen",
        "email": "lisa.nguyen@email.com",
        "phone": "(555) 888-9900",
        "stage": "New",
        "source": "Facebook Ad",
        "loan_type": "Purchase - FHA",
        "credit_score": 675,
        "annual_income": 78000,
        "property_value": 295000,
        "down_payment": 10325,
        "first_time_buyer": True,
        "city": "Garland",
        "state": "TX",
        "employer_name": "AT&T",
        "job_title": "Account Manager",
        "referral_source_score": 67,
        "referral_source_rating": "Good Referral Source"
    },
    {
        "name": "Thomas Mitchell",
        "email": "thomas.mitchell@email.com",
        "phone": "(555) 999-0011",
        "stage": "Application Started",
        "source": "Realtor Referral",
        "loan_type": "Purchase - Conventional",
        "credit_score": 755,
        "annual_income": 175000,
        "property_value": 595000,
        "down_payment": 119000,
        "city": "Coppell",
        "state": "TX",
        "employer_name": "Salesforce",
        "job_title": "Regional VP",
        "referral_source_score": 94,
        "referral_source_rating": "Strong Referral Source"
    },
    {
        "name": "Rachel Kim",
        "email": "rachel.kim@email.com",
        "phone": "(555) 000-1122",
        "stage": "Pre-Approved",
        "source": "LinkedIn",
        "loan_type": "Purchase - Jumbo",
        "credit_score": 785,
        "annual_income": 275000,
        "property_value": 925000,
        "down_payment": 185000,
        "city": "University Park",
        "state": "TX",
        "employer_name": "JPMorgan Chase",
        "job_title": "Vice President",
        "referral_source_score": 96,
        "referral_source_rating": "Strong Referral Source"
    },
    {
        "name": "Steven Garcia",
        "email": "steven.garcia@email.com",
        "phone": "(555) 112-2334",
        "stage": "Prospect",
        "source": "Website",
        "loan_type": "Purchase - Conventional",
        "credit_score": 700,
        "annual_income": 92000,
        "property_value": 345000,
        "down_payment": 69000,
        "city": "Lewisville",
        "state": "TX",
        "employer_name": "State Farm",
        "job_title": "Claims Manager",
        "referral_source_score": 72,
        "referral_source_rating": "Good Referral Source"
    },
    {
        "name": "Emily Thompson",
        "email": "emily.thompson@email.com",
        "phone": "(555) 223-3445",
        "stage": "New",
        "source": "Google",
        "loan_type": "Refinance - Cash Out",
        "credit_score": 745,
        "annual_income": 155000,
        "property_value": 565000,
        "city": "Flower Mound",
        "state": "TX",
        "employer_name": "Accenture",
        "job_title": "Managing Director",
        "referral_source_score": 89,
        "referral_source_rating": "Strong Referral Source"
    }
]

# Active Loans - In pipeline
DEMO_LOANS = [
    {
        "loan_number": "2025-001234",
        "borrower_name": "Michael Roberts",
        "coborrower_name": "Sarah Roberts",
        "stage": "Processing",
        "program": "Conventional 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 420000,
        "purchase_price": 525000,
        "down_payment": 105000,
        "rate": 6.875,
        "term": 360,
        "property_address": "1234 Oak Street, Austin, TX 78701",
        "closing_date_days": 25,
        "processor": "Amanda Foster",
        "days_in_stage": 18
    },
    {
        "loan_number": "2025-001235",
        "borrower_name": "Jennifer Kim",
        "stage": "UW Received",
        "program": "FHA 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 285000,
        "purchase_price": 300000,
        "down_payment": 10500,
        "rate": 6.625,
        "term": 360,
        "property_address": "5678 Elm Avenue, Houston, TX 77002",
        "closing_date_days": 18,
        "processor": "Robert Garcia"
    },
    {
        "loan_number": "2025-001236",
        "borrower_name": "William Turner",
        "coborrower_name": "Patricia Turner",
        "stage": "Approved",
        "program": "VA 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 365000,
        "purchase_price": 365000,
        "down_payment": 0,
        "rate": 6.500,
        "term": 360,
        "property_address": "9012 Pine Road, Dallas, TX 75201",
        "closing_date_days": 12,
        "processor": "Amanda Foster"
    },
    {
        "loan_number": "2025-001237",
        "borrower_name": "Thomas Jackson",
        "stage": "Disclosed",
        "program": "Conventional 15-Year Fixed",
        "loan_type": "Refinance",
        "amount": 295000,
        "rate": 6.250,
        "term": 180,
        "property_address": "3456 Maple Lane, San Antonio, TX 78201",
        "closing_date_days": 35,
        "processor": "Kevin Park"
    },
    {
        "loan_number": "2025-001238",
        "borrower_name": "Elizabeth Moore",
        "coborrower_name": "Richard Moore",
        "stage": "CTC",
        "program": "Jumbo 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 825000,
        "purchase_price": 1100000,
        "down_payment": 275000,
        "rate": 7.125,
        "term": 360,
        "property_address": "7890 Highland Drive, Plano, TX 75024",
        "closing_date_days": 5,
        "processor": "Robert Garcia"
    },
    {
        "loan_number": "2025-001239",
        "borrower_name": "David Nguyen",
        "stage": "Processing",
        "program": "FHA 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 245000,
        "purchase_price": 265000,
        "down_payment": 9275,
        "rate": 6.750,
        "term": 360,
        "property_address": "2345 Cedar Court, Fort Worth, TX 76101",
        "closing_date_days": 28,
        "processor": "Amanda Foster"
    },
    # Funded loans (for efficiency metrics)
    {
        "loan_number": "2024-008901",
        "borrower_name": "Anthony Martinez",
        "coborrower_name": "Laura Martinez",
        "stage": "Funded",
        "program": "Conventional 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 395000,
        "purchase_price": 495000,
        "down_payment": 100000,
        "rate": 6.875,
        "term": 360,
        "property_address": "1111 Sunset Blvd, Austin, TX 78704",
        "processor": "Robert Garcia",
        "funded_days_ago": 5,
        "created_days_ago": 38
    },
    {
        "loan_number": "2024-008902",
        "borrower_name": "Karen White",
        "stage": "Funded",
        "program": "FHA 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 275000,
        "purchase_price": 295000,
        "down_payment": 10325,
        "rate": 6.625,
        "term": 360,
        "property_address": "2222 River Road, Dallas, TX 75202",
        "processor": "Amanda Foster",
        "funded_days_ago": 12,
        "created_days_ago": 45
    },
    {
        "loan_number": "2024-008903",
        "borrower_name": "Steven Harris",
        "coborrower_name": "Michelle Harris",
        "stage": "Funded",
        "program": "VA 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 355000,
        "purchase_price": 355000,
        "down_payment": 0,
        "rate": 6.500,
        "term": 360,
        "property_address": "3333 Lake View, Houston, TX 77003",
        "processor": "Robert Garcia",
        "funded_days_ago": 18,
        "created_days_ago": 50
    },
    {
        "loan_number": "2024-008904",
        "borrower_name": "Patricia Lewis",
        "stage": "Funded",
        "program": "Conventional 15-Year Fixed",
        "loan_type": "Refinance",
        "amount": 320000,
        "rate": 6.250,
        "term": 180,
        "property_address": "4444 Park Avenue, San Antonio, TX 78202",
        "processor": "Kevin Park",
        "funded_days_ago": 25,
        "created_days_ago": 55
    }
]

# MUM Clients - Client for Life Engine with amortization data
DEMO_MUM_CLIENTS = [
    {
        "name": "Charles Bennett",
        "email": "charles.bennett@email.com",
        "phone": "(555) 111-2222",
        "original_loan_date": 730,  # days ago
        "original_loan_amount": 385000,
        "original_property_value": 450000,
        "interest_rate": 6.25,
        "loan_term": 30,
        "loan_type": "Conventional 30-Year Fixed",
        "engagement_level": "High",
        "last_contact_days": 45,
        "next_milestone": "Home Anniversary",
        "city": "Austin",
        "state": "TX"
    },
    {
        "name": "Rebecca Sullivan",
        "email": "rebecca.sullivan@email.com",
        "phone": "(555) 222-3333",
        "original_loan_date": 1095,  # 3 years
        "original_loan_amount": 425000,
        "original_property_value": 475000,
        "interest_rate": 5.875,
        "loan_term": 30,
        "loan_type": "Conventional 30-Year Fixed",
        "engagement_level": "Medium",
        "last_contact_days": 90,
        "next_milestone": "Equity Check-in",
        "city": "Dallas",
        "state": "TX"
    },
    {
        "name": "Gregory Phillips",
        "email": "gregory.phillips@email.com",
        "phone": "(555) 333-4444",
        "original_loan_date": 365,  # 1 year
        "original_loan_amount": 295000,
        "original_property_value": 310000,
        "interest_rate": 6.75,
        "loan_term": 30,
        "loan_type": "FHA 30-Year Fixed",
        "engagement_level": "High",
        "last_contact_days": 30,
        "next_milestone": "1-Year Anniversary",
        "city": "Houston",
        "state": "TX"
    },
    {
        "name": "Michelle Hayes",
        "email": "michelle.hayes@email.com",
        "phone": "(555) 444-5555",
        "original_loan_date": 1825,  # 5 years
        "original_loan_amount": 365000,
        "original_property_value": 420000,
        "interest_rate": 4.125,
        "loan_term": 30,
        "loan_type": "VA 30-Year Fixed",
        "engagement_level": "Medium",
        "last_contact_days": 120,
        "next_milestone": "Refinance Opportunity",
        "city": "San Antonio",
        "state": "TX"
    },
    {
        "name": "Jonathan Foster",
        "email": "jonathan.foster@email.com",
        "phone": "(555) 555-6666",
        "original_loan_date": 545,  # 18 months
        "original_loan_amount": 475000,
        "original_property_value": 500000,
        "interest_rate": 6.5,
        "loan_term": 30,
        "loan_type": "Jumbo 30-Year Fixed",
        "engagement_level": "Low",
        "last_contact_days": 180,
        "next_milestone": "Market Update",
        "city": "Plano",
        "state": "TX"
    },
    {
        "name": "Stephanie Ward",
        "email": "stephanie.ward@email.com",
        "phone": "(555) 666-7777",
        "original_loan_date": 275,  # 9 months
        "original_loan_amount": 335000,
        "original_property_value": 350000,
        "interest_rate": 7.0,
        "loan_term": 30,
        "loan_type": "Conventional 30-Year Fixed",
        "engagement_level": "High",
        "last_contact_days": 20,
        "next_milestone": "6-Month Check-in",
        "city": "Frisco",
        "state": "TX"
    },
    {
        "name": "Andrew Martinez",
        "email": "andrew.martinez@email.com",
        "phone": "(555) 777-8888",
        "original_loan_date": 1460,  # 4 years
        "original_loan_amount": 285000,
        "original_property_value": 320000,
        "interest_rate": 3.75,
        "loan_term": 15,
        "loan_type": "Conventional 15-Year Fixed",
        "engagement_level": "High",
        "last_contact_days": 60,
        "next_milestone": "Refinance Review",
        "city": "Katy",
        "state": "TX"
    },
    {
        "name": "Catherine Brooks",
        "email": "catherine.brooks@email.com",
        "phone": "(555) 888-9999",
        "original_loan_date": 910,  # 2.5 years
        "original_loan_amount": 520000,
        "original_property_value": 580000,
        "interest_rate": 5.5,
        "loan_term": 30,
        "loan_type": "Jumbo 30-Year Fixed",
        "engagement_level": "Medium",
        "last_contact_days": 75,
        "next_milestone": "Market Update",
        "city": "Southlake",
        "state": "TX"
    }
]

# Team Member Profiles with KPIs (for performance tracking)
TEAM_MEMBER_PROFILES = [
    # Processors
    {
        "name": "Robert Garcia",
        "email": "robert.garcia@company.com",
        "role": "processor",
        "department": "Processing",
        "loans_processed": 145,
        "avg_close_time": 28.5,
        "satisfaction_score": 4.7,
        "volume": 42500000
    },
    {
        "name": "Amanda Foster",
        "email": "amanda.foster@company.com",
        "role": "processor",
        "department": "Processing",
        "loans_processed": 132,
        "avg_close_time": 31.2,
        "satisfaction_score": 4.5,
        "volume": 38200000
    },
    {
        "name": "Kevin Park",
        "email": "kevin.park@company.com",
        "role": "processor",
        "department": "Processing",
        "loans_processed": 78,
        "avg_close_time": 35.8,
        "satisfaction_score": 4.1,
        "volume": 21500000
    },
    {
        "name": "Diana Cruz",
        "email": "diana.cruz@company.com",
        "role": "processor",
        "department": "Processing",
        "loans_processed": 95,
        "avg_close_time": 29.8,
        "satisfaction_score": 4.6,
        "volume": 28900000
    },
    # Underwriters
    {
        "name": "James Mitchell",
        "email": "james.mitchell@company.com",
        "role": "underwriter",
        "department": "Underwriting",
        "loans_processed": 168,
        "avg_close_time": 3.2,  # Days in UW
        "satisfaction_score": 4.8,
        "volume": 52000000
    },
    {
        "name": "Patricia Wong",
        "email": "patricia.wong@company.com",
        "role": "underwriter",
        "department": "Underwriting",
        "loans_processed": 142,
        "avg_close_time": 4.1,
        "satisfaction_score": 4.4,
        "volume": 43500000
    },
    {
        "name": "Brian Nelson",
        "email": "brian.nelson@company.com",
        "role": "underwriter",
        "department": "Underwriting",
        "loans_processed": 89,
        "avg_close_time": 5.8,  # Slow - underperformer
        "satisfaction_score": 3.9,  # Low satisfaction - underperformer
        "volume": 26800000
    },
    {
        "name": "Sandra Kim",
        "email": "sandra.kim@company.com",
        "role": "underwriter",
        "department": "Underwriting",
        "loans_processed": 156,
        "avg_close_time": 3.5,
        "satisfaction_score": 4.6,
        "volume": 48200000
    },
    # Closers
    {
        "name": "Mark Thompson",
        "email": "mark.thompson@company.com",
        "role": "closer",
        "department": "Closing",
        "loans_processed": 178,
        "avg_close_time": 2.1,
        "satisfaction_score": 4.9,
        "volume": 55000000
    },
    {
        "name": "Jennifer Adams",
        "email": "jennifer.adams@company.com",
        "role": "closer",
        "department": "Closing",
        "loans_processed": 165,
        "avg_close_time": 2.4,
        "satisfaction_score": 4.7,
        "volume": 51200000
    },
    {
        "name": "Carlos Rivera",
        "email": "carlos.rivera@company.com",
        "role": "closer",
        "department": "Closing",
        "loans_processed": 98,
        "avg_close_time": 3.8,  # Slow - underperformer
        "satisfaction_score": 4.2,
        "volume": 29500000
    }
]

# ============================================================================
# SEED FUNCTIONS
# ============================================================================

def create_team_member_profiles(db):
    """Create team member profiles with KPIs for performance tracking"""
    logger.info("📊 Creating team member profiles with KPIs...")

    created_count = 0

    for member in TEAM_MEMBER_PROFILES:
        # Check if profile exists
        existing = db.execute(text("""
            SELECT id FROM team_member_profiles WHERE email = :email
        """), {"email": member["email"]}).fetchone()

        if existing:
            logger.info(f"   ⏭️  Skipped {member['name']} (profile already exists)")
            continue

        # Calculate start date (random within last 1-5 years)
        start_days_ago = random.randint(365, 1825)
        start_date = datetime.now(timezone.utc).date() - timedelta(days=start_days_ago)

        db.execute(text("""
            INSERT INTO team_member_profiles (
                name, email, role, department,
                loans_processed, avg_close_time, satisfaction_score, volume,
                start_date, status, is_active, is_deleted,
                created_at, updated_at
            )
            VALUES (
                :name, :email, :role, :department,
                :loans_processed, :avg_close_time, :satisfaction_score, :volume,
                :start_date, 'active', true, false,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "name": member["name"],
            "email": member["email"],
            "role": member["role"],
            "department": member["department"],
            "loans_processed": member["loans_processed"],
            "avg_close_time": member["avg_close_time"],
            "satisfaction_score": member["satisfaction_score"],
            "volume": member["volume"],
            "start_date": start_date
        })

        created_count += 1
        logger.info(f"   ✅ Created profile: {member['name']} ({member['role']}) - {member['loans_processed']} loans")

    db.commit()
    logger.info(f"✅ Created {created_count} team member profiles")
    return created_count


def create_team_members(db):
    """Create team hierarchy: leadership → management → operations/sales"""
    logger.info("👥 Creating team members...")

    created_count = 0
    import os as _os
    _demo_pw = _os.getenv("DEMO_USER_PASSWORD", "")
    if not _demo_pw:
        raise ValueError("DEMO_USER_PASSWORD env var required")
    default_password = pwd_context.hash(_demo_pw)

    for category, members in TEAM_MEMBERS.items():
        for member in members:
            # Check if user exists
            existing = db.execute(text("""
                SELECT id FROM users WHERE email = :email
            """), {"email": member["email"]}).fetchone()

            if existing:
                logger.info(f"   ⏭️  Skipped {member['name']} (already exists)")
                continue

            # Insert user
            db.execute(text("""
                INSERT INTO users (
                    email, hashed_password, full_name, role,
                    account_status, department, created_at
                )
                VALUES (
                    :email, :password, :name, :role,
                    'active', :department, CURRENT_TIMESTAMP
                )
            """), {
                "email": member["email"],
                "password": default_password,
                "name": member["name"],
                "role": member["role"],
                "department": member["department"]
            })

            created_count += 1
            logger.info(f"   ✅ Created {member['name']} ({member['title']})")

    db.commit()
    logger.info(f"✅ Created {created_count} team members")
    return created_count


def create_leads(db):
    """Create demo leads at various stages"""
    logger.info("🎯 Creating demo leads...")

    # First try to find admin@perenniaai.com user (for AI chat to work)
    demo_user = db.execute(text("""
        SELECT id FROM users WHERE email = 'admin@perenniaai.com' LIMIT 1
    """)).fetchone()

    if demo_user:
        owner_id = demo_user.id
        logger.info(f"   📧 Assigning leads to demo user (ID: {owner_id})")
    else:
        # Fall back to loan officer
        loan_officer = db.execute(text("""
            SELECT id FROM users WHERE role IN ('loan_officer', 'sales') LIMIT 1
        """)).fetchone()

        if not loan_officer:
            logger.warning("   ⚠️  No loan officers found, skipping leads")
            return 0

        owner_id = loan_officer.id
        logger.info(f"   👤 Assigning leads to loan officer (ID: {owner_id})")
    created_count = 0

    for lead in DEMO_LEADS:
        # Check if lead exists
        existing = db.execute(text("""
            SELECT id FROM leads WHERE email = :email
        """), {"email": lead["email"]}).fetchone()

        if existing:
            logger.info(f"   ⏭️  Skipped {lead['name']} (already exists)")
            continue

        # Calculate loan details
        loan_amount = lead.get("property_value", 0) - lead.get("down_payment", 0)
        ltv = (loan_amount / lead.get("property_value", 1)) * 100 if lead.get("property_value") else 80
        dti = 35.0 + random.uniform(-10, 10)  # Random DTI around 35%

        db.execute(text("""
            INSERT INTO leads (
                name, email, phone, co_applicant_name,
                stage, source, loan_type, credit_score,
                annual_income, property_value, down_payment,
                loan_amount, ltv, dti, city, state,
                first_time_buyer, owner_id, ai_score, sentiment,
                employer_name, job_title,
                referral_source_score, referral_source_rating,
                created_at, updated_at
            )
            VALUES (
                :name, :email, :phone, :co_applicant,
                :stage, :source, :loan_type, :credit_score,
                :income, :property_value, :down_payment,
                :loan_amount, :ltv, :dti, :city, :state,
                :first_time, :owner_id, :ai_score, 'positive',
                :employer_name, :job_title,
                :referral_source_score, :referral_source_rating,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "name": lead["name"],
            "email": lead["email"],
            "phone": lead.get("phone"),
            "co_applicant": lead.get("co_applicant_name"),
            "stage": lead["stage"],
            "source": lead["source"],
            "loan_type": lead["loan_type"],
            "credit_score": lead.get("credit_score"),
            "income": lead.get("annual_income"),
            "property_value": lead.get("property_value"),
            "down_payment": lead.get("down_payment"),
            "loan_amount": loan_amount,
            "ltv": ltv,
            "dti": dti,
            "city": lead.get("city"),
            "state": lead.get("state"),
            "first_time": lead.get("first_time_buyer", False),
            "owner_id": owner_id,
            "ai_score": 50 + random.randint(-20, 30),
            "employer_name": lead.get("employer_name"),
            "job_title": lead.get("job_title"),
            "referral_source_score": lead.get("referral_source_score", 0),
            "referral_source_rating": lead.get("referral_source_rating")
        })

        created_count += 1
        logger.info(f"   ✅ Created lead: {lead['name']} ({lead['stage']})")

    db.commit()
    logger.info(f"✅ Created {created_count} leads")
    return created_count


def create_active_loans(db):
    """Create demo active loans"""
    logger.info("💰 Creating active loans...")

    # First try to find admin@perenniaai.com user (for AI chat to work)
    demo_user = db.execute(text("""
        SELECT id FROM users WHERE email = 'admin@perenniaai.com' LIMIT 1
    """)).fetchone()

    if demo_user:
        lo_id = demo_user.id
        logger.info(f"   📧 Assigning loans to demo user (ID: {lo_id})")
    else:
        # Fall back to loan officer
        loan_officer = db.execute(text("""
            SELECT id FROM users WHERE role IN ('loan_officer', 'sales') LIMIT 1
        """)).fetchone()

        if not loan_officer:
            logger.warning("   ⚠️  No loan officers found, skipping loans")
            return 0

        lo_id = loan_officer.id
        logger.info(f"   👤 Assigning loans to loan officer (ID: {lo_id})")
    created_count = 0

    for loan in DEMO_LOANS:
        # Check if loan exists
        existing = db.execute(text("""
            SELECT id FROM loans WHERE loan_number = :loan_number
        """), {"loan_number": loan["loan_number"]}).fetchone()

        if existing:
            logger.info(f"   ⏭️  Skipped {loan['loan_number']} (already exists)")
            continue

        # Calculate dates
        if loan["stage"] == "Funded":
            # Funded loans: set funded_date and created_at in the past
            funded_date = datetime.now(timezone.utc).date() - timedelta(days=loan.get("funded_days_ago", 10))
            created_at = datetime.now(timezone.utc) - timedelta(days=loan.get("created_days_ago", 40))
            closing_date = funded_date
            lock_date = datetime.now(timezone.utc) - timedelta(days=loan.get("created_days_ago", 40) - 5)
        else:
            # Active loans: closing date in future
            closing_date = datetime.now(timezone.utc) + timedelta(days=loan.get("closing_date_days", 30))
            lock_date = datetime.now(timezone.utc) - timedelta(days=random.randint(5, 15))
            funded_date = None
            created_at = datetime.now(timezone.utc)

        db.execute(text("""
            INSERT INTO loans (
                loan_number, borrower_name, coborrower_name,
                stage, program, loan_type, amount,
                purchase_price, down_payment, rate, term,
                property_address, closing_date, lock_date,
                funded_date, processor, loan_officer_id,
                days_in_stage, sla_status, risk_score,
                created_at, updated_at
            )
            VALUES (
                :loan_number, :borrower, :coborrower,
                :stage, :program, :loan_type, :amount,
                :purchase_price, :down_payment, :rate, :term,
                :address, :closing_date, :lock_date,
                :funded_date, :processor, :lo_id,
                :days_in_stage, 'on-track', :risk_score,
                :created_at, CURRENT_TIMESTAMP
            )
        """), {
            "loan_number": loan["loan_number"],
            "borrower": loan["borrower_name"],
            "coborrower": loan.get("coborrower_name"),
            "stage": loan["stage"],
            "program": loan["program"],
            "loan_type": loan["loan_type"],
            "amount": loan["amount"],
            "purchase_price": loan.get("purchase_price"),
            "down_payment": loan.get("down_payment"),
            "rate": loan["rate"],
            "term": loan["term"],
            "address": loan["property_address"],
            "closing_date": closing_date,
            "lock_date": lock_date,
            "funded_date": funded_date,
            "processor": loan.get("processor"),
            "lo_id": lo_id,
            "days_in_stage": loan.get("days_in_stage", random.randint(3, 15)),
            "risk_score": random.randint(10, 40),
            "created_at": created_at
        })

        created_count += 1
        logger.info(f"   ✅ Created loan: {loan['loan_number']} ({loan['stage']})")

    db.commit()
    logger.info(f"✅ Created {created_count} active loans")
    return created_count


def create_mum_clients(db):
    """Create MUM (Clients for Life) demo data"""
    logger.info("🏡 Creating MUM clients...")

    # Get a random loan officer
    loan_officer = db.execute(text("""
        SELECT id, full_name FROM users WHERE role IN ('loan_officer', 'sales') LIMIT 1
    """)).fetchone()

    if not loan_officer:
        logger.warning("   ⚠️  No loan officers found, skipping MUM clients")
        return 0

    created_count = 0

    for client in DEMO_MUM_CLIENTS:
        # Check if client exists
        existing = db.execute(text("""
            SELECT id FROM mum_clients WHERE email = :email
        """), {"email": client["email"]}).fetchone()

        if existing:
            logger.info(f"   ⏭️  Skipped {client['name']} (already exists)")
            continue

        # Calculate dates
        original_loan_date = datetime.now(timezone.utc) - timedelta(days=client["original_loan_date"])
        first_payment_date = original_loan_date + timedelta(days=45)  # ~45 days after closing
        last_contact = datetime.now(timezone.utc) - timedelta(days=client["last_contact_days"])

        # Get original property value
        original_property = client.get("original_property_value", client["original_loan_amount"] * 1.25)

        db.execute(text("""
            INSERT INTO mum_clients (
                name, email, phone, status,
                original_loan_date, original_loan_amount,
                original_property_value, current_property_value,
                interest_rate, loan_term, loan_type,
                first_payment_date,
                last_contact_date, next_touchpoint_type,
                engagement_score, lifecycle_stage,
                loan_officer_name, created_at
            )
            VALUES (
                :name, :email, :phone, 'active',
                :loan_date, :loan_amount,
                :original_property, :original_property,
                :interest_rate, :loan_term, :loan_type,
                :first_payment,
                :last_contact, :next_milestone,
                :engagement, 'active',
                :lo_name, CURRENT_TIMESTAMP
            )
        """), {
            "name": client["name"],
            "email": client["email"],
            "phone": client["phone"],
            "loan_date": original_loan_date,
            "loan_amount": client["original_loan_amount"],
            "original_property": original_property,
            "interest_rate": client.get("interest_rate", 6.5),
            "loan_term": client.get("loan_term", 30),
            "loan_type": client.get("loan_type", "Conventional 30-Year Fixed"),
            "first_payment": first_payment_date,
            "last_contact": last_contact,
            "next_milestone": client["next_milestone"],
            "engagement": 75 if client["engagement_level"] == "High" else 50 if client["engagement_level"] == "Medium" else 25,
            "lo_name": loan_officer.full_name
        })

        created_count += 1
        logger.info(f"   ✅ Created MUM client: {client['name']} ({client['engagement_level']} engagement)")

    db.commit()
    logger.info(f"✅ Created {created_count} MUM clients")
    return created_count


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def seed_all_demo_data():
    """Seed all demo data categories"""
    db = SessionLocal()

    try:
        logger.info("=" * 80)
        logger.info("🌱 SEEDING COMPREHENSIVE DEMO DATA")
        logger.info("=" * 80)
        logger.info("")

        # Create data in order of dependencies
        team_count = create_team_members(db)
        logger.info("")

        profile_count = create_team_member_profiles(db)
        logger.info("")

        leads_count = create_leads(db)
        logger.info("")

        loans_count = create_active_loans(db)
        logger.info("")

        mum_count = create_mum_clients(db)
        logger.info("")

        # Summary
        logger.info("=" * 80)
        logger.info("✅ DEMO DATA SEEDING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Team Members:   {team_count}")
        logger.info(f"Team Profiles:  {profile_count}")
        logger.info(f"Leads:          {leads_count}")
        logger.info(f"Active Loans:   {loans_count}")
        logger.info(f"MUM Clients:    {mum_count}")
        logger.info(f"TOTAL:          {team_count + profile_count + leads_count + loans_count + mum_count}")
        logger.info("")
        logger.info("📝 Demo Credentials:")
        logger.debug("   Demo users use standard demo password")
        logger.info("=" * 80)

        return {
            "success": True,
            "team_members": team_count,
            "team_profiles": profile_count,
            "leads": leads_count,
            "loans": loans_count,
            "mum_clients": mum_count,
            "total": team_count + profile_count + leads_count + loans_count + mum_count
        }

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error seeding demo data: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": "Internal server error"}
    finally:
        db.close()


if __name__ == "__main__":
    result = seed_all_demo_data()

    if not result["success"]:
        sys.exit(1)
