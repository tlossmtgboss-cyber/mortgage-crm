"""
Database Migration: Create Smart Document Collection Tables

This script creates all tables required for the Smart Document Collection system.
Run with: python -m migrations.create_smart_docs_tables

Features:
- Creates smart document tables for needs list management
- Creates screenshot detection and freshness tracking tables
- Seeds default needs list templates
- Idempotent - safe to run multiple times
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect
from database import DATABASE_URL, Base
from models.smart_docs_models import (
    DocType, RequestStatus, RequestPriority, AppliesTo, PayrollFrequency,
    DocumentDecision, RejectionCategory, DocPolicyEventType,
    DocumentRequest, SmartDocument, DocPolicyEvent, NeedsListTemplate
)


def create_tables(engine):
    """Create all smart document tables."""
    print("Creating smart document tables...")

    # Import models to register them with Base
    from models import smart_docs_models

    # List of smart docs tables to create
    smart_docs_tables = [
        DocumentRequest.__table__,
        SmartDocument.__table__,
        DocPolicyEvent.__table__,
        NeedsListTemplate.__table__,
    ]

    # Create only smart docs tables
    Base.metadata.create_all(bind=engine, tables=smart_docs_tables)

    print("Smart document tables created successfully!")


def seed_needs_list_templates(engine):
    """Seed default needs list templates for common loan scenarios."""
    from sqlalchemy.orm import Session
    import json

    session = Session(bind=engine)

    # Check if templates already exist
    existing = session.query(NeedsListTemplate).count()
    if existing > 0:
        print(f"Needs list templates already exist ({existing} found), skipping seed...")
        session.close()
        return

    print("Seeding needs list templates...")

    # Base document requirements for all loans
    base_requirements = [
        {
            "doc_type": "DRIVERS_LICENSE",
            "title": "Government-Issued ID",
            "description": "Valid driver's license or passport",
            "instructions": "Upload a clear photo or scan of your valid government-issued ID. Both front and back if applicable.",
            "required_count": 1,
            "priority": "HIGH",
            "applies_to": "BORROWER",
            "freshness_days": None,
            "auto_renew": False,
        },
        {
            "doc_type": "PAYSTUB",
            "title": "Recent Pay Stubs",
            "description": "Most recent 30 days of pay stubs",
            "instructions": "Upload your most recent pay stubs covering the last 30 days. Include all pages.",
            "required_count": 2,
            "priority": "HIGH",
            "applies_to": "BORROWER",
            "freshness_days": 30,
            "auto_renew": True,
        },
        {
            "doc_type": "W2",
            "title": "W-2 Forms",
            "description": "W-2s for the past 2 years",
            "instructions": "Upload W-2 forms from all employers for the past 2 years.",
            "required_count": 2,
            "priority": "HIGH",
            "applies_to": "BORROWER",
            "freshness_days": None,
            "auto_renew": False,
        },
        {
            "doc_type": "BANK_STATEMENT",
            "title": "Bank Statements",
            "description": "Most recent 2 months of bank statements",
            "instructions": "Upload complete bank statements (all pages) for all accounts for the past 2 months.",
            "required_count": 2,
            "priority": "HIGH",
            "applies_to": "BORROWER",
            "freshness_days": 90,
            "auto_renew": True,
        },
    ]

    # Self-employed additional requirements
    self_employed_additions = [
        {
            "doc_type": "TAX_RETURN",
            "title": "Personal Tax Returns",
            "description": "Complete tax returns with all schedules for past 2 years",
            "instructions": "Upload your complete personal tax returns (1040) with all schedules and attachments for the past 2 years.",
            "required_count": 2,
            "priority": "HIGH",
            "applies_to": "BORROWER",
            "freshness_days": None,
            "auto_renew": False,
        },
        {
            "doc_type": "BUSINESS_TAX_RETURN",
            "title": "Business Tax Returns",
            "description": "Business tax returns for past 2 years",
            "instructions": "Upload complete business tax returns for all businesses you own (1120, 1120S, 1065, or Schedule C).",
            "required_count": 2,
            "priority": "HIGH",
            "applies_to": "BORROWER",
            "freshness_days": None,
            "auto_renew": False,
        },
        {
            "doc_type": "PROFIT_LOSS",
            "title": "Year-to-Date Profit & Loss",
            "description": "Current year P&L statement",
            "instructions": "Upload a year-to-date profit and loss statement for your business.",
            "required_count": 1,
            "priority": "HIGH",
            "applies_to": "BORROWER",
            "freshness_days": 90,
            "auto_renew": True,
        },
        {
            "doc_type": "BALANCE_SHEET",
            "title": "Business Balance Sheet",
            "description": "Current business balance sheet",
            "instructions": "Upload a current balance sheet for your business.",
            "required_count": 1,
            "priority": "NORMAL",
            "applies_to": "BORROWER",
            "freshness_days": 90,
            "auto_renew": False,
        },
    ]

    # FHA-specific requirements
    fha_additions = [
        {
            "doc_type": "FHA_CERT",
            "title": "FHA Case Number Assignment",
            "description": "FHA case number documentation",
            "instructions": "This will be obtained by your loan officer.",
            "required_count": 1,
            "priority": "NORMAL",
            "applies_to": "BORROWER",
            "freshness_days": None,
            "auto_renew": False,
        },
    ]

    # VA-specific requirements
    va_additions = [
        {
            "doc_type": "VA_COE",
            "title": "Certificate of Eligibility",
            "description": "VA Certificate of Eligibility",
            "instructions": "Upload your VA Certificate of Eligibility (COE). If you don't have one, we can help obtain it.",
            "required_count": 1,
            "priority": "HIGH",
            "applies_to": "BORROWER",
            "freshness_days": None,
            "auto_renew": False,
        },
        {
            "doc_type": "DD214",
            "title": "DD-214",
            "description": "Military discharge papers",
            "instructions": "Upload your DD-214 showing honorable discharge. Required for veterans.",
            "required_count": 1,
            "priority": "HIGH",
            "applies_to": "BORROWER",
            "freshness_days": None,
            "auto_renew": False,
        },
    ]

    # Property-related requirements (for purchase)
    purchase_requirements = [
        {
            "doc_type": "PURCHASE_CONTRACT",
            "title": "Purchase Contract",
            "description": "Signed purchase agreement",
            "instructions": "Upload the fully executed purchase contract with all addenda.",
            "required_count": 1,
            "priority": "CRITICAL",
            "applies_to": "BORROWER",
            "freshness_days": None,
            "auto_renew": False,
        },
        {
            "doc_type": "HOMEOWNERS_INSURANCE",
            "title": "Homeowners Insurance Quote",
            "description": "Insurance quote or binder",
            "instructions": "Upload a homeowners insurance quote for the subject property.",
            "required_count": 1,
            "priority": "NORMAL",
            "applies_to": "BORROWER",
            "freshness_days": None,
            "auto_renew": False,
        },
    ]

    # Investment property requirements
    investment_additions = [
        {
            "doc_type": "LEASE_AGREEMENT",
            "title": "Lease Agreement",
            "description": "Current lease agreement if property is rented",
            "instructions": "Upload current lease agreement for the property if applicable.",
            "required_count": 1,
            "priority": "NORMAL",
            "applies_to": "BORROWER",
            "freshness_days": None,
            "auto_renew": False,
        },
    ]

    templates = [
        # Conventional W2 Purchase
        {
            "name": "Conventional W2 Purchase",
            "slug": "conventional-w2-purchase",
            "description": "Standard document requirements for conventional purchase with W2 income",
            "loan_programs": ["CONVENTIONAL"],
            "occupancy_types": ["PRIMARY", "SECOND_HOME"],
            "income_types": ["W2"],
            "request_templates": base_requirements + purchase_requirements,
            "is_active": True,
            "version": "1.0",
        },
        # Conventional Self-Employed Purchase
        {
            "name": "Conventional Self-Employed Purchase",
            "slug": "conventional-self-employed-purchase",
            "description": "Document requirements for self-employed borrowers on conventional loans",
            "loan_programs": ["CONVENTIONAL"],
            "occupancy_types": ["PRIMARY", "SECOND_HOME"],
            "income_types": ["SELF_EMPLOYED"],
            "request_templates": base_requirements + self_employed_additions + purchase_requirements,
            "is_active": True,
            "version": "1.0",
        },
        # FHA Purchase
        {
            "name": "FHA Purchase",
            "slug": "fha-purchase",
            "description": "Document requirements for FHA purchase loans",
            "loan_programs": ["FHA"],
            "occupancy_types": ["PRIMARY"],
            "income_types": ["W2", "SELF_EMPLOYED"],
            "request_templates": base_requirements + fha_additions + purchase_requirements,
            "is_active": True,
            "version": "1.0",
        },
        # VA Purchase
        {
            "name": "VA Purchase",
            "slug": "va-purchase",
            "description": "Document requirements for VA purchase loans",
            "loan_programs": ["VA"],
            "occupancy_types": ["PRIMARY"],
            "income_types": ["W2", "SELF_EMPLOYED"],
            "request_templates": base_requirements + va_additions + purchase_requirements,
            "is_active": True,
            "version": "1.0",
        },
        # Investment Property
        {
            "name": "Investment Property Purchase",
            "slug": "investment-property-purchase",
            "description": "Document requirements for investment property loans",
            "loan_programs": ["CONVENTIONAL"],
            "occupancy_types": ["INVESTMENT"],
            "income_types": ["W2", "SELF_EMPLOYED"],
            "request_templates": base_requirements + investment_additions + purchase_requirements,
            "is_active": True,
            "version": "1.0",
        },
        # Refinance (no purchase contract needed)
        {
            "name": "Conventional Refinance",
            "slug": "conventional-refinance",
            "description": "Document requirements for conventional refinance",
            "loan_programs": ["CONVENTIONAL"],
            "occupancy_types": ["PRIMARY", "SECOND_HOME", "INVESTMENT"],
            "income_types": ["W2"],
            "request_templates": base_requirements,
            "is_active": True,
            "version": "1.0",
        },
    ]

    for template_data in templates:
        # Convert request_templates to JSON
        template_data["request_templates"] = json.dumps(template_data["request_templates"])
        template_data["loan_programs"] = json.dumps(template_data["loan_programs"])
        template_data["occupancy_types"] = json.dumps(template_data["occupancy_types"])
        template_data["income_types"] = json.dumps(template_data["income_types"])

        template = NeedsListTemplate(**template_data)
        session.add(template)

    session.commit()
    print(f"Seeded {len(templates)} needs list templates")
    session.close()


def run_migration():
    """Run the complete migration."""
    print(f"Connecting to database: {DATABASE_URL[:50]}...")

    engine = create_engine(DATABASE_URL)

    # Create tables
    create_tables(engine)

    # Seed data
    seed_needs_list_templates(engine)

    print("\nSmart Document Collection migration complete!")


if __name__ == "__main__":
    run_migration()
