"""
Add partial unique indexes to credit_authorizations and econsent_agreements.

Prevents duplicate authorized/consented records per application at the DB level.
The service layer already has idempotency checks, but these indexes enforce it
even under concurrent requests or bypassed service calls.

Run: python migrations/pos_consent_unique_indexes.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from db import engine


def run():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_auth_one_per_app
            ON credit_authorizations (application_id)
            WHERE authorized = true
        """))

        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_econsent_one_per_app
            ON econsent_agreements (application_id)
            WHERE consented = true
        """))

    print("Partial unique indexes created on credit_authorizations and econsent_agreements.")


if __name__ == "__main__":
    run()
