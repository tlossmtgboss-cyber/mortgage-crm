"""
Database Migration: Create Income Intelligence Engine Tables

This migration adds tables for the Automated Income Intelligence Engine:
- income_summaries: Calculated income summary (single source of truth)
- income_calculation_details: Detailed calculation breakdown per income stream
- income_flags: Conditions, warnings, and required actions
- mileage_depreciation_rates: Year-keyed IRS mileage rates configuration
- income_worksheets: Generated Excel worksheet tracking

Run with: python -m migrations.add_income_intelligence_engine

These tables complement the existing income extraction tables (income_sources,
paystub_extractions, etc.) by storing the calculated results from the
Income Intelligence Engine orchestrator.
"""

import os
import sys
from datetime import datetime, date

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from database import DATABASE_URL


def get_db_type(database_url: str) -> str:
    """Determine database type from URL."""
    if 'sqlite' in database_url.lower():
        return 'sqlite'
    elif 'postgresql' in database_url.lower() or 'postgres' in database_url.lower():
        return 'postgresql'
    return 'unknown'


def check_tables_exist(engine) -> dict:
    """Check which tables already exist."""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    income_engine_tables = [
        'income_summaries',
        'income_calculation_details',
        'income_flags',
        'mileage_depreciation_rates',
        'income_worksheets'
    ]

    return {table: table in existing_tables for table in income_engine_tables}


def create_income_summaries_table(engine, db_type: str):
    """Create the income_summaries table - single source of truth for calculated income."""

    print("  Creating table 'income_summaries'...")

    if db_type == 'sqlite':
        sql = """
        CREATE TABLE IF NOT EXISTS income_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Foreign keys (no constraints in SQLite for flexibility)
            loan_id INTEGER NOT NULL,
            borrower_id INTEGER NOT NULL,

            -- Summary data
            total_monthly_income REAL NOT NULL DEFAULT 0,
            total_annual_income REAL NOT NULL DEFAULT 0,
            ruleset_version VARCHAR(50) NOT NULL DEFAULT '2025.1',

            -- Full JSON payloads
            income_streams TEXT NOT NULL DEFAULT '[]',
            source_documents TEXT NOT NULL DEFAULT '[]',

            -- Approvability
            is_approvable INTEGER NOT NULL DEFAULT 0,
            blocking_flags_count INTEGER NOT NULL DEFAULT 0,
            error_flags_count INTEGER NOT NULL DEFAULT 0,
            warning_flags_count INTEGER NOT NULL DEFAULT 0,
            info_flags_count INTEGER NOT NULL DEFAULT 0,

            -- Metadata
            calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            calculated_by INTEGER,
            calculation_duration_ms INTEGER,

            -- Status tracking
            status VARCHAR(50) NOT NULL DEFAULT 'CALCULATED',
            reviewed_at TIMESTAMP,
            reviewed_by INTEGER,
            review_notes TEXT,

            -- Investor/program context
            investor_code VARCHAR(50),
            program_code VARCHAR(50),

            -- Audit
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    else:  # PostgreSQL
        sql = """
        CREATE TABLE IF NOT EXISTS income_summaries (
            id SERIAL PRIMARY KEY,

            -- Foreign keys
            loan_id INTEGER NOT NULL,
            borrower_id INTEGER NOT NULL,

            -- Summary data
            total_monthly_income DECIMAL(15,2) NOT NULL DEFAULT 0,
            total_annual_income DECIMAL(15,2) NOT NULL DEFAULT 0,
            ruleset_version VARCHAR(50) NOT NULL DEFAULT '2025.1',

            -- Full JSON payloads
            income_streams JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_documents JSONB NOT NULL DEFAULT '[]'::jsonb,

            -- Approvability
            is_approvable BOOLEAN NOT NULL DEFAULT FALSE,
            blocking_flags_count INTEGER NOT NULL DEFAULT 0,
            error_flags_count INTEGER NOT NULL DEFAULT 0,
            warning_flags_count INTEGER NOT NULL DEFAULT 0,
            info_flags_count INTEGER NOT NULL DEFAULT 0,

            -- Metadata
            calculated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            calculated_by INTEGER,
            calculation_duration_ms INTEGER,

            -- Status tracking
            status VARCHAR(50) NOT NULL DEFAULT 'CALCULATED',
            reviewed_at TIMESTAMP,
            reviewed_by INTEGER,
            review_notes TEXT,

            -- Investor/program context
            investor_code VARCHAR(50),
            program_code VARCHAR(50),

            -- Audit
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

            -- Constraints
            CONSTRAINT valid_total_income CHECK (total_monthly_income >= 0)
        )
        """

    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()


def create_income_calculation_details_table(engine, db_type: str):
    """Create the income_calculation_details table for audit trail."""

    print("  Creating table 'income_calculation_details'...")

    if db_type == 'sqlite':
        sql = """
        CREATE TABLE IF NOT EXISTS income_calculation_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            income_summary_id INTEGER NOT NULL,

            -- Income stream identification
            stream_type VARCHAR(100) NOT NULL,
            stream_name VARCHAR(255),

            -- Calculated amounts
            monthly_income REAL NOT NULL DEFAULT 0,
            annual_income REAL DEFAULT 0,

            -- Calculation breakdown (full audit trail)
            calculation_inputs TEXT NOT NULL DEFAULT '{}',
            calculation_steps TEXT NOT NULL DEFAULT '[]',
            add_backs TEXT DEFAULT '{}',
            subtractions TEXT DEFAULT '{}',

            -- Source document
            document_id VARCHAR(255),
            document_type VARCHAR(100),
            tax_year INTEGER,

            -- Trending
            trending_direction VARCHAR(20),
            trending_percentage REAL,

            -- Flags specific to this stream
            stream_flags TEXT DEFAULT '[]',

            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (income_summary_id) REFERENCES income_summaries(id) ON DELETE CASCADE
        )
        """
    else:  # PostgreSQL
        sql = """
        CREATE TABLE IF NOT EXISTS income_calculation_details (
            id SERIAL PRIMARY KEY,

            income_summary_id INTEGER NOT NULL REFERENCES income_summaries(id) ON DELETE CASCADE,

            -- Income stream identification
            stream_type VARCHAR(100) NOT NULL,
            stream_name VARCHAR(255),

            -- Calculated amounts
            monthly_income DECIMAL(15,2) NOT NULL DEFAULT 0,
            annual_income DECIMAL(15,2) DEFAULT 0,

            -- Calculation breakdown (full audit trail)
            calculation_inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
            calculation_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
            add_backs JSONB DEFAULT '{}'::jsonb,
            subtractions JSONB DEFAULT '{}'::jsonb,

            -- Source document
            document_id VARCHAR(255),
            document_type VARCHAR(100),
            tax_year INTEGER,

            -- Trending
            trending_direction VARCHAR(20),
            trending_percentage DECIMAL(8,4),

            -- Flags specific to this stream
            stream_flags JSONB DEFAULT '[]'::jsonb,

            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """

    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()


def create_income_flags_table(engine, db_type: str):
    """Create the income_flags table for conditions and required actions."""

    print("  Creating table 'income_flags'...")

    if db_type == 'sqlite':
        sql = """
        CREATE TABLE IF NOT EXISTS income_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            income_summary_id INTEGER NOT NULL,

            -- Flag details
            rule_id VARCHAR(100) NOT NULL,
            severity VARCHAR(50) NOT NULL,
            message TEXT NOT NULL,
            required_action TEXT,

            -- Context
            affected_stream VARCHAR(100),
            affected_document_id VARCHAR(255),

            -- Flag metadata
            metadata TEXT DEFAULT '{}',

            -- Resolution tracking
            resolved INTEGER NOT NULL DEFAULT 0,
            resolved_at TIMESTAMP,
            resolved_by INTEGER,
            resolution_notes TEXT,
            resolution_type VARCHAR(50),

            -- Auto-condition creation
            condition_created INTEGER NOT NULL DEFAULT 0,
            condition_id INTEGER,

            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (income_summary_id) REFERENCES income_summaries(id) ON DELETE CASCADE
        )
        """
    else:  # PostgreSQL
        sql = """
        CREATE TABLE IF NOT EXISTS income_flags (
            id SERIAL PRIMARY KEY,

            income_summary_id INTEGER NOT NULL REFERENCES income_summaries(id) ON DELETE CASCADE,

            -- Flag details
            rule_id VARCHAR(100) NOT NULL,
            severity VARCHAR(50) NOT NULL,
            message TEXT NOT NULL,
            required_action TEXT,

            -- Context
            affected_stream VARCHAR(100),
            affected_document_id VARCHAR(255),

            -- Flag metadata
            metadata JSONB DEFAULT '{}'::jsonb,

            -- Resolution tracking
            resolved BOOLEAN NOT NULL DEFAULT FALSE,
            resolved_at TIMESTAMP,
            resolved_by INTEGER,
            resolution_notes TEXT,
            resolution_type VARCHAR(50),

            -- Auto-condition creation
            condition_created BOOLEAN NOT NULL DEFAULT FALSE,
            condition_id INTEGER,

            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """

    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()


def create_mileage_depreciation_rates_table(engine, db_type: str):
    """Create the mileage_depreciation_rates configuration table."""

    print("  Creating table 'mileage_depreciation_rates'...")

    if db_type == 'sqlite':
        sql = """
        CREATE TABLE IF NOT EXISTS mileage_depreciation_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            tax_year INTEGER NOT NULL UNIQUE,
            rate_per_mile REAL NOT NULL,

            -- Source documentation
            source VARCHAR(255) NOT NULL,
            source_url TEXT,
            effective_date DATE NOT NULL,

            -- Notes
            notes TEXT,

            -- Audit
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER
        )
        """
    else:  # PostgreSQL
        sql = """
        CREATE TABLE IF NOT EXISTS mileage_depreciation_rates (
            id SERIAL PRIMARY KEY,

            tax_year INTEGER NOT NULL UNIQUE,
            rate_per_mile DECIMAL(6,4) NOT NULL,

            -- Source documentation
            source VARCHAR(255) NOT NULL,
            source_url TEXT,
            effective_date DATE NOT NULL,

            -- Notes
            notes TEXT,

            -- Audit
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_by INTEGER,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_by INTEGER,

            -- Constraints
            CONSTRAINT valid_tax_year CHECK (tax_year >= 2000 AND tax_year <= 2100),
            CONSTRAINT valid_rate CHECK (rate_per_mile > 0 AND rate_per_mile < 10)
        )
        """

    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()


def create_income_worksheets_table(engine, db_type: str):
    """Create the income_worksheets table for tracking generated Excel files."""

    print("  Creating table 'income_worksheets'...")

    if db_type == 'sqlite':
        sql = """
        CREATE TABLE IF NOT EXISTS income_worksheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            income_summary_id INTEGER NOT NULL,

            -- Worksheet details
            worksheet_type VARCHAR(100) NOT NULL,
            template_version VARCHAR(50),

            -- File storage
            file_path TEXT NOT NULL,
            file_name VARCHAR(255),
            file_size INTEGER,
            s3_bucket VARCHAR(255),
            s3_key TEXT,

            -- Generation metadata
            generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            generated_by INTEGER,
            generation_duration_ms INTEGER,

            -- Download tracking
            download_count INTEGER NOT NULL DEFAULT 0,
            last_downloaded_at TIMESTAMP,
            last_downloaded_by INTEGER,

            FOREIGN KEY (income_summary_id) REFERENCES income_summaries(id) ON DELETE CASCADE
        )
        """
    else:  # PostgreSQL
        sql = """
        CREATE TABLE IF NOT EXISTS income_worksheets (
            id SERIAL PRIMARY KEY,

            income_summary_id INTEGER NOT NULL REFERENCES income_summaries(id) ON DELETE CASCADE,

            -- Worksheet details
            worksheet_type VARCHAR(100) NOT NULL,
            template_version VARCHAR(50),

            -- File storage
            file_path TEXT NOT NULL,
            file_name VARCHAR(255),
            file_size BIGINT,
            s3_bucket VARCHAR(255),
            s3_key TEXT,

            -- Generation metadata
            generated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            generated_by INTEGER,
            generation_duration_ms INTEGER,

            -- Download tracking
            download_count INTEGER NOT NULL DEFAULT 0,
            last_downloaded_at TIMESTAMP,
            last_downloaded_by INTEGER
        )
        """

    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()


def create_indexes(engine, db_type: str):
    """Create indexes for performance."""

    print("Creating indexes...")

    indexes = [
        # income_summaries indexes
        ("ix_income_summaries_loan", "income_summaries", "loan_id"),
        ("ix_income_summaries_borrower", "income_summaries", "borrower_id"),
        ("ix_income_summaries_status", "income_summaries", "status"),
        ("ix_income_summaries_calculated_at", "income_summaries", "calculated_at DESC"),
        ("ix_income_summaries_investor", "income_summaries", "investor_code"),

        # income_calculation_details indexes
        ("ix_income_calc_details_summary", "income_calculation_details", "income_summary_id"),
        ("ix_income_calc_details_stream", "income_calculation_details", "stream_type"),

        # income_flags indexes
        ("ix_income_flags_summary", "income_flags", "income_summary_id"),
        ("ix_income_flags_severity", "income_flags", "severity"),
        ("ix_income_flags_rule", "income_flags", "rule_id"),
        ("ix_income_flags_resolved", "income_flags", "resolved"),

        # income_worksheets indexes
        ("ix_income_worksheets_summary", "income_worksheets", "income_summary_id"),
        ("ix_income_worksheets_type", "income_worksheets", "worksheet_type"),
    ]

    with engine.connect() as conn:
        for index_name, table_name, column_spec in indexes:
            try:
                # Remove DESC for SQLite if present
                col = column_spec.replace(' DESC', '') if db_type == 'sqlite' else column_spec

                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON {table_name} ({col})
                """))
                print(f"  Created index '{index_name}'")
            except Exception as e:
                print(f"  Warning: Could not create index '{index_name}': {e}")

        conn.commit()


def seed_mileage_rates(engine, db_type: str):
    """Seed initial mileage depreciation rates."""

    print("Seeding mileage depreciation rates...")

    rates = [
        {
            'tax_year': 2021,
            'rate_per_mile': 0.26,
            'source': 'IRS Notice 2021-02',
            'effective_date': '2021-01-01',
            'notes': 'Standard depreciation component of IRS mileage rate'
        },
        {
            'tax_year': 2022,
            'rate_per_mile': 0.26,
            'source': 'IRS Notice 2022-03',
            'effective_date': '2022-01-01',
            'notes': 'Standard depreciation component (first half of year)'
        },
        {
            'tax_year': 2023,
            'rate_per_mile': 0.28,
            'source': 'IRS Notice 2023-03',
            'effective_date': '2023-01-01',
            'notes': 'Standard depreciation component of IRS mileage rate'
        },
        {
            'tax_year': 2024,
            'rate_per_mile': 0.30,
            'source': 'IRS Notice 2024-08',
            'effective_date': '2024-01-01',
            'notes': 'Standard depreciation component of IRS mileage rate'
        },
    ]

    with engine.connect() as conn:
        for rate in rates:
            try:
                # Check if rate already exists
                check_sql = text("""
                    SELECT id FROM mileage_depreciation_rates WHERE tax_year = :tax_year
                """)
                result = conn.execute(check_sql, {'tax_year': rate['tax_year']})

                if result.fetchone():
                    print(f"  Rate for {rate['tax_year']} already exists, skipping...")
                    continue

                # Insert new rate
                insert_sql = text("""
                    INSERT INTO mileage_depreciation_rates
                    (tax_year, rate_per_mile, source, effective_date, notes)
                    VALUES (:tax_year, :rate_per_mile, :source, :effective_date, :notes)
                """)
                conn.execute(insert_sql, rate)
                print(f"  Seeded rate for {rate['tax_year']}: ${rate['rate_per_mile']}/mile")

            except Exception as e:
                print(f"  Warning: Could not seed rate for {rate['tax_year']}: {e}")

        conn.commit()

    print("Mileage rates seeded successfully!")


def create_composite_indexes(engine, db_type: str):
    """Create composite indexes for common query patterns."""

    print("Creating composite indexes...")

    if db_type == 'postgresql':
        composite_indexes = [
            # Common query: get latest summary for loan+borrower
            ("ix_income_summaries_loan_borrower_date",
             "income_summaries",
             "loan_id, borrower_id, calculated_at DESC"),

            # Common query: unresolved flags by severity
            ("ix_income_flags_unresolved_severity",
             "income_flags",
             "income_summary_id, resolved, severity"),
        ]

        with engine.connect() as conn:
            for index_name, table_name, columns in composite_indexes:
                try:
                    conn.execute(text(f"""
                        CREATE INDEX IF NOT EXISTS {index_name}
                        ON {table_name} ({columns})
                    """))
                    print(f"  Created composite index '{index_name}'")
                except Exception as e:
                    print(f"  Warning: Could not create index '{index_name}': {e}")

            conn.commit()
    else:
        print("  Skipping composite indexes for SQLite (not needed)")


def run_migration():
    """Run the complete migration."""
    print("=" * 60)
    print("Income Intelligence Engine - Database Migration")
    print("=" * 60)

    print(f"\nConnecting to database...")
    db_type = get_db_type(DATABASE_URL)
    print(f"Database type: {db_type}")
    print(f"Database URL: {DATABASE_URL[:50]}...")

    engine = create_engine(DATABASE_URL)

    # Check current state
    table_status = check_tables_exist(engine)
    existing_count = sum(1 for exists in table_status.values() if exists)
    print(f"\nCurrent state: {existing_count}/5 income engine tables exist")
    for table, exists in table_status.items():
        status = "EXISTS" if exists else "MISSING"
        print(f"  - {table}: {status}")

    # Create tables
    print("\n" + "=" * 60)
    print("Creating tables...")
    print("=" * 60)

    if not table_status.get('income_summaries', False):
        create_income_summaries_table(engine, db_type)
    else:
        print("  Table 'income_summaries' already exists, skipping...")

    if not table_status.get('income_calculation_details', False):
        create_income_calculation_details_table(engine, db_type)
    else:
        print("  Table 'income_calculation_details' already exists, skipping...")

    if not table_status.get('income_flags', False):
        create_income_flags_table(engine, db_type)
    else:
        print("  Table 'income_flags' already exists, skipping...")

    if not table_status.get('mileage_depreciation_rates', False):
        create_mileage_depreciation_rates_table(engine, db_type)
    else:
        print("  Table 'mileage_depreciation_rates' already exists, skipping...")

    if not table_status.get('income_worksheets', False):
        create_income_worksheets_table(engine, db_type)
    else:
        print("  Table 'income_worksheets' already exists, skipping...")

    # Create indexes
    print("\n" + "=" * 60)
    create_indexes(engine, db_type)

    # Create composite indexes (PostgreSQL only)
    print("\n" + "=" * 60)
    create_composite_indexes(engine, db_type)

    # Seed mileage rates
    print("\n" + "=" * 60)
    seed_mileage_rates(engine, db_type)

    # Verify
    print("\n" + "=" * 60)
    print("Verifying migration...")
    table_status = check_tables_exist(engine)
    all_exist = all(table_status.values())

    for table, exists in table_status.items():
        status = "OK" if exists else "MISSING"
        print(f"  - {table}: {status}")

    if all_exist:
        print("\nAll Income Intelligence Engine tables created successfully!")
    else:
        missing = [t for t, exists in table_status.items() if not exists]
        print(f"\nWarning: Some tables are missing: {missing}")

    # Print summary
    print("\n" + "=" * 60)
    print("Income Intelligence Engine Migration Complete!")
    print("=" * 60)
    print("""
Tables Created:
  - income_summaries: Calculated income (single source of truth)
  - income_calculation_details: Audit trail for each income stream
  - income_flags: Conditions, warnings, required actions
  - mileage_depreciation_rates: IRS mileage rate configuration
  - income_worksheets: Generated Excel worksheet tracking

Mileage Rates Seeded:
  - 2021: $0.26/mile
  - 2022: $0.26/mile
  - 2023: $0.28/mile
  - 2024: $0.30/mile

Next Steps:
  1. Create SQLAlchemy models: models/income_engine_models.py
  2. Implement Income Engines: income_engine/engines/
  3. Implement Orchestrator: income_engine/orchestrator.py
  4. Add API routes: routes/income_calculation_routes.py
""")


if __name__ == "__main__":
    run_migration()
