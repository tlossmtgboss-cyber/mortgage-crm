"""Add organization_id to remaining telephony models."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import engine
from sqlalchemy import text


def run():
    tables = [
        "agent_telephony_settings",
        "verified_caller_ids",
        "dialer_session_tasks",
        "vapi_call_notes",
        "call_routing_log",
        "staff_availability",
        "call_transfer_config",
    ]
    with engine.connect() as conn:
        for table in tables:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)"))
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_org_id ON {table}(organization_id)"))
                print(f"  Added organization_id to {table}")
            except Exception as e:
                print(f"  Skipped {table}: {e}")
        conn.commit()
    print("Done.")


if __name__ == "__main__":
    run()
