"""
Add address and title fields to referral_partners table

Run with: python migrations/add_referral_partner_address.py
"""

import os
import logging
from sqlalchemy import create_engine, text, inspect

logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment or .env file."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith('DATABASE_URL='):
                    return line.strip().split('=', 1)[1]

    return "sqlite:///./mortgage_crm.db"


def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(conn, table_name):
    """Check if a table exists."""
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def run_migration():
    """Execute the migration."""
    database_url = get_database_url()
    print(f"Using database: {database_url[:50]}...")

    engine = create_engine(database_url)

    print("Adding address fields to referral_partners table...")

    with engine.connect() as conn:
        if not table_exists(conn, 'referral_partners'):
            print("WARNING: referral_partners table does not exist")
            return

        # Add street_address column
        if not column_exists(conn, 'referral_partners', 'street_address'):
            conn.execute(text("ALTER TABLE referral_partners ADD COLUMN street_address VARCHAR"))
            print("  Added street_address column")
        else:
            print("  street_address column already exists")

        # Add city column
        if not column_exists(conn, 'referral_partners', 'city'):
            conn.execute(text("ALTER TABLE referral_partners ADD COLUMN city VARCHAR"))
            print("  Added city column")
        else:
            print("  city column already exists")

        # Add state column
        if not column_exists(conn, 'referral_partners', 'state'):
            conn.execute(text("ALTER TABLE referral_partners ADD COLUMN state VARCHAR"))
            print("  Added state column")
        else:
            print("  state column already exists")

        # Add zip_code column
        if not column_exists(conn, 'referral_partners', 'zip_code'):
            conn.execute(text("ALTER TABLE referral_partners ADD COLUMN zip_code VARCHAR"))
            print("  Added zip_code column")
        else:
            print("  zip_code column already exists")

        # Add title column
        if not column_exists(conn, 'referral_partners', 'title'):
            conn.execute(text("ALTER TABLE referral_partners ADD COLUMN title VARCHAR"))
            print("  Added title column")
        else:
            print("  title column already exists")

        conn.commit()

    print("\nMigration completed successfully!")


if __name__ == "__main__":
    run_migration()
