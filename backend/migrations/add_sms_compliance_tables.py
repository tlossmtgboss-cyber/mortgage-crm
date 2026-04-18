"""
Migration: Add sms_opt_outs, sms_consent, and sms_compliance_log tables.

These tables back the SMS compliance gate (sms_compliance_gate.py) and opt-out
manager (sms_opt_out_manager.py).  All three are queried via raw SQL in those
modules, so the schema here must match the column names exactly.

Safe to re-run: uses CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Create the sms_opt_outs, sms_consent, and sms_compliance_log tables."""
    engine = create_engine(DATABASE_URL)
    is_postgres = "postgresql" in DATABASE_URL.lower()

    with engine.connect() as conn:
        # ------------------------------------------------------------------
        # 1. sms_opt_outs
        # ------------------------------------------------------------------
        if is_postgres:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_opt_outs (
                    id SERIAL PRIMARY KEY,
                    phone_number VARCHAR(20) NOT NULL UNIQUE,
                    opt_out_keyword VARCHAR(20) DEFAULT 'STOP',
                    lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
                    organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    opted_out_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    opted_in_at TIMESTAMP WITH TIME ZONE
                );

                CREATE INDEX IF NOT EXISTS ix_sms_opt_outs_phone
                    ON sms_opt_outs(phone_number);
                CREATE INDEX IF NOT EXISTS ix_sms_opt_outs_org_id
                    ON sms_opt_outs(organization_id);
                CREATE INDEX IF NOT EXISTS ix_sms_opt_outs_org_phone
                    ON sms_opt_outs(organization_id, phone_number);
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_opt_outs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number VARCHAR(20) NOT NULL UNIQUE,
                    opt_out_keyword VARCHAR(20) DEFAULT 'STOP',
                    lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
                    organization_id INTEGER,
                    active BOOLEAN NOT NULL DEFAULT 1,
                    opted_out_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    opted_in_at TIMESTAMP
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_opt_outs_phone ON sms_opt_outs(phone_number)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_opt_outs_org_id ON sms_opt_outs(organization_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_opt_outs_org_phone ON sms_opt_outs(organization_id, phone_number)"
            ))

        print("  [OK] sms_opt_outs")

        # ------------------------------------------------------------------
        # 2. sms_consent
        # ------------------------------------------------------------------
        if is_postgres:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_consent (
                    id SERIAL PRIMARY KEY,
                    phone_number VARCHAR(20) NOT NULL UNIQUE,
                    lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
                    consent_given BOOLEAN NOT NULL DEFAULT FALSE,
                    consent_source VARCHAR(50),
                    consented_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ip_address VARCHAR(45)
                );

                CREATE INDEX IF NOT EXISTS ix_sms_consent_phone
                    ON sms_consent(phone_number);
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_consent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number VARCHAR(20) NOT NULL UNIQUE,
                    lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
                    consent_given BOOLEAN NOT NULL DEFAULT 0,
                    consent_source VARCHAR(50),
                    consented_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address VARCHAR(45)
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_consent_phone ON sms_consent(phone_number)"
            ))

        print("  [OK] sms_consent")

        # ------------------------------------------------------------------
        # 3. sms_compliance_log
        # ------------------------------------------------------------------
        if is_postgres:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_compliance_log (
                    id SERIAL PRIMARY KEY,
                    phone_number VARCHAR(20) NOT NULL,
                    lead_id INTEGER,
                    user_id INTEGER,
                    check_result VARCHAR(50) NOT NULL,
                    checked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS ix_sms_compliance_log_phone
                    ON sms_compliance_log(phone_number);
                CREATE INDEX IF NOT EXISTS ix_sms_compliance_log_phone_checked
                    ON sms_compliance_log(phone_number, checked_at);
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_compliance_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number VARCHAR(20) NOT NULL,
                    lead_id INTEGER,
                    user_id INTEGER,
                    check_result VARCHAR(50) NOT NULL,
                    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_compliance_log_phone ON sms_compliance_log(phone_number)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_compliance_log_phone_checked ON sms_compliance_log(phone_number, checked_at)"
            ))

        print("  [OK] sms_compliance_log")

        conn.commit()
        print("\nSuccessfully created SMS compliance tables.")


def rollback_migration():
    """Drop all three SMS compliance tables."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS sms_compliance_log CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS sms_consent CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS sms_opt_outs CASCADE;"))
        conn.commit()
        print("Successfully dropped SMS compliance tables.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        rollback_migration()
    else:
        run_migration()
