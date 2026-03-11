"""
Add tcpa_consents table

Creates the tcpa_consents table used by the TCPA consent certificate system
(FCC 1:1 consent rule, effective April 11, 2026).

This migration is idempotent — safe to run multiple times (checkfirst=True).

Usage:
    python -m migrations.add_tcpa_consents_table
    # or
    from migrations.add_tcpa_consents_table import run_migration
    run_migration()
"""

import logging

logger = logging.getLogger(__name__)


def run_migration():
    """Create the tcpa_consents table if it does not already exist."""
    from database.models.tcpa_consent import TCPAConsent
    from db import engine

    logger.info("Running migration: add_tcpa_consents_table")
    TCPAConsent.__table__.create(engine, checkfirst=True)
    logger.info("tcpa_consents table created (or already existed)")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
    print("tcpa_consents table created")
