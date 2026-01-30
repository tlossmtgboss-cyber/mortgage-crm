"""
Database Migration: Add tenant_id to User and UserProfile tables

This migration adds the tenant_id column to link users to their tenant databases.
Run this after deploying the multi-tenant system components.
"""

from sqlalchemy import Column, Integer, ForeignKey, text
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


def upgrade(db: Session):
    """
    Add tenant_id column to users and onboarding_user_profiles tables.
    """
    logger.info("🔄 Starting tenant_id migration...")
    
    try:
        # Add tenant_id to users table
        db.execute(text("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS tenant_id INTEGER REFERENCES tenants(id) ON DELETE SET NULL;
        """))
        
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);
        """))
        
        logger.info("✅ Added tenant_id to users table")
        
        # Add tenant_id to onboarding_user_profiles table
        db.execute(text("""
            ALTER TABLE onboarding_user_profiles 
            ADD COLUMN IF NOT EXISTS tenant_id INTEGER REFERENCES tenants(id) ON DELETE SET NULL;
        """))
        
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_user_profiles_tenant_id 
            ON onboarding_user_profiles(tenant_id);
        """))
        
        logger.info("✅ Added tenant_id to onboarding_user_profiles table")
        
        db.commit()
        logger.info("✅ Tenant ID migration completed successfully")
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Migration failed: {e}")
        raise


def downgrade(db: Session):
    """
    Remove tenant_id column from users and onboarding_user_profiles tables.
    """
    logger.info("🔄 Rolling back tenant_id migration...")
    
    try:
        # Remove from users table
        db.execute(text("""
            DROP INDEX IF EXISTS idx_users_tenant_id;
        """))
        
        db.execute(text("""
            ALTER TABLE users DROP COLUMN IF EXISTS tenant_id;
        """))
        
        logger.info("✅ Removed tenant_id from users table")
        
        # Remove from onboarding_user_profiles table
        db.execute(text("""
            DROP INDEX IF EXISTS idx_onboarding_user_profiles_tenant_id;
        """))
        
        db.execute(text("""
            ALTER TABLE onboarding_user_profiles DROP COLUMN IF EXISTS tenant_id;
        """))
        
        logger.info("✅ Removed tenant_id from onboarding_user_profiles table")
        
        db.commit()
        logger.info("✅ Tenant ID rollback completed successfully")
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Rollback failed: {e}")
        raise


# Manual SQL script version (if you prefer to run directly in PostgreSQL)
MANUAL_UPGRADE_SQL = """
-- Add tenant_id to users table
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS tenant_id INTEGER REFERENCES tenants(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);

-- Add tenant_id to onboarding_user_profiles table
ALTER TABLE onboarding_user_profiles 
ADD COLUMN IF NOT EXISTS tenant_id INTEGER REFERENCES tenants(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_onboarding_user_profiles_tenant_id 
ON onboarding_user_profiles(tenant_id);

-- Verify changes
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'users' AND column_name = 'tenant_id';

SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'onboarding_user_profiles' AND column_name = 'tenant_id';
"""

MANUAL_DOWNGRADE_SQL = """
-- Remove tenant_id from users table
DROP INDEX IF EXISTS idx_users_tenant_id;
ALTER TABLE users DROP COLUMN IF EXISTS tenant_id;

-- Remove tenant_id from onboarding_user_profiles table
DROP INDEX IF EXISTS idx_onboarding_user_profiles_tenant_id;
ALTER TABLE onboarding_user_profiles DROP COLUMN IF EXISTS tenant_id;
"""


if __name__ == "__main__":
    """
    Run this migration manually if needed.
    
    Usage:
        python -m migrations.add_tenant_id_to_user_profile
    """
    from database import SessionLocal
    
    db = SessionLocal()
    try:
        print("Running tenant_id migration...")
        upgrade(db)
        print("Migration completed successfully!")
    except Exception as e:
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
