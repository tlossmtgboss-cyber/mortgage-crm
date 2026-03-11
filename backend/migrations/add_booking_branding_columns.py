"""
Migration: Add booking branding columns to organizations table

Adds columns for organization-level public booking page branding:
- booking_slug (unique URL-safe identifier)
- booking_logo_url, booking_primary_color, booking_accent_color
- booking_tagline, booking_welcome_message
- booking_custom_css, booking_cover_image_url
- booking_show_testimonials, booking_testimonials

Run: python migrations/add_booking_branding_columns.py
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_migration():
    from sqlalchemy import create_engine, text

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)

    columns = [
        ("booking_slug", "VARCHAR UNIQUE"),
        ("booking_logo_url", "TEXT"),
        ("booking_primary_color", "VARCHAR(7) DEFAULT '#1a73e8'"),
        ("booking_accent_color", "VARCHAR(7) DEFAULT '#34a853'"),
        ("booking_tagline", "VARCHAR(200)"),
        ("booking_welcome_message", "TEXT"),
        ("booking_custom_css", "TEXT"),
        ("booking_cover_image_url", "TEXT"),
        ("booking_show_testimonials", "BOOLEAN DEFAULT FALSE"),
        ("booking_testimonials", "JSONB DEFAULT '[]'::jsonb"),
    ]

    with engine.connect() as conn:
        for col_name, col_type in columns:
            try:
                conn.execute(text(
                    f"ALTER TABLE organizations ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                logger.info(f"  Added column: organizations.{col_name}")
            except Exception as e:
                logger.warning(f"  Column {col_name}: {e}")

        # Add index on booking_slug for fast public lookups
        try:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_organizations_booking_slug "
                "ON organizations (booking_slug) WHERE booking_slug IS NOT NULL"
            ))
            logger.info("  Added unique index on booking_slug")
        except Exception as e:
            logger.warning(f"  booking_slug index: {e}")

        conn.commit()

    logger.info("Booking branding migration complete")
    return True


if __name__ == "__main__":
    run_migration()
