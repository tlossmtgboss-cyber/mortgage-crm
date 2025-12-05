"""
Migration: Add user_integrations table
Description: Stores OAuth tokens for user-delegated API access (Microsoft, Google, etc.)
Created: 2024-12-05
"""

import os
from sqlalchemy import create_engine, text

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable not set")
    print("   Set it with: export DATABASE_URL='your_database_url'")
    exit(1)

# Fix Railway DATABASE_URL format (postgres:// -> postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def run_migration():
    """Create the user_integrations table."""

    migration_sql = """
    -- Create the user_integrations table
    CREATE TABLE IF NOT EXISTS user_integrations (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        provider VARCHAR(50) NOT NULL,  -- 'microsoft', 'google', etc.

        -- OAuth tokens
        access_token TEXT,
        refresh_token TEXT,
        expires_at TIMESTAMP,

        -- Additional metadata
        scopes TEXT,  -- Comma-separated list of granted scopes
        email VARCHAR(255),  -- User's email on the provider
        provider_user_id VARCHAR(255),  -- User ID on provider

        -- Timestamps
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        -- Constraints
        CONSTRAINT fk_user_integrations_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        CONSTRAINT uix_user_provider UNIQUE (user_id, provider)
    );
    """

    indexes_sql = """
    -- Create indexes (using DO block to handle IF NOT EXISTS for indexes)
    CREATE INDEX IF NOT EXISTS ix_user_integrations_user_id ON user_integrations(user_id);
    CREATE INDEX IF NOT EXISTS ix_user_integrations_user_provider ON user_integrations(user_id, provider);
    CREATE INDEX IF NOT EXISTS ix_user_integrations_provider ON user_integrations(provider);
    """

    comment_sql = """
    COMMENT ON TABLE user_integrations IS 'Stores OAuth tokens for user-delegated API access to external services';
    """

    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'user_integrations'
            );
        """))
        table_exists = result.scalar()

        if table_exists:
            print("✅ Table 'user_integrations' already exists - skipping creation")
        else:
            print("Creating user_integrations table...")
            conn.execute(text(migration_sql))
            conn.commit()
            print("✅ Created user_integrations table")

        # Create indexes (these are idempotent with IF NOT EXISTS)
        print("Creating indexes...")
        conn.execute(text(indexes_sql))
        conn.commit()
        print("✅ Indexes created/verified")

        # Add comment
        try:
            conn.execute(text(comment_sql))
            conn.commit()
            print("✅ Table comment added")
        except Exception as e:
            print(f"⚠️  Could not add comment (non-critical): {e}")

        print("\n✅ Migration complete!")


if __name__ == "__main__":
    print("=" * 60)
    print("Migration: Add user_integrations table")
    print("=" * 60)
    run_migration()
