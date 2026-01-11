"""
Database Migration: Add Usage Intelligence & Cost Tracking Tables

This script creates all tables required for the Usage Intelligence system.
Run with: python -m migrations.add_usage_tracking_tables

Features:
- Creates 8 new tables for usage tracking and cost projection
- Seeds default AI model pricing
- Adds user_id and team_id columns to service_usage_records
- Idempotent - safe to run multiple times
"""

import os
import sys
from datetime import datetime, date
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from database import DATABASE_URL, Base
from models.usage_tracking import (
    AITokenUsageLog,
    UserUsageSnapshot,
    TeamUsageSnapshot,
    OrgUsageSnapshot,
    UsageForecast,
    PricingRecommendation,
    UsageAlert,
    AIModelPricing
)


def create_tables(engine):
    """Create all usage tracking tables."""
    print("Creating usage tracking tables...")

    # Import models to register them with Base
    from models import usage_tracking

    # List of tables to create
    usage_tables = [
        AITokenUsageLog.__table__,
        UserUsageSnapshot.__table__,
        TeamUsageSnapshot.__table__,
        OrgUsageSnapshot.__table__,
        UsageForecast.__table__,
        PricingRecommendation.__table__,
        UsageAlert.__table__,
        AIModelPricing.__table__,
    ]

    # Create only usage tracking tables
    Base.metadata.create_all(bind=engine, tables=usage_tables)

    print("Usage tracking tables created successfully!")


def add_user_team_columns_to_service_usage(engine):
    """Add user_id and team_id columns to service_usage_records if they don't exist."""
    print("Checking service_usage_records for user_id/team_id columns...")

    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('service_usage_records')]

    with engine.connect() as conn:
        # Add user_id if not exists
        if 'user_id' not in columns:
            print("  Adding user_id column...")
            conn.execute(text("""
                ALTER TABLE service_usage_records
                ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_usage_user
                ON service_usage_records(user_id)
            """))
            conn.commit()
            print("  user_id column added.")
        else:
            print("  user_id column already exists.")

        # Add team_id if not exists
        if 'team_id' not in columns:
            print("  Adding team_id column...")
            conn.execute(text("""
                ALTER TABLE service_usage_records
                ADD COLUMN team_id INTEGER
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_usage_team
                ON service_usage_records(team_id)
            """))
            conn.commit()
            print("  team_id column added.")
        else:
            print("  team_id column already exists.")

        # Add request_id if not exists (for correlation with AITokenUsageLog)
        if 'request_id' not in columns:
            print("  Adding request_id column...")
            conn.execute(text("""
                ALTER TABLE service_usage_records
                ADD COLUMN request_id VARCHAR(100)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_usage_request
                ON service_usage_records(request_id)
            """))
            conn.commit()
            print("  request_id column added.")
        else:
            print("  request_id column already exists.")

    print("service_usage_records columns updated!")


def seed_ai_model_pricing(engine):
    """Seed default AI model pricing based on current provider rates."""
    session = Session(bind=engine)

    # Check if pricing already exists
    existing = session.query(AIModelPricing).count()
    if existing > 0:
        print(f"AI model pricing already exists ({existing} records), skipping seed...")
        session.close()
        return

    print("Seeding AI model pricing...")

    today = date.today()

    # Current AI model pricing (as of 2025)
    pricing_data = [
        # Anthropic Claude models
        {
            "provider": "anthropic",
            "model_id": "claude-opus-4-5-20251101",
            "model_name": "Claude Opus 4.5",
            "input_price_per_1m": Decimal("75.00"),
            "output_price_per_1m": Decimal("150.00"),
            "max_context_tokens": 200000,
            "max_output_tokens": 32000,
            "effective_date": today,
        },
        {
            "provider": "anthropic",
            "model_id": "claude-sonnet-4-20250514",
            "model_name": "Claude Sonnet 4",
            "input_price_per_1m": Decimal("3.00"),
            "output_price_per_1m": Decimal("15.00"),
            "max_context_tokens": 200000,
            "max_output_tokens": 64000,
            "effective_date": today,
        },
        {
            "provider": "anthropic",
            "model_id": "claude-3-5-sonnet-20241022",
            "model_name": "Claude 3.5 Sonnet",
            "input_price_per_1m": Decimal("3.00"),
            "output_price_per_1m": Decimal("15.00"),
            "max_context_tokens": 200000,
            "max_output_tokens": 8192,
            "effective_date": today,
        },
        {
            "provider": "anthropic",
            "model_id": "claude-3-5-haiku-20241022",
            "model_name": "Claude 3.5 Haiku",
            "input_price_per_1m": Decimal("0.80"),
            "output_price_per_1m": Decimal("4.00"),
            "max_context_tokens": 200000,
            "max_output_tokens": 8192,
            "effective_date": today,
        },
        # OpenAI GPT models
        {
            "provider": "openai",
            "model_id": "gpt-4o",
            "model_name": "GPT-4o",
            "input_price_per_1m": Decimal("2.50"),
            "output_price_per_1m": Decimal("10.00"),
            "max_context_tokens": 128000,
            "max_output_tokens": 16384,
            "effective_date": today,
        },
        {
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "model_name": "GPT-4o Mini",
            "input_price_per_1m": Decimal("0.15"),
            "output_price_per_1m": Decimal("0.60"),
            "max_context_tokens": 128000,
            "max_output_tokens": 16384,
            "effective_date": today,
        },
        {
            "provider": "openai",
            "model_id": "gpt-4-turbo",
            "model_name": "GPT-4 Turbo",
            "input_price_per_1m": Decimal("10.00"),
            "output_price_per_1m": Decimal("30.00"),
            "max_context_tokens": 128000,
            "max_output_tokens": 4096,
            "effective_date": today,
        },
        {
            "provider": "openai",
            "model_id": "o1",
            "model_name": "OpenAI o1",
            "input_price_per_1m": Decimal("15.00"),
            "output_price_per_1m": Decimal("60.00"),
            "max_context_tokens": 200000,
            "max_output_tokens": 100000,
            "effective_date": today,
        },
        {
            "provider": "openai",
            "model_id": "o1-mini",
            "model_name": "OpenAI o1-mini",
            "input_price_per_1m": Decimal("1.10"),
            "output_price_per_1m": Decimal("4.40"),
            "max_context_tokens": 128000,
            "max_output_tokens": 65536,
            "effective_date": today,
        },
        # Deepgram (Speech-to-Text)
        {
            "provider": "deepgram",
            "model_id": "nova-2",
            "model_name": "Deepgram Nova 2",
            "input_price_per_1m": Decimal("0.0043"),  # Per second, adjusted to minute
            "output_price_per_1m": Decimal("0.0"),  # STT doesn't have output tokens
            "effective_date": today,
            "notes": "Price is per audio minute, not tokens",
        },
        # ElevenLabs (Text-to-Speech)
        {
            "provider": "eleven_labs",
            "model_id": "eleven_multilingual_v2",
            "model_name": "ElevenLabs Multilingual v2",
            "input_price_per_1m": Decimal("0.24"),  # Per 1000 characters
            "output_price_per_1m": Decimal("0.0"),
            "effective_date": today,
            "notes": "Price is per 1000 characters",
        },
    ]

    for pricing in pricing_data:
        # Calculate per-token prices
        input_per_token = pricing["input_price_per_1m"] / Decimal("1000000")
        output_per_token = pricing["output_price_per_1m"] / Decimal("1000000")

        model_pricing = AIModelPricing(
            provider=pricing["provider"],
            model_id=pricing["model_id"],
            model_name=pricing["model_name"],
            input_price_per_1m=pricing["input_price_per_1m"],
            output_price_per_1m=pricing["output_price_per_1m"],
            input_price_per_token=input_per_token,
            output_price_per_token=output_per_token,
            max_context_tokens=pricing.get("max_context_tokens"),
            max_output_tokens=pricing.get("max_output_tokens"),
            effective_date=pricing["effective_date"],
            is_active=True,
            notes=pricing.get("notes"),
        )
        session.add(model_pricing)

    session.commit()
    print(f"Seeded {len(pricing_data)} AI model pricing records")
    session.close()


def run_migration():
    """Run the complete migration."""
    print(f"Connecting to database: {DATABASE_URL[:50]}...")

    engine = create_engine(DATABASE_URL)

    # Create new tables
    create_tables(engine)

    # Add columns to existing service_usage_records table
    add_user_team_columns_to_service_usage(engine)

    # Seed AI model pricing
    seed_ai_model_pricing(engine)

    print("\n" + "=" * 60)
    print("Usage Intelligence migration complete!")
    print("=" * 60)
    print("\nTables created:")
    print("  - ai_token_usage_log")
    print("  - user_usage_snapshots")
    print("  - team_usage_snapshots")
    print("  - org_usage_snapshots")
    print("  - usage_forecasts")
    print("  - pricing_recommendations")
    print("  - usage_alerts")
    print("  - ai_model_pricing")
    print("\nColumns added to service_usage_records:")
    print("  - user_id (FK to users)")
    print("  - team_id")
    print("  - request_id")
    print("=" * 60)


if __name__ == "__main__":
    run_migration()
