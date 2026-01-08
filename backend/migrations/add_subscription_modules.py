"""
Subscription Modules Migration

Creates tables for the modular subscription system:
- subscription_modules: Defines available modules and pricing
- organization_modules: Tracks which modules each org has enabled
"""

import os
import sys
import json
import logging
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)


# Module definitions with pricing and gated routes
MODULE_DEFINITIONS = [
    {
        "module_key": "base",
        "module_name": "Base Package",
        "description": "Core CRM functionality including leads, loans, portfolio, tasks, and scheduling",
        "category": "base",
        "monthly_price": 99.00,
        "annual_price": 990.00,
        "included_features": [
            "Lead Management",
            "Active Loan Management", 
            "MUM Clients (Portfolio)",
            "Tasks & Workflows",
            "Reconciliation",
            "Smart Docs",
            "Calendar/Scheduling",
            "Basic Dashboard"
        ],
        "gated_routes": [],
        "sort_order": 0,
    },
    {
        "module_key": "ai_assistant",
        "module_name": "AI Assistant",
        "description": "AI-powered chat, underwriting assistance, and email training",
        "category": "premium",
        "monthly_price": 149.00,
        "annual_price": 1490.00,
        "included_features": [
            "AI Chat Assistant",
            "AI Underwriter",
            "Email Training & Review",
            "AI-Powered Responses"
        ],
        "gated_routes": ["/ai-underwriter", "/ai-chat", "/ai-email-training"],
        "sort_order": 1,
    },
    {
        "module_key": "partner_portals",
        "module_name": "Partner Portals",
        "description": "Realtor portal, listing portal, and personalized client URLs",
        "category": "premium",
        "monthly_price": 99.00,
        "annual_price": 990.00,
        "included_features": [
            "Realtor Portal",
            "Listing Agent Portal",
            "PURL (Personal URLs)",
            "Partner Management"
        ],
        "gated_routes": ["/referral-partners", "/realtor-portal", "/listing-portal", "/purl"],
        "sort_order": 2,
    },
    {
        "module_key": "video_os",
        "module_name": "Video OS",
        "description": "AI video creation with avatars for marketing and client communication",
        "category": "premium",
        "monthly_price": 79.00,
        "annual_price": 790.00,
        "included_features": [
            "AI Video Creation",
            "Custom Avatars",
            "Video Templates",
            "Social Media Integration"
        ],
        "gated_routes": ["/video-os"],
        "sort_order": 3,
    },
    {
        "module_key": "recruiting_suite",
        "module_name": "Recruiting Suite",
        "description": "Full recruiting pipeline with DISC assessments and candidate management",
        "category": "premium",
        "monthly_price": 199.00,
        "annual_price": 1990.00,
        "included_features": [
            "Candidate Pipeline",
            "DISC Assessments",
            "Interview Scheduling",
            "Offer Management",
            "Recruiting Analytics"
        ],
        "gated_routes": ["/master-manager/recruiting", "/recruiting"],
        "sort_order": 4,
    },
    {
        "module_key": "conversation_intelligence",
        "module_name": "Conversation Intelligence",
        "description": "Call recording, transcription, QA scoring, and coaching tools",
        "category": "premium",
        "monthly_price": 129.00,
        "annual_price": 1290.00,
        "included_features": [
            "Call Recording",
            "AI Transcription",
            "QA Scoring",
            "Coaching Dashboard",
            "Real-time Assist"
        ],
        "gated_routes": ["/conversation-intelligence"],
        "sort_order": 5,
    },
    {
        "module_key": "advanced_analytics",
        "module_name": "Advanced Analytics",
        "description": "Decision Lab, profitability analysis, and market insights",
        "category": "premium",
        "monthly_price": 149.00,
        "annual_price": 1490.00,
        "included_features": [
            "Decision Lab",
            "Profitability Calculator",
            "Market Analysis",
            "Production Predictor",
            "Deal Alerts"
        ],
        "gated_routes": ["/profitability", "/market", "/decision-lab"],
        "sort_order": 6,
    },
    {
        "module_key": "integrations",
        "module_name": "Integrations",
        "description": "Connect with Salesforce, HubSpot, Encompass, and other platforms",
        "category": "premium",
        "monthly_price": 79.00,
        "annual_price": 790.00,
        "included_features": [
            "Salesforce Sync",
            "HubSpot Integration",
            "Encompass Connection",
            "Custom Webhooks"
        ],
        "gated_routes": ["/integrations", "/settings/integrations"],
        "sort_order": 7,
    },
]


def run_migration(engine):
    """Run the subscription modules migration."""
    
    # Detect database type
    db_url = str(engine.url)
    is_sqlite = 'sqlite' in db_url
    is_postgres = 'postgresql' in db_url
    
    logger.info(f"Running subscription modules migration (SQLite: {is_sqlite}, PostgreSQL: {is_postgres})")
    
    with engine.connect() as conn:
        # Create subscription_modules table
        if is_postgres:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS subscription_modules (
                    id SERIAL PRIMARY KEY,
                    module_key VARCHAR(100) UNIQUE NOT NULL,
                    module_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    category VARCHAR(50) NOT NULL DEFAULT 'premium',
                    monthly_price NUMERIC(10, 2) DEFAULT 0,
                    annual_price NUMERIC(10, 2) DEFAULT 0,
                    stripe_price_id_monthly VARCHAR(255),
                    stripe_price_id_annual VARCHAR(255),
                    included_features JSONB DEFAULT '[]',
                    gated_routes JSONB DEFAULT '[]',
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            
            # Create indexes
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sub_modules_key ON subscription_modules(module_key)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sub_modules_category ON subscription_modules(category)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sub_modules_active ON subscription_modules(is_active)"))
            
            # Create organization_modules table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS organization_modules (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    module_key VARCHAR(100) NOT NULL,
                    is_enabled BOOLEAN DEFAULT FALSE,
                    enabled_at TIMESTAMP WITH TIME ZONE,
                    disabled_at TIMESTAMP WITH TIME ZONE,
                    stripe_subscription_item_id VARCHAR(255),
                    is_trial BOOLEAN DEFAULT FALSE,
                    trial_ends_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(organization_id, module_key)
                )
            """))
            
            # Create indexes for organization_modules
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_org_modules_org_id ON organization_modules(organization_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_org_modules_enabled ON organization_modules(is_enabled)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_org_modules_trial ON organization_modules(is_trial, trial_ends_at)"))
            
        else:
            # SQLite version
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS subscription_modules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module_key VARCHAR(100) UNIQUE NOT NULL,
                    module_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    category VARCHAR(50) NOT NULL DEFAULT 'premium',
                    monthly_price REAL DEFAULT 0,
                    annual_price REAL DEFAULT 0,
                    stripe_price_id_monthly VARCHAR(255),
                    stripe_price_id_annual VARCHAR(255),
                    included_features TEXT DEFAULT '[]',
                    gated_routes TEXT DEFAULT '[]',
                    sort_order INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS organization_modules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER NOT NULL,
                    module_key VARCHAR(100) NOT NULL,
                    is_enabled INTEGER DEFAULT 0,
                    enabled_at TIMESTAMP,
                    disabled_at TIMESTAMP,
                    stripe_subscription_item_id VARCHAR(255),
                    is_trial INTEGER DEFAULT 0,
                    trial_ends_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(organization_id, module_key)
                )
            """))
        
        conn.commit()
        logger.info("Tables created successfully!")
        
        # Seed module definitions
        logger.info("Seeding module definitions...")
        
        for module in MODULE_DEFINITIONS:
            # Check if module already exists
            existing = conn.execute(
                text("SELECT id FROM subscription_modules WHERE module_key = :key"),
                {"key": module["module_key"]}
            ).fetchone()
            
            if existing:
                logger.info(f"  - {module['module_name']} already exists, skipping...")
                continue
            
            if is_postgres:
                conn.execute(text("""
                    INSERT INTO subscription_modules
                    (module_key, module_name, description, category, monthly_price,
                     annual_price, included_features, gated_routes, sort_order)
                    VALUES
                    (:module_key, :module_name, :description, :category, :monthly_price,
                     :annual_price, :included_features::jsonb, :gated_routes::jsonb, :sort_order)
                """), {
                    "module_key": module["module_key"],
                    "module_name": module["module_name"],
                    "description": module["description"],
                    "category": module["category"],
                    "monthly_price": module["monthly_price"],
                    "annual_price": module["annual_price"],
                    "included_features": json.dumps(module["included_features"]),
                    "gated_routes": json.dumps(module["gated_routes"]),
                    "sort_order": module["sort_order"],
                })
            else:
                conn.execute(text("""
                    INSERT INTO subscription_modules
                    (module_key, module_name, description, category, monthly_price,
                     annual_price, included_features, gated_routes, sort_order)
                    VALUES
                    (:module_key, :module_name, :description, :category, :monthly_price,
                     :annual_price, :included_features, :gated_routes, :sort_order)
                """), {
                    "module_key": module["module_key"],
                    "module_name": module["module_name"],
                    "description": module["description"],
                    "category": module["category"],
                    "monthly_price": module["monthly_price"],
                    "annual_price": module["annual_price"],
                    "included_features": json.dumps(module["included_features"]),
                    "gated_routes": json.dumps(module["gated_routes"]),
                    "sort_order": module["sort_order"],
                })
            
            logger.info(f"  + Added {module['module_name']} (${module['monthly_price']}/mo)")
        
        conn.commit()
        logger.info("Module definitions seeded successfully!")
        
        # Verify
        count = conn.execute(text("SELECT COUNT(*) FROM subscription_modules")).scalar()
        logger.info(f"Total modules in database: {count}")
        
        return True


# Allow running directly
if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from sqlalchemy import create_engine
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    logging.basicConfig(level=logging.INFO)
    engine = create_engine(database_url)
    success = run_migration(engine)
    sys.exit(0 if success else 1)
