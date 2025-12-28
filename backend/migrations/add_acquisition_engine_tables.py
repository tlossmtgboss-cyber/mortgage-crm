"""
Database Migration: Create Acquisition Engine Tables

This script creates all tables required for the Client Acquisition Engine.
Run with: python -m migrations.add_acquisition_engine_tables

Features:
- Creates campaign blueprint and instance tables
- Creates acquisition event tracking table
- Creates lead temperature scoring table
- Creates campaign attribution table
- Idempotent - safe to run multiple times

Tables created:
- campaign_blueprints: Immutable campaign templates
- campaign_instances: Active campaign runtime state
- acquisition_events: Behavioral event tracking
- lead_temperatures: Computed lead scoring
- campaign_attributions: Revenue attribution
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from database import DATABASE_URL, Base
from models.acquisition_engine.campaign_models import (
    CampaignBlueprint,
    CampaignInstance,
    GoalType,
    CampaignStatus,
)
from models.acquisition_engine.event_models import (
    AcquisitionEvent,
    EventType,
)
from models.acquisition_engine.scoring_models import (
    LeadTemperature,
    CampaignAttribution,
    Temperature,
)


def check_tables_exist(engine) -> dict:
    """Check which tables already exist."""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    acquisition_tables = [
        'campaign_blueprints',
        'campaign_instances',
        'acquisition_events',
        'lead_temperatures',
        'campaign_attributions',
    ]

    return {table: table in existing_tables for table in acquisition_tables}


def create_tables(engine):
    """Create all acquisition engine tables."""
    print("Creating acquisition engine tables...")

    # Import models to register them with Base
    from models.acquisition_engine import campaign_models, event_models, scoring_models

    # List of tables to create (in order due to foreign keys)
    acquisition_tables = [
        CampaignBlueprint.__table__,
        CampaignInstance.__table__,
        AcquisitionEvent.__table__,
        LeadTemperature.__table__,
        CampaignAttribution.__table__,
    ]

    # Check which tables already exist
    table_status = check_tables_exist(engine)

    for table in acquisition_tables:
        table_name = table.name
        if table_status.get(table_name, False):
            print(f"  Table '{table_name}' already exists, skipping...")
        else:
            print(f"  Creating table '{table_name}'...")
            table.create(bind=engine, checkfirst=True)

    print("Acquisition engine tables created successfully!")


def seed_default_blueprints(engine):
    """Seed default campaign blueprints."""
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Check if blueprints already exist
        existing = session.execute(text("SELECT COUNT(*) FROM campaign_blueprints")).scalar()
        if existing > 0:
            print(f"  {existing} blueprints already exist, skipping seed...")
            return

        print("Seeding default campaign blueprints...")

        # Default blueprints for each goal type
        default_blueprints = [
            {
                "name": "Purchase Buyer Acquisition",
                "description": "Optimized for first-time and move-up home buyers",
                "version": "1.0.0",
                "goal_type": GoalType.PURCHASE_BUYERS.value,
                "is_active": True,
                "is_default": True,
                "speed_to_lead_config": {
                    "hot_lead_sla_seconds": 300,  # 5 minutes
                    "warm_lead_sla_seconds": 3600,  # 1 hour
                    "enable_sms": True,
                    "enable_email": True,
                    "enable_dialer": True,
                    "enable_push_notification": True,
                },
                "dialer_rules": {
                    "priority": "HIGH",
                    "max_attempts": 5,
                    "call_window_start": "09:00",
                    "call_window_end": "20:00",
                    "retry_delay_hours": 4,
                },
                "min_budget": 50,
                "max_budget": 1000,
                "recommended_budget": 100,
            },
            {
                "name": "Refinance Prospect Campaign",
                "description": "Target existing homeowners for refinance opportunities",
                "version": "1.0.0",
                "goal_type": GoalType.REFI_PROSPECTS.value,
                "is_active": True,
                "is_default": True,
                "speed_to_lead_config": {
                    "hot_lead_sla_seconds": 300,
                    "warm_lead_sla_seconds": 1800,  # 30 min - refi leads more urgent
                    "enable_sms": True,
                    "enable_email": True,
                    "enable_dialer": True,
                    "enable_push_notification": True,
                },
                "dialer_rules": {
                    "priority": "HIGH",
                    "max_attempts": 6,
                    "call_window_start": "09:00",
                    "call_window_end": "21:00",
                    "retry_delay_hours": 3,
                },
                "min_budget": 50,
                "max_budget": 1000,
                "recommended_budget": 150,
            },
            {
                "name": "Realtor Partner Outreach",
                "description": "Build relationships with real estate agents",
                "version": "1.0.0",
                "goal_type": GoalType.REALTOR_PARTNERS.value,
                "is_active": True,
                "is_default": True,
                "speed_to_lead_config": {
                    "hot_lead_sla_seconds": 600,  # 10 minutes
                    "warm_lead_sla_seconds": 7200,  # 2 hours
                    "enable_sms": True,
                    "enable_email": True,
                    "enable_dialer": True,
                    "enable_push_notification": True,
                },
                "dialer_rules": {
                    "priority": "MEDIUM",
                    "max_attempts": 4,
                    "call_window_start": "09:00",
                    "call_window_end": "18:00",
                    "retry_delay_hours": 24,
                },
                "min_budget": 100,
                "max_budget": 2000,
                "recommended_budget": 300,
            },
            {
                "name": "Past Client Refi Campaign",
                "description": "Re-engage past clients for refinance opportunities",
                "version": "1.0.0",
                "goal_type": GoalType.PAST_CLIENT_REFI.value,
                "is_active": True,
                "is_default": True,
                "speed_to_lead_config": {
                    "hot_lead_sla_seconds": 600,
                    "warm_lead_sla_seconds": 3600,
                    "enable_sms": True,
                    "enable_email": True,
                    "enable_dialer": True,
                    "enable_push_notification": True,
                },
                "dialer_rules": {
                    "priority": "MEDIUM",
                    "max_attempts": 3,
                    "call_window_start": "10:00",
                    "call_window_end": "19:00",
                    "retry_delay_hours": 48,
                },
                "min_budget": 25,
                "max_budget": 500,
                "recommended_budget": 75,
            },
            {
                "name": "First-Time Buyer Education",
                "description": "Educational content for first-time home buyers",
                "version": "1.0.0",
                "goal_type": GoalType.FIRST_TIME_BUYERS.value,
                "is_active": True,
                "is_default": True,
                "speed_to_lead_config": {
                    "hot_lead_sla_seconds": 300,
                    "warm_lead_sla_seconds": 3600,
                    "enable_sms": True,
                    "enable_email": True,
                    "enable_dialer": True,
                    "enable_push_notification": True,
                },
                "dialer_rules": {
                    "priority": "HIGH",
                    "max_attempts": 5,
                    "call_window_start": "10:00",
                    "call_window_end": "20:00",
                    "retry_delay_hours": 4,
                },
                "min_budget": 50,
                "max_budget": 750,
                "recommended_budget": 125,
            },
        ]

        import uuid
        for blueprint_data in default_blueprints:
            blueprint = CampaignBlueprint(
                id=uuid.uuid4(),
                **blueprint_data,
                sms_sequence_ids=[],
                email_sequence_ids=[],
            )
            session.add(blueprint)

        session.commit()
        print(f"  Seeded {len(default_blueprints)} default blueprints")

    except Exception as e:
        session.rollback()
        print(f"  Error seeding blueprints: {e}")
        raise
    finally:
        session.close()


def create_indexes(engine):
    """Create additional indexes for performance."""
    print("Creating additional indexes...")

    indexes = [
        # Events indexes
        "CREATE INDEX IF NOT EXISTS idx_events_org_type ON acquisition_events(organization_id, event_type)",
        "CREATE INDEX IF NOT EXISTS idx_events_lead_type ON acquisition_events(lead_id, event_type) WHERE lead_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_events_anon_visitor ON acquisition_events(anonymous_visitor_id) WHERE anonymous_visitor_id IS NOT NULL",

        # Temperature indexes
        "CREATE INDEX IF NOT EXISTS idx_temp_hot ON lead_temperatures(temperature) WHERE temperature = 'HOT'",
        "CREATE INDEX IF NOT EXISTS idx_temp_score_desc ON lead_temperatures(score DESC)",

        # Campaign instance indexes
        "CREATE INDEX IF NOT EXISTS idx_campaign_active ON campaign_instances(status) WHERE status = 'ACTIVE'",
        "CREATE INDEX IF NOT EXISTS idx_campaign_user ON campaign_instances(user_id, status)",

        # Attribution indexes
        "CREATE INDEX IF NOT EXISTS idx_attr_funded ON campaign_attributions(is_funded) WHERE is_funded = true",
    ]

    with engine.connect() as conn:
        for idx_sql in indexes:
            try:
                conn.execute(text(idx_sql))
                conn.commit()
            except Exception as e:
                # Index might not work on SQLite, that's OK
                if "syntax error" not in str(e).lower():
                    print(f"  Note: {e}")


def run_migration():
    """Run the complete migration."""
    print("=" * 60)
    print("Acquisition Engine Migration")
    print("=" * 60)
    print(f"Database: {DATABASE_URL[:50]}...")
    print()

    # Create engine
    if DATABASE_URL.startswith("sqlite"):
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(DATABASE_URL)

    # Check current state
    print("Checking existing tables...")
    table_status = check_tables_exist(engine)
    for table, exists in table_status.items():
        status = "EXISTS" if exists else "MISSING"
        print(f"  {table}: {status}")
    print()

    # Create tables
    create_tables(engine)
    print()

    # Seed default blueprints
    seed_default_blueprints(engine)
    print()

    # Create indexes (PostgreSQL only)
    if not DATABASE_URL.startswith("sqlite"):
        create_indexes(engine)
        print()

    print("=" * 60)
    print("Migration complete!")
    print("=" * 60)


if __name__ == "__main__":
    run_migration()
