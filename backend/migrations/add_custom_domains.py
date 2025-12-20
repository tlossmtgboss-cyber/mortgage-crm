"""
Migration: Add custom_domains table

Creates the custom_domains table for multi-tenant custom domain support.
Allows dynamic CORS configuration without code changes.

Run with: python migrations/add_custom_domains.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from database import get_db_url

def run_migration():
    """Create custom_domains table."""
    database_url = get_db_url()
    engine = create_engine(database_url)

    # Check if table exists
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if "custom_domains" in existing_tables:
        print("✅ custom_domains table already exists")
        return

    # Determine SQL dialect
    is_sqlite = database_url.startswith("sqlite")

    if is_sqlite:
        create_sql = """
        CREATE TABLE custom_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain VARCHAR(255) NOT NULL UNIQUE,
            organization_id INTEGER,
            user_id INTEGER,
            is_verified BOOLEAN DEFAULT 0,
            verification_token VARCHAR(64),
            verified_at DATETIME,
            is_active BOOLEAN DEFAULT 1,
            ssl_status VARCHAR(50) DEFAULT 'pending',
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            FOREIGN KEY (organization_id) REFERENCES organizations(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        );
        CREATE INDEX idx_custom_domains_domain ON custom_domains(domain);
        CREATE INDEX idx_custom_domains_active ON custom_domains(domain, is_active);
        """
    else:
        # PostgreSQL
        create_sql = """
        CREATE TABLE custom_domains (
            id SERIAL PRIMARY KEY,
            domain VARCHAR(255) NOT NULL UNIQUE,
            organization_id INTEGER REFERENCES organizations(id),
            user_id INTEGER REFERENCES users(id),
            is_verified BOOLEAN DEFAULT FALSE,
            verification_token VARCHAR(64),
            verified_at TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            ssl_status VARCHAR(50) DEFAULT 'pending',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER REFERENCES users(id)
        );
        CREATE INDEX idx_custom_domains_domain ON custom_domains(domain);
        CREATE INDEX idx_custom_domains_active ON custom_domains(domain, is_active);
        """

    with engine.connect() as conn:
        for statement in create_sql.strip().split(';'):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
        conn.commit()

    print("✅ Created custom_domains table")

    # Insert seed data (the domains we already have)
    seed_sql = """
    INSERT INTO custom_domains (domain, is_verified, is_active, ssl_status, notes)
    VALUES
        ('www.timloss.com', 1, 1, 'active', 'Initial custom domain'),
        ('timloss.com', 1, 1, 'active', 'Apex domain for timloss');
    """

    try:
        with engine.connect() as conn:
            conn.execute(text(seed_sql))
            conn.commit()
        print("✅ Seeded initial custom domains")
    except Exception as e:
        print(f"⚠️ Could not seed domains (may already exist): {e}")


if __name__ == "__main__":
    run_migration()
