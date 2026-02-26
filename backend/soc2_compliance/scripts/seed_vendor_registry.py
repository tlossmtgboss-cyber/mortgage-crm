"""
Seed Vendor Registry — Pre-populate known third-party vendors.
SOC 2 Criteria: CC9 (Risk Mitigation)

Populates the soc2_vendor_registry table with vendors already in use by Perennia AI.
Idempotent — uses INSERT ... ON CONFLICT DO UPDATE.
"""
import logging
from datetime import date
from typing import List, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("soc2.vendor_seed")

VENDORS: List[Dict] = [
    {
        "vendor_name": "Railway",
        "category": "infrastructure",
        "data_access_level": "full",
        "soc2_status": "SOC 2 Type II certified",
        "risk_level": "low",
        "notes": "PaaS hosting provider. Hosts application and database. Full data access.",
    },
    {
        "vendor_name": "SendGrid",
        "category": "communication",
        "data_access_level": "limited",
        "soc2_status": "SOC 2 Type II certified",
        "risk_level": "low",
        "notes": "Transactional email delivery. Sees email addresses and content.",
    },
    {
        "vendor_name": "DataDog",
        "category": "monitoring",
        "data_access_level": "metadata",
        "soc2_status": "SOC 2 Type II certified",
        "risk_level": "low",
        "notes": "Application monitoring and logging. Sees structured logs and metrics.",
    },
    {
        "vendor_name": "Telnyx",
        "category": "telephony",
        "data_access_level": "limited",
        "soc2_status": "SOC 2 Type II certified",
        "risk_level": "medium",
        "notes": "Direct telephony provider for click-to-call and SMS. Sees phone numbers.",
    },
    {
        "vendor_name": "Twilio",
        "category": "telephony",
        "data_access_level": "limited",
        "soc2_status": "SOC 2 Type II certified",
        "risk_level": "medium",
        "notes": "Telephony provider backing Vapi AI outbound calls. Sees phone numbers.",
    },
    {
        "vendor_name": "Vapi",
        "category": "ai_telephony",
        "data_access_level": "limited",
        "soc2_status": "Review pending",
        "risk_level": "medium",
        "notes": "AI voice agent platform for outbound calls and voicemail drops.",
    },
    {
        "vendor_name": "OpenAI",
        "category": "ai_services",
        "data_access_level": "content",
        "soc2_status": "SOC 2 Type II certified",
        "risk_level": "medium",
        "notes": "LLM provider for AI agents. Processes conversation content; data not used for training per API ToS.",
    },
    {
        "vendor_name": "Salesforce",
        "category": "crm_integration",
        "data_access_level": "full",
        "soc2_status": "SOC 2 Type II certified",
        "risk_level": "low",
        "notes": "CRM data sync. Bidirectional sync of leads, loans, and contact data.",
    },
]


def seed_vendor_registry(db: Optional[Session] = None) -> int:
    """Seed vendor registry. Returns count of vendors upserted."""
    close_session = False
    if db is None:
        from db import SessionLocal
        db = SessionLocal()
        close_session = True

    try:
        count = 0
        today = date.today()
        next_review = date(today.year + 1, today.month, today.day)

        for vendor in VENDORS:
            db.execute(
                text("""
                    INSERT INTO soc2_vendor_registry (
                        vendor_name, category, data_access_level,
                        soc2_status, last_review_date, next_review_date,
                        risk_level, notes
                    ) VALUES (
                        :vendor_name, :category, :data_access_level,
                        :soc2_status, :last_review_date, :next_review_date,
                        :risk_level, :notes
                    )
                    ON CONFLICT (vendor_name) DO UPDATE SET
                        category = EXCLUDED.category,
                        data_access_level = EXCLUDED.data_access_level,
                        soc2_status = EXCLUDED.soc2_status,
                        risk_level = EXCLUDED.risk_level,
                        notes = EXCLUDED.notes,
                        updated_at = NOW()
                """),
                {
                    "vendor_name": vendor["vendor_name"],
                    "category": vendor["category"],
                    "data_access_level": vendor["data_access_level"],
                    "soc2_status": vendor["soc2_status"],
                    "last_review_date": today,
                    "next_review_date": next_review,
                    "risk_level": vendor["risk_level"],
                    "notes": vendor["notes"],
                }
            )
            count += 1

        db.commit()
        logger.info(f"Vendor registry seeded: {count} vendors upserted")
        return count

    except Exception as e:
        db.rollback()
        logger.error(f"Vendor registry seed failed: {e}")
        raise
    finally:
        if close_session:
            db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = seed_vendor_registry()
    print(f"Seeded {count} vendors")
