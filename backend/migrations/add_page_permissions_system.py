"""
Page Permissions System Migration
Creates tables for page-level access control and seeds default page definitions

This migration creates:
1. pages - Registry of all application pages/routes
2. page_permissions - Maps pages to permission requirements
3. page_category_permissions - Category-level permission defaults
4. user_page_overrides - User-specific page access overrides

Author: System
Date: 2025-01-03
"""

from sqlalchemy import create_engine, text
from datetime import datetime
import os
import json


def get_page_definitions():
    """Define all pages in the application with their metadata and default permissions"""
    return [
        # =====================================================================
        # DASHBOARD & HOME
        # =====================================================================
        {
            "path": "/dashboard",
            "name": "Dashboard",
            "category": "dashboard",
            "description": "Main dashboard with pipeline overview and metrics",
            "icon": "LayoutDashboard",
            "default_permissions": ["dashboard.view_all_widgets"],
            "min_role": "sales",
            "display_order": 1,
        },

        # =====================================================================
        # PIPELINE MANAGEMENT
        # =====================================================================
        {
            "path": "/leads",
            "name": "Leads",
            "category": "pipeline",
            "description": "Lead management and tracking",
            "icon": "Users",
            "default_permissions": ["leads.view_assigned"],
            "min_role": "sales",
            "display_order": 10,
        },
        {
            "path": "/leads/:id",
            "name": "Lead Detail",
            "category": "pipeline",
            "description": "Individual lead details and management",
            "icon": "User",
            "default_permissions": ["leads.view_assigned"],
            "min_role": "sales",
            "display_order": 11,
            "parent_path": "/leads",
        },
        {
            "path": "/clients",
            "name": "Clients",
            "category": "pipeline",
            "description": "Client management and tracking",
            "icon": "UserCheck",
            "default_permissions": ["clients.view_assigned"],
            "min_role": "sales",
            "display_order": 20,
        },
        {
            "path": "/clients/:id",
            "name": "Client Detail",
            "category": "pipeline",
            "description": "Individual client profile and history",
            "icon": "UserCheck",
            "default_permissions": ["clients.view_assigned"],
            "min_role": "sales",
            "display_order": 21,
            "parent_path": "/clients",
        },
        {
            "path": "/loans",
            "name": "Loans",
            "category": "pipeline",
            "description": "Loan pipeline management",
            "icon": "FileText",
            "default_permissions": ["loans.view_assigned"],
            "min_role": "sales",
            "display_order": 30,
        },
        {
            "path": "/loans/:id",
            "name": "Loan Detail",
            "category": "pipeline",
            "description": "Individual loan details and processing",
            "icon": "FileText",
            "default_permissions": ["loans.view_assigned"],
            "min_role": "sales",
            "display_order": 31,
            "parent_path": "/loans",
        },

        # =====================================================================
        # TASKS & WORKFLOW
        # =====================================================================
        {
            "path": "/tasks",
            "name": "Tasks",
            "category": "tasks",
            "description": "Task management and workflow",
            "icon": "CheckSquare",
            "default_permissions": ["tasks.view_assigned"],
            "min_role": "sales",
            "display_order": 40,
        },
        {
            "path": "/workflow",
            "name": "Workflow",
            "category": "tasks",
            "description": "Workflow automation and management",
            "icon": "GitBranch",
            "default_permissions": ["tasks.view_all"],
            "min_role": "operations",
            "display_order": 41,
        },

        # =====================================================================
        # CALENDAR & SCHEDULING
        # =====================================================================
        {
            "path": "/calendar",
            "name": "Calendar",
            "category": "calendar",
            "description": "Calendar and scheduling",
            "icon": "Calendar",
            "default_permissions": [],
            "min_role": "sales",
            "display_order": 50,
        },
        {
            "path": "/scheduler",
            "name": "Scheduler",
            "category": "calendar",
            "description": "Appointment scheduling",
            "icon": "Clock",
            "default_permissions": [],
            "min_role": "sales",
            "display_order": 51,
        },

        # =====================================================================
        # COMMUNICATION
        # =====================================================================
        {
            "path": "/email",
            "name": "Email",
            "category": "communication",
            "description": "Email management",
            "icon": "Mail",
            "default_permissions": [],
            "min_role": "sales",
            "display_order": 60,
        },
        {
            "path": "/sms",
            "name": "SMS",
            "category": "communication",
            "description": "SMS messaging",
            "icon": "MessageSquare",
            "default_permissions": [],
            "min_role": "sales",
            "display_order": 61,
        },

        # =====================================================================
        # DOCUMENTS
        # =====================================================================
        {
            "path": "/smart-docs",
            "name": "Smart Docs",
            "category": "documents",
            "description": "Document management with AI",
            "icon": "FileSearch",
            "default_permissions": [],
            "min_role": "sales",
            "display_order": 70,
        },
        {
            "path": "/smart-docs/dashboard",
            "name": "Smart Docs Dashboard",
            "category": "documents",
            "description": "Document status overview",
            "icon": "LayoutDashboard",
            "default_permissions": [],
            "min_role": "operations",
            "display_order": 71,
            "parent_path": "/smart-docs",
        },

        # =====================================================================
        # REPORTS & ANALYTICS
        # =====================================================================
        {
            "path": "/reports",
            "name": "Reports",
            "category": "reports",
            "description": "Business reports and analytics",
            "icon": "BarChart3",
            "default_permissions": ["reports.view_sales"],
            "min_role": "sales",
            "display_order": 80,
        },
        {
            "path": "/analytics",
            "name": "Analytics",
            "category": "reports",
            "description": "Advanced analytics dashboard",
            "icon": "TrendingUp",
            "default_permissions": ["analytics.view_all"],
            "min_role": "management",
            "display_order": 81,
        },
        {
            "path": "/profitability",
            "name": "Profitability",
            "category": "reports",
            "description": "Loan profitability analysis",
            "icon": "DollarSign",
            "default_permissions": ["reports.view_all"],
            "min_role": "management",
            "display_order": 82,
        },

        # =====================================================================
        # TEAM & HR
        # =====================================================================
        {
            "path": "/team",
            "name": "Team",
            "category": "team",
            "description": "Team member management",
            "icon": "Users",
            "default_permissions": ["team.view_team"],
            "min_role": "sales",
            "display_order": 90,
        },
        {
            "path": "/team/:id",
            "name": "Team Member Profile",
            "category": "team",
            "description": "Individual team member profile",
            "icon": "User",
            "default_permissions": ["team.view_team"],
            "min_role": "sales",
            "display_order": 91,
            "parent_path": "/team",
        },
        {
            "path": "/recruiting",
            "name": "Recruiting",
            "category": "team",
            "description": "Recruiting and hiring management",
            "icon": "UserPlus",
            "default_permissions": ["team.view_all"],
            "min_role": "management",
            "display_order": 92,
        },
        {
            "path": "/recruiting/candidates",
            "name": "Candidates",
            "category": "team",
            "description": "Candidate pipeline",
            "icon": "Users",
            "default_permissions": ["team.view_all"],
            "min_role": "management",
            "display_order": 93,
            "parent_path": "/recruiting",
        },
        {
            "path": "/onboarding",
            "name": "Onboarding",
            "category": "team",
            "description": "Employee onboarding",
            "icon": "Rocket",
            "default_permissions": ["team.view_all"],
            "min_role": "management",
            "display_order": 94,
        },

        # =====================================================================
        # MARKETING & CONTENT
        # =====================================================================
        {
            "path": "/marketing",
            "name": "Marketing",
            "category": "marketing",
            "description": "Marketing tools and campaigns",
            "icon": "Megaphone",
            "default_permissions": [],
            "min_role": "sales",
            "display_order": 100,
        },
        {
            "path": "/microsite/editor",
            "name": "Microsite Editor",
            "category": "marketing",
            "description": "Personal microsite management",
            "icon": "Globe",
            "default_permissions": [],
            "min_role": "sales",
            "display_order": 101,
        },
        {
            "path": "/ai-blog",
            "name": "AI Blog",
            "category": "marketing",
            "description": "AI-powered blog content generation",
            "icon": "PenTool",
            "default_permissions": [],
            "min_role": "sales",
            "display_order": 102,
        },
        {
            "path": "/video-os",
            "name": "Video OS",
            "category": "marketing",
            "description": "Video content creation",
            "icon": "Video",
            "default_permissions": [],
            "min_role": "sales",
            "display_order": 103,
        },

        # =====================================================================
        # PARTNER PORTALS
        # =====================================================================
        {
            "path": "/referral-partners",
            "name": "Referral Partners",
            "category": "partners",
            "description": "Referral partner management",
            "icon": "Handshake",
            "default_permissions": [],
            "min_role": "sales",
            "display_order": 110,
        },
        {
            "path": "/referral-partners/:id",
            "name": "Partner Detail",
            "category": "partners",
            "description": "Individual partner management",
            "icon": "User",
            "default_permissions": [],
            "min_role": "sales",
            "display_order": 111,
            "parent_path": "/referral-partners",
        },

        # =====================================================================
        # CONVERSATION INTELLIGENCE
        # =====================================================================
        {
            "path": "/conversation-intelligence",
            "name": "Conversation Intelligence",
            "category": "ai",
            "description": "Call recording and analysis",
            "icon": "Headphones",
            "default_permissions": [],
            "min_role": "management",
            "display_order": 120,
        },

        # =====================================================================
        # AI & AUTOMATION
        # =====================================================================
        {
            "path": "/ai-receptionist",
            "name": "AI Receptionist",
            "category": "ai",
            "description": "AI phone receptionist management",
            "icon": "Bot",
            "default_permissions": [],
            "min_role": "management",
            "display_order": 130,
        },
        {
            "path": "/ai-settings",
            "name": "AI Settings",
            "category": "ai",
            "description": "AI configuration and training",
            "icon": "Settings",
            "default_permissions": [],
            "min_role": "management",
            "display_order": 131,
        },

        # =====================================================================
        # ADMIN & SETTINGS
        # =====================================================================
        {
            "path": "/settings",
            "name": "Settings",
            "category": "admin",
            "description": "Application settings",
            "icon": "Settings",
            "default_permissions": ["settings.view"],
            "min_role": "sales",
            "display_order": 200,
        },
        {
            "path": "/settings/profile",
            "name": "Profile Settings",
            "category": "admin",
            "description": "User profile settings",
            "icon": "User",
            "default_permissions": ["settings.view"],
            "min_role": "sales",
            "display_order": 201,
            "parent_path": "/settings",
        },
        {
            "path": "/settings/integrations",
            "name": "Integrations",
            "category": "admin",
            "description": "Third-party integrations",
            "icon": "Plug",
            "default_permissions": ["settings.edit"],
            "min_role": "management",
            "display_order": 202,
            "parent_path": "/settings",
        },
        {
            "path": "/settings/permissions",
            "name": "Permissions",
            "category": "admin",
            "description": "User permissions management",
            "icon": "Shield",
            "default_permissions": ["permissions.manage"],
            "min_role": "management",
            "display_order": 203,
            "parent_path": "/settings",
        },
        {
            "path": "/admin",
            "name": "Admin",
            "category": "admin",
            "description": "System administration",
            "icon": "Shield",
            "default_permissions": ["permissions.manage"],
            "min_role": "management",
            "display_order": 210,
        },
        {
            "path": "/admin/users",
            "name": "User Management",
            "category": "admin",
            "description": "User account management",
            "icon": "Users",
            "default_permissions": ["permissions.manage"],
            "min_role": "management",
            "display_order": 211,
            "parent_path": "/admin",
        },
        {
            "path": "/admin/audit-log",
            "name": "Audit Log",
            "category": "admin",
            "description": "System audit trail",
            "icon": "FileText",
            "default_permissions": ["permissions.view_all"],
            "min_role": "management",
            "display_order": 212,
            "parent_path": "/admin",
        },
    ]


def get_page_categories():
    """Define page categories with their metadata"""
    return [
        {
            "code": "dashboard",
            "name": "Dashboard",
            "description": "Main dashboard and overview pages",
            "icon": "LayoutDashboard",
            "display_order": 1,
            "default_visible": True,
        },
        {
            "code": "pipeline",
            "name": "Pipeline",
            "description": "Lead, client, and loan management",
            "icon": "GitBranch",
            "display_order": 2,
            "default_visible": True,
        },
        {
            "code": "tasks",
            "name": "Tasks & Workflow",
            "description": "Task management and automation",
            "icon": "CheckSquare",
            "display_order": 3,
            "default_visible": True,
        },
        {
            "code": "calendar",
            "name": "Calendar",
            "description": "Calendar and scheduling",
            "icon": "Calendar",
            "display_order": 4,
            "default_visible": True,
        },
        {
            "code": "communication",
            "name": "Communication",
            "description": "Email and messaging",
            "icon": "MessageSquare",
            "display_order": 5,
            "default_visible": True,
        },
        {
            "code": "documents",
            "name": "Documents",
            "description": "Document management",
            "icon": "FileText",
            "display_order": 6,
            "default_visible": True,
        },
        {
            "code": "reports",
            "name": "Reports",
            "description": "Reports and analytics",
            "icon": "BarChart3",
            "display_order": 7,
            "default_visible": True,
        },
        {
            "code": "team",
            "name": "Team",
            "description": "Team and HR management",
            "icon": "Users",
            "display_order": 8,
            "default_visible": True,
        },
        {
            "code": "marketing",
            "name": "Marketing",
            "description": "Marketing tools and content",
            "icon": "Megaphone",
            "display_order": 9,
            "default_visible": True,
        },
        {
            "code": "partners",
            "name": "Partners",
            "description": "Partner portal management",
            "icon": "Handshake",
            "display_order": 10,
            "default_visible": True,
        },
        {
            "code": "ai",
            "name": "AI & Automation",
            "description": "AI tools and automation",
            "icon": "Bot",
            "display_order": 11,
            "default_visible": False,
        },
        {
            "code": "admin",
            "name": "Admin",
            "description": "Administration and settings",
            "icon": "Settings",
            "display_order": 99,
            "default_visible": True,
        },
    ]


def run_migration():
    """Execute the page permissions system migration"""

    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Fix postgres:// to postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    # Detect if SQLite
    is_sqlite = database_url.startswith("sqlite")

    # Create engine
    if is_sqlite:
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(database_url)

    print("🚀 Starting Page Permissions System Migration...\n")
    print(f"   Database: {'SQLite' if is_sqlite else 'PostgreSQL'}\n")

    with engine.connect() as conn:

        # Helper to execute multiple statements
        def execute_statements(statements):
            for stmt in statements:
                stmt = stmt.strip()
                if stmt:
                    try:
                        conn.execute(text(stmt))
                    except Exception as e:
                        # Ignore "already exists" errors
                        if "already exists" not in str(e).lower():
                            print(f"   ⚠️  Warning: {e}")

        # ====================================================================
        # STEP 1: Create page_categories table
        # ====================================================================
        print("📁 Step 1: Creating page_categories table...")

        if is_sqlite:
            execute_statements([
                """
                CREATE TABLE IF NOT EXISTS page_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    icon VARCHAR(50),
                    display_order INTEGER DEFAULT 0,
                    default_visible BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_page_categories_code ON page_categories(code)",
                "CREATE INDEX IF NOT EXISTS idx_page_categories_order ON page_categories(display_order)",
            ])
        else:
            execute_statements([
                """
                CREATE TABLE IF NOT EXISTS page_categories (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    icon VARCHAR(50),
                    display_order INTEGER DEFAULT 0,
                    default_visible BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_page_categories_code ON page_categories(code)",
                "CREATE INDEX IF NOT EXISTS idx_page_categories_order ON page_categories(display_order)",
            ])
        conn.commit()
        print("   ✅ Created page_categories table\n")

        # ====================================================================
        # STEP 2: Create pages table
        # ====================================================================
        print("📄 Step 2: Creating pages table...")

        if is_sqlite:
            execute_statements([
                """
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    category_id INTEGER REFERENCES page_categories(id),
                    category VARCHAR(50) NOT NULL,
                    icon VARCHAR(50),
                    parent_path VARCHAR(255),
                    display_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    requires_auth BOOLEAN DEFAULT 1,
                    min_role VARCHAR(50) DEFAULT 'sales',
                    default_permissions TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_pages_path ON pages(path)",
                "CREATE INDEX IF NOT EXISTS idx_pages_category ON pages(category)",
                "CREATE INDEX IF NOT EXISTS idx_pages_category_id ON pages(category_id)",
                "CREATE INDEX IF NOT EXISTS idx_pages_parent ON pages(parent_path)",
                "CREATE INDEX IF NOT EXISTS idx_pages_active ON pages(is_active)",
                "CREATE INDEX IF NOT EXISTS idx_pages_order ON pages(display_order)",
                "CREATE INDEX IF NOT EXISTS idx_pages_min_role ON pages(min_role)",
            ])
        else:
            execute_statements([
                """
                CREATE TABLE IF NOT EXISTS pages (
                    id SERIAL PRIMARY KEY,
                    path VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    category_id INTEGER REFERENCES page_categories(id),
                    category VARCHAR(50) NOT NULL,
                    icon VARCHAR(50),
                    parent_path VARCHAR(255),
                    display_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    requires_auth BOOLEAN DEFAULT TRUE,
                    min_role VARCHAR(50) DEFAULT 'sales',
                    default_permissions JSONB DEFAULT '[]',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT pages_min_role_check
                        CHECK (min_role IN ('sales', 'operations', 'management', 'admin'))
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_pages_path ON pages(path)",
                "CREATE INDEX IF NOT EXISTS idx_pages_category ON pages(category)",
                "CREATE INDEX IF NOT EXISTS idx_pages_category_id ON pages(category_id)",
                "CREATE INDEX IF NOT EXISTS idx_pages_parent ON pages(parent_path)",
                "CREATE INDEX IF NOT EXISTS idx_pages_active ON pages(is_active)",
                "CREATE INDEX IF NOT EXISTS idx_pages_order ON pages(display_order)",
                "CREATE INDEX IF NOT EXISTS idx_pages_min_role ON pages(min_role)",
            ])
        conn.commit()
        print("   ✅ Created pages table\n")

        # ====================================================================
        # STEP 3: Create page_permissions table
        # ====================================================================
        print("🔐 Step 3: Creating page_permissions table...")

        if is_sqlite:
            execute_statements([
                """
                CREATE TABLE IF NOT EXISTS page_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
                    permission_template_id INTEGER,
                    role VARCHAR(50),
                    can_view BOOLEAN DEFAULT 1,
                    can_edit BOOLEAN DEFAULT 0,
                    is_nav_visible BOOLEAN DEFAULT 1,
                    conditions TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (page_id, permission_template_id),
                    UNIQUE (page_id, role)
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_page_permissions_page ON page_permissions(page_id)",
                "CREATE INDEX IF NOT EXISTS idx_page_permissions_template ON page_permissions(permission_template_id)",
                "CREATE INDEX IF NOT EXISTS idx_page_permissions_role ON page_permissions(role)",
            ])
        else:
            execute_statements([
                """
                CREATE TABLE IF NOT EXISTS page_permissions (
                    id SERIAL PRIMARY KEY,
                    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
                    permission_template_id INTEGER REFERENCES permission_templates(id) ON DELETE CASCADE,
                    role VARCHAR(50),
                    can_view BOOLEAN DEFAULT TRUE,
                    can_edit BOOLEAN DEFAULT FALSE,
                    is_nav_visible BOOLEAN DEFAULT TRUE,
                    conditions JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT page_perm_role_or_template
                        CHECK (permission_template_id IS NOT NULL OR role IS NOT NULL),
                    CONSTRAINT page_perm_unique_template
                        UNIQUE (page_id, permission_template_id),
                    CONSTRAINT page_perm_unique_role
                        UNIQUE (page_id, role)
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_page_permissions_page ON page_permissions(page_id)",
                "CREATE INDEX IF NOT EXISTS idx_page_permissions_template ON page_permissions(permission_template_id)",
                "CREATE INDEX IF NOT EXISTS idx_page_permissions_role ON page_permissions(role)",
            ])
        conn.commit()
        print("   ✅ Created page_permissions table\n")

        # ====================================================================
        # STEP 4: Create user_page_overrides table
        # ====================================================================
        print("👤 Step 4: Creating user_page_overrides table...")

        if is_sqlite:
            execute_statements([
                """
                CREATE TABLE IF NOT EXISTS user_page_overrides (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
                    can_view BOOLEAN,
                    can_edit BOOLEAN,
                    is_nav_visible BOOLEAN,
                    is_pinned BOOLEAN DEFAULT 0,
                    pin_order INTEGER,
                    override_reason TEXT,
                    granted_by INTEGER REFERENCES users(id),
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, page_id)
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_user_page_overrides_user ON user_page_overrides(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_user_page_overrides_page ON user_page_overrides(page_id)",
            ])
        else:
            execute_statements([
                """
                CREATE TABLE IF NOT EXISTS user_page_overrides (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
                    can_view BOOLEAN,
                    can_edit BOOLEAN,
                    is_nav_visible BOOLEAN,
                    is_pinned BOOLEAN DEFAULT FALSE,
                    pin_order INTEGER,
                    override_reason TEXT,
                    granted_by INTEGER REFERENCES users(id),
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_user_page_override
                        UNIQUE (user_id, page_id)
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_user_page_overrides_user ON user_page_overrides(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_user_page_overrides_page ON user_page_overrides(page_id)",
            ])
        conn.commit()
        print("   ✅ Created user_page_overrides table\n")

        # ====================================================================
        # STEP 5: Create page_access_log table
        # ====================================================================
        print("📊 Step 5: Creating page_access_log table...")

        if is_sqlite:
            execute_statements([
                """
                CREATE TABLE IF NOT EXISTS page_access_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES users(id),
                    page_id INTEGER REFERENCES pages(id),
                    page_path VARCHAR(255) NOT NULL,
                    access_type VARCHAR(20) DEFAULT 'view',
                    access_granted BOOLEAN NOT NULL,
                    denial_reason VARCHAR(255),
                    ip_address VARCHAR(50),
                    user_agent TEXT,
                    session_id VARCHAR(255),
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_page_access_log_user ON page_access_log(user_id, accessed_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_page_access_log_page ON page_access_log(page_id, accessed_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_page_access_log_time ON page_access_log(accessed_at DESC)",
            ])
        else:
            execute_statements([
                """
                CREATE TABLE IF NOT EXISTS page_access_log (
                    id BIGSERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    page_id INTEGER REFERENCES pages(id),
                    page_path VARCHAR(255) NOT NULL,
                    access_type VARCHAR(20) DEFAULT 'view',
                    access_granted BOOLEAN NOT NULL,
                    denial_reason VARCHAR(255),
                    ip_address VARCHAR(50),
                    user_agent TEXT,
                    session_id VARCHAR(255),
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT page_access_type_check
                        CHECK (access_type IN ('view', 'edit', 'denied'))
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_page_access_log_user ON page_access_log(user_id, accessed_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_page_access_log_page ON page_access_log(page_id, accessed_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_page_access_log_time ON page_access_log(accessed_at DESC)",
            ])
        conn.commit()
        print("   ✅ Created page_access_log table\n")

        # ====================================================================
        # STEP 6: Seed page categories
        # ====================================================================
        print("🌱 Step 6: Seeding page categories...")

        categories = get_page_categories()

        for cat in categories:
            if is_sqlite:
                # SQLite doesn't support ON CONFLICT ... DO UPDATE in all versions
                # Check if exists first
                existing = conn.execute(text(
                    "SELECT id FROM page_categories WHERE code = :code"
                ), {"code": cat["code"]}).fetchone()

                if existing:
                    conn.execute(text("""
                        UPDATE page_categories SET
                            name = :name,
                            description = :description,
                            icon = :icon,
                            display_order = :display_order,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE code = :code
                    """), cat)
                else:
                    conn.execute(text("""
                        INSERT INTO page_categories (code, name, description, icon, display_order, default_visible)
                        VALUES (:code, :name, :description, :icon, :display_order, :default_visible)
                    """), cat)
            else:
                conn.execute(text("""
                    INSERT INTO page_categories (code, name, description, icon, display_order, default_visible)
                    VALUES (:code, :name, :description, :icon, :display_order, :default_visible)
                    ON CONFLICT (code) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        icon = EXCLUDED.icon,
                        display_order = EXCLUDED.display_order,
                        updated_at = CURRENT_TIMESTAMP
                """), cat)

        conn.commit()
        print(f"   ✅ Seeded {len(categories)} page categories\n")

        # ====================================================================
        # STEP 7: Seed page definitions
        # ====================================================================
        print("📄 Step 7: Seeding page definitions...")

        pages = get_page_definitions()

        # First, get category IDs
        cat_result = conn.execute(text("SELECT id, code FROM page_categories"))
        category_map = {row[1]: row[0] for row in cat_result}

        for page in pages:
            category_id = category_map.get(page["category"])
            page_data = {
                "path": page["path"],
                "name": page["name"],
                "description": page["description"],
                "category_id": category_id,
                "category": page["category"],
                "icon": page.get("icon"),
                "parent_path": page.get("parent_path"),
                "display_order": page.get("display_order", 0),
                "min_role": page.get("min_role", "sales"),
                "default_permissions": json.dumps(page.get("default_permissions", [])),
            }

            if is_sqlite:
                # Check if exists first
                existing = conn.execute(text(
                    "SELECT id FROM pages WHERE path = :path"
                ), {"path": page["path"]}).fetchone()

                if existing:
                    conn.execute(text("""
                        UPDATE pages SET
                            name = :name,
                            description = :description,
                            category_id = :category_id,
                            category = :category,
                            icon = :icon,
                            parent_path = :parent_path,
                            display_order = :display_order,
                            min_role = :min_role,
                            default_permissions = :default_permissions,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE path = :path
                    """), page_data)
                else:
                    conn.execute(text("""
                        INSERT INTO pages (
                            path, name, description, category_id, category, icon,
                            parent_path, display_order, min_role, default_permissions
                        )
                        VALUES (
                            :path, :name, :description, :category_id, :category, :icon,
                            :parent_path, :display_order, :min_role, :default_permissions
                        )
                    """), page_data)
            else:
                conn.execute(text("""
                    INSERT INTO pages (
                        path, name, description, category_id, category, icon,
                        parent_path, display_order, min_role, default_permissions
                    )
                    VALUES (
                        :path, :name, :description, :category_id, :category, :icon,
                        :parent_path, :display_order, :min_role, :default_permissions::jsonb
                    )
                    ON CONFLICT (path) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        category_id = EXCLUDED.category_id,
                        category = EXCLUDED.category,
                        icon = EXCLUDED.icon,
                        parent_path = EXCLUDED.parent_path,
                        display_order = EXCLUDED.display_order,
                        min_role = EXCLUDED.min_role,
                        default_permissions = EXCLUDED.default_permissions,
                        updated_at = CURRENT_TIMESTAMP
                """), page_data)

        conn.commit()
        print(f"   ✅ Seeded {len(pages)} page definitions\n")

        # ====================================================================
        # STEP 8: Create default page permissions for roles
        # ====================================================================
        print("🔑 Step 8: Creating default role-based page permissions...")

        # Get all pages with their IDs
        page_result = conn.execute(text("SELECT id, path, min_role FROM pages"))
        page_data = [(row[0], row[1], row[2]) for row in page_result]

        role_hierarchy = {
            "sales": 1,
            "operations": 2,
            "management": 3,
            "admin": 4,
        }

        roles = ["sales", "operations", "management"]

        for page_id, path, min_role in page_data:
            min_role_level = role_hierarchy.get(min_role, 1)

            for role in roles:
                role_level = role_hierarchy.get(role, 1)
                can_view = role_level >= min_role_level
                can_edit = role == "management" or role_level > min_role_level

                perm_data = {
                    "page_id": page_id,
                    "role": role,
                    "can_view": 1 if can_view else 0 if is_sqlite else can_view,
                    "can_edit": 1 if can_edit else 0 if is_sqlite else can_edit,
                    "is_nav_visible": 1 if can_view else 0 if is_sqlite else can_view,
                }

                try:
                    if is_sqlite:
                        # Check if exists
                        existing = conn.execute(text(
                            "SELECT id FROM page_permissions WHERE page_id = :page_id AND role = :role"
                        ), {"page_id": page_id, "role": role}).fetchone()

                        if existing:
                            conn.execute(text("""
                                UPDATE page_permissions SET
                                    can_view = :can_view,
                                    can_edit = :can_edit,
                                    is_nav_visible = :is_nav_visible,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE page_id = :page_id AND role = :role
                            """), perm_data)
                        else:
                            conn.execute(text("""
                                INSERT INTO page_permissions (page_id, role, can_view, can_edit, is_nav_visible)
                                VALUES (:page_id, :role, :can_view, :can_edit, :is_nav_visible)
                            """), perm_data)
                    else:
                        conn.execute(text("""
                            INSERT INTO page_permissions (page_id, role, can_view, can_edit, is_nav_visible)
                            VALUES (:page_id, :role, :can_view, :can_edit, :is_nav_visible)
                            ON CONFLICT (page_id, role) DO UPDATE SET
                                can_view = EXCLUDED.can_view,
                                can_edit = EXCLUDED.can_edit,
                                updated_at = CURRENT_TIMESTAMP
                        """), perm_data)
                except Exception as e:
                    # Skip duplicates or other errors
                    pass

        conn.commit()
        print(f"   ✅ Created role-based page permissions\n")

        # ====================================================================
        # STEP 9: Create helper functions (PostgreSQL only)
        # ====================================================================
        print("🔧 Step 9: Creating helper functions...")

        if is_sqlite:
            print("   ⚠️  Skipping PL/pgSQL functions (SQLite mode)\n")
        else:
            try:
                conn.execute(text("""
                    CREATE OR REPLACE FUNCTION user_can_access_page(
                        p_user_id INTEGER,
                        p_page_path VARCHAR
                    )
                    RETURNS TABLE (
                        can_view BOOLEAN,
                        can_edit BOOLEAN,
                        is_nav_visible BOOLEAN,
                        access_source VARCHAR
                    ) AS $$
                    DECLARE
                        v_page_id INTEGER;
                        v_user_role VARCHAR;
                        v_override RECORD;
                        v_role_perm RECORD;
                    BEGIN
                        -- Get page ID
                        SELECT id INTO v_page_id FROM pages WHERE path = p_page_path AND is_active = TRUE;
                        IF v_page_id IS NULL THEN
                            RETURN QUERY SELECT FALSE, FALSE, FALSE, 'page_not_found'::VARCHAR;
                            RETURN;
                        END IF;

                        -- Check user override first (highest priority)
                        SELECT upo.can_view, upo.can_edit, upo.is_nav_visible
                        INTO v_override
                        FROM user_page_overrides upo
                        WHERE upo.user_id = p_user_id
                            AND upo.page_id = v_page_id
                            AND (upo.expires_at IS NULL OR upo.expires_at > CURRENT_TIMESTAMP);

                        IF FOUND THEN
                            RETURN QUERY SELECT
                                COALESCE(v_override.can_view, TRUE),
                                COALESCE(v_override.can_edit, FALSE),
                                COALESCE(v_override.is_nav_visible, TRUE),
                                'user_override'::VARCHAR;
                            RETURN;
                        END IF;

                        -- Get user role
                        SELECT permission_role INTO v_user_role FROM users WHERE id = p_user_id;
                        IF v_user_role IS NULL THEN
                            v_user_role := 'sales';
                        END IF;

                        -- Check role-based permissions
                        SELECT pp.can_view, pp.can_edit, pp.is_nav_visible
                        INTO v_role_perm
                        FROM page_permissions pp
                        WHERE pp.page_id = v_page_id AND pp.role = v_user_role;

                        IF FOUND THEN
                            RETURN QUERY SELECT
                                v_role_perm.can_view,
                                v_role_perm.can_edit,
                                v_role_perm.is_nav_visible,
                                'role_permission'::VARCHAR;
                            RETURN;
                        END IF;

                        -- Default: check min_role
                        RETURN QUERY SELECT TRUE, FALSE, TRUE, 'default'::VARCHAR;
                    END;
                    $$ LANGUAGE plpgsql;
                """))

                conn.execute(text("""
                    CREATE OR REPLACE FUNCTION get_user_accessible_pages(
                        p_user_id INTEGER
                    )
                    RETURNS TABLE (
                        page_id INTEGER,
                        path VARCHAR,
                        name VARCHAR,
                        category VARCHAR,
                        icon VARCHAR,
                        parent_path VARCHAR,
                        display_order INTEGER,
                        can_view BOOLEAN,
                        can_edit BOOLEAN,
                        is_pinned BOOLEAN,
                        pin_order INTEGER
                    ) AS $$
                    BEGIN
                        RETURN QUERY
                        SELECT
                            p.id,
                            p.path,
                            p.name,
                            p.category,
                            p.icon,
                            p.parent_path,
                            p.display_order,
                            COALESCE(upo.can_view, pp.can_view, TRUE) as can_view,
                            COALESCE(upo.can_edit, pp.can_edit, FALSE) as can_edit,
                            COALESCE(upo.is_pinned, FALSE) as is_pinned,
                            upo.pin_order
                        FROM pages p
                        LEFT JOIN user_page_overrides upo ON upo.page_id = p.id
                            AND upo.user_id = p_user_id
                            AND (upo.expires_at IS NULL OR upo.expires_at > CURRENT_TIMESTAMP)
                        LEFT JOIN page_permissions pp ON pp.page_id = p.id
                            AND pp.role = (SELECT permission_role FROM users WHERE id = p_user_id)
                        WHERE p.is_active = TRUE
                            AND COALESCE(upo.is_nav_visible, pp.is_nav_visible, TRUE) = TRUE
                        ORDER BY
                            COALESCE(upo.is_pinned, FALSE) DESC,
                            upo.pin_order NULLS LAST,
                            p.display_order;
                    END;
                    $$ LANGUAGE plpgsql;
                """))

                conn.commit()
                print("   ✅ Created helper functions\n")
            except Exception as e:
                print(f"   ⚠️  Warning creating functions: {e}\n")

        # ====================================================================
        # STEP 10: Verify migration
        # ====================================================================
        print("✅ Step 10: Verifying migration...")

        # Count tables
        page_count = conn.execute(text("SELECT COUNT(*) FROM pages")).fetchone()[0]
        cat_count = conn.execute(text("SELECT COUNT(*) FROM page_categories")).fetchone()[0]
        perm_count = conn.execute(text("SELECT COUNT(*) FROM page_permissions")).fetchone()[0]

        print("\n" + "=" * 60)
        print("📊 PAGE PERMISSIONS MIGRATION SUMMARY")
        print("=" * 60)
        print(f"\n✅ Tables Created:")
        print("   • page_categories")
        print("   • pages")
        print("   • page_permissions")
        print("   • user_page_overrides")
        print("   • page_access_log")
        print(f"\n✅ Data Seeded:")
        print(f"   • {cat_count} page categories")
        print(f"   • {page_count} pages")
        print(f"   • {perm_count} page permissions")
        print(f"\n✅ Functions Created:")
        print("   • user_can_access_page()")
        print("   • get_user_accessible_pages()")
        print("\n" + "=" * 60)
        print("🎉 Page Permissions Migration Completed Successfully!\n")


if __name__ == '__main__':
    run_migration()
