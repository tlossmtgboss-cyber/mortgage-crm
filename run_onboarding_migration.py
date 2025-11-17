#!/usr/bin/env python3
"""
Run onboarding tables migration via Python
This script can be executed via: railway run python run_onboarding_migration.py
"""

import os
import sys
from sqlalchemy import create_engine, text

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

# Fix Railway DATABASE_URL format (postgres:// -> postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"Connecting to database...")
engine = create_engine(DATABASE_URL)

migration_steps = []

try:
    with engine.begin() as conn:
        # Step 1: Add columns to users table
        print("\n1. Adding columns to users table...")
        conn.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
        """))
        conn.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS nmls_number VARCHAR(50);
        """))
        conn.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS business_address VARCHAR(500);
        """))
        conn.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS current_role VARCHAR(100);
        """))
        conn.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS business_hours JSONB;
        """))
        conn.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP WITH TIME ZONE;
        """))
        conn.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMP WITH TIME ZONE;
        """))
        migration_steps.append("✅ Added columns to users table")
        print("   ✅ Done")

        # Step 2: Create indexes on users table
        print("\n2. Creating indexes on users table...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_users_nmls_number ON users(nmls_number);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_users_email_verified_at ON users(email_verified_at);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_users_phone_verified_at ON users(phone_verified_at);
        """))
        migration_steps.append("✅ Created indexes on users table")
        print("   ✅ Done")

        # Step 3: Create onboarding_progress table
        print("\n3. Creating onboarding_progress table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_progress (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                current_step INTEGER NOT NULL DEFAULT 1,
                step_1_data JSONB,
                step_2_data JSONB,
                step_3_data JSONB,
                step_4_data JSONB,
                step_5_data JSONB,
                step_6_data JSONB,
                step_7_data JSONB,
                step_8_data JSONB,
                step_9_data JSONB,
                step_10_data JSONB,
                completed_at TIMESTAMP WITH TIME ZONE,
                last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """))
        migration_steps.append("✅ Created onboarding_progress table")
        print("   ✅ Done")

        # Step 4: Create indexes on onboarding_progress
        print("\n4. Creating indexes on onboarding_progress...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_progress_user_id ON onboarding_progress(user_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_progress_current_step ON onboarding_progress(current_step);
        """))
        migration_steps.append("✅ Created indexes on onboarding_progress")
        print("   ✅ Done")

        # Step 5: Create onboarding_errors table
        print("\n5. Creating onboarding_errors table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_errors (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                error_code VARCHAR(20) NOT NULL,
                step_number INTEGER NOT NULL,
                error_message TEXT NOT NULL,
                error_context JSONB,
                user_action VARCHAR(50),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """))
        migration_steps.append("✅ Created onboarding_errors table")
        print("   ✅ Done")

        # Step 6: Create indexes on onboarding_errors
        print("\n6. Creating indexes on onboarding_errors...")
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
        migration_steps.append("✅ Created indexes on onboarding_errors")
        print("   ✅ Done")

        # Step 7: Create verification_tokens table
        print("\n7. Creating verification_tokens table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS verification_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_type VARCHAR(20) NOT NULL,
                token VARCHAR(10) NOT NULL,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                used_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """))
        migration_steps.append("✅ Created verification_tokens table")
        print("   ✅ Done")

        # Step 8: Create indexes on verification_tokens
        print("\n8. Creating indexes on verification_tokens...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_verification_tokens_user_id ON verification_tokens(user_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_verification_tokens_token ON verification_tokens(token);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_verification_tokens_expires_at ON verification_tokens(expires_at);
        """))
        migration_steps.append("✅ Created indexes on verification_tokens")
        print("   ✅ Done")

    print("\n" + "="*60)
    print("🎉 MIGRATION COMPLETED SUCCESSFULLY!")
    print("="*60)
    print("\nSteps completed:")
    for step in migration_steps:
        print(f"  {step}")

    print("\n✅ All onboarding tables and indexes have been created!")
    print("\nYou can now test the onboarding wizard at:")
    print("  https://mortgage-crm-nine.vercel.app/onboarding/1")

except Exception as e:
    print(f"\n❌ MIGRATION FAILED!")
    print(f"Error: {str(e)}")
    sys.exit(1)
