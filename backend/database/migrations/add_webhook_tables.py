"""
Database Migration: Add Webhook Tables
Enterprise Readiness - Domain 11

Creates tables for:
- webhook_subscriptions
- webhook_delivery_logs
- webhook_event_catalog

Run with: python -m database.migrations.add_webhook_tables
"""

from sqlalchemy import text
from database import get_db, engine
from database.models import WebhookSubscription, WebhookDeliveryLog, WebhookEventCatalog
from database.seed_webhook_events import seed_webhook_events
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Create webhook tables and seed event catalog"""

    try:
        # Create tables
        logger.info("Creating webhook tables...")
        WebhookSubscription.__table__.create(engine, checkfirst=True)
        WebhookDeliveryLog.__table__.create(engine, checkfirst=True)
        WebhookEventCatalog.__table__.create(engine, checkfirst=True)
        logger.info("✅ Webhook tables created successfully")

        # Seed webhook event catalog
        db = next(get_db())
        try:
            logger.info("Seeding webhook event catalog...")
            seed_webhook_events(db)
            logger.info("✅ Webhook event catalog seeded successfully")
        finally:
            db.close()

    except Exception as e:
        logger.error(f"❌ Migration failed: {str(e)}")
        raise


if __name__ == "__main__":
    run_migration()
    print("\n✅ Migration complete: Webhook tables added")
    print("Enterprise Domain 11 improvements:")
    print("  - API Key CRUD with database persistence (Check 11.4)")
    print("  - Per-API-key rate limiting (Check 11.5)")
    print("  - Webhook event catalog (Check 11.7)")
    print("  - Webhook retry with exponential backoff (Check 11.8)")
