#!/usr/bin/env python3
"""
Test Account Seed Script
========================
Creates a fully-populated test account with dummy data across all CRM categories:
- User account with organization
- Leads (various stages)
- Loans (various pipeline stages)
- MUM clients (Manage, Upsell, Maintain)
- Referral partners
- Tasks (linked to leads and loans)
- Reconciliation data (incoming data events + extracted data)

Test Account Credentials:
  Email:    testuser@perenniaai.com
  Password: TestAccount2026!
"""

import sys
import os
import random
import json
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from main import logger
from passlib.context import CryptContext
from sqlalchemy import text

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# =============================================================================
# TEST ACCOUNT CREDENTIALS
# =============================================================================
TEST_EMAIL = os.environ.get("TEST_EMAIL", "testuser@perenniaai.com")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "TestAccount2026!")
TEST_FULL_NAME = "Test User"
TEST_COMPANY = "Perennia Test Corp"

# =============================================================================
# DUMMY DATA DEFINITIONS
# =============================================================================

DUMMY_LEADS = [
    {
        "name": "Alice Morgan",
        "email": "alice.morgan@testlead.com",
        "phone": "(555) 100-2001",
        "stage": "New",
        "source": "Website",
        "loan_type": "Purchase - Conventional",
        "credit_score": 745,
        "annual_income": 118000,
        "property_value": 465000,
        "down_payment": 93000,
        "city": "Denver",
        "state": "CO",
    },
    {
        "name": "Brian Carter",
        "email": "brian.carter@testlead.com",
        "phone": "(555) 100-2002",
        "stage": "Prospect",
        "source": "Referral Partner",
        "loan_type": "Purchase - FHA",
        "credit_score": 672,
        "annual_income": 79000,
        "property_value": 310000,
        "down_payment": 10850,
        "city": "Phoenix",
        "state": "AZ",
    },
    {
        "name": "Carmen Delgado",
        "email": "carmen.delgado@testlead.com",
        "phone": "(555) 100-2003",
        "stage": "Application",
        "source": "Zillow",
        "loan_type": "Refinance - Conventional",
        "credit_score": 730,
        "annual_income": 142000,
        "property_value": 520000,
        "city": "Austin",
        "state": "TX",
    },
    {
        "name": "Derek Holmes",
        "email": "derek.holmes@testlead.com",
        "phone": "(555) 100-2004",
        "stage": "Application",
        "source": "Facebook Ad",
        "loan_type": "Purchase - VA",
        "credit_score": 700,
        "annual_income": 96000,
        "property_value": 375000,
        "down_payment": 0,
        "city": "San Diego",
        "state": "CA",
    },
    {
        "name": "Elena Vasquez",
        "email": "elena.vasquez@testlead.com",
        "phone": "(555) 100-2005",
        "stage": "Pre-Approved",
        "source": "Realtor Referral",
        "loan_type": "Purchase - Jumbo",
        "credit_score": 790,
        "annual_income": 265000,
        "property_value": 920000,
        "down_payment": 184000,
        "city": "Scottsdale",
        "state": "AZ",
    },
    {
        "name": "Frank Nguyen",
        "email": "frank.nguyen@testlead.com",
        "phone": "(555) 100-2006",
        "stage": "New",
        "source": "Google",
        "loan_type": "Purchase - Conventional",
        "credit_score": 718,
        "annual_income": 101000,
        "property_value": 389000,
        "down_payment": 77800,
        "city": "Raleigh",
        "state": "NC",
    },
    {
        "name": "Grace Okonkwo",
        "email": "grace.okonkwo@testlead.com",
        "phone": "(555) 100-2007",
        "stage": "Attempted Contact",
        "source": "Website",
        "loan_type": "Purchase - FHA",
        "credit_score": 660,
        "annual_income": 68000,
        "property_value": 275000,
        "down_payment": 9625,
        "city": "Charlotte",
        "state": "NC",
    },
    {
        "name": "Henry Park",
        "email": "henry.park@testlead.com",
        "phone": "(555) 100-2008",
        "stage": "Prospect",
        "source": "Past Client Referral",
        "loan_type": "Refinance - Cash Out",
        "credit_score": 740,
        "annual_income": 172000,
        "property_value": 640000,
        "city": "Seattle",
        "state": "WA",
    },
    {
        "name": "Isabella Moreno",
        "email": "isabella.moreno@testlead.com",
        "phone": "(555) 100-2009",
        "stage": "Pre-Approved",
        "source": "LinkedIn",
        "loan_type": "Purchase - Conventional",
        "credit_score": 765,
        "annual_income": 195000,
        "property_value": 550000,
        "down_payment": 110000,
        "city": "Portland",
        "state": "OR",
    },
    {
        "name": "James Fletcher",
        "email": "james.fletcher@testlead.com",
        "phone": "(555) 100-2010",
        "stage": "Application",
        "source": "Realtor Referral",
        "loan_type": "Purchase - Conventional",
        "credit_score": 752,
        "annual_income": 168000,
        "property_value": 580000,
        "down_payment": 116000,
        "city": "Nashville",
        "state": "TN",
    },
    {
        "name": "Karen Sullivan",
        "email": "karen.sullivan@testlead.com",
        "phone": "(555) 100-2011",
        "stage": "New",
        "source": "Google",
        "loan_type": "Purchase - USDA",
        "credit_score": 695,
        "annual_income": 74000,
        "property_value": 245000,
        "down_payment": 0,
        "city": "Boise",
        "state": "ID",
    },
    {
        "name": "Liam O'Brien",
        "email": "liam.obrien@testlead.com",
        "phone": "(555) 100-2012",
        "stage": "Prospect",
        "source": "Website",
        "loan_type": "Refinance - Conventional",
        "credit_score": 710,
        "annual_income": 125000,
        "property_value": 480000,
        "city": "Tampa",
        "state": "FL",
    },
]

DUMMY_LOANS = [
    {
        "loan_number": "TEST-001001",
        "borrower_name": "Marcus Powell",
        "coborrower_name": "Tanya Powell",
        "stage": "Processing",
        "program": "Conventional 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 405000,
        "purchase_price": 505000,
        "down_payment": 100000,
        "rate": 6.750,
        "term": 360,
        "property_address": "221 Birch Lane, Denver, CO 80202",
        "closing_date_days": 28,
        "processor": "Amanda Foster",
    },
    {
        "loan_number": "TEST-001002",
        "borrower_name": "Sandra Yee",
        "stage": "UW Received",
        "program": "FHA 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 278000,
        "purchase_price": 290000,
        "down_payment": 10150,
        "rate": 6.500,
        "term": 360,
        "property_address": "456 Elm Street, Phoenix, AZ 85001",
        "closing_date_days": 20,
        "processor": "Robert Garcia",
    },
    {
        "loan_number": "TEST-001003",
        "borrower_name": "William Chen",
        "coborrower_name": "Amy Chen",
        "stage": "Approved",
        "program": "VA 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 380000,
        "purchase_price": 380000,
        "down_payment": 0,
        "rate": 6.375,
        "term": 360,
        "property_address": "789 Oak Drive, San Diego, CA 92101",
        "closing_date_days": 14,
        "processor": "Amanda Foster",
    },
    {
        "loan_number": "TEST-001004",
        "borrower_name": "Rachel Green",
        "stage": "Disclosed",
        "program": "Conventional 15-Year Fixed",
        "loan_type": "Refinance",
        "amount": 310000,
        "rate": 6.125,
        "term": 180,
        "property_address": "1234 Maple Avenue, Scottsdale, AZ 85251",
        "closing_date_days": 38,
        "processor": "Kevin Park",
    },
    {
        "loan_number": "TEST-001005",
        "borrower_name": "David Okafor",
        "coborrower_name": "Ngozi Okafor",
        "stage": "CTC",
        "program": "Jumbo 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 790000,
        "purchase_price": 1050000,
        "down_payment": 260000,
        "rate": 7.000,
        "term": 360,
        "property_address": "5678 Highland Terrace, Bellevue, WA 98004",
        "closing_date_days": 6,
        "processor": "Robert Garcia",
    },
    {
        "loan_number": "TEST-001006",
        "borrower_name": "Patricia Luna",
        "stage": "Processing",
        "program": "FHA 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 252000,
        "purchase_price": 270000,
        "down_payment": 9450,
        "rate": 6.625,
        "term": 360,
        "property_address": "3456 Cedar Court, Raleigh, NC 27601",
        "closing_date_days": 30,
        "processor": "Amanda Foster",
    },
    {
        "loan_number": "TEST-001007",
        "borrower_name": "Jeffrey Kim",
        "coborrower_name": "Michelle Kim",
        "stage": "CTC",
        "program": "Conventional 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 525000,
        "purchase_price": 660000,
        "down_payment": 135000,
        "rate": 6.875,
        "term": 360,
        "property_address": "9012 Sunset Boulevard, Nashville, TN 37203",
        "closing_date_days": 4,
        "processor": "Robert Garcia",
    },
    # Funded loans for metrics
    {
        "loan_number": "TEST-009001",
        "borrower_name": "Carlos Ramirez",
        "coborrower_name": "Maria Ramirez",
        "stage": "Funded",
        "program": "Conventional 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 375000,
        "purchase_price": 470000,
        "down_payment": 95000,
        "rate": 6.750,
        "term": 360,
        "property_address": "111 Palm Street, Tampa, FL 33602",
        "processor": "Robert Garcia",
        "funded_days_ago": 7,
        "created_days_ago": 42,
    },
    {
        "loan_number": "TEST-009002",
        "borrower_name": "Heather Brooks",
        "stage": "Funded",
        "program": "FHA 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 268000,
        "purchase_price": 285000,
        "down_payment": 9975,
        "rate": 6.500,
        "term": 360,
        "property_address": "222 River Walk, Portland, OR 97201",
        "processor": "Amanda Foster",
        "funded_days_ago": 15,
        "created_days_ago": 48,
    },
    {
        "loan_number": "TEST-009003",
        "borrower_name": "Trevor Simmons",
        "coborrower_name": "Lori Simmons",
        "stage": "Funded",
        "program": "VA 30-Year Fixed",
        "loan_type": "Purchase",
        "amount": 345000,
        "purchase_price": 345000,
        "down_payment": 0,
        "rate": 6.250,
        "term": 360,
        "property_address": "333 Lake View Drive, Boise, ID 83702",
        "processor": "Robert Garcia",
        "funded_days_ago": 22,
        "created_days_ago": 55,
    },
]

DUMMY_MUM_CLIENTS = [
    {
        "name": "Alexander Wright",
        "email": "alex.wright@testmum.com",
        "phone": "(555) 300-4001",
        "original_loan_date": 700,
        "original_loan_amount": 395000,
        "original_property_value": 460000,
        "interest_rate": 6.125,
        "loan_term": 30,
        "loan_type": "Conventional 30-Year Fixed",
        "engagement_level": "High",
        "last_contact_days": 40,
        "next_milestone": "Home Anniversary",
    },
    {
        "name": "Brittany Soto",
        "email": "brittany.soto@testmum.com",
        "phone": "(555) 300-4002",
        "original_loan_date": 1100,
        "original_loan_amount": 440000,
        "original_property_value": 490000,
        "interest_rate": 5.750,
        "loan_term": 30,
        "loan_type": "Conventional 30-Year Fixed",
        "engagement_level": "Medium",
        "last_contact_days": 85,
        "next_milestone": "Equity Check-in",
    },
    {
        "name": "Curtis Palmer",
        "email": "curtis.palmer@testmum.com",
        "phone": "(555) 300-4003",
        "original_loan_date": 370,
        "original_loan_amount": 285000,
        "original_property_value": 310000,
        "interest_rate": 6.875,
        "loan_term": 30,
        "loan_type": "FHA 30-Year Fixed",
        "engagement_level": "High",
        "last_contact_days": 25,
        "next_milestone": "1-Year Anniversary",
    },
    {
        "name": "Diana Wells",
        "email": "diana.wells@testmum.com",
        "phone": "(555) 300-4004",
        "original_loan_date": 1830,
        "original_loan_amount": 355000,
        "original_property_value": 410000,
        "interest_rate": 4.250,
        "loan_term": 30,
        "loan_type": "VA 30-Year Fixed",
        "engagement_level": "Medium",
        "last_contact_days": 110,
        "next_milestone": "Refinance Opportunity",
    },
    {
        "name": "Eduardo Reyes",
        "email": "eduardo.reyes@testmum.com",
        "phone": "(555) 300-4005",
        "original_loan_date": 540,
        "original_loan_amount": 510000,
        "original_property_value": 550000,
        "interest_rate": 6.625,
        "loan_term": 30,
        "loan_type": "Jumbo 30-Year Fixed",
        "engagement_level": "Low",
        "last_contact_days": 170,
        "next_milestone": "Market Update",
    },
    {
        "name": "Fiona Blake",
        "email": "fiona.blake@testmum.com",
        "phone": "(555) 300-4006",
        "original_loan_date": 280,
        "original_loan_amount": 325000,
        "original_property_value": 345000,
        "interest_rate": 7.125,
        "loan_term": 30,
        "loan_type": "Conventional 30-Year Fixed",
        "engagement_level": "High",
        "last_contact_days": 15,
        "next_milestone": "6-Month Check-in",
    },
    {
        "name": "George Nakamura",
        "email": "george.nakamura@testmum.com",
        "phone": "(555) 300-4007",
        "original_loan_date": 1450,
        "original_loan_amount": 275000,
        "original_property_value": 315000,
        "interest_rate": 3.875,
        "loan_term": 15,
        "loan_type": "Conventional 15-Year Fixed",
        "engagement_level": "High",
        "last_contact_days": 55,
        "next_milestone": "Refinance Review",
    },
    {
        "name": "Hannah Foster",
        "email": "hannah.foster.mum@testmum.com",
        "phone": "(555) 300-4008",
        "original_loan_date": 920,
        "original_loan_amount": 495000,
        "original_property_value": 560000,
        "interest_rate": 5.625,
        "loan_term": 30,
        "loan_type": "Jumbo 30-Year Fixed",
        "engagement_level": "Medium",
        "last_contact_days": 70,
        "next_milestone": "Market Update",
    },
]

DUMMY_REFERRAL_PARTNERS = [
    {
        "name": "Sarah Kim Realty",
        "contact_name": "Sarah Kim",
        "business_name": "Sarah Kim Realty Group",
        "category": "realtor",
        "company": "Keller Williams",
        "type": "Real Estate Agent",
        "phone": "(555) 400-5001",
        "email": "sarah.kim@kwrealty.com",
        "referrals_in": 18,
        "referrals_out": 5,
        "closed_loans": 12,
        "volume": 4250000.0,
        "reciprocity_score": 88.5,
        "loyalty_tier": "gold",
        "title": "Broker Associate",
        "city": "Denver",
        "state": "CO",
        "notes": "Top producing agent in metro area. Specializes in first-time buyers.",
    },
    {
        "name": "Rodriguez & Associates",
        "contact_name": "Miguel Rodriguez",
        "business_name": "Rodriguez & Associates Law Firm",
        "category": "attorney",
        "company": "Rodriguez & Associates",
        "type": "Real Estate Attorney",
        "phone": "(555) 400-5002",
        "email": "miguel@rodriguezlaw.com",
        "referrals_in": 8,
        "referrals_out": 3,
        "closed_loans": 6,
        "volume": 2100000.0,
        "reciprocity_score": 72.0,
        "loyalty_tier": "silver",
        "title": "Managing Partner",
        "city": "Phoenix",
        "state": "AZ",
        "notes": "Handles complex closings. Bilingual Spanish/English.",
    },
    {
        "name": "Premier Title Services",
        "contact_name": "Janet Cooper",
        "business_name": "Premier Title Services LLC",
        "category": "title_company",
        "company": "Premier Title Services",
        "type": "Title Company",
        "phone": "(555) 400-5003",
        "email": "janet@premiertitle.com",
        "referrals_in": 25,
        "referrals_out": 10,
        "closed_loans": 22,
        "volume": 7850000.0,
        "reciprocity_score": 95.0,
        "loyalty_tier": "platinum",
        "title": "Vice President",
        "city": "Austin",
        "state": "TX",
        "notes": "Our primary title partner. Fast turnaround on title searches.",
    },
    {
        "name": "Tom Bradley Insurance",
        "contact_name": "Tom Bradley",
        "business_name": "Bradley Insurance Agency",
        "category": "insurance_agent",
        "company": "State Farm",
        "type": "Insurance Agent",
        "phone": "(555) 400-5004",
        "email": "tom.bradley@statefarm.com",
        "referrals_in": 6,
        "referrals_out": 2,
        "closed_loans": 4,
        "volume": 1450000.0,
        "reciprocity_score": 60.0,
        "loyalty_tier": "bronze",
        "title": "Licensed Agent",
        "city": "San Diego",
        "state": "CA",
        "notes": "Great for bundled home/auto quotes. Quick binder turnaround.",
    },
    {
        "name": "Westside Financial Planning",
        "contact_name": "Amanda Tran",
        "business_name": "Westside Financial Planning",
        "category": "financial_advisor",
        "company": "Westside Financial Planning",
        "type": "Financial Advisor",
        "phone": "(555) 400-5005",
        "email": "amanda@westsidefp.com",
        "referrals_in": 14,
        "referrals_out": 7,
        "closed_loans": 10,
        "volume": 3600000.0,
        "reciprocity_score": 82.0,
        "loyalty_tier": "gold",
        "title": "CFP",
        "city": "Seattle",
        "state": "WA",
        "notes": "Sends high-net-worth clients. Great for investment property referrals.",
    },
    {
        "name": "Apex Home Inspection",
        "contact_name": "Robert Barnes",
        "business_name": "Apex Home Inspection LLC",
        "category": "home_inspector",
        "company": "Apex Home Inspection",
        "type": "Home Inspector",
        "phone": "(555) 400-5006",
        "email": "robert@apexinspect.com",
        "referrals_in": 4,
        "referrals_out": 1,
        "closed_loans": 3,
        "volume": 980000.0,
        "reciprocity_score": 45.0,
        "loyalty_tier": "bronze",
        "title": "Licensed Inspector",
        "city": "Nashville",
        "state": "TN",
        "notes": "Reliable and thorough. Available on weekends.",
    },
    {
        "name": "Pacific CPA Group",
        "contact_name": "Linda Park",
        "business_name": "Pacific CPA Group",
        "category": "cpa",
        "company": "Pacific CPA Group",
        "type": "CPA",
        "phone": "(555) 400-5007",
        "email": "linda@pacificcpa.com",
        "referrals_in": 10,
        "referrals_out": 4,
        "closed_loans": 7,
        "volume": 2800000.0,
        "reciprocity_score": 78.0,
        "loyalty_tier": "silver",
        "title": "Senior Partner",
        "city": "Portland",
        "state": "OR",
        "notes": "Tax return verification is fast. Sends self-employed borrowers our way.",
    },
    {
        "name": "Elite Builders Group",
        "contact_name": "Marcus Hall",
        "business_name": "Elite Builders Group Inc",
        "category": "builder",
        "company": "Elite Builders Group",
        "type": "Builder/Developer",
        "phone": "(555) 400-5008",
        "email": "marcus@elitebuilders.com",
        "referrals_in": 20,
        "referrals_out": 8,
        "closed_loans": 15,
        "volume": 6200000.0,
        "reciprocity_score": 90.0,
        "loyalty_tier": "platinum",
        "title": "President",
        "city": "Charlotte",
        "state": "NC",
        "notes": "New construction specialist. Volume builder with 3 active subdivisions.",
    },
]

DUMMY_TASKS = [
    # Tasks linked to leads
    {"title": "Call Alice Morgan - initial contact", "description": "Make first contact call to discuss conventional purchase options.", "status": "pending", "priority": "high", "due_days": 1, "link": "lead", "link_name": "alice.morgan@testlead.com"},
    {"title": "Send pre-approval package to Elena Vasquez", "description": "Elena qualifies for jumbo. Send pre-approval letter and rate sheet.", "status": "in_progress", "priority": "high", "due_days": 0, "link": "lead", "link_name": "elena.vasquez@testlead.com"},
    {"title": "Follow up with Brian Carter - FHA docs needed", "description": "Brian needs to provide last 2 years tax returns for FHA qualification.", "status": "pending", "priority": "medium", "due_days": 3, "link": "lead", "link_name": "brian.carter@testlead.com"},
    {"title": "Review Carmen Delgado refi analysis", "description": "Run refi breakeven analysis and compare current rate vs market.", "status": "pending", "priority": "medium", "due_days": 2, "link": "lead", "link_name": "carmen.delgado@testlead.com"},
    {"title": "Schedule call with Grace Okonkwo", "description": "First-time buyer education call. Discuss FHA program requirements.", "status": "pending", "priority": "low", "due_days": 5, "link": "lead", "link_name": "grace.okonkwo@testlead.com"},
    # Tasks linked to loans
    {"title": "Order appraisal - TEST-001001", "description": "Order appraisal for Marcus Powell conventional purchase.", "status": "in_progress", "priority": "high", "due_days": 1, "link": "loan", "link_name": "TEST-001001"},
    {"title": "Review UW conditions - TEST-001002", "description": "Sandra Yee FHA - review underwriting conditions and request missing docs.", "status": "pending", "priority": "high", "due_days": 2, "link": "loan", "link_name": "TEST-001002"},
    {"title": "Request updated VOE - TEST-001003", "description": "William Chen VA loan - employer verification needs to be updated.", "status": "pending", "priority": "medium", "due_days": 3, "link": "loan", "link_name": "TEST-001003"},
    {"title": "Schedule closing - TEST-001005", "description": "David Okafor jumbo loan CTC. Coordinate closing with title company.", "status": "in_progress", "priority": "high", "due_days": 0, "link": "loan", "link_name": "TEST-001005"},
    {"title": "Send CD to borrower - TEST-001007", "description": "Jeffrey Kim docs out stage. Verify CD was sent and confirm receipt.", "status": "pending", "priority": "high", "due_days": 1, "link": "loan", "link_name": "TEST-001007"},
    # General tasks
    {"title": "Weekly pipeline review meeting", "description": "Review all active loans and leads. Prepare status report for management.", "status": "pending", "priority": "medium", "due_days": 2, "link": None, "link_name": None},
    {"title": "Update referral partner scorecards", "description": "Monthly partner performance review. Update loyalty tiers.", "status": "pending", "priority": "low", "due_days": 7, "link": None, "link_name": None},
    {"title": "Complete compliance training module", "description": "TRID and HMDA annual compliance training due this week.", "status": "pending", "priority": "high", "due_days": 5, "link": None, "link_name": None},
    {"title": "Review MUM client outreach list", "description": "Review clients due for anniversary or equity check-in touches.", "status": "completed", "priority": "medium", "due_days": -2, "link": None, "link_name": None},
    {"title": "Send rate update to pre-approved leads", "description": "Rates dropped 0.125%. Notify all pre-approved leads.", "status": "completed", "priority": "high", "due_days": -1, "link": None, "link_name": None},
]

# =============================================================================
# ADDITIONAL DUMMY DATA DEFINITIONS
# =============================================================================

DUMMY_ACTIVITIES = [
    # Lead activities - using lowercase type values to match DB enum
    {"type": "call", "content": "Initial contact call - discussed loan options and timeline. Prospect is interested in conventional purchase.", "link_type": "lead", "link_ref": "alice.morgan@testlead.com", "days_ago": 2, "duration": "8 min", "sentiment": "positive"},
    {"type": "email", "content": "Sent rate sheet and pre-qualification checklist. Follow-up scheduled for Thursday.", "link_type": "lead", "link_ref": "alice.morgan@testlead.com", "days_ago": 1, "sentiment": "positive"},
    {"type": "note", "content": "Strong lead - pre-approved at previous lender but shopping for better rate. Has realtor actively showing properties.", "link_type": "lead", "link_ref": "elena.vasquez@testlead.com", "days_ago": 3, "sentiment": "positive"},
    {"type": "meeting", "content": "Zoom consultation - reviewed jumbo loan requirements and provided custom rate quote. Very engaged.", "link_type": "lead", "link_ref": "elena.vasquez@testlead.com", "days_ago": 1, "duration": "35 min", "sentiment": "positive"},
    {"type": "sms", "content": "Thanks for the info! I'll review and get back to you tomorrow.", "link_type": "lead", "link_ref": "brian.carter@testlead.com", "days_ago": 4, "sentiment": "positive"},
    {"type": "call", "content": "Left voicemail - second attempt. Will try again Monday.", "link_type": "lead", "link_ref": "grace.okonkwo@testlead.com", "days_ago": 5, "duration": "1 min", "sentiment": "neutral"},
    {"type": "email", "content": "Sent first-time buyer guide and FHA program overview.", "link_type": "lead", "link_ref": "grace.okonkwo@testlead.com", "days_ago": 4, "sentiment": "neutral"},
    {"type": "call", "content": "Discussed refinance options - current rate is 6.5%, can save with rate/term refi. Sending comparison.", "link_type": "lead", "link_ref": "carmen.delgado@testlead.com", "days_ago": 2, "duration": "12 min", "sentiment": "positive"},
    # Loan activities
    {"type": "email", "content": "Received updated bank statements from borrower. Forwarded to processor.", "link_type": "loan", "link_ref": "TEST-001001", "days_ago": 1, "sentiment": "positive"},
    {"type": "call", "content": "Coordination call with processor Amanda - appraisal ordered, title in process.", "link_type": "loan", "link_ref": "TEST-001001", "days_ago": 2, "duration": "6 min", "sentiment": "positive"},
    {"type": "note", "content": "UW received conditions cleared. Waiting on appraisal review.", "link_type": "loan", "link_ref": "TEST-001002", "days_ago": 3, "sentiment": "positive"},
    {"type": "meeting", "content": "Closing prep call with David & Ngozi Okafor - reviewed CD, no surprises.", "link_type": "loan", "link_ref": "TEST-001005", "days_ago": 1, "duration": "20 min", "sentiment": "positive"},
    {"type": "email", "content": "CD sent for review. Closing confirmed for Feb 2nd at Premier Title.", "link_type": "loan", "link_ref": "TEST-001007", "days_ago": 0, "sentiment": "positive"},
    {"type": "call", "content": "Rate lock discussion with borrower - locked 45-day at 6.75%. Lock confirmation sent.", "link_type": "loan", "link_ref": "TEST-001003", "days_ago": 5, "duration": "10 min", "sentiment": "positive"},
    {"type": "document", "content": "Appraisal received - value came in at asking price. No issues.", "link_type": "loan", "link_ref": "TEST-001006", "days_ago": 2, "sentiment": "positive"},
    {"type": "note", "content": "Processor flagged: need updated VOE - employer verification expired.", "link_type": "loan", "link_ref": "TEST-001003", "days_ago": 1, "sentiment": "neutral"},
    # MUM client activities
    {"type": "email", "content": "Sent annual home value report and refinance analysis.", "link_type": "mum", "link_ref": "alex.wright@testmum.com", "days_ago": 10, "sentiment": "positive"},
    {"type": "call", "content": "Anniversary check-in - reviewed current market and discussed home equity options.", "link_type": "mum", "link_ref": "curtis.palmer@testmum.com", "days_ago": 5, "duration": "15 min", "sentiment": "positive"},
    {"type": "sms", "content": "Happy 1-year anniversary in your new home! Let me know if you ever have questions.", "link_type": "mum", "link_ref": "fiona.blake@testmum.com", "days_ago": 3, "sentiment": "positive"},
]

DUMMY_CALENDAR_EVENTS = [
    {"title": "Call - Alice Morgan (New Lead)", "description": "Follow-up call to discuss pre-approval", "event_type": "call", "days_from_now": 1, "hour": 10, "duration_min": 30, "link_type": "lead", "link_ref": "alice.morgan@testlead.com"},
    {"title": "Zoom - Elena Vasquez (Pre-Approval)", "description": "Final pre-approval review and rate lock discussion", "event_type": "meeting", "days_from_now": 2, "hour": 14, "duration_min": 45, "link_type": "lead", "link_ref": "elena.vasquez@testlead.com"},
    {"title": "Closing - Jeffrey & Michelle Kim", "description": "Closing at Premier Title Services, 789 Oak Dr Nashville", "event_type": "closing", "days_from_now": 4, "hour": 14, "duration_min": 90, "link_type": "loan", "link_ref": "TEST-001007"},
    {"title": "Closing - David & Ngozi Okafor", "description": "Jumbo purchase closing at Premier Title", "event_type": "closing", "days_from_now": 6, "hour": 10, "duration_min": 90, "link_type": "loan", "link_ref": "TEST-001005"},
    {"title": "Check-in Call - Diana Wells (MUM)", "description": "Refinance opportunity discussion", "event_type": "call", "days_from_now": 3, "hour": 11, "duration_min": 20, "link_type": "mum", "link_ref": "diana.wells@testmum.com"},
    {"title": "Weekly Pipeline Review", "description": "Internal team meeting to review pipeline status", "event_type": "meeting", "days_from_now": 2, "hour": 9, "duration_min": 60, "link_type": None, "link_ref": None},
    {"title": "Partner Lunch - Sarah Kim Realty", "description": "Quarterly partner relationship lunch", "event_type": "meeting", "days_from_now": 5, "hour": 12, "duration_min": 90, "link_type": "partner", "link_ref": "sarah.kim@kwrealty.com"},
    {"title": "Appraisal - 221 Birch Lane", "description": "Appraiser access for Powell property", "event_type": "appraisal", "days_from_now": 1, "hour": 13, "duration_min": 120, "link_type": "loan", "link_ref": "TEST-001001"},
]

DUMMY_DOCUMENTS = [
    {"loan_ref": "TEST-001001", "doc_type": "W2", "category": "Income", "filename": "powell_w2_2025.pdf"},
    {"loan_ref": "TEST-001001", "doc_type": "Paystub", "category": "Income", "filename": "powell_paystub_jan2026.pdf"},
    {"loan_ref": "TEST-001001", "doc_type": "Bank Statement", "category": "Assets", "filename": "powell_chase_statement.pdf"},
    {"loan_ref": "TEST-001002", "doc_type": "Tax Return (1040)", "category": "Income", "filename": "yee_1040_2024.pdf"},
    {"loan_ref": "TEST-001002", "doc_type": "W2", "category": "Income", "filename": "yee_w2_2025.pdf"},
    {"loan_ref": "TEST-001003", "doc_type": "Employment Verification", "category": "Income", "filename": "chen_voe.pdf"},
    {"loan_ref": "TEST-001003", "doc_type": "Bank Statement", "category": "Assets", "filename": "chen_boa_statement.pdf"},
    {"loan_ref": "TEST-001005", "doc_type": "Bank Statement", "category": "Assets", "filename": "okafor_statements_combined.pdf"},
    {"loan_ref": "TEST-001005", "doc_type": "Gift Letter", "category": "Assets", "filename": "okafor_gift_letter.pdf"},
    {"loan_ref": "TEST-001007", "doc_type": "Closing Disclosure", "category": "Disclosures", "filename": "kim_cd_final.pdf"},
]

DUMMY_NOTIFICATIONS = [
    {"type": "loan_milestone", "title": "Closing in 4 days", "message": "Jeffrey Kim loan closing scheduled for Feb 2nd.", "days_ago": 0, "read": False},
    {"type": "loan_milestone", "title": "Appraisal Received", "message": "Appraisal for Sandra Yee (TEST-001002) received - value: $295,000", "days_ago": 1, "read": True},
    {"type": "task_due", "title": "Task Due Today", "message": "Send pre-approval package to Elena Vasquez", "days_ago": 0, "read": False},
    {"type": "lead_activity", "title": "New Lead Response", "message": "Isabella Moreno replied to your email about Portland home purchase", "days_ago": 1, "read": True},
    {"type": "partner_referral", "title": "New Referral from Sarah Kim", "message": "New lead referral from Sarah Kim Realty - John Smith interested in $400K purchase", "days_ago": 2, "read": True},
    {"type": "rate_alert", "title": "Rate Alert Triggered", "message": "30-year fixed dropped below 6.5% - consider notifying pre-approved leads", "days_ago": 3, "read": True},
    {"type": "compliance", "title": "Disclosure Reminder", "message": "LE disclosure due for Brian Carter within 2 business days", "days_ago": 0, "read": False},
    {"type": "system", "title": "Weekly Report Available", "message": "Your weekly pipeline performance report is ready to view", "days_ago": 1, "read": False},
]

DUMMY_SMS_CONVERSATIONS = [
    {
        "contact_phone": "(555) 100-2001",
        "contact_name": "Alice Morgan",
        "link_ref": "alice.morgan@testlead.com",
        "messages": [
            {"direction": "outbound", "content": "Hi Alice, this is Test User from Perennia. Great speaking with you! Here's the pre-approval checklist we discussed.", "hours_ago": 48},
            {"direction": "inbound", "content": "Thanks! I'll gather those documents this week.", "hours_ago": 46},
            {"direction": "outbound", "content": "Perfect! Let me know when you're ready and we can schedule a call to review.", "hours_ago": 45},
        ]
    },
    {
        "contact_phone": "(555) 100-2005",
        "contact_name": "Elena Vasquez",
        "link_ref": "elena.vasquez@testlead.com",
        "messages": [
            {"direction": "outbound", "content": "Hi Elena! Just sent over the jumbo loan rate sheet. Let me know if you have any questions.", "hours_ago": 24},
            {"direction": "inbound", "content": "Got it, thanks! The 7% rate looks good. Can we lock that?", "hours_ago": 22},
            {"direction": "outbound", "content": "Absolutely! I'll send over the lock agreement. We can discuss on our call tomorrow.", "hours_ago": 21},
            {"direction": "inbound", "content": "Sounds great, talk then!", "hours_ago": 20},
        ]
    },
]

DUMMY_EMAIL_MESSAGES = [
    {"link_type": "lead", "link_ref": "alice.morgan@testlead.com", "to_email": "alice.morgan@testlead.com", "subject": "Your Pre-Approval Checklist", "body": "Hi Alice,\n\nThank you for your interest in obtaining a mortgage pre-approval. Attached is the checklist we discussed...", "direction": "outbound", "days_ago": 2},
    {"link_type": "lead", "link_ref": "elena.vasquez@testlead.com", "to_email": "elena.vasquez@testlead.com", "subject": "Jumbo Loan Rate Quote", "body": "Hi Elena,\n\nGreat speaking with you today! Here are the jumbo loan options we discussed...", "direction": "outbound", "days_ago": 1},
    {"link_type": "lead", "link_ref": "elena.vasquez@testlead.com", "to_email": "testuser@perenniaai.com", "subject": "Re: Jumbo Loan Rate Quote", "body": "Thanks for sending this over! The rates look competitive. I'm ready to move forward with the pre-approval.", "direction": "inbound", "days_ago": 0},
    {"link_type": "loan", "link_ref": "TEST-001001", "to_email": "marcus.powell@email.com", "subject": "Rate Lock Confirmation", "body": "Hi Marcus,\n\nThis email confirms your rate lock at 6.750% for 45 days...", "direction": "outbound", "days_ago": 5},
    {"link_type": "loan", "link_ref": "TEST-001007", "to_email": "jeffrey.kim@email.com", "subject": "Closing Disclosure - Please Review", "body": "Hi Jeffrey & Michelle,\n\nAttached is your Closing Disclosure for review before closing on Feb 2nd...", "direction": "outbound", "days_ago": 1},
]

DUMMY_STAGE_HISTORY = [
    # Lead stage progressions
    {"entity_type": "lead", "ref": "alice.morgan@testlead.com", "stages": [("New", 3)]},
    {"entity_type": "lead", "ref": "brian.carter@testlead.com", "stages": [("New", 10), ("Prospect", 5)]},
    {"entity_type": "lead", "ref": "elena.vasquez@testlead.com", "stages": [("New", 14), ("Prospect", 10), ("Application Started", 6), ("Pre-Approved", 2)]},
    {"entity_type": "lead", "ref": "carmen.delgado@testlead.com", "stages": [("New", 8), ("Prospect", 5), ("Application Started", 2)]},
    {"entity_type": "lead", "ref": "grace.okonkwo@testlead.com", "stages": [("New", 12), ("Attempted Contact", 7)]},
    # Loan stage progressions
    {"entity_type": "loan", "ref": "TEST-001001", "stages": [("Disclosed", 20), ("Processing", 10)]},
    {"entity_type": "loan", "ref": "TEST-001002", "stages": [("Disclosed", 18), ("Processing", 12), ("UW Received", 5)]},
    {"entity_type": "loan", "ref": "TEST-001003", "stages": [("Disclosed", 25), ("Processing", 18), ("UW Received", 12), ("Approved", 6)]},
    {"entity_type": "loan", "ref": "TEST-001005", "stages": [("Disclosed", 30), ("Processing", 22), ("UW Received", 15), ("Approved", 10), ("CTC", 4)]},
    {"entity_type": "loan", "ref": "TEST-001007", "stages": [("Disclosed", 28), ("Processing", 20), ("UW Received", 14), ("Approved", 8), ("CTC", 5), ("Docs Out", 2)]},
]

DUMMY_GOALS = [
    {
        "objective": "Close 15 loans in Q1 2026",
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "status": "on_track",
        "key_results": [
            {"metric": "Closed Loans", "target": 15, "current": 3, "unit": "loans"},
            {"metric": "Total Volume", "target": 5000000, "current": 988000, "unit": "dollars"},
            {"metric": "Average Loan Size", "target": 333333, "current": 329333, "unit": "dollars"},
        ],
    },
    {
        "objective": "Build referral partner network",
        "start_date": "2026-01-01",
        "end_date": "2026-06-30",
        "status": "on_track",
        "key_results": [
            {"metric": "Active Partners", "target": 15, "current": 8, "unit": "partners"},
            {"metric": "Partner Referrals", "target": 20, "current": 6, "unit": "referrals"},
            {"metric": "Partner Closed Loans", "target": 8, "current": 2, "unit": "loans"},
        ],
    },
    {
        "objective": "Improve lead conversion rate",
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "status": "at_risk",
        "key_results": [
            {"metric": "Lead Response Time", "target": 5, "current": 8, "unit": "minutes"},
            {"metric": "Conversion Rate", "target": 25, "current": 18, "unit": "percent"},
            {"metric": "Pre-Approvals Issued", "target": 30, "current": 8, "unit": "pre-approvals"},
        ],
    },
]

DUMMY_CALL_LOGS = [
    {"contact_phone": "(555) 100-2001", "contact_name": "Alice Morgan", "link_type": "lead", "link_ref": "alice.morgan@testlead.com", "outcome": "completed", "duration": 480, "disposition": "interested", "notes": "Discussed conventional loan options. Very interested in 20% down.", "days_ago": 2},
    {"contact_phone": "(555) 100-2005", "contact_name": "Elena Vasquez", "link_type": "lead", "link_ref": "elena.vasquez@testlead.com", "outcome": "completed", "duration": 2100, "disposition": "application_started", "notes": "Deep dive into jumbo requirements. Starting application.", "days_ago": 1},
    {"contact_phone": "(555) 100-2007", "contact_name": "Grace Okonkwo", "link_type": "lead", "link_ref": "grace.okonkwo@testlead.com", "outcome": "no_answer", "duration": 60, "disposition": "voicemail", "notes": "Left voicemail - will try again Monday", "days_ago": 5},
    {"contact_phone": "(555) 100-2003", "contact_name": "Carmen Delgado", "link_type": "lead", "link_ref": "carmen.delgado@testlead.com", "outcome": "completed", "duration": 720, "disposition": "interested", "notes": "Refi analysis - can save $200/mo. Sending comparison.", "days_ago": 2},
    {"contact_phone": "(555) 400-5001", "contact_name": "Sarah Kim", "link_type": "partner", "link_ref": "sarah.kim@kwrealty.com", "outcome": "completed", "duration": 600, "disposition": "partnership", "notes": "Monthly check-in. She has 3 buyers in the pipeline.", "days_ago": 3},
    {"contact_phone": "(555) 300-4003", "contact_name": "Curtis Palmer", "link_type": "mum", "link_ref": "curtis.palmer@testmum.com", "outcome": "completed", "duration": 900, "disposition": "annual_review", "notes": "1-year anniversary call. Happy with service, may refer friends.", "days_ago": 5},
]


# =============================================================================
# SEED FUNCTIONS
# =============================================================================

def create_test_account(db):
    """Create the test user account and organization."""
    logger.info("Creating test user account...")

    # Check if already exists
    existing = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": TEST_EMAIL}).fetchone()
    if existing:
        logger.info(f"  Test user already exists (ID: {existing.id}). Returning existing.")
        # Get organization_id
        user_row = db.execute(text("SELECT id, organization_id FROM users WHERE email = :email"), {"email": TEST_EMAIL}).fetchone()
        return user_row.id, user_row.organization_id

    # Create organization
    import secrets as sec
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', TEST_COMPANY.lower()).strip('-')
    slug = f"{slug}-{sec.token_hex(4)}"

    db.execute(text("""
        INSERT INTO organizations (name, slug, subscription_tier, is_active, created_at, updated_at)
        VALUES (:name, :slug, 'professional', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """), {"name": TEST_COMPANY, "slug": slug})
    db.flush()

    org = db.execute(text("SELECT id FROM organizations WHERE slug = :slug"), {"slug": slug}).fetchone()
    org_id = org.id
    logger.info(f"  Created organization: {TEST_COMPANY} (ID: {org_id})")

    # Create user
    hashed_pw = pwd_context.hash(TEST_PASSWORD)
    db.execute(text("""
        INSERT INTO users (
            email, hashed_password, full_name, role, permission_role,
            organization_id, is_active, account_status, onboarding_completed,
            created_at
        ) VALUES (
            :email, :password, :name, 'site_admin', 'site_admin',
            :org_id, true, 'active', true,
            CURRENT_TIMESTAMP
        )
    """), {
        "email": TEST_EMAIL,
        "password": hashed_pw,
        "name": TEST_FULL_NAME,
        "org_id": org_id,
    })
    db.flush()

    user = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": TEST_EMAIL}).fetchone()
    user_id = user.id

    logger.info(f"  Created user: {TEST_EMAIL} (ID: {user_id})")
    db.commit()
    return user_id, org_id


def create_test_leads(db, owner_id, org_id):
    """Create dummy leads for the test account."""
    logger.info("Creating test leads...")
    created = 0

    for lead in DUMMY_LEADS:
        existing = db.execute(text("SELECT id FROM leads WHERE email = :email"), {"email": lead["email"]}).fetchone()
        if existing:
            logger.info(f"  Skipped {lead['name']} (already exists)")
            continue

        loan_amount = lead.get("property_value", 0) - lead.get("down_payment", 0)
        ltv = (loan_amount / lead["property_value"]) * 100 if lead.get("property_value") else 80
        dti = round(35.0 + random.uniform(-10, 10), 1)

        # Use only core fields that are guaranteed to exist in production DB
        db.execute(text("""
            INSERT INTO leads (
                name, email, phone,
                stage, source, loan_type, credit_score,
                annual_income, property_value, down_payment,
                loan_amount, ltv, dti, city, state,
                owner_id, organization_id,
                ai_score, sentiment,
                created_at, updated_at
            ) VALUES (
                :name, :email, :phone,
                :stage, :source, :loan_type, :credit_score,
                :income, :property_value, :down_payment,
                :loan_amount, :ltv, :dti, :city, :state,
                :owner_id, :org_id,
                :ai_score, 'positive',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "name": lead["name"],
            "email": lead["email"],
            "phone": lead.get("phone"),
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
            "owner_id": owner_id,
            "org_id": org_id,
            "ai_score": 50 + random.randint(-20, 30),
        })
        created += 1
        logger.info(f"  Created lead: {lead['name']} ({lead['stage']})")

    db.commit()
    logger.info(f"Created {created} test leads")
    return created


def create_test_loans(db, owner_id, org_id):
    """Create dummy loans for the test account."""
    logger.info("Creating test loans...")
    created = 0

    for loan in DUMMY_LOANS:
        existing = db.execute(text("SELECT id FROM loans WHERE loan_number = :ln"), {"ln": loan["loan_number"]}).fetchone()
        if existing:
            logger.info(f"  Skipped {loan['loan_number']} (already exists)")
            continue

        if loan["stage"] == "Funded":
            funded_date = datetime.now(timezone.utc).date() - timedelta(days=loan.get("funded_days_ago", 10))
            created_at = datetime.now(timezone.utc) - timedelta(days=loan.get("created_days_ago", 40))
            closing_date = funded_date
            lock_date = datetime.now(timezone.utc) - timedelta(days=loan.get("created_days_ago", 40) - 5)
        else:
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
                funded_date, processor, loan_officer_id, organization_id,
                days_in_stage, sla_status, risk_score,
                created_at, updated_at
            ) VALUES (
                :loan_number, :borrower, :coborrower,
                :stage, :program, :loan_type, :amount,
                :purchase_price, :down_payment, :rate, :term,
                :address, :closing_date, :lock_date,
                :funded_date, :processor, :lo_id, :org_id,
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
            "lo_id": owner_id,
            "org_id": org_id,
            "days_in_stage": loan.get("days_in_stage", random.randint(3, 15)),
            "risk_score": random.randint(10, 40),
            "created_at": created_at,
        })
        created += 1
        logger.info(f"  Created loan: {loan['loan_number']} ({loan['stage']})")

    db.commit()
    logger.info(f"Created {created} test loans")
    return created


def create_test_mum_clients(db, owner_id, org_id):
    """Create dummy MUM clients for the test account."""
    logger.info("Creating test MUM clients...")
    created = 0

    # Get the test user's full name for loan_officer_name field
    user_row = db.execute(text("SELECT full_name FROM users WHERE id = :uid"), {"uid": owner_id}).fetchone()
    lo_name = user_row.full_name if user_row else TEST_FULL_NAME

    for client in DUMMY_MUM_CLIENTS:
        existing = db.execute(text("SELECT id FROM mum_clients WHERE email = :email"), {"email": client["email"]}).fetchone()
        if existing:
            logger.info(f"  Skipped {client['name']} (already exists)")
            continue

        original_loan_date = datetime.now(timezone.utc) - timedelta(days=client["original_loan_date"])
        first_payment_date = original_loan_date + timedelta(days=45)
        last_contact = datetime.now(timezone.utc) - timedelta(days=client["last_contact_days"])
        original_property = client.get("original_property_value", client["original_loan_amount"] * 1.25)
        engagement = 75 if client["engagement_level"] == "High" else 50 if client["engagement_level"] == "Medium" else 25

        db.execute(text("""
            INSERT INTO mum_clients (
                client_name, email, phone, status,
                organization_id,
                original_close_date, closing_date, first_payment_date,
                interest_rate, original_loan_amount, current_loan_amount,
                appraisal_value_at_closing, current_property_value,
                engagement_score, last_contact, next_touchpoint
            ) VALUES (
                :name, :email, :phone, 'active',
                :org_id,
                :close_date, :close_date, :first_payment,
                :rate, :loan_amount, :loan_amount,
                :appraisal_value, :current_prop,
                :engagement, :last_contact, :next_touchpoint
            )
        """), {
            "name": client["name"],
            "email": client["email"],
            "phone": client["phone"],
            "org_id": org_id,
            "close_date": original_loan_date,
            "first_payment": first_payment_date,
            "rate": client["interest_rate"],
            "loan_amount": client["original_loan_amount"],
            "appraisal_value": original_property,
            "current_prop": original_property * 1.05,  # Slight appreciation
            "engagement": engagement,
            "last_contact": last_contact,
            "next_touchpoint": datetime.now(timezone.utc) + timedelta(days=30),
        })
        created += 1
        logger.info(f"  Created MUM client: {client['name']} ({client['engagement_level']})")

    db.commit()
    logger.info(f"Created {created} test MUM clients")
    return created


def create_test_referral_partners(db, owner_id, org_id):
    """Create dummy referral partners for the test account."""
    logger.info("Creating test referral partners...")
    created = 0

    for partner in DUMMY_REFERRAL_PARTNERS:
        existing = db.execute(text("SELECT id FROM referral_partners WHERE email = :email AND organization_id = :org_id"),
                              {"email": partner["email"], "org_id": org_id}).fetchone()
        if existing:
            logger.info(f"  Skipped {partner['name']} (already exists)")
            continue

        last_interaction = datetime.now(timezone.utc) - timedelta(days=random.randint(5, 60))

        db.execute(text("""
            INSERT INTO referral_partners (
                name, contact_name, business_name, category,
                company, type, phone, email,
                referrals_in, referrals_out, closed_loans, volume,
                reciprocity_score, status, loyalty_tier, partner_category,
                title, city, state, notes,
                last_interaction, owner_id, organization_id, created_at
            ) VALUES (
                :name, :contact_name, :business_name, :category,
                :company, :type, :phone, :email,
                :referrals_in, :referrals_out, :closed_loans, :volume,
                :reciprocity_score, 'active', :loyalty_tier, 'individual',
                :title, :city, :state, :notes,
                :last_interaction, :owner_id, :org_id, CURRENT_TIMESTAMP
            )
        """), {
            "name": partner["name"],
            "contact_name": partner["contact_name"],
            "business_name": partner["business_name"],
            "category": partner["category"],
            "company": partner["company"],
            "type": partner["type"],
            "phone": partner["phone"],
            "email": partner["email"],
            "referrals_in": partner["referrals_in"],
            "referrals_out": partner["referrals_out"],
            "closed_loans": partner["closed_loans"],
            "volume": partner["volume"],
            "reciprocity_score": partner["reciprocity_score"],
            "loyalty_tier": partner["loyalty_tier"],
            "title": partner["title"],
            "city": partner["city"],
            "state": partner["state"],
            "notes": partner["notes"],
            "last_interaction": last_interaction,
            "owner_id": owner_id,
            "org_id": org_id,
        })
        created += 1
        logger.info(f"  Created referral partner: {partner['name']} ({partner['category']})")

    db.commit()
    logger.info(f"Created {created} test referral partners")
    return created


def create_test_tasks(db, owner_id, org_id):
    """Create dummy tasks linked to leads and loans for the test account."""
    logger.info("Creating test tasks...")
    created = 0

    for task in DUMMY_TASKS:
        # Resolve lead_id or loan_id based on link type
        lead_id = None
        loan_id = None
        related_name = None

        if task["link"] == "lead" and task["link_name"]:
            row = db.execute(text("SELECT id, name FROM leads WHERE email = :email AND organization_id = :org"),
                             {"email": task["link_name"], "org": org_id}).fetchone()
            if row:
                lead_id = row.id
                related_name = row.name
        elif task["link"] == "loan" and task["link_name"]:
            row = db.execute(text("SELECT id, borrower_name FROM loans WHERE loan_number = :ln AND organization_id = :org"),
                             {"ln": task["link_name"], "org": org_id}).fetchone()
            if row:
                loan_id = row.id
                related_name = row.borrower_name

        due_date = datetime.now(timezone.utc) + timedelta(days=task["due_days"])
        completed_at = due_date if task["status"] == "completed" else None

        db.execute(text("""
            INSERT INTO tasks (
                title, description, status, priority,
                due_date, owner_id, organization_id,
                lead_id, loan_id, related_contact_name,
                completed_at, created_at, updated_at
            ) VALUES (
                :title, :desc, :status, :priority,
                :due, :owner, :org,
                :lead_id, :loan_id, :contact_name,
                :completed, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "title": task["title"],
            "desc": task["description"],
            "status": task["status"],
            "priority": task["priority"],
            "due": due_date,
            "owner": owner_id,
            "org": org_id,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "contact_name": related_name,
            "completed": completed_at,
        })
        created += 1
        logger.info(f"  Created task: {task['title']} ({task['status']})")

    db.commit()
    logger.info(f"Created {created} test tasks")
    return created


def create_test_reconciliation_data(db, user_id, org_id):
    """Create dummy reconciliation data (incoming data events + extracted data)."""
    logger.info("Creating test reconciliation data...")
    created_events = 0
    created_extracts = 0

    reconciliation_events = [
        {
            "source": "outlook",
            "subject": "Rate Lock Confirmation - Powell Loan #TEST-001001",
            "sender": "locks@wholesalelender.com",
            "raw_text": "Rate lock confirmed for borrower Marcus Powell. Loan TEST-001001. Rate: 6.750% locked for 45 days. Lock expiration: 03/15/2026.",
            "category": "loan_update",
            "subcategory": "rate_lock",
            "fields": {"rate": {"value": "6.750", "confidence": 0.98}, "lock_expiration_date": {"value": "2026-03-15", "confidence": 0.95}},
            "match_entity_type": "loan",
            "match_entity_ref": "TEST-001001",
            "ai_confidence": 0.96,
            "status": "auto_applied",
        },
        {
            "source": "outlook",
            "subject": "Appraisal Received - 456 Elm Street, Phoenix",
            "sender": "orders@appraisalcompany.com",
            "raw_text": "Appraisal completed for 456 Elm Street, Phoenix AZ 85001. Appraised value: $295,000. Borrower: Sandra Yee.",
            "category": "loan_update",
            "subcategory": "appraisal",
            "fields": {"appraisal_value": {"value": "295000", "confidence": 0.97}, "appraisal_received_date": {"value": "2026-01-25", "confidence": 0.90}},
            "match_entity_type": "loan",
            "match_entity_ref": "TEST-001002",
            "ai_confidence": 0.94,
            "status": "pending_review",
        },
        {
            "source": "outlook",
            "subject": "Title Clear - Okafor Purchase",
            "sender": "closings@premiertitle.com",
            "raw_text": "Title search completed. Property at 5678 Highland Terrace, Bellevue WA is clear. No liens or encumbrances found.",
            "category": "loan_update",
            "subcategory": "title_clear",
            "fields": {"title_status": {"value": "clear", "confidence": 0.99}},
            "match_entity_type": "loan",
            "match_entity_ref": "TEST-001005",
            "ai_confidence": 0.92,
            "status": "pending_review",
        },
        {
            "source": "outlook",
            "subject": "New Lead Inquiry - Isabella Moreno",
            "sender": "isabella.moreno@testlead.com",
            "raw_text": "Hi, I'm interested in purchasing a home in Portland. I have a budget of around $550K and excellent credit. Can we schedule a call?",
            "category": "lead_update",
            "subcategory": "new_inquiry",
            "fields": {"loan_amount": {"value": "550000", "confidence": 0.85}, "city": {"value": "Portland", "confidence": 0.95}},
            "match_entity_type": "lead",
            "match_entity_ref": "isabella.moreno@testlead.com",
            "ai_confidence": 0.88,
            "status": "auto_applied",
        },
        {
            "source": "calendar",
            "subject": "Closing Scheduled - Kim Purchase",
            "sender": "calendar@system.com",
            "raw_text": "Closing scheduled for Jeffrey & Michelle Kim at Premier Title Services, Feb 2, 2026 at 2:00 PM.",
            "category": "loan_update",
            "subcategory": "closing_scheduled",
            "fields": {"scheduled_closing_date": {"value": "2026-02-02", "confidence": 0.97}, "title_company": {"value": "Premier Title Services", "confidence": 0.90}},
            "match_entity_type": "loan",
            "match_entity_ref": "TEST-001007",
            "ai_confidence": 0.91,
            "status": "pending_review",
        },
        {
            "source": "outlook",
            "subject": "UW Conditions - Sandra Yee FHA",
            "sender": "underwriting@lender.com",
            "raw_text": "Loan TEST-001002 has been conditionally approved. Prior-to-docs conditions: 1) Updated bank statement (most recent), 2) VOE reverification, 3) Gift letter for down payment.",
            "category": "loan_update",
            "subcategory": "conditions",
            "fields": {"conditions_count": {"value": "3", "confidence": 0.92}, "condition_status": {"value": "conditional_approval", "confidence": 0.88}},
            "match_entity_type": "loan",
            "match_entity_ref": "TEST-001002",
            "ai_confidence": 0.90,
            "status": "pending_review",
        },
    ]

    for evt in reconciliation_events:
        # Insert incoming data event
        db.execute(text("""
            INSERT INTO incoming_data_events (
                source, subject, sender, raw_text,
                processed, user_id, received_at, created_at
            ) VALUES (
                :source, :subject, :sender, :raw_text,
                true, :user_id, CURRENT_TIMESTAMP - interval '1 day' * :days_ago, CURRENT_TIMESTAMP
            )
        """), {
            "source": evt["source"],
            "subject": evt["subject"],
            "sender": evt["sender"],
            "raw_text": evt["raw_text"],
            "user_id": user_id,
            "days_ago": random.randint(0, 5),
        })
        db.flush()
        created_events += 1

        # Get the event id
        event_row = db.execute(text("""
            SELECT id FROM incoming_data_events
            WHERE subject = :subject AND user_id = :uid
            ORDER BY id DESC LIMIT 1
        """), {"subject": evt["subject"], "uid": user_id}).fetchone()

        if not event_row:
            continue

        event_id = event_row.id

        # Resolve match entity id
        match_entity_id = None
        if evt["match_entity_type"] == "loan":
            loan_row = db.execute(text("SELECT id FROM loans WHERE loan_number = :ln AND organization_id = :org"),
                                  {"ln": evt["match_entity_ref"], "org": org_id}).fetchone()
            if loan_row:
                match_entity_id = loan_row.id
        elif evt["match_entity_type"] == "lead":
            lead_row = db.execute(text("SELECT id FROM leads WHERE email = :email AND organization_id = :org"),
                                  {"email": evt["match_entity_ref"], "org": org_id}).fetchone()
            if lead_row:
                match_entity_id = lead_row.id

        applied_at = datetime.now(timezone.utc) if evt["status"] == "auto_applied" else None

        db.execute(text("""
            INSERT INTO extracted_data (
                event_id, category, subcategory,
                fields, match_entity_type, match_entity_id,
                match_confidence, ai_confidence,
                status, applied_at, created_at
            ) VALUES (
                :event_id, :category, :subcategory,
                :fields, :match_type, :match_id,
                :match_conf, :ai_conf,
                :status, :applied_at, CURRENT_TIMESTAMP
            )
        """), {
            "event_id": event_id,
            "category": evt["category"],
            "subcategory": evt["subcategory"],
            "fields": json.dumps(evt["fields"]),
            "match_type": evt["match_entity_type"],
            "match_id": match_entity_id,
            "match_conf": round(random.uniform(0.85, 0.99), 2),
            "ai_conf": evt["ai_confidence"],
            "status": evt["status"],
            "applied_at": applied_at,
        })
        created_extracts += 1
        logger.info(f"  Created reconciliation: {evt['subject']} ({evt['status']})")

    db.commit()
    logger.info(f"Created {created_events} data events + {created_extracts} extracted data records")
    return created_events, created_extracts


def create_test_activities(db, user_id, org_id):
    """Create test activity records."""
    logger.info("Creating test activities...")
    created = 0

    for activity in DUMMY_ACTIVITIES:
        # Resolve linked entity
        lead_id = None
        loan_id = None
        mum_client_id = None

        if activity["link_type"] == "lead":
            row = db.execute(text("SELECT id FROM leads WHERE email = :email AND organization_id = :org"),
                            {"email": activity["link_ref"], "org": org_id}).fetchone()
            if row:
                lead_id = row.id
        elif activity["link_type"] == "loan":
            row = db.execute(text("SELECT id FROM loans WHERE loan_number = :ln AND organization_id = :org"),
                            {"ln": activity["link_ref"], "org": org_id}).fetchone()
            if row:
                loan_id = row.id
        elif activity["link_type"] == "mum":
            row = db.execute(text("SELECT id FROM mum_clients WHERE email = :email"),
                            {"email": activity["link_ref"]}).fetchone()
            if row:
                mum_client_id = row.id

        created_at = datetime.now(timezone.utc) - timedelta(days=activity.get("days_ago", 0))

        db.execute(text("""
            INSERT INTO activities (
                organization_id, type, content, lead_id, loan_id, mum_client_id,
                user_id, duration, sentiment, created_at
            ) VALUES (
                :org_id, :type, :content, :lead_id, :loan_id, :mum_id,
                :user_id, :duration, :sentiment, :created_at
            )
        """), {
            "org_id": org_id,
            "type": activity["type"],
            "content": activity["content"],
            "lead_id": lead_id,
            "loan_id": loan_id,
            "mum_id": mum_client_id,
            "user_id": user_id,
            "duration": activity.get("duration"),
            "sentiment": activity.get("sentiment", "neutral"),
            "created_at": created_at,
        })
        created += 1

    db.commit()
    logger.info(f"Created {created} test activities")
    return created


def create_test_calendar_events(db, user_id, org_id):
    """Create test calendar events."""
    logger.info("Creating test calendar events...")
    created = 0

    for event in DUMMY_CALENDAR_EVENTS:
        lead_id = None
        loan_id = None

        if event["link_type"] == "lead":
            row = db.execute(text("SELECT id FROM leads WHERE email = :email AND organization_id = :org"),
                            {"email": event["link_ref"], "org": org_id}).fetchone()
            if row:
                lead_id = row.id
        elif event["link_type"] == "loan":
            row = db.execute(text("SELECT id FROM loans WHERE loan_number = :ln AND organization_id = :org"),
                            {"ln": event["link_ref"], "org": org_id}).fetchone()
            if row:
                loan_id = row.id
        elif event["link_type"] == "mum":
            # MUM events don't have direct FK, just note in description
            pass

        start_time = datetime.now(timezone.utc).replace(hour=event["hour"], minute=0, second=0, microsecond=0) + timedelta(days=event["days_from_now"])
        end_time = start_time + timedelta(minutes=event["duration_min"])

        db.execute(text("""
            INSERT INTO calendar_events (
                title, description, start_time, end_time, event_type,
                lead_id, loan_id, user_id, status, created_at
            ) VALUES (
                :title, :desc, :start, :end, :type,
                :lead_id, :loan_id, :user_id, 'scheduled', CURRENT_TIMESTAMP
            )
        """), {
            "title": event["title"],
            "desc": event["description"],
            "start": start_time,
            "end": end_time,
            "type": event["event_type"],
            "lead_id": lead_id,
            "loan_id": loan_id,
            "user_id": user_id,
        })
        created += 1

    db.commit()
    logger.info(f"Created {created} test calendar events")
    return created


def create_test_documents(db, user_id, org_id):
    """Create test document records."""
    logger.info("Creating test documents...")
    created = 0

    for doc in DUMMY_DOCUMENTS:
        row = db.execute(text("SELECT id, borrower_name FROM loans WHERE loan_number = :ln AND organization_id = :org"),
                        {"ln": doc["loan_ref"], "org": org_id}).fetchone()
        if not row:
            continue

        loan_id = row.id

        db.execute(text("""
            INSERT INTO documents (
                organization_id, loan_id, doc_type, doc_category,
                filename, original_filename, file_location, status,
                source, uploaded_by_user_id, uploaded_at
            ) VALUES (
                :org_id, :loan_id, :doc_type, :category,
                :filename, :filename, :location, 'active',
                'MANUAL_UPLOAD', :user_id, CURRENT_TIMESTAMP
            )
        """), {
            "org_id": org_id,
            "loan_id": loan_id,
            "doc_type": doc["doc_type"],
            "category": doc["category"],
            "filename": doc["filename"],
            "location": f"/documents/{org_id}/{loan_id}/{doc['filename']}",
            "user_id": user_id,
        })
        created += 1

    db.commit()
    logger.info(f"Created {created} test documents")
    return created


def create_test_notifications(db, user_id, org_id):
    """Create test notifications."""
    logger.info("Creating test notifications...")
    created = 0

    for notif in DUMMY_NOTIFICATIONS:
        created_at = datetime.now(timezone.utc) - timedelta(days=notif.get("days_ago", 0))
        read_at = created_at if notif.get("read") else None

        db.execute(text("""
            INSERT INTO notifications (
                user_id, type, title, message, is_read, read_at, created_at
            ) VALUES (
                :user_id, :type, :title, :message, :is_read, :read_at, :created_at
            )
        """), {
            "user_id": user_id,
            "type": notif["type"],
            "title": notif["title"],
            "message": notif["message"],
            "is_read": notif.get("read", False),
            "read_at": read_at,
            "created_at": created_at,
        })
        created += 1

    db.commit()
    logger.info(f"Created {created} test notifications")
    return created


def create_test_sms_conversations(db, user_id, org_id):
    """Create test SMS conversations."""
    logger.info("Creating test SMS conversations...")
    conv_count = 0
    msg_count = 0

    for conv in DUMMY_SMS_CONVERSATIONS:
        # Get lead_id
        lead_id = None
        row = db.execute(text("SELECT id FROM leads WHERE email = :email AND organization_id = :org"),
                        {"email": conv["link_ref"], "org": org_id}).fetchone()
        if row:
            lead_id = row.id

        # Create conversation
        db.execute(text("""
            INSERT INTO sms_conversations (
                phone_number, user_id, lead_id, contact_name,
                is_active, ai_enabled, message_count, created_at
            ) VALUES (
                :phone, :user_id, :lead_id, :contact_name,
                true, true, :msg_count, CURRENT_TIMESTAMP
            )
        """), {
            "phone": conv["contact_phone"],
            "user_id": user_id,
            "lead_id": lead_id,
            "contact_name": conv["contact_name"],
            "msg_count": len(conv["messages"]),
        })
        db.flush()
        conv_count += 1

        # Get conversation ID
        conv_row = db.execute(text("""
            SELECT id FROM sms_conversations WHERE phone_number = :phone AND user_id = :user_id
            ORDER BY id DESC LIMIT 1
        """), {"phone": conv["contact_phone"], "user_id": user_id}).fetchone()

        if not conv_row:
            continue

        conv_id = conv_row.id

        # Create messages
        for msg in conv["messages"]:
            created_at = datetime.now(timezone.utc) - timedelta(hours=msg["hours_ago"])
            from_num = "(555) 000-0000" if msg["direction"] == "outbound" else conv["contact_phone"]
            to_num = conv["contact_phone"] if msg["direction"] == "outbound" else "(555) 000-0000"

            db.execute(text("""
                INSERT INTO sms_messages (
                    user_id, lead_id, conversation_id,
                    to_number, from_number, message, direction,
                    status, created_at
                ) VALUES (
                    :user_id, :lead_id, :conv_id,
                    :to_num, :from_num, :message, :direction,
                    :status, :created_at
                )
            """), {
                "user_id": user_id,
                "lead_id": lead_id,
                "conv_id": conv_id,
                "to_num": to_num,
                "from_num": from_num,
                "message": msg["content"],
                "direction": msg["direction"],
                "status": "delivered" if msg["direction"] == "outbound" else "received",
                "created_at": created_at,
            })
            msg_count += 1

    db.commit()
    logger.info(f"Created {conv_count} SMS conversations with {msg_count} messages")
    return conv_count, msg_count


def create_test_email_messages(db, user_id, org_id):
    """Create test email messages."""
    logger.info("Creating test email messages...")
    created = 0

    user_email = TEST_EMAIL

    for email in DUMMY_EMAIL_MESSAGES:
        lead_id = None
        loan_id = None

        if email["link_type"] == "lead":
            row = db.execute(text("SELECT id FROM leads WHERE email = :email AND organization_id = :org"),
                            {"email": email["link_ref"], "org": org_id}).fetchone()
            if row:
                lead_id = row.id
        elif email["link_type"] == "loan":
            row = db.execute(text("SELECT id FROM loans WHERE loan_number = :ln AND organization_id = :org"),
                            {"ln": email["link_ref"], "org": org_id}).fetchone()
            if row:
                loan_id = row.id

        created_at = datetime.now(timezone.utc) - timedelta(days=email.get("days_ago", 0))

        to_addr = email["to_email"] if email["direction"] == "outbound" else user_email
        from_addr = user_email if email["direction"] == "outbound" else email["to_email"]

        db.execute(text("""
            INSERT INTO email_messages (
                user_id, lead_id, loan_id, to_email, from_email,
                subject, body, direction, status, created_at
            ) VALUES (
                :user_id, :lead_id, :loan_id, :to_email, :from_email,
                :subject, :body, :direction, :status, :created_at
            )
        """), {
            "user_id": user_id,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "to_email": to_addr,
            "from_email": from_addr,
            "subject": email["subject"],
            "body": email["body"],
            "direction": email["direction"],
            "status": "sent" if email["direction"] == "outbound" else "received",
            "created_at": created_at,
        })
        created += 1

    db.commit()
    logger.info(f"Created {created} test email messages")
    return created


def create_test_stage_history(db, user_id, org_id):
    """Create test stage history records."""
    logger.info("Creating test stage history...")
    created = 0

    for history in DUMMY_STAGE_HISTORY:
        entity_id = None
        lead_id = None
        loan_id = None

        if history["entity_type"] == "lead":
            row = db.execute(text("SELECT id FROM leads WHERE email = :email AND organization_id = :org"),
                            {"email": history["ref"], "org": org_id}).fetchone()
            if row:
                entity_id = row.id
                lead_id = row.id
        elif history["entity_type"] == "loan":
            row = db.execute(text("SELECT id FROM loans WHERE loan_number = :ln AND organization_id = :org"),
                            {"ln": history["ref"], "org": org_id}).fetchone()
            if row:
                entity_id = row.id
                loan_id = row.id

        if not entity_id:
            continue

        # Create stage progression
        prev_stage = None
        for to_stage, days_ago in history["stages"]:
            changed_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

            db.execute(text("""
                INSERT INTO stage_history (
                    organization_id, entity_type, entity_id,
                    lead_id, loan_id, from_stage, to_stage,
                    changed_at, changed_by_id
                ) VALUES (
                    :org_id, :entity_type, :entity_id,
                    :lead_id, :loan_id, :from_stage, :to_stage,
                    :changed_at, :changed_by
                )
            """), {
                "org_id": org_id,
                "entity_type": history["entity_type"],
                "entity_id": entity_id,
                "lead_id": lead_id,
                "loan_id": loan_id,
                "from_stage": prev_stage,
                "to_stage": to_stage,
                "changed_at": changed_at,
                "changed_by": user_id,
            })
            created += 1
            prev_stage = to_stage

    db.commit()
    logger.info(f"Created {created} test stage history records")
    return created


def create_test_goals(db, user_id, org_id):
    """Create test user goals with key results."""
    logger.info("Creating test goals...")
    goal_count = 0
    kr_count = 0

    for goal in DUMMY_GOALS:
        start_date = datetime.strptime(goal["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(goal["end_date"], "%Y-%m-%d").date()

        db.execute(text("""
            INSERT INTO user_goals (
                user_id, objective, start_date, end_date, status,
                created_by_id, created_at
            ) VALUES (
                :user_id, :objective, :start_date, :end_date, :status,
                :user_id, CURRENT_TIMESTAMP
            )
        """), {
            "user_id": user_id,
            "objective": goal["objective"],
            "start_date": start_date,
            "end_date": end_date,
            "status": goal["status"],
        })
        db.flush()
        goal_count += 1

        # Get goal ID
        goal_row = db.execute(text("""
            SELECT id FROM user_goals WHERE user_id = :user_id AND objective = :obj
            ORDER BY id DESC LIMIT 1
        """), {"user_id": user_id, "obj": goal["objective"]}).fetchone()

        if not goal_row:
            continue

        goal_id = goal_row.id

        # Create key results
        for kr in goal["key_results"]:
            kr_status = "on_track"
            if kr["current"] >= kr["target"]:
                kr_status = "completed"
            elif kr["current"] < kr["target"] * 0.5:
                kr_status = "at_risk"
            elif kr["current"] > kr["target"]:
                kr_status = "ahead"

            db.execute(text("""
                INSERT INTO goal_key_results (
                    goal_id, metric, target, current, unit, status
                ) VALUES (
                    :goal_id, :metric, :target, :current, :unit, :status
                )
            """), {
                "goal_id": goal_id,
                "metric": kr["metric"],
                "target": kr["target"],
                "current": kr["current"],
                "unit": kr["unit"],
                "status": kr_status,
            })
            kr_count += 1

    db.commit()
    logger.info(f"Created {goal_count} goals with {kr_count} key results")
    return goal_count, kr_count


def create_test_call_logs(db, user_id, org_id):
    """Create test call log records."""
    logger.info("Creating test call logs...")
    created = 0

    for call in DUMMY_CALL_LOGS:
        lead_id = None
        referral_partner_id = None
        mum_client_id = None

        if call["link_type"] == "lead":
            row = db.execute(text("SELECT id FROM leads WHERE email = :email AND organization_id = :org"),
                            {"email": call["link_ref"], "org": org_id}).fetchone()
            if row:
                lead_id = row.id
        elif call["link_type"] == "partner":
            row = db.execute(text("SELECT id FROM referral_partners WHERE email = :email AND organization_id = :org"),
                            {"email": call["link_ref"], "org": org_id}).fetchone()
            if row:
                referral_partner_id = row.id
        elif call["link_type"] == "mum":
            row = db.execute(text("SELECT id FROM mum_clients WHERE email = :email"),
                            {"email": call["link_ref"]}).fetchone()
            if row:
                mum_client_id = row.id

        start_time = datetime.now(timezone.utc) - timedelta(days=call.get("days_ago", 0), hours=random.randint(9, 17))
        end_time = start_time + timedelta(seconds=call.get("duration", 0))

        db.execute(text("""
            INSERT INTO call_logs (
                agent_id, contact_phone, contact_name,
                lead_id, referral_partner_id, mum_client_id,
                start_time, end_time, duration_seconds,
                outcome, disposition, notes, created_at
            ) VALUES (
                :agent_id, :phone, :name,
                :lead_id, :partner_id, :mum_id,
                :start_time, :end_time, :duration,
                :outcome, :disposition, :notes, :created_at
            )
        """), {
            "agent_id": user_id,
            "phone": call["contact_phone"],
            "name": call["contact_name"],
            "lead_id": lead_id,
            "partner_id": referral_partner_id,
            "mum_id": mum_client_id,
            "start_time": start_time,
            "end_time": end_time,
            "duration": call.get("duration", 0),
            "outcome": call["outcome"],
            "disposition": call.get("disposition"),
            "notes": call.get("notes"),
            "created_at": start_time,
        })
        created += 1

    db.commit()
    logger.info(f"Created {created} test call logs")
    return created


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def seed_test_account():
    """Seed the complete test account with all dummy data."""
    db = SessionLocal()

    try:
        logger.info("=" * 80)
        logger.info("SEEDING TEST ACCOUNT WITH DUMMY DATA")
        logger.info("=" * 80)
        logger.info("")

        # 1. Create account
        user_id, org_id = create_test_account(db)
        logger.info("")

        # 2. Create leads
        leads_count = create_test_leads(db, user_id, org_id)
        logger.info("")

        # 3. Create loans
        loans_count = create_test_loans(db, user_id, org_id)
        logger.info("")

        # 4. Create MUM clients
        mum_count = create_test_mum_clients(db, user_id, org_id)
        logger.info("")

        # 5. Create referral partners
        partner_count = create_test_referral_partners(db, user_id, org_id)
        logger.info("")

        # 6. Create tasks
        task_count = create_test_tasks(db, user_id, org_id)
        logger.info("")

        # 7. Create reconciliation data
        event_count, extract_count = create_test_reconciliation_data(db, user_id, org_id)
        logger.info("")

        # 8-16: Skipped due to schema compatibility issues with production database
        # These can be added later once enum/schema issues are resolved
        activity_count = 0
        calendar_count = 0
        document_count = 0
        notification_count = 0
        sms_conv_count = 0
        sms_msg_count = 0
        email_count = 0
        stage_history_count = 0
        goal_count = 0
        kr_count = 0
        call_log_count = 0
        logger.info("Skipped secondary data (activities, calendar, etc.) due to schema compatibility")

        # Summary
        logger.info("=" * 80)
        logger.info("TEST ACCOUNT SEEDING COMPLETE")
        logger.info("=" * 80)
        logger.info("")
        logger.info("  Test Account Credentials:")
        logger.info(f"    Email:    {TEST_EMAIL}")
        logger.info(f"    Password: {TEST_PASSWORD}")
        logger.info("")
        logger.info("  Data Summary:")
        logger.info(f"    Leads:              {leads_count}")
        logger.info(f"    Loans:              {loans_count}")
        logger.info(f"    MUM Clients:        {mum_count}")
        logger.info(f"    Referral Partners:  {partner_count}")
        logger.info(f"    Tasks:              {task_count}")
        logger.info(f"    Data Events:        {event_count}")
        logger.info(f"    Extracted Data:     {extract_count}")
        logger.info(f"    Activities:         {activity_count}")
        logger.info(f"    Calendar Events:    {calendar_count}")
        logger.info(f"    Documents:          {document_count}")
        logger.info(f"    Notifications:      {notification_count}")
        logger.info(f"    SMS Conversations:  {sms_conv_count} ({sms_msg_count} messages)")
        logger.info(f"    Email Messages:     {email_count}")
        logger.info(f"    Stage History:      {stage_history_count}")
        logger.info(f"    Goals:              {goal_count} ({kr_count} key results)")
        logger.info(f"    Call Logs:          {call_log_count}")
        total = (leads_count + loans_count + mum_count + partner_count + task_count +
                 event_count + extract_count + activity_count + calendar_count +
                 document_count + notification_count + sms_conv_count + sms_msg_count +
                 email_count + stage_history_count + goal_count + kr_count + call_log_count)
        logger.info(f"    TOTAL RECORDS:      {total}")
        logger.info("=" * 80)

        return {
            "success": True,
            "credentials": {
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
            },
            "data": {
                "leads": leads_count,
                "loans": loans_count,
                "mum_clients": mum_count,
                "referral_partners": partner_count,
                "tasks": task_count,
                "data_events": event_count,
                "extracted_data": extract_count,
                "activities": activity_count,
                "calendar_events": calendar_count,
                "documents": document_count,
                "notifications": notification_count,
                "sms_conversations": sms_conv_count,
                "sms_messages": sms_msg_count,
                "email_messages": email_count,
                "stage_history": stage_history_count,
                "goals": goal_count,
                "goal_key_results": kr_count,
                "call_logs": call_log_count,
            },
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding test account: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": "Internal server error"}
    finally:
        db.close()


if __name__ == "__main__":
    result = seed_test_account()
    if not result["success"]:
        sys.exit(1)
    else:
        print(f"\nTest account ready!")
        print(f"  Email:    {result['credentials']['email']}")
        print(f"  Password: {result['credentials']['password']}")
