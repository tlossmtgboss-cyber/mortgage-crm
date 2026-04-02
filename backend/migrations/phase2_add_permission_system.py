"""
Phase 2: Permission System Migration
Creates permission tables and adds role field to existing users table
Integrates with Phase 1 impersonation system

Author: System
Date: 2025-11-16
"""

from sqlalchemy import create_engine, text
from datetime import datetime, timezone
import os
import json

def get_management_permissions():
    """Full access template for management roles"""
    return {
        # Dashboard & Analytics
        "dashboard.view_all_widgets": True,
        "dashboard.customize": True,
        "dashboard.export": True,
        "analytics.view_all": True,
        "analytics.export": True,

        # Lead Management
        "leads.view_all": True,
        "leads.view_team": True,
        "leads.view_assigned": True,
        "leads.create": True,
        "leads.edit_all": True,
        "leads.edit_own": True,
        "leads.delete": True,
        "leads.assign": True,
        "leads.export": True,

        # Client Management
        "clients.view_all": True,
        "clients.view_team": True,
        "clients.view_assigned": True,
        "clients.create": True,
        "clients.edit_all": True,
        "clients.edit_own": True,
        "clients.delete": True,
        "clients.export": True,

        # Loan Management
        "loans.view_all": True,
        "loans.view_team": True,
        "loans.view_assigned": True,
        "loans.create": True,
        "loans.edit_all": True,
        "loans.edit_own": True,
        "loans.delete": True,
        "loans.process": True,
        "loans.export": True,

        # Team Management
        "team.view_all": True,
        "team.view_team": True,
        "team.edit_members": True,
        "team.manage_permissions": True,
        "team.impersonate": True,
        "team.view_performance": True,

        # Reports
        "reports.view_all": True,
        "reports.view_sales": True,
        "reports.view_operations": True,
        "reports.export": True,

        # Settings
        "settings.view": True,
        "settings.edit": True,
        "permissions.view_all": True,
        "permissions.manage": True,

        # Tasks
        "tasks.view_all": True,
        "tasks.view_team": True,
        "tasks.view_assigned": True,
        "tasks.create": True,
        "tasks.edit_all": True,
        "tasks.delete": True,
    }

def get_sales_permissions():
    """Sales-focused template - own data only"""
    return {
        # Dashboard & Analytics
        "dashboard.view_all_widgets": False,
        "dashboard.customize": True,
        "dashboard.export": True,
        "analytics.view_all": False,
        "analytics.export": True,

        # Lead Management
        "leads.view_all": False,
        "leads.view_team": True,
        "leads.view_assigned": True,
        "leads.create": True,
        "leads.edit_all": False,
        "leads.edit_own": True,
        "leads.delete": False,
        "leads.assign": False,
        "leads.export": True,

        # Client Management
        "clients.view_all": False,
        "clients.view_team": True,
        "clients.view_assigned": True,
        "clients.create": True,
        "clients.edit_all": False,
        "clients.edit_own": True,
        "clients.delete": False,
        "clients.export": True,

        # Loan Management
        "loans.view_all": False,
        "loans.view_team": True,
        "loans.view_assigned": True,
        "loans.create": True,
        "loans.edit_all": False,
        "loans.edit_own": True,
        "loans.delete": False,
        "loans.process": False,
        "loans.export": True,

        # Team Management
        "team.view_all": False,
        "team.view_team": True,
        "team.edit_members": False,
        "team.manage_permissions": False,
        "team.impersonate": False,
        "team.view_performance": True,

        # Reports
        "reports.view_all": False,
        "reports.view_sales": True,
        "reports.view_operations": False,
        "reports.export": True,

        # Settings
        "settings.view": True,
        "settings.edit": False,
        "permissions.view_all": False,
        "permissions.manage": False,

        # Tasks
        "tasks.view_all": False,
        "tasks.view_team": True,
        "tasks.view_assigned": True,
        "tasks.create": True,
        "tasks.edit_all": False,
        "tasks.delete": False,
    }

def get_operations_permissions():
    """Operations-focused template - processing focus"""
    return {
        # Dashboard & Analytics
        "dashboard.view_all_widgets": False,
        "dashboard.customize": True,
        "dashboard.export": True,
        "analytics.view_all": False,
        "analytics.export": True,

        # Lead Management
        "leads.view_all": True,
        "leads.view_team": True,
        "leads.view_assigned": True,
        "leads.create": False,
        "leads.edit_all": True,
        "leads.edit_own": True,
        "leads.delete": False,
        "leads.assign": True,
        "leads.export": True,

        # Client Management
        "clients.view_all": True,
        "clients.view_team": True,
        "clients.view_assigned": True,
        "clients.create": False,
        "clients.edit_all": True,
        "clients.edit_own": True,
        "clients.delete": False,
        "clients.export": True,

        # Loan Management
        "loans.view_all": True,
        "loans.view_team": True,
        "loans.view_assigned": True,
        "loans.create": True,
        "loans.edit_all": True,
        "loans.edit_own": True,
        "loans.delete": False,
        "loans.process": True,
        "loans.export": True,

        # Team Management
        "team.view_all": False,
        "team.view_team": True,
        "team.edit_members": False,
        "team.manage_permissions": False,
        "team.impersonate": False,
        "team.view_performance": True,

        # Reports
        "reports.view_all": False,
        "reports.view_sales": False,
        "reports.view_operations": True,
        "reports.export": True,

        # Settings
        "settings.view": True,
        "settings.edit": False,
        "permissions.view_all": False,
        "permissions.manage": False,

        # Tasks
        "tasks.view_all": True,
        "tasks.view_team": True,
        "tasks.view_assigned": True,
        "tasks.create": True,
        "tasks.edit_all": True,
        "tasks.delete": False,
    }


def run_migration():
    """Execute Phase 2 permission system migration"""

    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Fix postgres:// to postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    # Create engine
    engine = create_engine(database_url)

    print("🚀 Starting Phase 2: Permission System Migration...\n")

    with engine.connect() as conn:

        # ====================================================================
        # STEP 1: Add role field to users table
        # ====================================================================
        print("👤 Step 1: Adding role field to users table...")

        try:
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS permission_role VARCHAR(50) DEFAULT 'sales';
            """))
            conn.commit()
            print("   ✅ Added permission_role column to users table\n")
        except Exception as e:
            print(f"   ⚠️  Column may already exist: {e}\n")

        # ====================================================================
        # STEP 2: Create permission_templates table
        # ====================================================================
        print("📋 Step 2: Creating permission_templates table...")

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS permission_templates (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                description TEXT,
                category VARCHAR(50) NOT NULL,
                permissions JSONB NOT NULL DEFAULT '{}',
                is_system_default BOOLEAN DEFAULT FALSE,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                CONSTRAINT template_category_check CHECK (category IN ('management', 'sales', 'operations', 'custom'))
            );

            CREATE INDEX IF NOT EXISTS idx_permission_templates_category
                ON permission_templates(category);
            CREATE INDEX IF NOT EXISTS idx_permission_templates_system
                ON permission_templates(is_system_default) WHERE is_system_default = TRUE;
        """))
        conn.commit()
        print("   ✅ Created permission_templates table\n")

        # ====================================================================
        # STEP 3: Create user_permissions table
        # ====================================================================
        print("🔐 Step 3: Creating user_permissions table...")

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_permissions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                permission_key VARCHAR(255) NOT NULL,
                granted BOOLEAN DEFAULT TRUE,
                granted_by INTEGER REFERENCES users(id),
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                inherited_from VARCHAR(50) DEFAULT 'template',

                CONSTRAINT unique_user_permission UNIQUE (user_id, permission_key)
            );

            -- CRITICAL: These indexes power permission checks
            CREATE INDEX IF NOT EXISTS idx_user_permissions_user
                ON user_permissions(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_permissions_composite
                ON user_permissions(user_id, permission_key, granted);
            CREATE INDEX IF NOT EXISTS idx_user_permissions_expires
                ON user_permissions(expires_at) WHERE expires_at IS NOT NULL;
        """))
        conn.commit()
        print("   ✅ Created user_permissions table\n")

        # ====================================================================
        # STEP 4: Seed default permission templates
        # ====================================================================
        print("🌱 Step 4: Seeding default permission templates...")

        # Check if templates already exist
        result = conn.execute(text("""
            SELECT COUNT(*) as count FROM permission_templates
            WHERE name IN ('Management', 'Sales', 'Operations')
        """))
        existing_count = result.fetchone()[0]

        if existing_count > 0:
            print(f"   ⚠️  Found {existing_count} existing templates. Skipping seed.\n")
        else:
            # Insert Management Template
            management_perms = get_management_permissions()
            conn.execute(text("""
                INSERT INTO permission_templates
                (name, description, permissions, is_system_default, category, created_at)
                VALUES
                (:name, :description, CAST(:permissions AS jsonb), :is_system, :category, :created_at)
            """), {
                'name': 'Management',
                'description': 'Full access for management and leadership roles',
                'permissions': json.dumps(management_perms),
                'is_system': True,
                'category': 'management',
                'created_at': datetime.now(timezone.utc)
            })

            # Insert Sales Template
            sales_perms = get_sales_permissions()
            conn.execute(text("""
                INSERT INTO permission_templates
                (name, description, permissions, is_system_default, category, created_at)
                VALUES
                (:name, :description, CAST(:permissions AS jsonb), :is_system, :category, :created_at)
            """), {
                'name': 'Sales',
                'description': 'Sales-focused template for sales reps and loan officers',
                'permissions': json.dumps(sales_perms),
                'is_system': True,
                'category': 'sales',
                'created_at': datetime.now(timezone.utc)
            })

            # Insert Operations Template
            operations_perms = get_operations_permissions()
            conn.execute(text("""
                INSERT INTO permission_templates
                (name, description, permissions, is_system_default, category, created_at)
                VALUES
                (:name, :description, CAST(:permissions AS jsonb), :is_system, :category, :created_at)
            """), {
                'name': 'Operations',
                'description': 'Operations template for processors and underwriters',
                'permissions': json.dumps(operations_perms),
                'is_system': True,
                'category': 'operations',
                'created_at': datetime.now(timezone.utc)
            })

            conn.commit()
            print("   ✅ Seeded 3 default templates\n")

        # ====================================================================
        # STEP 5: Verify migration
        # ====================================================================
        print("✅ Step 5: Verifying migration...")

        # Count templates
        result = conn.execute(text("""
            SELECT name, category, jsonb_object_keys(permissions) as perm_count
            FROM permission_templates
            WHERE is_system_default = TRUE
        """))

        templates = {}
        for row in result:
            template_name = row[0]
            if template_name not in templates:
                templates[template_name] = {'category': row[1], 'count': 0}
            templates[template_name]['count'] += 1

        print("\n📊 MIGRATION SUMMARY")
        print("=" * 60)
        print(f"\n✅ Tables Created:")
        print("   • permission_templates")
        print("   • user_permissions")
        print(f"\n✅ Field Added:")
        print("   • users.permission_role")
        print(f"\n✅ Templates Seeded:")
        for name, data in templates.items():
            print(f"   • {name} ({data['category']}) - {data['count']} permissions")

        print("\n" + "=" * 60)
        print("🎉 Phase 2 Migration Completed Successfully!\n")
        print("Next Steps:")
        print("1. Update User model in main.py to include permission_role field")
        print("2. Create API endpoint to assign roles to users")
        print("3. Implement permission middleware")
        print("4. Add data filtering to existing endpoints")
        print()


if __name__ == '__main__':
    run_migration()
