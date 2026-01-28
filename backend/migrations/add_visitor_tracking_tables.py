"""
Migration: Add Visitor Tracking Tables
======================================
Creates tables for tracking website visitors and auto-creating leads.
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

MIGRATION_SQL = """
-- Website Visitors Table
CREATE TABLE IF NOT EXISTS website_visitors (
    id SERIAL PRIMARY KEY,
    visitor_id VARCHAR(64) NOT NULL UNIQUE,
    visitor_hash VARCHAR(64),
    ip_address VARCHAR(45),
    user_agent TEXT,
    device_type VARCHAR(20),
    browser VARCHAR(50),
    os VARCHAR(50),
    first_visit_at TIMESTAMP WITH TIME ZONE,
    last_visit_at TIMESTAMP WITH TIME ZONE,
    visit_count INTEGER DEFAULT 1,
    first_page_url TEXT,
    first_referrer TEXT,
    utm_source VARCHAR(255),
    utm_medium VARCHAR(255),
    utm_campaign VARCHAR(255),
    utm_term VARCHAR(255),
    utm_content VARCHAR(255),
    screen_width INTEGER,
    screen_height INTEGER,
    timezone VARCHAR(100),
    language VARCHAR(20),
    lead_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_website_visitors_visitor_id ON website_visitors(visitor_id);
CREATE INDEX IF NOT EXISTS idx_website_visitors_ip ON website_visitors(ip_address);
CREATE INDEX IF NOT EXISTS idx_website_visitors_last_visit ON website_visitors(last_visit_at);

-- Website Page Views Table
CREATE TABLE IF NOT EXISTS website_page_views (
    id SERIAL PRIMARY KEY,
    visitor_id VARCHAR(64) NOT NULL,
    page_url TEXT NOT NULL,
    page_title VARCHAR(500),
    referrer TEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,
    viewed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_page_views_visitor ON website_page_views(visitor_id);
CREATE INDEX IF NOT EXISTS idx_page_views_viewed_at ON website_page_views(viewed_at);
CREATE INDEX IF NOT EXISTS idx_page_views_page_url ON website_page_views(page_url);

-- Website Visitor Leads Table (for Admin CRM)
CREATE TABLE IF NOT EXISTS website_visitor_leads (
    id SERIAL PRIMARY KEY,
    visitor_id VARCHAR(64) NOT NULL UNIQUE,
    ip_address VARCHAR(45),
    source VARCHAR(255),
    status VARCHAR(50) DEFAULT 'anonymous',
    first_seen_at TIMESTAMP WITH TIME ZONE,
    last_seen_at TIMESTAMP WITH TIME ZONE,
    page_views INTEGER DEFAULT 0,
    utm_source VARCHAR(255),
    utm_medium VARCHAR(255),
    utm_campaign VARCHAR(255),
    device_type VARCHAR(20),
    browser VARCHAR(50),
    os VARCHAR(50),
    email VARCHAR(255),
    name VARCHAR(255),
    phone VARCHAR(50),
    company VARCHAR(255),
    notes TEXT,
    converted_lead_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_visitor_leads_visitor_id ON website_visitor_leads(visitor_id);
CREATE INDEX IF NOT EXISTS idx_visitor_leads_status ON website_visitor_leads(status);
CREATE INDEX IF NOT EXISTS idx_visitor_leads_last_seen ON website_visitor_leads(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_visitor_leads_email ON website_visitor_leads(email);
"""


def run_migration():
    """Run the migration to add visitor tracking tables."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            # Execute each statement separately
            for statement in MIGRATION_SQL.split(';'):
                statement = statement.strip()
                if statement:
                    conn.execute(text(statement))
            conn.commit()

        logger.info("Visitor tracking tables created successfully")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
