"""Add trigram indexes for ILIKE search performance."""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Create GIN trigram indexes on commonly searched text columns.

    Requires the pg_trgm extension. Indexes use gin_trgm_ops for fast
    ILIKE/LIKE pattern matching on lead name, email, phone and loan
    borrower_name fields.
    """
    with engine.connect() as conn:
        # Enable pg_trgm extension (requires superuser or rds_superuser on RDS/Railway)
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.commit()
        except Exception as e:
            logger.warning("pg_trgm extension could not be created: %s", e)
            conn.rollback()
            return  # Cannot create trigram indexes without the extension

        indexes = [
            ("idx_leads_name_trgm", "leads", "name"),
            ("idx_leads_email_trgm", "leads", "email"),
            ("idx_leads_phone_trgm", "leads", "phone"),
            ("idx_loans_borrower_name_trgm", "loans", "borrower_name"),
        ]
        for idx_name, table, column in indexes:
            try:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} "
                    f"ON {table} USING gin ({column} gin_trgm_ops)"
                ))
                conn.commit()
                logger.info("Created trigram index %s", idx_name)
            except Exception as e:
                logger.warning("Index %s: %s", idx_name, e)
                conn.rollback()
