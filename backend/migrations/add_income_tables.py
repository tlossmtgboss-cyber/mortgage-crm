"""
Database Migration: Create Income Extraction & Management Tables

This script creates all tables required for the AI-powered income extraction system.
Run with: python -m migrations.add_income_tables

Features:
- Creates income source tracking tables
- Creates paystub extraction tables with full field support
- Creates employment tracking tables
- Creates self-employment and rental income tables
- Creates income calculation history for audit trail
- Idempotent - safe to run multiple times
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from database import DATABASE_URL, Base
from models.income_models import (
    IncomeType, IncomeCalculationMethod, IncomeVerificationStatus,
    EmploymentStatus, PayrollFrequency,
    IncomeSource, PaystubExtraction, Employment,
    SelfEmploymentIncome, RentalIncomeProperty, IncomeCalculationHistory
)


def check_tables_exist(engine) -> dict:
    """Check which tables already exist."""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    income_tables = [
        'income_sources',
        'paystub_extractions',
        'employments',
        'self_employment_income',
        'rental_income_properties',
        'income_calculation_history'
    ]

    return {table: table in existing_tables for table in income_tables}


def create_tables(engine):
    """Create all income-related tables."""
    print("Creating income tables...")

    # Import models to register them with Base
    from models import income_models

    # List of income tables to create
    income_tables = [
        IncomeSource.__table__,
        PaystubExtraction.__table__,
        Employment.__table__,
        SelfEmploymentIncome.__table__,
        RentalIncomeProperty.__table__,
        IncomeCalculationHistory.__table__,
    ]

    # Check which tables already exist
    table_status = check_tables_exist(engine)

    for table in income_tables:
        table_name = table.name
        if table_status.get(table_name, False):
            print(f"  Table '{table_name}' already exists, skipping...")
        else:
            print(f"  Creating table '{table_name}'...")
            table.create(bind=engine, checkfirst=True)

    print("Income tables created successfully!")


def create_indexes(engine):
    """Create additional indexes for performance."""
    print("Creating additional indexes...")

    indexes = [
        # Income sources indexes
        ("ix_income_sources_type", "income_sources", "income_type"),
        ("ix_income_sources_verification", "income_sources", "verification_status"),

        # Paystub extractions indexes
        ("ix_paystub_pay_date", "paystub_extractions", "pay_date"),
        ("ix_paystub_expires_at", "paystub_extractions", "expires_at"),
        ("ix_paystub_applied", "paystub_extractions", "applied_to_profile"),

        # Employment indexes
        ("ix_employment_status", "employments", "status"),
        ("ix_employment_employer", "employments", "employer_name"),

        # Self-employment indexes
        ("ix_self_emp_tax_year", "self_employment_income", "tax_year"),

        # Rental income indexes
        ("ix_rental_property_address", "rental_income_properties", "property_address_line1"),
    ]

    with engine.connect() as conn:
        for index_name, table_name, column_name in indexes:
            try:
                # Check if index exists first
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


def add_pay_frequency_expiration_days():
    """
    Returns expiration days based on pay frequency.
    This is used by the application when setting expires_at on paystub extractions.
    """
    return {
        "WEEKLY": 7,
        "BIWEEKLY": 30,
        "SEMIMONTHLY": 30,
        "MONTHLY": 45
    }


def run_migration():
    """Run the complete migration."""
    print(f"Connecting to database...")
    print(f"Database URL: {DATABASE_URL[:50]}...")

    engine = create_engine(DATABASE_URL)

    # Check current state
    table_status = check_tables_exist(engine)
    existing_count = sum(1 for exists in table_status.values() if exists)
    print(f"\nCurrent state: {existing_count}/6 income tables exist")
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
        print("All income tables created successfully!")
    else:
        missing = [t for t, exists in table_status.items() if not exists]
        print(f"Warning: Some tables are missing: {missing}")

    print("\n" + "="*50)
    print("Income Tables Migration Complete!")
    print("\nPay frequency expiration rules:")
    for freq, days in add_pay_frequency_expiration_days().items():
        print(f"  - {freq}: {days} days after pay date")


if __name__ == "__main__":
    run_migration()
