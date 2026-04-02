"""
Database Migration: Create Bank Statement Worksheet Tables

This script creates all tables required for the Non-QM Bank Statement income system.
Run with: python -m migrations.add_bank_statement_tables

Features:
- Creates bank statement worksheet tracking tables
- Creates account and monthly data tables
- Creates ineligible deposit tracking for audit trail
- Supports personal and business statements
- Supports 3 calculation methods: Uniform Expense Ratio, CPA P&L, CPA Expense Ratio
- Idempotent - safe to run multiple times
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from database import DATABASE_URL, Base
from models.bank_statement_models import (
    StatementType, CalculationMethod, ExtractionStatus,
    BankStatementWorksheet, BankStatementAccount,
    BankStatementMonth, BankStatementIneligibleItem
)


def check_tables_exist(engine) -> dict:
    """Check which tables already exist."""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    bank_statement_tables = [
        'bank_statement_worksheets',
        'bank_statement_accounts',
        'bank_statement_months',
        'bank_statement_ineligible_items'
    ]

    return {table: table in existing_tables for table in bank_statement_tables}


def create_tables(engine):
    """Create all bank statement-related tables."""
    print("Creating bank statement tables...")

    # Import models to register them with Base
    from models import bank_statement_models

    # List of bank statement tables to create
    bank_statement_tables = [
        BankStatementWorksheet.__table__,
        BankStatementAccount.__table__,
        BankStatementMonth.__table__,
        BankStatementIneligibleItem.__table__,
    ]

    # Check which tables already exist
    table_status = check_tables_exist(engine)

    for table in bank_statement_tables:
        table_name = table.name
        if table_status.get(table_name, False):
            print(f"  Table '{table_name}' already exists, skipping...")
        else:
            print(f"  Creating table '{table_name}'...")
            table.create(bind=engine, checkfirst=True)

    print("Bank statement tables created successfully!")


def create_indexes(engine):
    """Create additional indexes for performance."""
    print("Creating additional indexes...")

    indexes = [
        # Worksheet indexes
        ("ix_bsw_loan_id", "bank_statement_worksheets", "loan_id"),
        ("ix_bsw_borrower_id", "bank_statement_worksheets", "borrower_id"),
        ("ix_bsw_status", "bank_statement_worksheets", "status"),

        # Account indexes
        ("ix_bsa_worksheet_id", "bank_statement_accounts", "worksheet_id"),
        ("ix_bsa_statement_type", "bank_statement_accounts", "statement_type"),

        # Month indexes
        ("ix_bsm_account_id", "bank_statement_months", "account_id"),
        ("ix_bsm_worksheet_id", "bank_statement_months", "worksheet_id"),
        ("ix_bsm_month_number", "bank_statement_months", "month_number"),

        # Ineligible items indexes
        ("ix_bsi_month_id", "bank_statement_ineligible_items", "month_id"),
    ]

    with engine.connect() as conn:
        for index_name, table_name, column_name in indexes:
            try:
                # Check if index exists first (PostgreSQL)
                result = conn.execute(text("""
                    SELECT 1 FROM pg_indexes
                    WHERE indexname = :index_name
                """), {"index_name": index_name})
                if result.fetchone():
                    print(f"  Index '{index_name}' already exists, skipping...")
                    continue

                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON {table_name} ({column_name})
                """))
                print(f"  Created index '{index_name}'")
            except Exception as e:
                # SQLite doesn't have pg_indexes, try direct creation
                try:
                    conn.execute(text(f"""
                        CREATE INDEX IF NOT EXISTS {index_name}
                        ON {table_name} ({column_name})
                    """))
                    print(f"  Created index '{index_name}'")
                except Exception as e2:
                    print(f"  Warning: Could not create index '{index_name}': {e2}")

        conn.commit()

    print("Indexes created successfully!")


def get_calculation_method_info():
    """Returns information about the 3 calculation methods."""
    return {
        "UNIFORM_EXPENSE_RATIO": {
            "name": "Method 1: Uniform Expense Ratio",
            "description": "50% expense ratio for LTV <= 80%, 60% for LTV > 80%",
            "requires_cpa": False
        },
        "CPA_PL": {
            "name": "Method 2: CPA Prepared P&L",
            "description": "Income based on CPA-prepared Profit & Loss statement",
            "requires_cpa": True
        },
        "CPA_EXPENSE_RATIO": {
            "name": "Method 3: CPA Letter Expense Ratio",
            "description": "Uses CPA-stated expense ratio from letter",
            "requires_cpa": True
        }
    }


def run_migration():
    """Run the complete migration."""
    print(f"Connecting to database...")
    print(f"Database URL: {DATABASE_URL[:50]}...")

    engine = create_engine(DATABASE_URL)

    # Check current state
    table_status = check_tables_exist(engine)
    existing_count = sum(1 for exists in table_status.values() if exists)
    print(f"\nCurrent state: {existing_count}/4 bank statement tables exist")
    for table, exists in table_status.items():
        status = "exists" if exists else "missing"
        print(f"  - {table}: {status}")

    # Create tables
    print("\n" + "="*50)
    create_tables(engine)

    # Create additional indexes
    print("\n" + "="*50)
    create_indexes(engine)

    # Verify
    print("\n" + "="*50)
    print("Verifying migration...")
    table_status = check_tables_exist(engine)
    all_exist = all(table_status.values())

    if all_exist:
        print("All bank statement tables created successfully!")
    else:
        missing = [t for t, exists in table_status.items() if not exists]
        print(f"Warning: Some tables are missing: {missing}")

    print("\n" + "="*50)
    print("Bank Statement Tables Migration Complete!")
    print("\nCalculation Methods Supported:")
    for method, info in get_calculation_method_info().items():
        print(f"  - {info['name']}")
        print(f"    {info['description']}")
        print(f"    Requires CPA: {'Yes' if info['requires_cpa'] else 'No'}")


if __name__ == "__main__":
    run_migration()
