"""
Migration: Add organization_id to telephony models for multi-tenant isolation.

Tables affected:
  - contact_dnc_status (+ replace global unique on phone_number with per-org unique)
  - active_calls
  - vapi_calls
  - vapi_assistants
  - vapi_phone_numbers

Run with: python migrations/add_telephony_org_id.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from db import get_engine


def run_migration():
    engine = get_engine()

    alterations = [
        # ContactDNCStatus
        "ALTER TABLE contact_dnc_status ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)",
        "CREATE INDEX IF NOT EXISTS ix_contact_dnc_status_organization_id ON contact_dnc_status(organization_id)",
        # Drop old unique constraint on phone_number alone, add composite unique per org
        "ALTER TABLE contact_dnc_status DROP CONSTRAINT IF EXISTS contact_dnc_status_phone_number_key",

        # ActiveCall
        "ALTER TABLE active_calls ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)",
        "CREATE INDEX IF NOT EXISTS ix_active_calls_organization_id ON active_calls(organization_id)",

        # VapiCall
        "ALTER TABLE vapi_calls ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)",
        "CREATE INDEX IF NOT EXISTS ix_vapi_calls_organization_id ON vapi_calls(organization_id)",

        # VapiAssistant
        "ALTER TABLE vapi_assistants ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)",
        "CREATE INDEX IF NOT EXISTS ix_vapi_assistants_organization_id ON vapi_assistants(organization_id)",

        # VapiPhoneNumber
        "ALTER TABLE vapi_phone_numbers ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)",
        "CREATE INDEX IF NOT EXISTS ix_vapi_phone_numbers_organization_id ON vapi_phone_numbers(organization_id)",
    ]

    with engine.connect() as conn:
        for sql in alterations:
            try:
                conn.execute(text(sql))
                print(f"  OK: {sql[:80]}...")
            except Exception as e:
                print(f"  SKIP: {sql[:60]}... ({e})")

        # Add composite unique constraint separately with proper error handling
        # (cannot use IF NOT EXISTS for constraints in PostgreSQL)
        try:
            conn.execute(text(
                "ALTER TABLE contact_dnc_status "
                "ADD CONSTRAINT uq_dnc_phone_org UNIQUE (phone_number, organization_id)"
            ))
            print("  OK: ADD CONSTRAINT uq_dnc_phone_org UNIQUE (phone_number, organization_id)")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("  SKIP: uq_dnc_phone_org already exists")
            else:
                print(f"  SKIP: uq_dnc_phone_org ({e})")

        conn.commit()

    print("\nMigration complete.")


if __name__ == "__main__":
    run_migration()
