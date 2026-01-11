"""
Add Salesforce Property Details and 1st Loan Fields Migration

This migration adds new fields to the loans table to support Salesforce
Transaction Property sync for:
- Property Details section
- 1st Loan section
- Borrower/Loan information

Run: python migrations/add_salesforce_property_loan_fields.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")

# New fields to add to loans table
NEW_LOAN_FIELDS = [
    # Property Details
    ("property_type", "VARCHAR(50)", "Property type (Single Family, Condo, etc.)"),
    ("occupancy_type", "VARCHAR(50)", "Occupancy type (Primary, Investment, Second Home)"),
    ("property_county", "VARCHAR(100)", "Property county"),
    ("property_ownership_type", "VARCHAR(50)", "Fee Simple or Leasehold"),
    ("property_units", "INTEGER", "Number of units"),

    # 1st Loan Financial Details
    ("rate_type", "VARCHAR(50)", "Rate type (Fixed, ARM, etc.)"),
    ("property_tax", "DECIMAL(12,2)", "Annual property tax amount"),
    ("estimated_prepaid_interest", "DECIMAL(12,2)", "Estimated prepaid interest"),
    ("hazard_insurance", "DECIMAL(12,2)", "Monthly hazard insurance"),
    ("origination_fee", "DECIMAL(12,2)", "Origination fee amount"),
    ("mortgage_insurance", "DECIMAL(12,2)", "Monthly mortgage insurance"),
    ("hoa_amount", "DECIMAL(12,2)", "Monthly HOA dues"),
    ("points", "DECIMAL(5,3)", "Discount points"),
    ("index_rate", "DECIMAL(5,3)", "Index rate for ARMs"),
    ("margin", "DECIMAL(5,3)", "Margin for ARMs"),
    ("monthly_payment", "DECIMAL(12,2)", "Monthly P&I payment"),
    ("total_monthly_payment", "DECIMAL(12,2)", "Total monthly payment (PITI)"),

    # Additional Loan Info
    ("loan_purpose", "VARCHAR(50)", "Purchase, Refinance, Cash-Out, etc."),
    ("loan_date", "DATE", "Loan origination date"),
    ("aus_du_run_date", "DATE", "AUS/DU run date"),
    ("lender_state_eligibility", "VARCHAR(100)", "Lender state eligibility"),

    # LTV/CLTV
    ("ltv", "DECIMAL(5,2)", "Loan to value ratio"),
    ("cltv", "DECIMAL(5,2)", "Combined loan to value ratio"),

    # Borrower Additional Info
    ("borrower_account", "VARCHAR(100)", "Borrower account reference"),
    ("file_state", "VARCHAR(50)", "File state/status"),

    # 2nd Loan fields (if applicable)
    ("second_loan_amount", "DECIMAL(12,2)", "2nd loan amount"),
    ("second_loan_rate", "DECIMAL(5,3)", "2nd loan interest rate"),
    ("second_loan_payment", "DECIMAL(12,2)", "2nd loan monthly payment"),

    # Present vs Proposed
    ("present_housing_expense", "DECIMAL(12,2)", "Current housing expense"),
    ("proposed_housing_expense", "DECIMAL(12,2)", "Proposed housing expense"),
    ("present_monthly_payment", "DECIMAL(12,2)", "Current monthly payment"),
    ("proposed_monthly_payment", "DECIMAL(12,2)", "Proposed monthly payment"),
]

# Salesforce field mappings for Property Details and 1st Loan
SALESFORCE_FIELD_MAPPINGS = [
    # Property Details
    {
        "salesforce_field": "MtgPlanner_CRM__Property_Type__c",
        "crm_field": "property_type",
        "transform_type": None,
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Occupancy_Type__c",
        "crm_field": "occupancy_type",
        "transform_type": None,
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Property_County__c",
        "crm_field": "property_county",
        "transform_type": None,
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Property_Ownership_Type__c",
        "crm_field": "property_ownership_type",
        "transform_type": None,
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Property_Units__c",
        "crm_field": "property_units",
        "transform_type": "integer",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Appraised_Value__c",
        "crm_field": "appraisal_value",
        "transform_type": "decimal",
        "direction": "inbound"
    },

    # 1st Loan Details
    {
        "salesforce_field": "MtgPlanner_CRM__Rate_Type_1st_TD__c",
        "crm_field": "rate_type",
        "transform_type": None,
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Note_Rate__c",
        "crm_field": "interest_rate",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Property_Tax_1st_TD__c",
        "crm_field": "property_tax",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Est_Prepaid_Int_1st_TD__c",
        "crm_field": "estimated_prepaid_interest",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Hazard_Ins_1st_TD__c",
        "crm_field": "hazard_insurance",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Origination_1st_TD__c",
        "crm_field": "origination_fee",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Mortgage_Ins_1st_TD__c",
        "crm_field": "mortgage_insurance",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__HOA_1st_TD__c",
        "crm_field": "hoa_amount",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Points_1st_TD__c",
        "crm_field": "points",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Index_1st_TD__c",
        "crm_field": "index_rate",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Margin_1st_TD__c",
        "crm_field": "margin",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Monthly_Payment_1st_TD__c",
        "crm_field": "monthly_payment",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Loan_Date_1st_TD__c",
        "crm_field": "loan_date",
        "transform_type": "date",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__AUS_DU_Run_Date_1st_TD__c",
        "crm_field": "aus_du_run_date",
        "transform_type": "date",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Lender_State_Elig_1st_TD__c",
        "crm_field": "lender_state_eligibility",
        "transform_type": None,
        "direction": "inbound"
    },

    # LTV/CLTV
    {
        "salesforce_field": "MtgPlanner_CRM__LTV__c",
        "crm_field": "ltv",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__CLTV__c",
        "crm_field": "cltv",
        "transform_type": "decimal",
        "direction": "inbound"
    },

    # Loan Purpose and Additional Info
    {
        "salesforce_field": "MtgPlanner_CRM__Loan_Purpose__c",
        "crm_field": "loan_purpose",
        "transform_type": None,
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__File_State__c",
        "crm_field": "file_state",
        "transform_type": None,
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Account__c",
        "crm_field": "borrower_account",
        "transform_type": None,
        "direction": "inbound"
    },

    # 2nd Loan
    {
        "salesforce_field": "MtgPlanner_CRM__Loan_Amount_2nd_TD__c",
        "crm_field": "second_loan_amount",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Rate_2nd_TD__c",
        "crm_field": "second_loan_rate",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Monthly_Payment_2nd_TD__c",
        "crm_field": "second_loan_payment",
        "transform_type": "decimal",
        "direction": "inbound"
    },

    # Present vs Proposed
    {
        "salesforce_field": "MtgPlanner_CRM__Present_Total_Expenses__c",
        "crm_field": "present_housing_expense",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Proposed_Total_Expenses__c",
        "crm_field": "proposed_housing_expense",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Present_Monthly_Payment__c",
        "crm_field": "present_monthly_payment",
        "transform_type": "decimal",
        "direction": "inbound"
    },
    {
        "salesforce_field": "MtgPlanner_CRM__Proposed_Monthly_Payment_1st_TD__c",
        "crm_field": "proposed_monthly_payment",
        "transform_type": "decimal",
        "direction": "inbound"
    },
]


def run_migration():
    """Run the migration to add new fields and mappings."""
    engine = create_engine(DATABASE_URL)

    is_sqlite = "sqlite" in DATABASE_URL.lower()

    print("=" * 60)
    print("Salesforce Property & 1st Loan Fields Migration")
    print("=" * 60)

    with engine.connect() as conn:
        # Step 1: Add new columns to loans table
        print("\n[1/3] Adding new columns to loans table...")

        columns_added = 0
        columns_exist = 0

        for col_name, col_type, description in NEW_LOAN_FIELDS:
            try:
                # Check if column exists
                if is_sqlite:
                    result = conn.execute(text(f"PRAGMA table_info(loans)"))
                    existing_cols = [row[1] for row in result.fetchall()]
                    exists = col_name in existing_cols
                else:
                    result = conn.execute(text("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = 'loans' AND column_name = :col_name
                    """), {"col_name": col_name})
                    exists = result.fetchone() is not None

                if not exists:
                    # Add the column
                    conn.execute(text(f"ALTER TABLE loans ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    print(f"  + Added: {col_name} ({col_type})")
                    columns_added += 1
                else:
                    columns_exist += 1

            except Exception as e:
                print(f"  ! Error adding {col_name}: {e}")

        print(f"\n  Summary: {columns_added} added, {columns_exist} already existed")

        # Step 2: Check if salesforce_field_mappings table exists
        print("\n[2/3] Checking salesforce_field_mappings table...")

        try:
            if is_sqlite:
                result = conn.execute(text("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='salesforce_field_mappings'
                """))
            else:
                result = conn.execute(text("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = 'salesforce_field_mappings'
                """))

            if not result.fetchone():
                # Create the table
                print("  Creating salesforce_field_mappings table...")
                conn.execute(text("""
                    CREATE TABLE salesforce_field_mappings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        organization_id INTEGER DEFAULT 1,
                        salesforce_object VARCHAR(255) DEFAULT 'MtgPlanner_CRM__Transaction_Property__c',
                        salesforce_field VARCHAR(255) NOT NULL,
                        crm_entity VARCHAR(50) DEFAULT 'loan',
                        crm_field VARCHAR(255) NOT NULL,
                        transform_type VARCHAR(50),
                        is_active BOOLEAN DEFAULT 1,
                        direction VARCHAR(20) DEFAULT 'inbound',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.commit()
                print("  + Created salesforce_field_mappings table")
            else:
                print("  Table already exists")

        except Exception as e:
            print(f"  ! Error with table: {e}")

        # Step 3: Insert field mappings
        print("\n[3/3] Adding Salesforce field mappings...")

        mappings_added = 0
        mappings_exist = 0

        for mapping in SALESFORCE_FIELD_MAPPINGS:
            try:
                # Check if mapping exists
                result = conn.execute(text("""
                    SELECT id FROM salesforce_field_mappings
                    WHERE salesforce_field = :sf_field AND crm_field = :crm_field
                """), {
                    "sf_field": mapping["salesforce_field"],
                    "crm_field": mapping["crm_field"]
                })

                if not result.fetchone():
                    conn.execute(text("""
                        INSERT INTO salesforce_field_mappings
                        (salesforce_field, crm_field, transform_type, direction)
                        VALUES (:sf_field, :crm_field, :transform, :direction)
                    """), {
                        "sf_field": mapping["salesforce_field"],
                        "crm_field": mapping["crm_field"],
                        "transform": mapping.get("transform_type"),
                        "direction": mapping.get("direction", "inbound")
                    })
                    conn.commit()
                    print(f"  + {mapping['salesforce_field']} → {mapping['crm_field']}")
                    mappings_added += 1
                else:
                    mappings_exist += 1

            except Exception as e:
                print(f"  ! Error adding mapping: {e}")

        print(f"\n  Summary: {mappings_added} mappings added, {mappings_exist} already existed")

    print("\n" + "=" * 60)
    print("Migration completed!")
    print("=" * 60)

    # Print field mapping summary
    print("\n📋 NEW FIELD MAPPINGS SUMMARY")
    print("-" * 60)
    print("\nProperty Details:")
    print("  - Property Type, Occupancy, County, Ownership Type")
    print("  - Appraised Value, Property Units")
    print("\n1st Loan Details:")
    print("  - Rate Type, Note Rate, Points, Index, Margin")
    print("  - Property Tax, Hazard Insurance, Mortgage Insurance")
    print("  - Origination Fee, HOA, Monthly Payment")
    print("  - Loan Date, AUS/DU Run Date")
    print("\nLTV/Financial:")
    print("  - LTV, CLTV, Loan Purpose, File State")
    print("\n2nd Loan:")
    print("  - Amount, Rate, Monthly Payment")
    print("\nPresent vs Proposed:")
    print("  - Housing Expenses, Monthly Payments")


if __name__ == "__main__":
    run_migration()
