"""
Migration: Add Referral Intelligence Fields
Adds all fields required for the Employment Tab Referral Intelligence System
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from database import DATABASE_URL

def run_migration():
    """Add referral intelligence columns to lead_profiles, active_loan_profiles, and mum_clients"""

    engine = create_engine(DATABASE_URL)

    # New columns for referral intelligence
    new_columns = [
        # Borrower Opportunity Score Fields
        ("leadership_level", "VARCHAR(50)"),
        ("employees_managed", "INTEGER DEFAULT 0"),
        ("company_size", "VARCHAR(50)"),
        ("influence_score", "VARCHAR(50)"),

        # Referral Potential Fields
        ("referral_industry_flag", "VARCHAR(20)"),

        # Future Purchase Opportunity Fields
        ("career_stability_score", "VARCHAR(20)"),
        ("future_purchase_likelihood", "VARCHAR(20)"),
        ("future_purchase_timeline", "VARCHAR(20)"),

        # Referral Network Mapping Fields
        ("manages_potential_buyers", "VARCHAR(20)"),
        ("employer_hiring_frequency", "VARCHAR(50)"),
        ("referral_comfort_level", "VARCHAR(50)"),

        # Overall Referral Score
        ("referral_source_score", "INTEGER DEFAULT 0"),
        ("referral_source_rating", "VARCHAR(50)"),
    ]

    # Tables to update
    tables = ["leads", "active_loans", "mum_clients"]

    with engine.connect() as conn:
        for table in tables:
            print(f"\nUpdating table: {table}")

            for col_name, col_type in new_columns:
                try:
                    # Check if column exists
                    check_sql = text("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = :table_name AND column_name = :col_name
                    """)
                    result = conn.execute(check_sql, {"table_name": table, "col_name": col_name})

                    if result.fetchone() is None:
                        # Add column
                        alter_sql = text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                        conn.execute(alter_sql)
                        print(f"  Added: {col_name}")
                    else:
                        print(f"  Exists: {col_name}")

                except Exception as e:
                    print(f"  Error adding {col_name}: {e}")

        conn.commit()

    print("\nMigration completed successfully!")

if __name__ == "__main__":
    run_migration()
