"""
Page-Based Permissions System Migration
Creates tables for page-level role-based access control (RBAC)
Perennia AI - TL Development LLC

This migration creates:
1. pages - All available pages/routes in the system
2. permission_roles - Role definitions (loan_officer, branch_manager, etc.)
3. role_page_permissions - Maps roles to pages
4. user_page_overrides - Custom permissions per user
5. page_permission_audit_log - Track all permission changes

Author: Claude Code
Date: 2025-01-03
"""

from sqlalchemy import create_engine, text
from datetime import datetime
import os
import json


# =============================================================================
# PAGE DEFINITIONS
# =============================================================================

def get_all_pages():
    """All available pages in the system organized by category"""
    return [
        # Dashboard & Home
        {"page_key": "DASHBOARD", "name": "Dashboard", "path": "/dashboard", "category": "Dashboard", "stage": "all", "display_order": 1},
        {"page_key": "COMMAND_CENTER", "name": "Command Center", "path": "/command-center", "category": "Dashboard", "stage": "all", "display_order": 2},

        # Lead Management
        {"page_key": "LEADS_LIST", "name": "Leads List", "path": "/leads", "category": "Lead Management", "stage": "lead", "display_order": 10},
        {"page_key": "LEAD_DETAIL", "name": "Lead Detail", "path": "/leads/:id", "category": "Lead Management", "stage": "lead", "display_order": 11},
        {"page_key": "LEAD_CREATE", "name": "Create Lead", "path": "/leads/new", "category": "Lead Management", "stage": "lead", "display_order": 12},
        {"page_key": "LEAD_IMPORT", "name": "Import Leads", "path": "/leads/import", "category": "Lead Management", "stage": "lead", "display_order": 13},
        {"page_key": "LEAD_ASSIGNMENT", "name": "Lead Assignment", "path": "/leads/assignment", "category": "Lead Management", "stage": "lead", "display_order": 14},

        # Active Loans / Pipeline
        {"page_key": "PIPELINE", "name": "Loan Pipeline", "path": "/pipeline", "category": "Active Loans", "stage": "active_loan", "display_order": 20},
        {"page_key": "LOAN_DETAIL", "name": "Loan Detail", "path": "/loans/:id", "category": "Active Loans", "stage": "active_loan", "display_order": 21},
        {"page_key": "LOAN_CREATE", "name": "Create Loan", "path": "/loans/new", "category": "Active Loans", "stage": "active_loan", "display_order": 22},
        {"page_key": "LOAN_MILESTONES", "name": "Milestones Tracker", "path": "/loans/:id/milestones", "category": "Active Loans", "stage": "active_loan", "display_order": 23},
        {"page_key": "LOAN_CONDITIONS", "name": "Conditions Manager", "path": "/loans/:id/conditions", "category": "Active Loans", "stage": "active_loan", "display_order": 24},
        {"page_key": "LOAN_DOCUMENTS", "name": "Document Manager", "path": "/loans/:id/documents", "category": "Active Loans", "stage": "active_loan", "display_order": 25},
        {"page_key": "RATE_LOCK", "name": "Rate Lock Advisory", "path": "/rate-lock", "category": "Active Loans", "stage": "active_loan", "display_order": 26},

        # Portfolio Management
        {"page_key": "PORTFOLIO", "name": "Portfolio Overview", "path": "/portfolio", "category": "Portfolio", "stage": "portfolio", "display_order": 30},
        {"page_key": "PORTFOLIO_PERFORMANCE", "name": "Performance Analytics", "path": "/portfolio/performance", "category": "Portfolio", "stage": "portfolio", "display_order": 31},
        {"page_key": "PORTFOLIO_RETENTION", "name": "Retention Dashboard", "path": "/portfolio/retention", "category": "Portfolio", "stage": "portfolio", "display_order": 32},
        {"page_key": "PORTFOLIO_CROSSSELL", "name": "Cross-Sell Opportunities", "path": "/portfolio/cross-sell", "category": "Portfolio", "stage": "portfolio", "display_order": 33},

        # Partners & Referrals
        {"page_key": "PARTNERS_LIST", "name": "Partners List", "path": "/partners", "category": "Partners", "stage": "lead", "display_order": 40},
        {"page_key": "PARTNER_DETAIL", "name": "Partner Detail", "path": "/partners/:id", "category": "Partners", "stage": "lead", "display_order": 41},
        {"page_key": "PARTNER_CREATE", "name": "Add Partner", "path": "/partners/new", "category": "Partners", "stage": "lead", "display_order": 42},
        {"page_key": "PARTNER_SCOREBOARD", "name": "Referral Scoreboard", "path": "/partners/scoreboard", "category": "Partners", "stage": "lead", "display_order": 43},
        {"page_key": "PARTNER_UPDATES", "name": "Partner Updates", "path": "/partners/updates", "category": "Partners", "stage": "lead", "display_order": 44},

        # Communication Hub
        {"page_key": "INBOX", "name": "Inbox", "path": "/inbox", "category": "Communication", "stage": "all", "display_order": 50},
        {"page_key": "EMAIL_TEMPLATES", "name": "Email Templates", "path": "/templates/email", "category": "Communication", "stage": "all", "display_order": 51},
        {"page_key": "SMS_TEMPLATES", "name": "SMS Templates", "path": "/templates/sms", "category": "Communication", "stage": "all", "display_order": 52},
        {"page_key": "VOICEMAIL_DROP", "name": "Voicemail Drop", "path": "/voicemail-drop", "category": "Communication", "stage": "all", "display_order": 53},
        {"page_key": "POWER_DIALER", "name": "Power Dialer", "path": "/power-dialer", "category": "Communication", "stage": "all", "display_order": 54},
        {"page_key": "CALL_LOG", "name": "Call Log", "path": "/calls", "category": "Communication", "stage": "all", "display_order": 55},

        # Task & Workflow
        {"page_key": "TASKS", "name": "My Tasks", "path": "/tasks", "category": "Tasks & Workflow", "stage": "all", "display_order": 60},
        {"page_key": "WORKFLOWS", "name": "Workflow Manager", "path": "/workflows", "category": "Tasks & Workflow", "stage": "all", "display_order": 61},
        {"page_key": "WORKFLOW_BUILDER", "name": "Workflow Builder", "path": "/workflows/builder", "category": "Tasks & Workflow", "stage": "all", "display_order": 62},
        {"page_key": "AUTOMATIONS", "name": "Automations", "path": "/automations", "category": "Tasks & Workflow", "stage": "all", "display_order": 63},

        # Reports & Analytics
        {"page_key": "REPORTS_DASHBOARD", "name": "Reports Dashboard", "path": "/reports", "category": "Reports", "stage": "all", "display_order": 70},
        {"page_key": "REPORTS_PRODUCTION", "name": "Production Report", "path": "/reports/production", "category": "Reports", "stage": "all", "display_order": 71},
        {"page_key": "REPORTS_PIPELINE", "name": "Pipeline Report", "path": "/reports/pipeline", "category": "Reports", "stage": "active_loan", "display_order": 72},
        {"page_key": "REPORTS_CONVERSION", "name": "Conversion Report", "path": "/reports/conversion", "category": "Reports", "stage": "lead", "display_order": 73},
        {"page_key": "REPORTS_PARTNER", "name": "Partner Performance", "path": "/reports/partners", "category": "Reports", "stage": "lead", "display_order": 74},
        {"page_key": "REPORTS_PROFITABILITY", "name": "Profitability Analysis", "path": "/reports/profitability", "category": "Reports", "stage": "all", "display_order": 75},
        {"page_key": "REPORTS_SLA", "name": "SLA Tracking", "path": "/reports/sla", "category": "Reports", "stage": "active_loan", "display_order": 76},
        {"page_key": "REPORTS_TEAM", "name": "Team Performance", "path": "/reports/team", "category": "Reports", "stage": "all", "display_order": 77},

        # AI & Agents
        {"page_key": "AGENTS_DASHBOARD", "name": "Agent Dashboard", "path": "/agents", "category": "AI & Agents", "stage": "all", "display_order": 80},
        {"page_key": "AGENT_PROFILE", "name": "Agent Profiles", "path": "/agent/:id", "category": "AI & Agents", "stage": "all", "display_order": 81},
        {"page_key": "AGENT_GYM", "name": "Agent Gym", "path": "/agent-gym", "category": "AI & Agents", "stage": "all", "display_order": 82},
        {"page_key": "AI_RECEPTIONIST", "name": "AI Receptionist", "path": "/ai-receptionist", "category": "AI & Agents", "stage": "all", "display_order": 83},
        {"page_key": "CONVERSATION_INTEL", "name": "Conversation Intelligence", "path": "/conversation-intelligence", "category": "AI & Agents", "stage": "all", "display_order": 84},

        # Team Management
        {"page_key": "TEAM_LIST", "name": "Team Members", "path": "/team", "category": "Team", "stage": "all", "display_order": 90},
        {"page_key": "EMPLOYEE_PROFILE", "name": "Employee Profile", "path": "/team/:id", "category": "Team", "stage": "all", "display_order": 91},
        {"page_key": "EMPLOYEE_CREATE", "name": "Add Employee", "path": "/team/new", "category": "Team", "stage": "all", "display_order": 92},
        {"page_key": "EMPLOYEE_IMPORT", "name": "Import Employees", "path": "/team/import", "category": "Team", "stage": "all", "display_order": 93},
        {"page_key": "TEAM_SCORECARDS", "name": "Team Scorecards", "path": "/team/scorecards", "category": "Team", "stage": "all", "display_order": 94},
        {"page_key": "EMPLOYEE_IMPERSONATE", "name": "Impersonate User", "path": "/impersonate", "category": "Team", "stage": "all", "display_order": 95},

        # Settings
        {"page_key": "SETTINGS_ACCOUNT", "name": "Account Settings", "path": "/settings/account", "category": "Settings", "stage": "all", "display_order": 100},
        {"page_key": "SETTINGS_PROFILE", "name": "Profile Settings", "path": "/settings/profile", "category": "Settings", "stage": "all", "display_order": 101},
        {"page_key": "SETTINGS_NOTIFICATIONS", "name": "Notification Settings", "path": "/settings/notifications", "category": "Settings", "stage": "all", "display_order": 102},
        {"page_key": "SETTINGS_INTEGRATIONS", "name": "Integrations", "path": "/settings/integrations", "category": "Settings", "stage": "all", "display_order": 103},
        {"page_key": "SETTINGS_EMAIL_SYNC", "name": "Email Sync", "path": "/settings/email-sync", "category": "Settings", "stage": "all", "display_order": 104},
        {"page_key": "SETTINGS_TELEPHONY", "name": "Telephony Settings", "path": "/settings/telephony", "category": "Settings", "stage": "all", "display_order": 105},
        {"page_key": "SETTINGS_AI_PREFS", "name": "AI Preferences", "path": "/settings/ai", "category": "Settings", "stage": "all", "display_order": 106},
        {"page_key": "SETTINGS_AGENT_GOVERNANCE", "name": "Agent Governance", "path": "/settings/agent-governance", "category": "Settings", "stage": "all", "display_order": 107},

        # Admin Only
        {"page_key": "ADMIN_PERMISSIONS", "name": "Permissions", "path": "/admin/permissions", "category": "Admin", "stage": "all", "display_order": 110},
        {"page_key": "ADMIN_SUBSCRIPTIONS", "name": "Subscription Management", "path": "/admin/subscriptions", "category": "Admin", "stage": "all", "display_order": 111},
        {"page_key": "ADMIN_BILLING", "name": "Billing", "path": "/admin/billing", "category": "Admin", "stage": "all", "display_order": 112},
        {"page_key": "ADMIN_AUDIT_LOG", "name": "Audit Log", "path": "/admin/audit-log", "category": "Admin", "stage": "all", "display_order": 113},
        {"page_key": "ADMIN_SYSTEM_HEALTH", "name": "System Health", "path": "/admin/health", "category": "Admin", "stage": "all", "display_order": 114},
        {"page_key": "ADMIN_COMPANY", "name": "Company Settings", "path": "/admin/company", "category": "Admin", "stage": "all", "display_order": 115},
    ]


# =============================================================================
# ROLE DEFINITIONS
# =============================================================================

def get_role_definitions():
    """All available roles in the system"""
    return [
        {"role_key": "loan_officer", "name": "Loan Officer", "description": "Individual loan originator with client-facing responsibilities", "color": "blue", "icon": "Users", "hierarchy_level": 10, "is_system_role": True},
        {"role_key": "branch_manager", "name": "Branch Manager", "description": "Manages a branch office and its loan officers", "color": "green", "icon": "Building2", "hierarchy_level": 30, "is_system_role": True},
        {"role_key": "area_manager", "name": "Area Manager", "description": "Oversees multiple branches within an area", "color": "purple", "icon": "MapPin", "hierarchy_level": 50, "is_system_role": True},
        {"role_key": "regional_manager", "name": "Regional Manager", "description": "Manages multiple areas within a region", "color": "orange", "icon": "Globe", "hierarchy_level": 70, "is_system_role": True},
        {"role_key": "production_assistant", "name": "Production Assistant", "description": "Supports loan officers with administrative tasks", "color": "pink", "icon": "Headphones", "hierarchy_level": 5, "is_system_role": True},
        {"role_key": "processor", "name": "Processor", "description": "Handles loan processing and documentation", "color": "cyan", "icon": "FileCheck", "hierarchy_level": 15, "is_system_role": True},
        {"role_key": "evp", "name": "EVP", "description": "Executive Vice President with broad access", "color": "amber", "icon": "Crown", "hierarchy_level": 90, "is_system_role": True},
        {"role_key": "administrator", "name": "Administrator", "description": "Full system access and configuration rights", "color": "red", "icon": "Settings", "hierarchy_level": 100, "is_system_role": True},
    ]


# =============================================================================
# DEFAULT PERMISSIONS PER ROLE
# =============================================================================

def get_default_permissions():
    """Default page access permissions for each role"""
    return {
        "loan_officer": [
            "DASHBOARD", "LEADS_LIST", "LEAD_DETAIL", "LEAD_CREATE", "PIPELINE", "LOAN_DETAIL",
            "LOAN_MILESTONES", "LOAN_CONDITIONS", "LOAN_DOCUMENTS", "PARTNERS_LIST", "PARTNER_DETAIL",
            "PARTNER_CREATE", "INBOX", "EMAIL_TEMPLATES", "SMS_TEMPLATES", "VOICEMAIL_DROP",
            "POWER_DIALER", "CALL_LOG", "TASKS", "REPORTS_PRODUCTION", "SETTINGS_ACCOUNT",
            "SETTINGS_PROFILE", "SETTINGS_NOTIFICATIONS", "SETTINGS_AI_PREFS"
        ],
        "branch_manager": [
            "DASHBOARD", "COMMAND_CENTER", "LEADS_LIST", "LEAD_DETAIL", "LEAD_CREATE", "LEAD_IMPORT",
            "LEAD_ASSIGNMENT", "PIPELINE", "LOAN_DETAIL", "LOAN_CREATE", "LOAN_MILESTONES",
            "LOAN_CONDITIONS", "LOAN_DOCUMENTS", "RATE_LOCK", "PARTNERS_LIST", "PARTNER_DETAIL",
            "PARTNER_CREATE", "PARTNER_SCOREBOARD", "PARTNER_UPDATES", "INBOX", "EMAIL_TEMPLATES",
            "SMS_TEMPLATES", "VOICEMAIL_DROP", "POWER_DIALER", "CALL_LOG", "TASKS", "WORKFLOWS",
            "REPORTS_DASHBOARD", "REPORTS_PRODUCTION", "REPORTS_PIPELINE", "REPORTS_CONVERSION",
            "REPORTS_PARTNER", "REPORTS_TEAM", "TEAM_LIST", "EMPLOYEE_PROFILE", "TEAM_SCORECARDS",
            "SETTINGS_ACCOUNT", "SETTINGS_PROFILE", "SETTINGS_NOTIFICATIONS", "SETTINGS_AI_PREFS"
        ],
        "area_manager": [
            "DASHBOARD", "COMMAND_CENTER", "LEADS_LIST", "LEAD_DETAIL", "LEAD_CREATE", "LEAD_IMPORT",
            "LEAD_ASSIGNMENT", "PIPELINE", "LOAN_DETAIL", "LOAN_CREATE", "LOAN_MILESTONES",
            "LOAN_CONDITIONS", "LOAN_DOCUMENTS", "RATE_LOCK", "PORTFOLIO", "PARTNERS_LIST",
            "PARTNER_DETAIL", "PARTNER_CREATE", "PARTNER_SCOREBOARD", "PARTNER_UPDATES", "INBOX",
            "EMAIL_TEMPLATES", "SMS_TEMPLATES", "VOICEMAIL_DROP", "POWER_DIALER", "CALL_LOG",
            "TASKS", "WORKFLOWS", "AUTOMATIONS", "REPORTS_DASHBOARD", "REPORTS_PRODUCTION",
            "REPORTS_PIPELINE", "REPORTS_CONVERSION", "REPORTS_PARTNER", "REPORTS_PROFITABILITY",
            "REPORTS_SLA", "REPORTS_TEAM", "TEAM_LIST", "EMPLOYEE_PROFILE", "EMPLOYEE_CREATE",
            "TEAM_SCORECARDS", "EMPLOYEE_IMPERSONATE", "SETTINGS_ACCOUNT", "SETTINGS_PROFILE",
            "SETTINGS_NOTIFICATIONS", "SETTINGS_INTEGRATIONS", "SETTINGS_AI_PREFS"
        ],
        "regional_manager": [
            "DASHBOARD", "COMMAND_CENTER", "LEADS_LIST", "LEAD_DETAIL", "LEAD_CREATE", "LEAD_IMPORT",
            "LEAD_ASSIGNMENT", "PIPELINE", "LOAN_DETAIL", "LOAN_CREATE", "LOAN_MILESTONES",
            "LOAN_CONDITIONS", "LOAN_DOCUMENTS", "RATE_LOCK", "PORTFOLIO", "PORTFOLIO_PERFORMANCE",
            "PORTFOLIO_RETENTION", "PORTFOLIO_CROSSSELL", "PARTNERS_LIST", "PARTNER_DETAIL",
            "PARTNER_CREATE", "PARTNER_SCOREBOARD", "PARTNER_UPDATES", "INBOX", "EMAIL_TEMPLATES",
            "SMS_TEMPLATES", "VOICEMAIL_DROP", "POWER_DIALER", "CALL_LOG", "TASKS", "WORKFLOWS",
            "WORKFLOW_BUILDER", "AUTOMATIONS", "REPORTS_DASHBOARD", "REPORTS_PRODUCTION",
            "REPORTS_PIPELINE", "REPORTS_CONVERSION", "REPORTS_PARTNER", "REPORTS_PROFITABILITY",
            "REPORTS_SLA", "REPORTS_TEAM", "AGENTS_DASHBOARD", "TEAM_LIST", "EMPLOYEE_PROFILE",
            "EMPLOYEE_CREATE", "EMPLOYEE_IMPORT", "TEAM_SCORECARDS", "EMPLOYEE_IMPERSONATE",
            "SETTINGS_ACCOUNT", "SETTINGS_PROFILE", "SETTINGS_NOTIFICATIONS", "SETTINGS_INTEGRATIONS",
            "SETTINGS_EMAIL_SYNC", "SETTINGS_TELEPHONY", "SETTINGS_AI_PREFS", "SETTINGS_AGENT_GOVERNANCE"
        ],
        "production_assistant": [
            "DASHBOARD", "LEADS_LIST", "LEAD_DETAIL", "PIPELINE", "LOAN_DETAIL", "LOAN_MILESTONES",
            "LOAN_CONDITIONS", "LOAN_DOCUMENTS", "INBOX", "TASKS", "CALL_LOG", "SETTINGS_ACCOUNT",
            "SETTINGS_PROFILE", "SETTINGS_NOTIFICATIONS"
        ],
        "processor": [
            "DASHBOARD", "PIPELINE", "LOAN_DETAIL", "LOAN_MILESTONES", "LOAN_CONDITIONS",
            "LOAN_DOCUMENTS", "INBOX", "TASKS", "CALL_LOG", "REPORTS_PIPELINE", "REPORTS_SLA",
            "SETTINGS_ACCOUNT", "SETTINGS_PROFILE", "SETTINGS_NOTIFICATIONS"
        ],
        "evp": [
            "DASHBOARD", "COMMAND_CENTER", "LEADS_LIST", "LEAD_DETAIL", "LEAD_CREATE", "LEAD_IMPORT",
            "LEAD_ASSIGNMENT", "PIPELINE", "LOAN_DETAIL", "LOAN_CREATE", "LOAN_MILESTONES",
            "LOAN_CONDITIONS", "LOAN_DOCUMENTS", "RATE_LOCK", "PORTFOLIO", "PORTFOLIO_PERFORMANCE",
            "PORTFOLIO_RETENTION", "PORTFOLIO_CROSSSELL", "PARTNERS_LIST", "PARTNER_DETAIL",
            "PARTNER_CREATE", "PARTNER_SCOREBOARD", "PARTNER_UPDATES", "INBOX", "EMAIL_TEMPLATES",
            "SMS_TEMPLATES", "VOICEMAIL_DROP", "POWER_DIALER", "CALL_LOG", "TASKS", "WORKFLOWS",
            "WORKFLOW_BUILDER", "AUTOMATIONS", "REPORTS_DASHBOARD", "REPORTS_PRODUCTION",
            "REPORTS_PIPELINE", "REPORTS_CONVERSION", "REPORTS_PARTNER", "REPORTS_PROFITABILITY",
            "REPORTS_SLA", "REPORTS_TEAM", "AGENTS_DASHBOARD", "AGENT_PROFILE", "AGENT_GYM",
            "AI_RECEPTIONIST", "CONVERSATION_INTEL", "TEAM_LIST", "EMPLOYEE_PROFILE", "EMPLOYEE_CREATE",
            "EMPLOYEE_IMPORT", "TEAM_SCORECARDS", "EMPLOYEE_IMPERSONATE", "SETTINGS_ACCOUNT",
            "SETTINGS_PROFILE", "SETTINGS_NOTIFICATIONS", "SETTINGS_INTEGRATIONS", "SETTINGS_EMAIL_SYNC",
            "SETTINGS_TELEPHONY", "SETTINGS_AI_PREFS", "SETTINGS_AGENT_GOVERNANCE"
        ],
        "administrator": None,  # Will be set to all pages
    }


def run_migration():
    """Execute page permissions system migration"""

    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Fix postgres:// to postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    # Create engine
    engine = create_engine(database_url)

    print("=" * 70)
    print("PAGE PERMISSIONS SYSTEM MIGRATION")
    print("Perennia AI - TL Development LLC")
    print("=" * 70)
    print()

    with engine.connect() as conn:

        # ====================================================================
        # STEP 1: Create pages table
        # ====================================================================
        print("📄 Step 1: Creating pages table...")

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pages (
                id SERIAL PRIMARY KEY,
                page_key VARCHAR(100) UNIQUE NOT NULL,
                name VARCHAR(200) NOT NULL,
                path VARCHAR(300) NOT NULL,
                category VARCHAR(100) NOT NULL,
                stage VARCHAR(50) NOT NULL DEFAULT 'all',
                description TEXT,
                is_active BOOLEAN DEFAULT true,
                display_order INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_pages_category ON pages(category);
            CREATE INDEX IF NOT EXISTS idx_pages_stage ON pages(stage);
            CREATE INDEX IF NOT EXISTS idx_pages_key ON pages(page_key);
        """))
        conn.commit()
        print("   ✅ Created pages table\n")

        # ====================================================================
        # STEP 2: Create permission_roles table
        # ====================================================================
        print("👥 Step 2: Creating permission_roles table...")

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS permission_roles (
                id SERIAL PRIMARY KEY,
                role_key VARCHAR(100) UNIQUE NOT NULL,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                color VARCHAR(50),
                icon VARCHAR(100),
                hierarchy_level INTEGER DEFAULT 0,
                is_system_role BOOLEAN DEFAULT false,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_permission_roles_key ON permission_roles(role_key);
        """))
        conn.commit()
        print("   ✅ Created permission_roles table\n")

        # ====================================================================
        # STEP 3: Create role_page_permissions table
        # ====================================================================
        print("🔗 Step 3: Creating role_page_permissions table...")

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS role_page_permissions (
                id SERIAL PRIMARY KEY,
                role_id INTEGER NOT NULL REFERENCES permission_roles(id) ON DELETE CASCADE,
                page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
                can_view BOOLEAN DEFAULT true,
                can_create BOOLEAN DEFAULT false,
                can_edit BOOLEAN DEFAULT false,
                can_delete BOOLEAN DEFAULT false,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(role_id, page_id)
            );

            CREATE INDEX IF NOT EXISTS idx_role_page_permissions_role ON role_page_permissions(role_id);
            CREATE INDEX IF NOT EXISTS idx_role_page_permissions_page ON role_page_permissions(page_id);
        """))
        conn.commit()
        print("   ✅ Created role_page_permissions table\n")

        # ====================================================================
        # STEP 4: Create user_page_overrides table
        # ====================================================================
        print("👤 Step 4: Creating user_page_overrides table...")

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_page_overrides (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
                can_view BOOLEAN,
                can_create BOOLEAN,
                can_edit BOOLEAN,
                can_delete BOOLEAN,
                granted_by INTEGER REFERENCES users(id),
                granted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                expires_at TIMESTAMP WITH TIME ZONE,
                reason TEXT,
                UNIQUE(user_id, page_id)
            );

            CREATE INDEX IF NOT EXISTS idx_user_page_overrides_user ON user_page_overrides(user_id);
        """))
        conn.commit()
        print("   ✅ Created user_page_overrides table\n")

        # ====================================================================
        # STEP 5: Create page_permission_audit_log table
        # ====================================================================
        print("📝 Step 5: Creating page_permission_audit_log table...")

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS page_permission_audit_log (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                user_id INTEGER NOT NULL REFERENCES users(id),
                user_email VARCHAR(255),
                target_type VARCHAR(50) NOT NULL,
                target_id INTEGER NOT NULL,
                target_name VARCHAR(200),
                action VARCHAR(100) NOT NULL,
                changes JSONB NOT NULL,
                ip_address INET,
                user_agent TEXT,
                session_id VARCHAR(255)
            );

            CREATE INDEX IF NOT EXISTS idx_page_audit_timestamp ON page_permission_audit_log(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_page_audit_user ON page_permission_audit_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_page_audit_target ON page_permission_audit_log(target_type, target_id);
        """))
        conn.commit()
        print("   ✅ Created page_permission_audit_log table\n")

        # ====================================================================
        # STEP 6: Insert all pages
        # ====================================================================
        print("🌱 Step 6: Seeding pages...")

        pages = get_all_pages()
        for page in pages:
            try:
                conn.execute(text("""
                    INSERT INTO pages (page_key, name, path, category, stage, display_order)
                    VALUES (:page_key, :name, :path, :category, :stage, :display_order)
                    ON CONFLICT (page_key) DO UPDATE SET
                        name = EXCLUDED.name,
                        path = EXCLUDED.path,
                        category = EXCLUDED.category,
                        stage = EXCLUDED.stage,
                        display_order = EXCLUDED.display_order,
                        updated_at = NOW()
                """), page)
            except Exception as e:
                print(f"   ⚠️  Error inserting page {page['page_key']}: {e}")

        conn.commit()
        print(f"   ✅ Seeded {len(pages)} pages\n")

        # ====================================================================
        # STEP 7: Insert all roles
        # ====================================================================
        print("👥 Step 7: Seeding roles...")

        roles = get_role_definitions()
        for role in roles:
            try:
                conn.execute(text("""
                    INSERT INTO permission_roles (role_key, name, description, color, icon, hierarchy_level, is_system_role)
                    VALUES (:role_key, :name, :description, :color, :icon, :hierarchy_level, :is_system_role)
                    ON CONFLICT (role_key) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        color = EXCLUDED.color,
                        icon = EXCLUDED.icon,
                        hierarchy_level = EXCLUDED.hierarchy_level,
                        updated_at = NOW()
                """), role)
            except Exception as e:
                print(f"   ⚠️  Error inserting role {role['role_key']}: {e}")

        conn.commit()
        print(f"   ✅ Seeded {len(roles)} roles\n")

        # ====================================================================
        # STEP 8: Insert default role permissions
        # ====================================================================
        print("🔐 Step 8: Seeding role permissions...")

        # Get all page keys for administrator
        all_page_keys = [p["page_key"] for p in pages]

        permissions = get_default_permissions()
        permissions["administrator"] = all_page_keys  # Admin gets all pages

        for role_key, page_keys in permissions.items():
            if not page_keys:
                continue

            # Get role ID
            result = conn.execute(text(
                "SELECT id FROM permission_roles WHERE role_key = :role_key"
            ), {"role_key": role_key})
            role_row = result.fetchone()

            if not role_row:
                print(f"   ⚠️  Role {role_key} not found")
                continue

            role_id = role_row[0]

            for page_key in page_keys:
                # Get page ID
                result = conn.execute(text(
                    "SELECT id FROM pages WHERE page_key = :page_key"
                ), {"page_key": page_key})
                page_row = result.fetchone()

                if not page_row:
                    continue

                page_id = page_row[0]

                try:
                    conn.execute(text("""
                        INSERT INTO role_page_permissions (role_id, page_id, can_view)
                        VALUES (:role_id, :page_id, true)
                        ON CONFLICT (role_id, page_id) DO UPDATE SET
                            can_view = true,
                            updated_at = NOW()
                    """), {"role_id": role_id, "page_id": page_id})
                except Exception as e:
                    print(f"   ⚠️  Error inserting permission for {role_key}/{page_key}: {e}")

            print(f"   ✅ Added {len(page_keys)} permissions for {role_key}")

        conn.commit()
        print()

        # ====================================================================
        # STEP 9: Add page_permission_role column to users table
        # ====================================================================
        print("👤 Step 9: Adding page_permission_role to users table...")

        try:
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS page_permission_role VARCHAR(100) DEFAULT 'loan_officer';
            """))
            conn.commit()
            print("   ✅ Added page_permission_role column\n")
        except Exception as e:
            print(f"   ⚠️  Column may already exist: {e}\n")

        # ====================================================================
        # MIGRATION SUMMARY
        # ====================================================================

        print()
        print("=" * 70)
        print("MIGRATION SUMMARY")
        print("=" * 70)
        print()
        print("✅ Tables Created:")
        print("   • pages")
        print("   • permission_roles")
        print("   • role_page_permissions")
        print("   • user_page_overrides")
        print("   • page_permission_audit_log")
        print()
        print("✅ Field Added:")
        print("   • users.page_permission_role")
        print()
        print(f"✅ Data Seeded:")
        print(f"   • {len(pages)} pages")
        print(f"   • {len(roles)} roles")
        print(f"   • Role permissions for all roles")
        print()
        print("=" * 70)
        print("🎉 Page Permissions System Migration Completed Successfully!")
        print("=" * 70)
        print()


if __name__ == '__main__':
    run_migration()
