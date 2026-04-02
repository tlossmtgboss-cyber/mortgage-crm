"""
Seed Default Permission Templates Migration
Creates the three core permission templates: Management, Sales, and Operations

Run this after create_employee_permission_system.py

Author: System
Date: 2025-11-15
"""

from sqlalchemy import create_engine, text
from datetime import datetime
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
        "leads.view_territory": True,
        "leads.view_assigned": True,
        "leads.create": True,
        "leads.edit_all": True,
        "leads.edit_team": True,
        "leads.edit_own": True,
        "leads.delete": True,
        "leads.assign": True,
        "leads.reassign": True,
        "leads.export": True,
        "leads.import": True,
        "leads.merge": True,

        # Client Management
        "clients.view_all": True,
        "clients.view_team": True,
        "clients.view_territory": True,
        "clients.view_assigned": True,
        "clients.create": True,
        "clients.edit_all": True,
        "clients.edit_team": True,
        "clients.edit_own": True,
        "clients.delete": True,
        "clients.export": True,
        "clients.import": True,
        "clients.merge": True,

        # Loan Management
        "loans.view_all": True,
        "loans.view_team": True,
        "loans.view_territory": True,
        "loans.view_assigned": True,
        "loans.create": True,
        "loans.edit_all": True,
        "loans.edit_team": True,
        "loans.edit_own": True,
        "loans.delete": True,
        "loans.approve": True,
        "loans.reject": True,
        "loans.process": True,
        "loans.export": True,

        # Team Management
        "team.view_all": True,
        "team.view_team": True,
        "team.view_territory": True,
        "team.create_members": True,
        "team.edit_members": True,
        "team.delete_members": True,
        "team.manage_roles": True,
        "team.manage_permissions": True,
        "team.impersonate": True,
        "team.view_performance": True,
        "team.manage_territories": True,
        "team.manage_teams": True,

        # Reports & Compliance
        "reports.view_all": True,
        "reports.view_sales": True,
        "reports.view_operations": True,
        "reports.view_financial": True,
        "reports.view_compliance": True,
        "reports.export": True,
        "reports.schedule": True,
        "compliance.view_all": True,
        "compliance.certify": True,
        "compliance.audit": True,

        # System Administration
        "settings.view": True,
        "settings.edit_company": True,
        "settings.edit_integrations": True,
        "settings.edit_notifications": True,
        "settings.edit_workflows": True,
        "audit_logs.view_all": True,
        "audit_logs.export": True,
        "permissions.view_all": True,
        "permissions.manage": True,
        "permissions.create_templates": True,

        # Tasks & Activities
        "tasks.view_all": True,
        "tasks.view_team": True,
        "tasks.view_assigned": True,
        "tasks.create": True,
        "tasks.edit_all": True,
        "tasks.edit_own": True,
        "tasks.delete": True,
        "tasks.assign": True,

        # Documents
        "documents.view_all": True,
        "documents.view_team": True,
        "documents.view_assigned": True,
        "documents.upload": True,
        "documents.edit": True,
        "documents.delete": True,
        "documents.share": True,

        # Communications
        "communications.view_all": True,
        "communications.view_team": True,
        "communications.view_assigned": True,
        "communications.send_email": True,
        "communications.send_sms": True,
        "communications.make_calls": True,
        "communications.view_history": True,

        # AI Features
        "ai.use_assistant": True,
        "ai.use_smart_chat": True,
        "ai.use_voice": True,
        "ai.view_insights": True,
    }

def get_sales_permissions():
    """Sales-focused template with limited operations visibility"""
    return {
        # Dashboard & Analytics (Sales-focused)
        "dashboard.view_all_widgets": False,
        "dashboard.customize": True,
        "dashboard.export": True,
        "analytics.view_all": False,
        "analytics.export": True,

        # Lead Management (Full sales access)
        "leads.view_all": False,
        "leads.view_team": True,
        "leads.view_territory": True,
        "leads.view_assigned": True,
        "leads.create": True,
        "leads.edit_all": False,
        "leads.edit_team": False,
        "leads.edit_own": True,
        "leads.delete": False,
        "leads.assign": False,
        "leads.reassign": False,
        "leads.export": True,
        "leads.import": True,
        "leads.merge": False,

        # Client Management (Own clients only)
        "clients.view_all": False,
        "clients.view_team": True,
        "clients.view_territory": True,
        "clients.view_assigned": True,
        "clients.create": True,
        "clients.edit_all": False,
        "clients.edit_team": False,
        "clients.edit_own": True,
        "clients.delete": False,
        "clients.export": True,
        "clients.import": False,
        "clients.merge": False,

        # Loan Management (Own loans only)
        "loans.view_all": False,
        "loans.view_team": True,
        "loans.view_territory": True,
        "loans.view_assigned": True,
        "loans.create": True,
        "loans.edit_all": False,
        "loans.edit_team": False,
        "loans.edit_own": True,
        "loans.delete": False,
        "loans.approve": False,
        "loans.reject": False,
        "loans.process": False,
        "loans.export": True,

        # Team Management (Limited visibility)
        "team.view_all": False,
        "team.view_team": True,
        "team.view_territory": True,
        "team.create_members": False,
        "team.edit_members": False,
        "team.delete_members": False,
        "team.manage_roles": False,
        "team.manage_permissions": False,
        "team.impersonate": False,
        "team.view_performance": True,
        "team.manage_territories": False,
        "team.manage_teams": False,

        # Reports & Compliance (Sales only)
        "reports.view_all": False,
        "reports.view_sales": True,
        "reports.view_operations": False,
        "reports.view_financial": False,
        "reports.view_compliance": False,
        "reports.export": True,
        "reports.schedule": False,
        "compliance.view_all": False,
        "compliance.certify": False,
        "compliance.audit": False,

        # System Administration (No access)
        "settings.view": True,
        "settings.edit_company": False,
        "settings.edit_integrations": False,
        "settings.edit_notifications": True,
        "settings.edit_workflows": False,
        "audit_logs.view_all": False,
        "audit_logs.export": False,
        "permissions.view_all": False,
        "permissions.manage": False,
        "permissions.create_templates": False,

        # Tasks & Activities (Own tasks)
        "tasks.view_all": False,
        "tasks.view_team": True,
        "tasks.view_assigned": True,
        "tasks.create": True,
        "tasks.edit_all": False,
        "tasks.edit_own": True,
        "tasks.delete": False,
        "tasks.assign": True,

        # Documents (Own documents)
        "documents.view_all": False,
        "documents.view_team": True,
        "documents.view_assigned": True,
        "documents.upload": True,
        "documents.edit": True,
        "documents.delete": False,
        "documents.share": True,

        # Communications (Full access)
        "communications.view_all": False,
        "communications.view_team": True,
        "communications.view_assigned": True,
        "communications.send_email": True,
        "communications.send_sms": True,
        "communications.make_calls": True,
        "communications.view_history": True,

        # AI Features (Full access)
        "ai.use_assistant": True,
        "ai.use_smart_chat": True,
        "ai.use_voice": True,
        "ai.view_insights": True,
    }

def get_operations_permissions():
    """Operations-focused template with processing capabilities"""
    return {
        # Dashboard & Analytics (Operations-focused)
        "dashboard.view_all_widgets": False,
        "dashboard.customize": True,
        "dashboard.export": True,
        "analytics.view_all": False,
        "analytics.export": True,

        # Lead Management (View for processing)
        "leads.view_all": True,
        "leads.view_team": True,
        "leads.view_territory": True,
        "leads.view_assigned": True,
        "leads.create": False,
        "leads.edit_all": True,
        "leads.edit_team": True,
        "leads.edit_own": True,
        "leads.delete": False,
        "leads.assign": True,
        "leads.reassign": True,
        "leads.export": True,
        "leads.import": True,
        "leads.merge": True,

        # Client Management (Full processing access)
        "clients.view_all": True,
        "clients.view_team": True,
        "clients.view_territory": True,
        "clients.view_assigned": True,
        "clients.create": False,
        "clients.edit_all": True,
        "clients.edit_team": True,
        "clients.edit_own": True,
        "clients.delete": False,
        "clients.export": True,
        "clients.import": True,
        "clients.merge": True,

        # Loan Management (Full processing access)
        "loans.view_all": True,
        "loans.view_team": True,
        "loans.view_territory": True,
        "loans.view_assigned": True,
        "loans.create": True,
        "loans.edit_all": True,
        "loans.edit_team": True,
        "loans.edit_own": True,
        "loans.delete": False,
        "loans.approve": True,
        "loans.reject": True,
        "loans.process": True,
        "loans.export": True,

        # Team Management (Limited visibility)
        "team.view_all": False,
        "team.view_team": True,
        "team.view_territory": True,
        "team.create_members": False,
        "team.edit_members": False,
        "team.delete_members": False,
        "team.manage_roles": False,
        "team.manage_permissions": False,
        "team.impersonate": False,
        "team.view_performance": True,
        "team.manage_territories": False,
        "team.manage_teams": False,

        # Reports & Compliance (Operations focused)
        "reports.view_all": False,
        "reports.view_sales": False,
        "reports.view_operations": True,
        "reports.view_financial": True,
        "reports.view_compliance": True,
        "reports.export": True,
        "reports.schedule": False,
        "compliance.view_all": True,
        "compliance.certify": True,
        "compliance.audit": False,

        # System Administration (Limited)
        "settings.view": True,
        "settings.edit_company": False,
        "settings.edit_integrations": False,
        "settings.edit_notifications": True,
        "settings.edit_workflows": True,
        "audit_logs.view_all": False,
        "audit_logs.export": False,
        "permissions.view_all": False,
        "permissions.manage": False,
        "permissions.create_templates": False,

        # Tasks & Activities (Team tasks)
        "tasks.view_all": True,
        "tasks.view_team": True,
        "tasks.view_assigned": True,
        "tasks.create": True,
        "tasks.edit_all": True,
        "tasks.edit_own": True,
        "tasks.delete": False,
        "tasks.assign": True,

        # Documents (Full processing access)
        "documents.view_all": True,
        "documents.view_team": True,
        "documents.view_assigned": True,
        "documents.upload": True,
        "documents.edit": True,
        "documents.delete": False,
        "documents.share": True,

        # Communications (Full access)
        "communications.view_all": True,
        "communications.view_team": True,
        "communications.view_assigned": True,
        "communications.send_email": True,
        "communications.send_sms": True,
        "communications.make_calls": True,
        "communications.view_history": True,

        # AI Features (Full access)
        "ai.use_assistant": True,
        "ai.use_smart_chat": True,
        "ai.use_voice": True,
        "ai.view_insights": True,
    }

def run_migration():
    """Insert the three default permission templates"""

    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Create engine
    engine = create_engine(database_url)

    print("Starting seed data migration for default permission templates...")

    with engine.connect() as conn:
        # Check if templates already exist
        result = conn.execute(text("""
            SELECT COUNT(*) as count FROM permission_templates
            WHERE name IN ('Management', 'Sales', 'Operations')
        """))
        existing_count = result.fetchone()[0]

        if existing_count > 0:
            print(f"⚠️  Found {existing_count} existing templates. Skipping seed data.")
            print("To re-seed, delete existing templates first.")
            return

        # Insert Management Template
        print("📋 Creating Management template (full access)...")
        management_perms = get_management_permissions()
        conn.execute(text("""
            INSERT INTO permission_templates
            (name, description, permissions, is_system_default, category, created_by, created_at)
            VALUES
            (:name, :description, CAST(:permissions AS jsonb), :is_system, :category, 1, :created_at)
        """), {
            'name': 'Management',
            'description': 'Full access template for management and leadership roles. Includes all permissions for team management, reports, settings, and system administration.',
            'permissions': json.dumps(management_perms),
            'is_system': True,
            'category': 'management',
            'created_at': datetime.now(timezone.utc)
        })

        # Insert Sales Template
        print("📋 Creating Sales template (sales-focused)...")
        sales_perms = get_sales_permissions()
        conn.execute(text("""
            INSERT INTO permission_templates
            (name, description, permissions, is_system_default, category, created_by, created_at)
            VALUES
            (:name, :description, CAST(:permissions AS jsonb), :is_system, :category, 1, :created_at)
        """), {
            'name': 'Sales',
            'description': 'Sales-focused template for sales representatives and account executives. Full access to assigned leads, clients, and sales features. Limited visibility to operations and settings.',
            'permissions': json.dumps(sales_perms),
            'is_system': True,
            'category': 'sales',
            'created_at': datetime.now(timezone.utc)
        })

        # Insert Operations Template
        print("📋 Creating Operations template (operations-focused)...")
        operations_perms = get_operations_permissions()
        conn.execute(text("""
            INSERT INTO permission_templates
            (name, description, permissions, is_system_default, category, created_by, created_at)
            VALUES
            (:name, :description, CAST(:permissions AS jsonb), :is_system, :category, 1, :created_at)
        """), {
            'name': 'Operations',
            'description': 'Operations-focused template for loan processors, underwriters, and operations staff. Full access to loan processing, document management, and compliance features. Limited sales visibility.',
            'permissions': json.dumps(operations_perms),
            'is_system': True,
            'category': 'operations',
            'created_at': datetime.now(timezone.utc)
        })

        # Commit the transaction
        conn.commit()

        # Verify templates were created
        result = conn.execute(text("""
            SELECT id, name
            FROM permission_templates
            WHERE is_system_default = TRUE
            ORDER BY name
        """))

        print("\n✅ Default permission templates created successfully:\n")
        for row in result:
            # Count actual permissions from the Python objects
            if row[1] == 'Management':
                perm_count = len(get_management_permissions())
            elif row[1] == 'Sales':
                perm_count = len(get_sales_permissions())
            else:
                perm_count = len(get_operations_permissions())

            print(f"   • {row[1]} Template (ID: {row[0]}) - {perm_count} permissions")

        print("\n📊 Permission Summary:")
        print(f"   • Management: {len(get_management_permissions())} permissions (Full Access)")
        print(f"   • Sales: {len(get_sales_permissions())} permissions (Sales-Focused)")
        print(f"   • Operations: {len(get_operations_permissions())} permissions (Operations-Focused)")

        print("\n✅ Seed data migration completed successfully!")
        print("\nNext steps:")
        print("1. Apply these templates to employees via employee_permissions table")
        print("2. Build permission enforcement middleware")
        print("3. Implement Redis caching layer")

if __name__ == '__main__':
    run_migration()
