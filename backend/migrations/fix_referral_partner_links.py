"""
Migration: Fix referral partner links for existing applications
Links leads/loans to their correct referral partners based on application declarations
"""

import logging
from database import SessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration():
    """
    Fix referral partner links for existing leads and loans.
    Specifically fixes Steve Latterson -> Timothy Loss (partner ID 22) link.
    """
    db = SessionLocal()
    try:
        logger.info("Starting referral partner link fix migration...")

        # Update leads with name containing "Latterson" to link to Timothy Loss (ID 22)
        result = db.execute(text("""
            UPDATE leads
            SET referral_partner_id = 22,
                updated_at = NOW()
            WHERE (LOWER(name) LIKE '%latterson%' OR LOWER(first_name) LIKE '%steve%' AND LOWER(last_name) LIKE '%latterson%')
              AND (referral_partner_id IS NULL OR referral_partner_id != 22)
            RETURNING id, name, referral_partner_id
        """))

        updated_leads = result.fetchall()
        logger.info(f"Updated {len(updated_leads)} leads: {updated_leads}")

        # Also update loans table if applicable
        result = db.execute(text("""
            UPDATE loans
            SET referral_partner_id = 22,
                updated_at = NOW()
            WHERE LOWER(borrower_name) LIKE '%latterson%'
              AND (referral_partner_id IS NULL OR referral_partner_id != 22)
            RETURNING id, borrower_name, referral_partner_id
        """))

        updated_loans = result.fetchall()
        logger.info(f"Updated {len(updated_loans)} loans: {updated_loans}")

        db.commit()

        return {
            "success": True,
            "updated_leads": len(updated_leads),
            "updated_loans": len(updated_loans),
            "details": {
                "leads": [{"id": r[0], "name": r[1]} for r in updated_leads],
                "loans": [{"id": r[0], "borrower_name": r[1]} for r in updated_loans]
            }
        }

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_migration()
    print(f"Migration result: {result}")
