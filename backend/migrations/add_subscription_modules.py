"""
Migration: Add Subscription Modules System

Creates tables for modular subscription system where organizations
can select premium add-on modules on top of a base package.

Run with: DATABASE_URL=... python -m migrations.add_subscription_modules
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Module definitions
SUBSCRIPTION_MODULES = [
    # Base Package (always included)
    {
        'module_key': 'base',
        'module_name': 'Core CRM',
        'description': 'Lead Management, Active Loans, MUM Clients, Tasks, Reconciliation, Smart Docs, Calendar, Basic Dashboard',
        'category': 'base',
        'monthly_price': 99.00,
        'annual_price': 990.00,
        'included_features': ['leads', 'active_loans', 'mum_clients', 'tasks', 'reconciliation', 'smart_docs', 'calendar', 'basic_dashboard'],
        'gated_routes': ['/leads', '/loans', '/portfolio', '/tasks', '/reconciliation', '/smart-docs', '/calendar', '/dashboard'],
        'sort_order': 0,
        'icon': 'LayoutDashboard'
    },
    # Premium Add-On Modules
    {
        'module_key': 'ai_assistant',
        'module_name': 'AI Assistant',
        'description': 'AI Chat, AI Underwriter, Email Training, Hallucination Monitoring',
        'category': 'premium',
        'monthly_price': 149.00,
        'annual_price': 1490.00,
        'included_features': ['ai_chat', 'ai_underwriter', 'email_training', 'hallucination_monitoring'],
        'gated_routes': ['/ai-underwriter', '/ai-chat', '/email-training', '/settings/ai'],
        'sort_order': 1,
        'icon': 'Bot'
    },
    {
        'module_key': 'partner_portals',
        'module_name': 'Partner Portals',
        'description': 'Realtor Portal, Listing Agent Portal, Client PURL Portals',
        'category': 'premium',
        'monthly_price': 99.00,
        'annual_price': 990.00,
        'included_features': ['realtor_portal', 'listing_portal', 'purl_portals', 'partner_management'],
        'gated_routes': ['/referral-partners', '/portals', '/purl', '/listing-portal'],
        'sort_order': 2,
        'icon': 'Users'
    },
    {
        'module_key': 'video_os',
        'module_name': 'Video OS',
        'description': 'Video creation, AI avatars, content library',
        'category': 'premium',
        'monthly_price': 79.00,
        'annual_price': 790.00,
        'included_features': ['video_creation', 'ai_avatars', 'video_library', 'video_templates'],
        'gated_routes': ['/video-os', '/marketing/videos'],
        'sort_order': 3,
        'icon': 'Video'
    },
    {
        'module_key': 'recruiting_suite',
        'module_name': 'Recruiting Suite',
        'description': 'Candidate management, assessments, DISC profiles, recruiting portal',
        'category': 'premium',
        'monthly_price': 199.00,
        'annual_price': 1990.00,
        'included_features': ['recruiting', 'disc_assessment', 'recruit_portal', 'candidate_grading', 'interview_scheduling'],
        'gated_routes': ['/master-manager/recruiting', '/recruiting', '/partner-recruiting'],
        'sort_order': 4,
        'icon': 'UserPlus'
    },
    {
        'module_key': 'conversation_intelligence',
        'module_name': 'Conversation Intelligence',
        'description': 'Call recording, QA scoring, coaching, transcription',
        'category': 'premium',
        'monthly_price': 129.00,
        'annual_price': 1290.00,
        'included_features': ['call_recording', 'qa_scoring', 'coaching', 'transcription', 'sentiment_analysis'],
        'gated_routes': ['/conversation-intelligence', '/call-recordings', '/qa-dashboard'],
        'sort_order': 5,
        'icon': 'Phone'
    },
    {
        'module_key': 'advanced_analytics',
        'module_name': 'Advanced Analytics',
        'description': 'Decision Lab, Confidence Engine, Profitability analysis, Market insights',
        'category': 'premium',
        'monthly_price': 149.00,
        'annual_price': 1490.00,
        'included_features': ['decision_lab', 'confidence_engine', 'profitability', 'market_insights'],
        'gated_routes': ['/decision-lab', '/profitability', '/market', '/analytics'],
        'sort_order': 6,
        'icon': 'TrendingUp'
    },
    {
        'module_key': 'integrations',
        'module_name': 'Integrations',
        'description': 'Salesforce, HubSpot, Encompass sync and more',
        'category': 'premium',
        'monthly_price': 79.00,
        'annual_price': 790.00,
        'included_features': ['salesforce_sync', 'hubspot_sync', 'encompass_sync', 'api_access'],
        'gated_routes': ['/integrations', '/settings/integrations'],
        'sort_order': 7,
        'icon': 'Plug'
    },
]


def run_migration():
    """Run the subscription modules migration."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print("Starting subscription modules migration...")

        # Create subscription_modules table
        print("Creating subscription_modules table...")
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS subscription_modules (
                id SERIAL PRIMARY KEY,
                module_key VARCHAR(100) UNIQUE NOT NULL,
                module_name VARCHAR(255) NOT NULL,
                description TEXT,
                category VARCHAR(50) NOT NULL DEFAULT 'premium',
                icon VARCHAR(50) DEFAULT 'Settings',
                monthly_price NUMERIC(10, 2) DEFAULT 0,
                annual_price NUMERIC(10, 2) DEFAULT 0,
                stripe_price_id_monthly VARCHAR(255),
                stripe_price_id_annual VARCHAR(255),
                included_features JSONB DEFAULT '[]',
                gated_routes JSONB DEFAULT '[]',
                sort_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # Create organization_modules table
        print("Creating organization_modules table...")
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS organization_modules (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE NOT NULL,
                module_key VARCHAR(100) NOT NULL,
                is_enabled BOOLEAN DEFAULT FALSE,
                enabled_at TIMESTAMP,
                enabled_by INTEGER REFERENCES users(id),
                stripe_subscription_item_id VARCHAR(255),
                billing_status VARCHAR(20) DEFAULT 'active',
                is_trial BOOLEAN DEFAULT FALSE,
                trial_ends_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(organization_id, module_key)
            )
        """))

        # Create index for faster lookups
        print("Creating indexes...")
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_org_modules_org_id
            ON organization_modules(organization_id)
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_org_modules_module_key
            ON organization_modules(module_key)
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_org_modules_enabled
            ON organization_modules(organization_id, is_enabled)
        """))

        # Add subscription_type column to organizations if not exists
        print("Updating organizations table...")
        session.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'organizations' AND column_name = 'subscription_type'
                ) THEN
                    ALTER TABLE organizations ADD COLUMN subscription_type VARCHAR(20) DEFAULT 'modular';
                END IF;
            END $$;
        """))

        session.commit()
        print("Tables created successfully!")

        # Seed module definitions
        print("\nSeeding module definitions...")
        import json

        for module in SUBSCRIPTION_MODULES:
            # Check if module already exists
            existing = session.execute(
                text("SELECT id FROM subscription_modules WHERE module_key = :key"),
                {"key": module['module_key']}
            ).fetchone()

            if existing:
                print(f"  Updating module: {module['module_key']}")
                session.execute(text("""
                    UPDATE subscription_modules SET
                        module_name = :module_name,
                        description = :description,
                        category = :category,
                        icon = :icon,
                        monthly_price = :monthly_price,
                        annual_price = :annual_price,
                        included_features = :included_features,
                        gated_routes = :gated_routes,
                        sort_order = :sort_order,
                        updated_at = NOW()
                    WHERE module_key = :module_key
                """), {
                    'module_key': module['module_key'],
                    'module_name': module['module_name'],
                    'description': module['description'],
                    'category': module['category'],
                    'icon': module.get('icon', 'Settings'),
                    'monthly_price': module['monthly_price'],
                    'annual_price': module['annual_price'],
                    'included_features': json.dumps(module['included_features']),
                    'gated_routes': json.dumps(module['gated_routes']),
                    'sort_order': module['sort_order']
                })
            else:
                print(f"  Creating module: {module['module_key']}")
                session.execute(text("""
                    INSERT INTO subscription_modules
                    (module_key, module_name, description, category, icon, monthly_price, annual_price,
                     included_features, gated_routes, sort_order)
                    VALUES
                    (:module_key, :module_name, :description, :category, :icon, :monthly_price, :annual_price,
                     :included_features, :gated_routes, :sort_order)
                """), {
                    'module_key': module['module_key'],
                    'module_name': module['module_name'],
                    'description': module['description'],
                    'category': module['category'],
                    'icon': module.get('icon', 'Settings'),
                    'monthly_price': module['monthly_price'],
                    'annual_price': module['annual_price'],
                    'included_features': json.dumps(module['included_features']),
                    'gated_routes': json.dumps(module['gated_routes']),
                    'sort_order': module['sort_order']
                })

        session.commit()
        print("Module definitions seeded successfully!")

        # Enable base module for all existing organizations
        print("\nEnabling base module for existing organizations...")
        session.execute(text("""
            INSERT INTO organization_modules (organization_id, module_key, is_enabled, enabled_at)
            SELECT id, 'base', TRUE, NOW()
            FROM organizations
            WHERE NOT EXISTS (
                SELECT 1 FROM organization_modules
                WHERE organization_modules.organization_id = organizations.id
                AND organization_modules.module_key = 'base'
            )
        """))
        session.commit()

        # Count results
        module_count = session.execute(text("SELECT COUNT(*) FROM subscription_modules")).scalar()
        org_module_count = session.execute(text("SELECT COUNT(*) FROM organization_modules")).scalar()

        print(f"\n=== Migration Complete ===")
        print(f"Total modules defined: {module_count}")
        print(f"Organization module assignments: {org_module_count}")

    except Exception as e:
        session.rollback()
        print(f"ERROR: Migration failed - {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run_migration()
