"""
Migration: Add Onboarding Tables and User Verification Fields
Created: 2024-01-15
Description: Adds onboarding_progress, onboarding_errors, verification_tokens tables
             and adds onboarding fields to users table
"""

from sqlalchemy import create_engine, text
import os

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable not set")
    exit(1)

# Fix Railway DATABASE_URL format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def upgrade():
    """Apply the migration"""
    print("Starting migration: Add onboarding tables...")

    with engine.begin() as conn:
        # Add fields to users table
        print("Adding fields to users table...")
        conn.execute(text("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS phone VARCHAR(20),
            ADD COLUMN IF NOT EXISTS nmls_number VARCHAR(50),
            ADD COLUMN IF NOT EXISTS business_address VARCHAR(500),
            ADD COLUMN IF NOT EXISTS current_role VARCHAR(100),
            ADD COLUMN IF NOT EXISTS business_hours JSON,
            ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMP;
        """))

        # Create indexes on users table
        print("Creating indexes on users table...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_users_nmls_number ON users(nmls_number);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_users_email_verified_at ON users(email_verified_at);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_users_phone_verified_at ON users(phone_verified_at);
        """))

        # Create onboarding_progress table
        print("Creating onboarding_progress table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_progress (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                current_step INTEGER NOT NULL DEFAULT 1,
                step_1_data JSON,
                step_2_data JSON,
                step_3_data JSON,
                step_4_data JSON,
                step_5_data JSON,
                step_6_data JSON,
                step_7_data JSON,
                step_8_data JSON,
                step_9_data JSON,
                step_10_data JSON,
                completed_at TIMESTAMP,
                last_updated TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        # Create indexes on onboarding_progress
        print("Creating indexes on onboarding_progress...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_progress_user_id ON onboarding_progress(user_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_progress_current_step ON onboarding_progress(current_step);
        """))

        # Create onboarding_errors table
        print("Creating onboarding_errors table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_errors (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                error_code VARCHAR(20) NOT NULL,
                step_number INTEGER NOT NULL,
                error_message TEXT NOT NULL,
                error_context JSON,
                user_action VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        # Create indexes on onboarding_errors
        print("Creating indexes on onboarding_errors...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_errors_user_id ON onboarding_errors(user_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_errors_error_code ON onboarding_errors(error_code);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_errors_step_number ON onboarding_errors(step_number);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_errors_created_at ON onboarding_errors(created_at);
        """))

        # Create verification_tokens table
        print("Creating verification_tokens table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS verification_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_type VARCHAR(20) NOT NULL,
                token VARCHAR(10) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        # Create indexes on verification_tokens
        print("Creating indexes on verification_tokens...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_verification_tokens_user_id ON verification_tokens(user_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_verification_tokens_token ON verification_tokens(token);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_verification_tokens_expires_at ON verification_tokens(expires_at);
        """))

    print("Migration completed successfully!")

def downgrade():
    """Rollback the migration"""
    print("Rolling back migration: Add onboarding tables...")

    with engine.begin() as conn:
        # Drop verification_tokens table
        print("Dropping verification_tokens table...")
        conn.execute(text("DROP TABLE IF EXISTS verification_tokens CASCADE;"))

        # Drop onboarding_errors table
        print("Dropping onboarding_errors table...")
        conn.execute(text("DROP TABLE IF EXISTS onboarding_errors CASCADE;"))

        # Drop onboarding_progress table
        print("Dropping onboarding_progress table...")
        conn.execute(text("DROP TABLE IF NOT EXISTS onboarding_progress CASCADE;"))

        # Remove fields from users table
        print("Removing fields from users table...")
        conn.execute(text("""
            ALTER TABLE users
            DROP COLUMN IF EXISTS phone_verified_at,
            DROP COLUMN IF EXISTS email_verified_at,
            DROP COLUMN IF EXISTS business_hours,
            DROP COLUMN IF EXISTS current_role,
            DROP COLUMN IF EXISTS business_address,
            DROP COLUMN IF EXISTS nmls_number,
            DROP COLUMN IF EXISTS phone;
        """))

        # Drop indexes
        print("Dropping indexes...")
        conn.execute(text("DROP INDEX IF EXISTS idx_users_phone_verified_at;"))
        conn.execute(text("DROP INDEX IF EXISTS idx_users_email_verified_at;"))
        conn.execute(text("DROP INDEX IF EXISTS idx_users_nmls_number;"))

    print("Rollback completed successfully!")

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python add_onboarding_tables.py [upgrade|downgrade]")
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "upgrade":
        upgrade()
    elif action == "downgrade":
        downgrade()
    else:
        print(f"Unknown action: {action}")
        print("Usage: python add_onboarding_tables.py [upgrade|downgrade]")
        sys.exit(1)
