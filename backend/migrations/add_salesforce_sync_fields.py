"""
Add Salesforce Sync Fields to Loans and Leads Tables
Migration to add fields for Salesforce data synchronization

Run with: python migrations/add_salesforce_sync_fields.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")

def run_migration():
    """Add Salesforce sync fields to loans and leads tables"""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable not set")
        return False

    engine = create_engine(DATABASE_URL)

    # Columns to add to LOANS table
    loan_columns = [
        # Property Details
        ("property_type", "VARCHAR"),
        ("occupancy_type", "VARCHAR"),
        ("property_county", "VARCHAR"),
        ("property_ownership_type", "VARCHAR"),
        ("property_units", "INTEGER"),

        # 1st Loan Financial Details
        ("rate_type", "VARCHAR"),
        ("monthly_payment", "FLOAT"),
        ("property_tax", "FLOAT"),
        ("hazard_insurance", "FLOAT"),
        ("mortgage_insurance", "FLOAT"),
        ("hoa_amount", "FLOAT"),
        ("origination_fee", "FLOAT"),
        ("estimated_prepaid_interest", "FLOAT"),
        ("points", "FLOAT"),
        ("index_rate", "FLOAT"),
        ("margin", "FLOAT"),

        # LTV/CLTV
        ("ltv", "FLOAT"),
        ("cltv", "FLOAT"),
        ("loan_purpose", "VARCHAR"),
        ("file_state", "VARCHAR"),

        # 2nd Loan Details
        ("second_loan_amount", "FLOAT"),
        ("second_loan_rate", "FLOAT"),
        ("second_loan_payment", "FLOAT"),

        # Present vs Proposed Housing
        ("present_housing_expense", "FLOAT"),
        ("proposed_housing_expense", "FLOAT"),
        ("present_monthly_payment", "FLOAT"),
        ("proposed_monthly_payment", "FLOAT"),
    ]

    # Columns to add to LEADS table (some already exist like ltv, cltv, points)
    lead_columns = [
        # Property Details (property_type already exists in leads)
        ("occupancy_type", "VARCHAR"),
        ("property_county", "VARCHAR"),
        ("property_ownership_type", "VARCHAR"),
        ("property_units", "INTEGER"),

        # 1st Loan Financial Details
        ("rate_type", "VARCHAR"),
        ("monthly_payment", "FLOAT"),
        ("property_tax", "FLOAT"),
        ("hazard_insurance", "FLOAT"),
        ("mortgage_insurance", "FLOAT"),
        ("hoa_amount", "FLOAT"),
        ("origination_fee", "FLOAT"),
        ("estimated_prepaid_interest", "FLOAT"),
        ("index_rate", "FLOAT"),
        ("margin", "FLOAT"),

        # Additional LTV/CLTV fields
        ("loan_purpose", "VARCHAR"),
        ("file_state", "VARCHAR"),

        # 2nd Loan Details
        ("second_loan_amount", "FLOAT"),
        ("second_loan_rate", "FLOAT"),
        ("second_loan_payment", "FLOAT"),

        # Present vs Proposed Housing
        ("present_housing_expense", "FLOAT"),
        ("proposed_housing_expense", "FLOAT"),
        ("present_monthly_payment", "FLOAT"),
        ("proposed_monthly_payment", "FLOAT"),
    ]

    with engine.connect() as conn:
        total_added = 0
        total_skipped = 0

        # Process LOANS table
        print("\n📊 Adding columns to LOANS table...")
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'loans'
        """))
        existing_loan_columns = {row[0] for row in result}

        for col_name, col_type in loan_columns:
            if col_name in existing_loan_columns:
                print(f"  Column '{col_name}' already exists, skipping")
                total_skipped += 1
            else:
                try:
                    conn.execute(text(f"ALTER TABLE loans ADD COLUMN {col_name} {col_type}"))
                    print(f"  ✓ Added column '{col_name}' ({col_type})")
                    total_added += 1
                except Exception as e:
                    print(f"  ✗ Error adding column '{col_name}': {e}")

        # Process LEADS table
        print("\n📊 Adding columns to LEADS table...")
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'leads'
        """))
        existing_lead_columns = {row[0] for row in result}

        for col_name, col_type in lead_columns:
            if col_name in existing_lead_columns:
                print(f"  Column '{col_name}' already exists, skipping")
                total_skipped += 1
            else:
                try:
                    conn.execute(text(f"ALTER TABLE leads ADD COLUMN {col_name} {col_type}"))
                    print(f"  ✓ Added column '{col_name}' ({col_type})")
                    total_added += 1
                except Exception as e:
                    print(f"  ✗ Error adding column '{col_name}': {e}")

        conn.commit()

        print(f"\n✓ Migration complete: {total_added} columns added, {total_skipped} already existed")
        return True


if __name__ == "__main__":
    print(f"Running Salesforce Sync Fields Migration at {datetime.now()}")
    print("-" * 60)
    success = run_migration()
    sys.exit(0 if success else 1)
