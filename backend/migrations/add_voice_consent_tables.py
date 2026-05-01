"""
Add Voice Consent Tables for TCPA AI Voice Call Compliance

Creates:
  - voice_consents: Per-phone consent records with full provenance for
    AI-generated voice calls (Vapi/Telnyx).
  - voice_consent_audit: Immutable append-only audit trail for every
    consent lifecycle event (created, verified, revoked, expired).

FCC ruling (Nov 2023, eff. Feb 2024): AI-generated voices are "artificial
or prerecorded voice" under TCPA 47 U.S.C. 227.
Mortgage One class action (Feb 2026): $500-$1,500 per AI voice call
placed without proper consent.

Consent records must be retained for a minimum of 5 years.

Usage:
    python -m migrations.add_voice_consent_tables
    # or
    from migrations.add_voice_consent_tables import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Create voice_consents and voice_consent_audit tables."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        # -------------------------------------------------------------------
        # 1. Create voice_consents table
        # -------------------------------------------------------------------
        logger.info("Creating voice_consents table...")
        try:
            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS voice_consents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        organization_id INTEGER NOT NULL,
                        lead_id INTEGER,
                        borrower_id INTEGER,
                        phone_number VARCHAR(20) NOT NULL,
                        consent_type VARCHAR(30) NOT NULL,
                        consent_channel VARCHAR(20) NOT NULL,
                        consent_language_version VARCHAR(20),
                        consent_text TEXT,
                        recording_url VARCHAR(500),
                        ip_address VARCHAR(45),
                        user_agent VARCHAR(500),
                        consented_at TIMESTAMP NOT NULL,
                        revoked_at TIMESTAMP,
                        revocation_reason VARCHAR(500),
                        retention_expires_at TIMESTAMP,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (organization_id) REFERENCES organizations(id),
                        FOREIGN KEY (lead_id) REFERENCES leads(id),
                        FOREIGN KEY (borrower_id) REFERENCES leads(id)
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS voice_consents (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL REFERENCES organizations(id),
                        lead_id INTEGER REFERENCES leads(id),
                        borrower_id INTEGER REFERENCES leads(id),
                        phone_number VARCHAR(20) NOT NULL,
                        consent_type VARCHAR(30) NOT NULL,
                        consent_channel VARCHAR(20) NOT NULL,
                        consent_language_version VARCHAR(20),
                        consent_text TEXT,
                        recording_url VARCHAR(500),
                        ip_address VARCHAR(45),
                        user_agent VARCHAR(500),
                        consented_at TIMESTAMP NOT NULL,
                        revoked_at TIMESTAMP,
                        revocation_reason VARCHAR(500),
                        retention_expires_at TIMESTAMP,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                """))

            conn.commit()
            logger.info("  voice_consents table created successfully")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  voice_consents table already exists")
            else:
                logger.error(f"Failed to create voice_consents table: {e}")
                return False

        # Create indexes for voice_consents
        indexes = [
            (
                "ix_voice_consents_org_id",
                "voice_consents (organization_id)",
            ),
            (
                "ix_voice_consents_lead_id",
                "voice_consents (lead_id)",
            ),
            (
                "ix_voice_consents_borrower_id",
                "voice_consents (borrower_id)",
            ),
            (
                "ix_voice_consents_phone",
                "voice_consents (phone_number)",
            ),
            (
                "ix_vc_org_phone",
                "voice_consents (organization_id, phone_number)",
            ),
            (
                "ix_vc_phone_type",
                "voice_consents (phone_number, consent_type)",
            ),
        ]

        for idx_name, idx_def in indexes:
            try:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}"
                ))
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str:
                    pass
                else:
                    logger.warning(f"Could not create index {idx_name}: {e}")

        conn.commit()
        logger.info("  voice_consents indexes created")

        # -------------------------------------------------------------------
        # 2. Create voice_consent_audit table
        # -------------------------------------------------------------------
        logger.info("Creating voice_consent_audit table...")
        try:
            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS voice_consent_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        voice_consent_id INTEGER NOT NULL,
                        action VARCHAR(20) NOT NULL,
                        actor_user_id INTEGER,
                        actor_ip VARCHAR(45),
                        details JSON,
                        timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (voice_consent_id) REFERENCES voice_consents(id),
                        FOREIGN KEY (actor_user_id) REFERENCES users(id)
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS voice_consent_audit (
                        id SERIAL PRIMARY KEY,
                        voice_consent_id INTEGER NOT NULL REFERENCES voice_consents(id),
                        action VARCHAR(20) NOT NULL,
                        actor_user_id INTEGER REFERENCES users(id),
                        actor_ip VARCHAR(45),
                        details JSONB,
                        timestamp TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                """))

            conn.commit()
            logger.info("  voice_consent_audit table created successfully")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  voice_consent_audit table already exists")
            else:
                logger.error(f"Failed to create voice_consent_audit table: {e}")
                return False

        # Create indexes for voice_consent_audit
        audit_indexes = [
            (
                "ix_vca_consent_id",
                "voice_consent_audit (voice_consent_id)",
            ),
            (
                "ix_vca_consent_action",
                "voice_consent_audit (voice_consent_id, action)",
            ),
            (
                "ix_vca_timestamp",
                "voice_consent_audit (timestamp)",
            ),
        ]

        for idx_name, idx_def in audit_indexes:
            try:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}"
                ))
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str:
                    pass
                else:
                    logger.warning(f"Could not create index {idx_name}: {e}")

        conn.commit()
        logger.info("  voice_consent_audit indexes created")

    logger.info("Voice consent migration complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
