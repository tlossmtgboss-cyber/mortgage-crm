#!/usr/bin/env python3
"""
Quick migration script to fix 500 errors by creating missing tables.
Run with: railway run python run_fix_500_migration.py
"""

import os
import sys
import json
from sqlalchemy import create_engine, text

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

# Fix Railway DATABASE_URL format (postgres:// -> postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"Connecting to database...")
engine = create_engine(DATABASE_URL)

results = {
    "tables_created": [],
    "columns_added": [],
    "errors": [],
    "skipped": []
}

with engine.connect() as conn:
    # ================================================================
    # 1. Create notifications table
    # ================================================================
    print("\n1. Creating notifications table...")
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                type VARCHAR(50) NOT NULL,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                link VARCHAR(500),
                is_read BOOLEAN DEFAULT FALSE,
                read_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()

        # Create indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
            CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);
            CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);
        """))
        conn.commit()
        results["tables_created"].append("notifications")
        print("   ✅ notifications table created")
    except Exception as e:
        if "already exists" in str(e).lower():
            results["skipped"].append("notifications table")
            print("   ⏭️  notifications table already exists")
        else:
            results["errors"].append(f"notifications: {str(e)[:100]}")
            print(f"   ❌ Error: {e}")

    # ================================================================
    # 2. Create user_permissions table
    # ================================================================
    print("\n2. Creating user_permissions table...")
    try:
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
            )
        """))
        conn.commit()

        # Create indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_user_permissions_user ON user_permissions(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_permissions_composite ON user_permissions(user_id, permission_key, granted);
        """))
        conn.commit()
        results["tables_created"].append("user_permissions")
        print("   ✅ user_permissions table created")
    except Exception as e:
        if "already exists" in str(e).lower():
            results["skipped"].append("user_permissions table")
            print("   ⏭️  user_permissions table already exists")
        else:
            results["errors"].append(f"user_permissions: {str(e)[:100]}")
            print(f"   ❌ Error: {e}")

    # ================================================================
    # 3. Create permission_templates table
    # ================================================================
    print("\n3. Creating permission_templates table...")
    try:
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
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        results["tables_created"].append("permission_templates")
        print("   ✅ permission_templates table created")
    except Exception as e:
        if "already exists" in str(e).lower():
            results["skipped"].append("permission_templates table")
            print("   ⏭️  permission_templates table already exists")
        else:
            results["errors"].append(f"permission_templates: {str(e)[:100]}")
            print(f"   ❌ Error: {e}")

    # ================================================================
    # 4. Add permission_role column to users table
    # ================================================================
    print("\n4. Adding permission_role column to users table...")
    try:
        conn.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS permission_role VARCHAR(50) DEFAULT 'sales'
        """))
        conn.commit()
        results["columns_added"].append("users.permission_role")
        print("   ✅ users.permission_role column added")
    except Exception as e:
        if "already exists" in str(e).lower():
            results["skipped"].append("users.permission_role")
            print("   ⏭️  users.permission_role already exists")
        else:
            results["errors"].append(f"users.permission_role: {str(e)[:100]}")
            print(f"   ❌ Error: {e}")

    # ================================================================
    # 5. Create ai_tasks table
    # ================================================================
    print("\n5. Creating ai_tasks table...")
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_tasks (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                type VARCHAR(50),
                category VARCHAR(100),
                priority INTEGER DEFAULT 0,
                status VARCHAR(50) DEFAULT 'pending',
                ai_confidence FLOAT,
                ai_reasoning TEXT,
                suggested_action TEXT,
                due_date TIMESTAMP,
                assigned_to_id INTEGER REFERENCES users(id),
                created_by_id INTEGER REFERENCES users(id),
                lead_id INTEGER,
                loan_id INTEGER,
                entity_type VARCHAR(50),
                entity_id INTEGER,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()

        # Create indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_ai_tasks_assigned ON ai_tasks(assigned_to_id);
            CREATE INDEX IF NOT EXISTS idx_ai_tasks_status ON ai_tasks(status);
            CREATE INDEX IF NOT EXISTS idx_ai_tasks_created ON ai_tasks(created_at DESC);
        """))
        conn.commit()
        results["tables_created"].append("ai_tasks")
        print("   ✅ ai_tasks table created")
    except Exception as e:
        if "already exists" in str(e).lower():
            results["skipped"].append("ai_tasks table")
            print("   ⏭️  ai_tasks table already exists")
        else:
            results["errors"].append(f"ai_tasks: {str(e)[:100]}")
            print(f"   ❌ Error: {e}")

    # ================================================================
    # 6. Create incoming_data_events table
    # ================================================================
    print("\n6. Creating incoming_data_events table...")
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS incoming_data_events (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                source VARCHAR(50) NOT NULL,
                source_id VARCHAR(255),
                event_type VARCHAR(50),
                raw_data JSONB,
                processed BOOLEAN DEFAULT FALSE,
                processed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        results["tables_created"].append("incoming_data_events")
        print("   ✅ incoming_data_events table created")
    except Exception as e:
        if "already exists" in str(e).lower():
            results["skipped"].append("incoming_data_events table")
            print("   ⏭️  incoming_data_events table already exists")
        else:
            results["errors"].append(f"incoming_data_events: {str(e)[:100]}")
            print(f"   ❌ Error: {e}")

    # ================================================================
    # 7. Create extracted_data table
    # ================================================================
    print("\n7. Creating extracted_data table...")
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS extracted_data (
                id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES incoming_data_events(id) ON DELETE CASCADE,
                data_type VARCHAR(50),
                fields JSONB,
                match_entity_type VARCHAR(50),
                match_entity_id INTEGER,
                match_confidence FLOAT,
                status VARCHAR(50) DEFAULT 'pending_review',
                reviewed_by INTEGER REFERENCES users(id),
                reviewed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        results["tables_created"].append("extracted_data")
        print("   ✅ extracted_data table created")
    except Exception as e:
        if "already exists" in str(e).lower():
            results["skipped"].append("extracted_data table")
            print("   ⏭️  extracted_data table already exists")
        else:
            results["errors"].append(f"extracted_data: {str(e)[:100]}")
            print(f"   ❌ Error: {e}")

    # ================================================================
    # 8. Seed default permission templates
    # ================================================================
    print("\n8. Seeding default permission templates...")
    try:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM permission_templates WHERE name IN ('Management', 'Sales', 'Operations')
        """))
        count = result.scalar()

        if count == 0:
            management_perms = {
                "dashboard.view_all_widgets": True, "leads.view_all": True,
                "loans.view_all": True, "team.view_all": True,
                "team.manage_permissions": True, "permissions.view_all": True,
                "permissions.manage": True, "tasks.view_all": True
            }

            sales_perms = {
                "leads.view_assigned": True, "leads.create": True,
                "leads.edit_own": True, "loans.view_assigned": True,
                "tasks.view_assigned": True, "tasks.create": True
            }

            operations_perms = {
                "leads.view_all": True, "loans.view_all": True,
                "loans.process": True, "tasks.view_all": True
            }

            conn.execute(text("""
                INSERT INTO permission_templates (name, description, category, permissions, is_system_default)
                VALUES
                ('Management', 'Full access for management roles', 'management', :mgmt_perms, TRUE),
                ('Sales', 'Sales-focused permissions', 'sales', :sales_perms, TRUE),
                ('Operations', 'Operations-focused permissions', 'operations', :ops_perms, TRUE)
            """), {
                "mgmt_perms": json.dumps(management_perms),
                "sales_perms": json.dumps(sales_perms),
                "ops_perms": json.dumps(operations_perms)
            })
            conn.commit()
            results["tables_created"].append("permission_templates (seeded)")
            print("   ✅ Default permission templates seeded")
        else:
            results["skipped"].append("permission_templates (already seeded)")
            print("   ⏭️  Permission templates already exist")
    except Exception as e:
        results["errors"].append(f"permission_templates seeding: {str(e)[:100]}")
        print(f"   ❌ Error: {e}")

print("\n" + "="*60)
print("MIGRATION RESULTS")
print("="*60)
print(f"\n✅ Tables created: {results['tables_created']}")
print(f"✅ Columns added: {results['columns_added']}")
print(f"⏭️  Skipped (already exist): {results['skipped']}")
if results['errors']:
    print(f"❌ Errors: {results['errors']}")
print("\n🎉 Migration completed!")
