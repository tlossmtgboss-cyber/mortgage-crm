"""
Fix Admin Permissions Migration

This migration fixes the admin permissions system by:
1. Creating the missing user_has_permission PostgreSQL function
2. Creating the user_has_stage_access helper function
3. Updating the admin@perenniaai.com user to have proper admin permissions
4. Creating required permission tables if they don't exist

Author: System
Date: 2025-01-05
"""

from sqlalchemy import create_engine, text
from datetime import datetime
import os


def run_migration():
    """Execute admin permissions fix migration"""

    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Fix postgres:// to postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)

    print("🔧 Starting Admin Permissions Fix Migration...\n")

    with engine.connect() as conn:

        # ====================================================================
        # STEP 1: Ensure required tables exist
        # ====================================================================
        print("📋 Step 1: Ensuring required permission tables exist...")

        # Create loan_stages table if not exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS loan_stages (
                id SERIAL PRIMARY KEY,
                code VARCHAR(50) NOT NULL UNIQUE,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                display_order INTEGER DEFAULT 0,
                icon VARCHAR(50),
                color VARCHAR(20),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Insert default stages if they don't exist
        conn.execute(text("""
            INSERT INTO loan_stages (code, name, description, display_order, icon, color)
            VALUES
                ('lead', 'Lead Management', 'Lead intake, qualification, and nurturing', 1, 'UserPlus', '#3B82F6'),
                ('active_loan', 'Active Loan', 'Loan processing, underwriting, and closing', 2, 'FileText', '#10B981'),
                ('portfolio', 'Portfolio', 'Client retention, MUM, and referral management', 3, 'Briefcase', '#8B5CF6')
            ON CONFLICT (code) DO NOTHING;
        """))

        # Create permission_definitions table if not exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS permission_definitions (
                id SERIAL PRIMARY KEY,
                key VARCHAR(255) NOT NULL UNIQUE,
                stage_code VARCHAR(50),
                category VARCHAR(100) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                requires_subscription BOOLEAN DEFAULT TRUE,
                risk_level VARCHAR(20) DEFAULT 'low',
                display_order INTEGER DEFAULT 0,
                group_name VARCHAR(100),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Create user_stage_access table if not exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_stage_access (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                stage_code VARCHAR(50) NOT NULL,
                access_type VARCHAR(50) DEFAULT 'subscription',
                template_id INTEGER,
                data_scope VARCHAR(50) DEFAULT 'assigned',
                is_active BOOLEAN DEFAULT TRUE,
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                granted_by INTEGER,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, stage_code)
            );
        """))

        # Create user_permission_overrides table if not exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_permission_overrides (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                permission_key VARCHAR(255) NOT NULL,
                granted BOOLEAN NOT NULL,
                scope_override VARCHAR(50),
                is_temporary BOOLEAN DEFAULT FALSE,
                expires_at TIMESTAMP,
                reason TEXT,
                granted_by INTEGER,
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, permission_key)
            );
        """))

        # Create stage_permission_templates table if not exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stage_permission_templates (
                id SERIAL PRIMARY KEY,
                code VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                stage_code VARCHAR(50),
                role_type VARCHAR(50) NOT NULL,
                permissions JSONB NOT NULL DEFAULT '{}',
                default_scope VARCHAR(50) DEFAULT 'assigned',
                is_system_default BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                display_order INTEGER DEFAULT 0,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        conn.commit()
        print("   ✅ Permission tables verified/created\n")

        # ====================================================================
        # STEP 2: Create user_has_stage_access function
        # ====================================================================
        print("🔐 Step 2: Creating user_has_stage_access function...")

        conn.execute(text("""
            CREATE OR REPLACE FUNCTION user_has_stage_access(p_user_id INTEGER, p_stage_code VARCHAR)
            RETURNS BOOLEAN AS $$
            BEGIN
                -- Admin users always have stage access
                IF EXISTS (
                    SELECT 1 FROM users
                    WHERE id = p_user_id
                    AND (
                        permission_role IN ('admin', 'leadership', 'management')
                        OR role IN ('admin', 'manager')
                    )
                ) THEN
                    RETURN TRUE;
                END IF;

                RETURN EXISTS (
                    SELECT 1 FROM user_stage_access
                    WHERE user_id = p_user_id
                    AND stage_code = p_stage_code
                    AND is_active = TRUE
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                );
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.commit()
        print("   ✅ user_has_stage_access function created\n")

        # ====================================================================
        # STEP 3: Create user_has_permission function
        # ====================================================================
        print("🔑 Step 3: Creating user_has_permission function...")

        conn.execute(text("""
            CREATE OR REPLACE FUNCTION user_has_permission(p_user_id INTEGER, p_permission_key VARCHAR)
            RETURNS BOOLEAN AS $$
            DECLARE
                v_stage_code VARCHAR;
                v_template_permissions JSONB;
                v_override_granted BOOLEAN;
                v_user_role VARCHAR;
                v_permission_role VARCHAR;
            BEGIN
                -- First check if user is an admin (admin users have ALL permissions)
                SELECT role, permission_role INTO v_user_role, v_permission_role
                FROM users WHERE id = p_user_id;

                -- Admin bypass: admin users have all permissions
                IF v_permission_role IN ('admin', 'leadership', 'management')
                   OR v_user_role IN ('admin', 'manager') THEN
                    RETURN TRUE;
                END IF;

                -- Get the stage for this permission (if any)
                SELECT stage_code INTO v_stage_code
                FROM permission_definitions WHERE key = p_permission_key;

                -- If stage-specific, check stage access first
                IF v_stage_code IS NOT NULL THEN
                    IF NOT user_has_stage_access(p_user_id, v_stage_code) THEN
                        RETURN FALSE;
                    END IF;
                END IF;

                -- Check for individual override first
                SELECT granted INTO v_override_granted
                FROM user_permission_overrides
                WHERE user_id = p_user_id
                AND permission_key = p_permission_key
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP);

                IF v_override_granted IS NOT NULL THEN
                    RETURN v_override_granted;
                END IF;

                -- Check template permissions
                SELECT spt.permissions INTO v_template_permissions
                FROM user_stage_access usa
                JOIN stage_permission_templates spt ON spt.id = usa.template_id
                WHERE usa.user_id = p_user_id
                AND usa.stage_code = v_stage_code
                AND usa.is_active = TRUE;

                IF v_template_permissions IS NOT NULL THEN
                    RETURN COALESCE((v_template_permissions->>p_permission_key)::BOOLEAN, FALSE);
                END IF;

                RETURN FALSE;
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.commit()
        print("   ✅ user_has_permission function created\n")

        # ====================================================================
        # STEP 4: Update admin user permissions
        # ====================================================================
        print("👤 Step 4: Updating admin@perenniaai.com user permissions...")

        # Check if admin user exists
        result = conn.execute(text("""
            SELECT id, email, role, permission_role FROM users
            WHERE email = 'admin@perenniaai.com'
        """))
        admin_user = result.fetchone()

        if admin_user:
            print(f"   Found admin user (ID: {admin_user[0]})")
            print(f"   Current role: {admin_user[2]}")
            print(f"   Current permission_role: {admin_user[3]}")

            # Update to admin role
            conn.execute(text("""
                UPDATE users
                SET permission_role = 'admin',
                    role = 'admin'
                WHERE email = 'admin@perenniaai.com'
            """))
            conn.commit()
            print("   ✅ Updated admin user to have admin permissions\n")

            # Grant all stage access to admin
            admin_id = admin_user[0]
            for stage in ['lead', 'active_loan', 'portfolio']:
                conn.execute(text("""
                    INSERT INTO user_stage_access (user_id, stage_code, access_type, data_scope, is_active)
                    VALUES (:user_id, :stage_code, 'granted', 'all', TRUE)
                    ON CONFLICT (user_id, stage_code)
                    DO UPDATE SET data_scope = 'all', is_active = TRUE
                """), {"user_id": admin_id, "stage_code": stage})

            conn.commit()
            print("   ✅ Granted admin user access to all stages\n")
        else:
            print("   ⚠️  admin@perenniaai.com user not found\n")

            # Check what users exist
            result = conn.execute(text("""
                SELECT id, email, role, permission_role FROM users LIMIT 5
            """))
            users = result.fetchall()
            if users:
                print("   Existing users:")
                for user in users:
                    print(f"     - {user[1]} (role: {user[2]}, permission_role: {user[3]})")
                print()

        # ====================================================================
        # STEP 5: Verify the fix
        # ====================================================================
        print("✅ Step 5: Verifying the fix...")

        # Test the function
        result = conn.execute(text("""
            SELECT
                user_has_permission(
                    (SELECT id FROM users WHERE email = 'admin@perenniaai.com' LIMIT 1),
                    'team.manage_permissions'
                ) as has_permission
        """))
        row = result.fetchone()

        if row and row[0]:
            print("   ✅ Admin user now has 'team.manage_permissions' permission\n")
        else:
            print("   ⚠️  Could not verify admin permissions (user may not exist)\n")

        # Show summary
        print("=" * 60)
        print("🎉 Admin Permissions Fix Migration Completed!")
        print("=" * 60)
        print("\nChanges made:")
        print("  1. Created user_has_stage_access PostgreSQL function")
        print("  2. Created user_has_permission PostgreSQL function")
        print("  3. Updated admin@perenniaai.com to permission_role = 'admin'")
        print("  4. Granted admin user access to all stages")
        print("\nThe admin user should now have full platform access.")
        print()


if __name__ == '__main__':
    run_migration()
