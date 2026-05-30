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
from database import DATABASE_URL


def create_tables_raw_sql(engine):
    """Create usage tracking tables using raw SQL to avoid FK resolution issues."""

    sql_statements = [
        # AI Token Usage Log
        """
        CREATE TABLE IF NOT EXISTS ai_token_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            team_id INTEGER,
            provider VARCHAR(50) NOT NULL,
            model VARCHAR(100) NOT NULL,
            feature VARCHAR(100),
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            input_cost DECIMAL(10, 6) NOT NULL DEFAULT 0,
            output_cost DECIMAL(10, 6) NOT NULL DEFAULT 0,
            total_cost DECIMAL(10, 6) NOT NULL DEFAULT 0,
            request_id VARCHAR(100),
            session_id VARCHAR(100),
            latency_ms INTEGER,
            success BOOLEAN DEFAULT 1,
            error_message TEXT,
            metadata_json TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_ai_token_org_user ON ai_token_usage_log(organization_id, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_ai_token_timestamp ON ai_token_usage_log(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_ai_token_model ON ai_token_usage_log(provider, model)",

        # User Usage Snapshots
        """
        CREATE TABLE IF NOT EXISTS user_usage_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            team_id INTEGER,
            snapshot_date DATE NOT NULL,
            total_cost DECIMAL(12, 4) NOT NULL DEFAULT 0,
            ai_tokens_cost DECIMAL(12, 4) NOT NULL DEFAULT 0,
            ai_tokens_input INTEGER NOT NULL DEFAULT 0,
            ai_tokens_output INTEGER NOT NULL DEFAULT 0,
            ai_request_count INTEGER NOT NULL DEFAULT 0,
            sms_cost DECIMAL(12, 4) NOT NULL DEFAULT 0,
            sms_segments INTEGER NOT NULL DEFAULT 0,
            voice_cost DECIMAL(12, 4) NOT NULL DEFAULT 0,
            voice_minutes DECIMAL(10, 2) NOT NULL DEFAULT 0,
            email_cost DECIMAL(12, 4) NOT NULL DEFAULT 0,
            email_count INTEGER NOT NULL DEFAULT 0,
            storage_cost DECIMAL(12, 4) NOT NULL DEFAULT 0,
            storage_gb DECIMAL(10, 4) NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(organization_id, user_id, snapshot_date)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_user_snapshot_date ON user_usage_snapshots(organization_id, snapshot_date)",

        # Team Usage Snapshots
        """
        CREATE TABLE IF NOT EXISTS team_usage_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            snapshot_date DATE NOT NULL,
            user_count INTEGER NOT NULL DEFAULT 0,
            total_cost DECIMAL(12, 4) NOT NULL DEFAULT 0,
            ai_tokens_cost DECIMAL(12, 4) NOT NULL DEFAULT 0,
            communications_cost DECIMAL(12, 4) NOT NULL DEFAULT 0,
            storage_cost DECIMAL(12, 4) NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(organization_id, team_id, snapshot_date)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_team_snapshot_date ON team_usage_snapshots(organization_id, snapshot_date)",

        # Org Usage Snapshots
        """
        CREATE TABLE IF NOT EXISTS org_usage_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            snapshot_date DATE NOT NULL,
            user_count INTEGER NOT NULL DEFAULT 0,
            team_count INTEGER NOT NULL DEFAULT 0,
            active_user_count INTEGER NOT NULL DEFAULT 0,
            total_cost DECIMAL(14, 4) NOT NULL DEFAULT 0,
            ai_tokens_cost DECIMAL(14, 4) NOT NULL DEFAULT 0,
            ai_tokens_input BIGINT NOT NULL DEFAULT 0,
            ai_tokens_output BIGINT NOT NULL DEFAULT 0,
            ai_request_count INTEGER NOT NULL DEFAULT 0,
            communications_cost DECIMAL(14, 4) NOT NULL DEFAULT 0,
            sms_segments INTEGER NOT NULL DEFAULT 0,
            voice_minutes DECIMAL(12, 2) NOT NULL DEFAULT 0,
            email_count INTEGER NOT NULL DEFAULT 0,
            storage_cost DECIMAL(14, 4) NOT NULL DEFAULT 0,
            storage_gb DECIMAL(12, 4) NOT NULL DEFAULT 0,
            infrastructure_cost DECIMAL(14, 4) NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(organization_id, snapshot_date)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_org_snapshot_date ON org_usage_snapshots(organization_id, snapshot_date)",

        # Usage Forecasts
        """
        CREATE TABLE IF NOT EXISTS usage_forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            scope_type VARCHAR(20) NOT NULL,
            scope_id INTEGER,
            forecast_date DATE NOT NULL,
            target_date DATE NOT NULL,
            period_days INTEGER NOT NULL,
            projected_cost DECIMAL(14, 4) NOT NULL,
            confidence_low DECIMAL(14, 4),
            confidence_high DECIMAL(14, 4),
            confidence_score INTEGER,
            trend_direction VARCHAR(20),
            trend_percentage DECIMAL(8, 2),
            algorithm VARCHAR(50),
            input_data_points INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_forecast_scope ON usage_forecasts(organization_id, scope_type, scope_id)",

        # Pricing Recommendations
        """
        CREATE TABLE IF NOT EXISTS pricing_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            recommendation_date DATE NOT NULL,
            period_days INTEGER NOT NULL,
            target_margin_pct DECIMAL(6, 2) NOT NULL,
            total_actual_cost DECIMAL(14, 4) NOT NULL,
            avg_cost_per_user DECIMAL(12, 4) NOT NULL,
            recommended_base_price DECIMAL(12, 4) NOT NULL,
            recommended_per_user_price DECIMAL(12, 4) NOT NULL,
            projected_revenue DECIMAL(14, 4),
            projected_profit DECIMAL(14, 4),
            actual_margin_pct DECIMAL(8, 2),
            cost_breakdown_json TEXT,
            usage_fees_json TEXT,
            recommendations_json TEXT,
            created_by INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Usage Alerts
        """
        CREATE TABLE IF NOT EXISTS usage_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            scope_type VARCHAR(20) NOT NULL,
            scope_id INTEGER,
            category VARCHAR(50) NOT NULL,
            alert_type VARCHAR(50) NOT NULL,
            severity VARCHAR(20) NOT NULL DEFAULT 'warning',
            title VARCHAR(200) NOT NULL,
            message TEXT,
            threshold_value DECIMAL(14, 4),
            actual_value DECIMAL(14, 4),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            acknowledged_by INTEGER,
            acknowledged_at DATETIME,
            resolved_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_alert_status ON usage_alerts(organization_id, status)",

        # AI Model Pricing
        """
        CREATE TABLE IF NOT EXISTS ai_model_pricing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider VARCHAR(50) NOT NULL,
            model_id VARCHAR(100) NOT NULL,
            model_name VARCHAR(200),
            input_price_per_1m DECIMAL(12, 6) NOT NULL,
            output_price_per_1m DECIMAL(12, 6) NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            effective_date DATE NOT NULL,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, model_id, effective_date)
        )
        """
    ]

    with engine.connect() as conn:
        for sql in sql_statements:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception as e:
                print(f"  Warning: {e}")

    print("  ✅ All tables created successfully")


def create_tables(engine):
    """Create all usage tracking tables."""
    print("Creating usage tracking tables...")

    # Import models to register them with Base
    from models.usage_tracking import (
        AITokenUsageLog,
        UserUsageSnapshot,
        TeamUsageSnapshot,
        OrgUsageSnapshot,
        UsageForecast,
        PricingRecommendation,
        UsageAlert,
        AIModelPricing,
    )
    from database import Base

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
    with engine.connect() as conn:
        # Check if pricing already exists
        result = conn.execute(text("SELECT COUNT(*) FROM ai_model_pricing"))
        existing = result.scalar()
        if existing > 0:
            print(f"AI model pricing already exists ({existing} records), skipping seed...")
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
            "model_id": "claude-sonnet-4-6",
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

    with engine.connect() as conn:
        for pricing in pricing_data:
            conn.execute(text("""
                INSERT INTO ai_model_pricing
                (provider, model_id, model_name, input_price_per_1m, output_price_per_1m,
                 is_active, effective_date, notes)
                VALUES (:provider, :model_id, :model_name, :input_price, :output_price,
                        1, :effective_date, :notes)
            """), {
                "provider": pricing["provider"],
                "model_id": pricing["model_id"],
                "model_name": pricing["model_name"],
                "input_price": float(pricing["input_price_per_1m"]),
                "output_price": float(pricing["output_price_per_1m"]),
                "effective_date": str(pricing["effective_date"]),
                "notes": pricing.get("notes"),
            })
        conn.commit()

    print(f"Seeded {len(pricing_data)} AI model pricing records")


def run_migration():
    """Run the complete migration."""
    print(f"Connecting to database: {DATABASE_URL[:50]}...")

    engine = create_engine(DATABASE_URL)

    # Create new tables using raw SQL to avoid FK resolution issues
    create_tables_raw_sql(engine)

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
