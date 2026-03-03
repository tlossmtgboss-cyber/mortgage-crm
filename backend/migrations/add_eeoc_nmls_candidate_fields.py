"""
Migration: Add EEOC demographic data and NMLS license tracking fields to mm_candidates.

EEOC fields support voluntary self-identification per OFCCP/EEO-1 requirements.
NMLS fields support mortgage-specific license compliance tracking.
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")

    engine = create_engine(database_url)

    columns = [
        # NMLS License Tracking
        ("nmls_id", "VARCHAR(20)"),
        ("license_states", "JSONB"),
        ("license_expiration_dates", "JSONB"),
        ("ce_credits_completed", "BOOLEAN"),
        ("sponsorship_transfer_status", "VARCHAR(30)"),
        # EEOC/OFCCP Demographic Data
        ("eeoc_consent_given", "BOOLEAN DEFAULT false"),
        ("eeoc_consent_date", "TIMESTAMP"),
        ("eeoc_gender", "VARCHAR(30)"),
        ("eeoc_race_ethnicity", "VARCHAR(50)"),
        ("eeoc_veteran_status", "VARCHAR(30)"),
        ("eeoc_disability_status", "VARCHAR(30)"),
    ]

    added = []
    skipped = []

    with engine.connect() as conn:
        for col_name, col_type in columns:
            try:
                conn.execute(text(f"""
                    ALTER TABLE mm_candidates
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                """))
                added.append(col_name)
            except Exception as e:
                if "already exists" in str(e).lower():
                    skipped.append(col_name)
                else:
                    logger.error(f"Failed to add {col_name}: {e}")
                    skipped.append(f"{col_name}: {e}")

        # Add organization_id to recruit_social_posts if missing
        try:
            conn.execute(text("""
                ALTER TABLE recruit_social_posts
                ADD COLUMN IF NOT EXISTS organization_id INTEGER
            """))
            added.append("recruit_social_posts.organization_id")
        except Exception as e:
            skipped.append(f"recruit_social_posts.organization_id: {e}")

        conn.commit()

    result = {
        "status": "success",
        "added": added,
        "skipped": skipped,
        "message": f"Added {len(added)} columns, skipped {len(skipped)}"
    }
    logger.info(f"Migration result: {result}")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_migration()
    print(result)
