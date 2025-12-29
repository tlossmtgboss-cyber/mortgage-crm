"""
Migration: Add User Creation Wizard Tables
Created: 2024-12-29
Description: Creates all tables needed for the User Creation Wizard feature including:
- onboarding_roles
- onboarding_categories
- onboarding_responsibilities
- onboarding_permission_templates
- onboarding_user_profiles
- onboarding_user_categories
- onboarding_user_responsibilities
- onboarding_user_permissions
- onboarding_kpi_scorecards
- onboarding_sessions
- onboarding_bulk_upload_sessions
- onboarding_bulk_user_drafts
- onboarding_user_audit_logs
- onboarding_role_default_categories
- onboarding_role_default_responsibilities

Supports both PostgreSQL and SQLite.
"""

from sqlalchemy import create_engine, text, inspect
import os
import sys

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable not set")
    sys.exit(1)

# Fix Railway DATABASE_URL format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

# Detect database type
is_sqlite = DATABASE_URL.startswith("sqlite")
is_postgres = DATABASE_URL.startswith("postgresql")


def get_serial_type():
    """Return appropriate auto-increment type"""
    return "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "SERIAL PRIMARY KEY"


def get_json_type():
    """Return appropriate JSON type"""
    return "TEXT" if is_sqlite else "JSONB"


def get_now_func():
    """Return appropriate NOW() function"""
    return "CURRENT_TIMESTAMP" if is_sqlite else "NOW()"


def upgrade():
    """Apply the migration"""
    print("Starting migration: Add User Creation Wizard tables...")
    print(f"Database type: {'SQLite' if is_sqlite else 'PostgreSQL'}")

    serial = get_serial_type()
    json_type = get_json_type()
    now_func = get_now_func()

    with engine.begin() as conn:
        # ========================================================================
        # PERMISSION TEMPLATES TABLE (must be created first due to FK references)
        # ========================================================================
        print("Creating onboarding_permission_templates table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_permission_templates (
                    id {serial},
                    name VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    permissions {json_type} DEFAULT '{{}}',
                    is_system_template BOOLEAN DEFAULT 0,
                    risk_level VARCHAR(20) DEFAULT 'medium',
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_permission_templates (
                    id {serial},
                    name VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    permissions {json_type} DEFAULT '{{}}',
                    is_system_template BOOLEAN DEFAULT FALSE,
                    risk_level VARCHAR(20) DEFAULT 'medium',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_permission_templates_name
                    ON onboarding_permission_templates(name)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_permission_templates_active
                    ON onboarding_permission_templates(is_active)
            """))

        # ========================================================================
        # ROLES TABLE
        # ========================================================================
        print("Creating onboarding_roles table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_roles (
                    id {serial},
                    name VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    default_permission_template_id INTEGER REFERENCES onboarding_permission_templates(id),
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_roles (
                    id {serial},
                    name VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    default_permission_template_id INTEGER REFERENCES onboarding_permission_templates(id),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_roles_name ON onboarding_roles(name)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_roles_active ON onboarding_roles(is_active)
            """))

        # ========================================================================
        # CATEGORIES TABLE
        # ========================================================================
        print("Creating onboarding_categories table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_categories (
                    id {serial},
                    name VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_categories (
                    id {serial},
                    name VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT {now_func}
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_categories_name ON onboarding_categories(name)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_categories_active ON onboarding_categories(is_active)
            """))

        # ========================================================================
        # RESPONSIBILITIES TABLE
        # ========================================================================
        print("Creating onboarding_responsibilities table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_responsibilities (
                    id {serial},
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    category_id INTEGER NOT NULL REFERENCES onboarding_categories(id),
                    applicable_role_ids {json_type} DEFAULT '[]',
                    kpi_mapping {json_type},
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_responsibilities (
                    id {serial},
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    category_id INTEGER NOT NULL REFERENCES onboarding_categories(id) ON DELETE CASCADE,
                    applicable_role_ids {json_type} DEFAULT '[]',
                    kpi_mapping {json_type},
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_responsibilities_name
                    ON onboarding_responsibilities(name)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_responsibilities_category
                    ON onboarding_responsibilities(category_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_responsibilities_active
                    ON onboarding_responsibilities(is_active)
            """))

        # ========================================================================
        # ROLE DEFAULT CATEGORIES (Junction)
        # ========================================================================
        print("Creating onboarding_role_default_categories table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_role_default_categories (
                    id {serial},
                    role_id INTEGER NOT NULL REFERENCES onboarding_roles(id),
                    category_id INTEGER NOT NULL REFERENCES onboarding_categories(id),
                    created_at TIMESTAMP DEFAULT {now_func},
                    UNIQUE (role_id, category_id)
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_role_default_categories (
                    id {serial},
                    role_id INTEGER NOT NULL REFERENCES onboarding_roles(id) ON DELETE CASCADE,
                    category_id INTEGER NOT NULL REFERENCES onboarding_categories(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT {now_func},
                    CONSTRAINT uix_onboarding_role_default_category UNIQUE (role_id, category_id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_role_default_categories_role
                    ON onboarding_role_default_categories(role_id)
            """))

        # ========================================================================
        # ROLE DEFAULT RESPONSIBILITIES (Junction)
        # ========================================================================
        print("Creating onboarding_role_default_responsibilities table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_role_default_responsibilities (
                    id {serial},
                    role_id INTEGER NOT NULL REFERENCES onboarding_roles(id),
                    responsibility_id INTEGER NOT NULL REFERENCES onboarding_responsibilities(id),
                    created_at TIMESTAMP DEFAULT {now_func},
                    UNIQUE (role_id, responsibility_id)
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_role_default_responsibilities (
                    id {serial},
                    role_id INTEGER NOT NULL REFERENCES onboarding_roles(id) ON DELETE CASCADE,
                    responsibility_id INTEGER NOT NULL REFERENCES onboarding_responsibilities(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT {now_func},
                    CONSTRAINT uix_onboarding_role_default_responsibility UNIQUE (role_id, responsibility_id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_role_default_responsibilities_role
                    ON onboarding_role_default_responsibilities(role_id)
            """))

        # ========================================================================
        # USER PROFILES TABLE
        # ========================================================================
        print("Creating onboarding_user_profiles table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_user_profiles (
                    id {serial},
                    user_id INTEGER NOT NULL UNIQUE,
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    role_id INTEGER REFERENCES onboarding_roles(id),
                    permission_template_id INTEGER REFERENCES onboarding_permission_templates(id),
                    status VARCHAR(50) DEFAULT 'pending_setup',
                    activation_token VARCHAR(100),
                    activation_token_expires_at TIMESTAMP,
                    activated_at TIMESTAMP,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_user_profiles (
                    id {serial},
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    role_id INTEGER REFERENCES onboarding_roles(id),
                    permission_template_id INTEGER REFERENCES onboarding_permission_templates(id),
                    status VARCHAR(50) DEFAULT 'pending_setup',
                    activation_token VARCHAR(100),
                    activation_token_expires_at TIMESTAMP,
                    activated_at TIMESTAMP,
                    created_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func},
                    CONSTRAINT unique_onboarding_user UNIQUE (user_id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_user_profiles_user
                    ON onboarding_user_profiles(user_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_user_profiles_role
                    ON onboarding_user_profiles(role_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_user_profiles_status
                    ON onboarding_user_profiles(status)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_user_profiles_token
                    ON onboarding_user_profiles(activation_token)
            """))

        # ========================================================================
        # USER CATEGORIES (Junction)
        # ========================================================================
        print("Creating onboarding_user_categories table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_user_categories (
                    id {serial},
                    user_profile_id INTEGER NOT NULL REFERENCES onboarding_user_profiles(id),
                    category_id INTEGER NOT NULL REFERENCES onboarding_categories(id),
                    created_at TIMESTAMP DEFAULT {now_func},
                    UNIQUE (user_profile_id, category_id)
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_user_categories (
                    id {serial},
                    user_profile_id INTEGER NOT NULL REFERENCES onboarding_user_profiles(id) ON DELETE CASCADE,
                    category_id INTEGER NOT NULL REFERENCES onboarding_categories(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT {now_func},
                    CONSTRAINT uix_onboarding_user_category UNIQUE (user_profile_id, category_id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_user_categories_profile
                    ON onboarding_user_categories(user_profile_id)
            """))

        # ========================================================================
        # USER RESPONSIBILITIES (Junction)
        # ========================================================================
        print("Creating onboarding_user_responsibilities table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_user_responsibilities (
                    id {serial},
                    user_profile_id INTEGER NOT NULL REFERENCES onboarding_user_profiles(id),
                    responsibility_id INTEGER NOT NULL REFERENCES onboarding_responsibilities(id),
                    created_at TIMESTAMP DEFAULT {now_func},
                    UNIQUE (user_profile_id, responsibility_id)
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_user_responsibilities (
                    id {serial},
                    user_profile_id INTEGER NOT NULL REFERENCES onboarding_user_profiles(id) ON DELETE CASCADE,
                    responsibility_id INTEGER NOT NULL REFERENCES onboarding_responsibilities(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT {now_func},
                    CONSTRAINT uix_onboarding_user_responsibility UNIQUE (user_profile_id, responsibility_id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_user_responsibilities_profile
                    ON onboarding_user_responsibilities(user_profile_id)
            """))

        # ========================================================================
        # USER PERMISSIONS TABLE
        # ========================================================================
        print("Creating onboarding_user_permissions table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_user_permissions (
                    id {serial},
                    user_profile_id INTEGER NOT NULL UNIQUE REFERENCES onboarding_user_profiles(id),
                    permissions {json_type} DEFAULT '{{}}',
                    source VARCHAR(50) DEFAULT 'template',
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_user_permissions (
                    id {serial},
                    user_profile_id INTEGER NOT NULL REFERENCES onboarding_user_profiles(id) ON DELETE CASCADE,
                    permissions {json_type} DEFAULT '{{}}',
                    source VARCHAR(50) DEFAULT 'template',
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func},
                    CONSTRAINT unique_onboarding_user_permissions UNIQUE (user_profile_id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_user_permissions_profile
                    ON onboarding_user_permissions(user_profile_id)
            """))

        # ========================================================================
        # KPI SCORECARDS TABLE
        # ========================================================================
        print("Creating onboarding_kpi_scorecards table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_kpi_scorecards (
                    id {serial},
                    user_profile_id INTEGER NOT NULL UNIQUE REFERENCES onboarding_user_profiles(id),
                    scorecard_config {json_type} DEFAULT '{{}}',
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_kpi_scorecards (
                    id {serial},
                    user_profile_id INTEGER NOT NULL REFERENCES onboarding_user_profiles(id) ON DELETE CASCADE,
                    scorecard_config {json_type} DEFAULT '{{}}',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func},
                    CONSTRAINT unique_onboarding_kpi_scorecard UNIQUE (user_profile_id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_kpi_scorecards_profile
                    ON onboarding_kpi_scorecards(user_profile_id)
            """))

        # ========================================================================
        # ONBOARDING SESSIONS TABLE
        # ========================================================================
        print("Creating onboarding_sessions table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_sessions (
                    id {serial},
                    user_id INTEGER,
                    session_type VARCHAR(50) DEFAULT 'single',
                    current_step INTEGER DEFAULT 1,
                    session_data {json_type} DEFAULT '{{}}',
                    status VARCHAR(50) DEFAULT 'in_progress',
                    created_by INTEGER,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_sessions (
                    id {serial},
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    session_type VARCHAR(50) DEFAULT 'single',
                    current_step INTEGER DEFAULT 1,
                    session_data {json_type} DEFAULT '{{}}',
                    status VARCHAR(50) DEFAULT 'in_progress',
                    created_by INTEGER REFERENCES users(id),
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_user
                    ON onboarding_sessions(user_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_status
                    ON onboarding_sessions(status)
            """))

        # ========================================================================
        # BULK UPLOAD SESSIONS TABLE
        # ========================================================================
        print("Creating onboarding_bulk_upload_sessions table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_bulk_upload_sessions (
                    id {serial},
                    filename VARCHAR(255),
                    original_headers {json_type} DEFAULT '[]',
                    column_mapping {json_type} DEFAULT '{{}}',
                    total_rows INTEGER DEFAULT 0,
                    valid_rows INTEGER DEFAULT 0,
                    error_rows INTEGER DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'pending',
                    created_by INTEGER,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_bulk_upload_sessions (
                    id {serial},
                    filename VARCHAR(255),
                    original_headers {json_type} DEFAULT '[]',
                    column_mapping {json_type} DEFAULT '{{}}',
                    total_rows INTEGER DEFAULT 0,
                    valid_rows INTEGER DEFAULT 0,
                    error_rows INTEGER DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'pending',
                    created_by INTEGER REFERENCES users(id),
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_bulk_sessions_status
                    ON onboarding_bulk_upload_sessions(status)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_bulk_sessions_created_by
                    ON onboarding_bulk_upload_sessions(created_by)
            """))

        # ========================================================================
        # BULK USER DRAFTS TABLE
        # ========================================================================
        print("Creating onboarding_bulk_user_drafts table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_bulk_user_drafts (
                    id {serial},
                    session_id INTEGER NOT NULL REFERENCES onboarding_bulk_upload_sessions(id),
                    row_number INTEGER NOT NULL,
                    raw_data {json_type} DEFAULT '{{}}',
                    parsed_data {json_type} DEFAULT '{{}}',
                    validation_errors {json_type} DEFAULT '[]',
                    is_valid BOOLEAN DEFAULT 1,
                    is_processed BOOLEAN DEFAULT 0,
                    created_user_id INTEGER,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_bulk_user_drafts (
                    id {serial},
                    session_id INTEGER NOT NULL REFERENCES onboarding_bulk_upload_sessions(id) ON DELETE CASCADE,
                    row_number INTEGER NOT NULL,
                    raw_data {json_type} DEFAULT '{{}}',
                    parsed_data {json_type} DEFAULT '{{}}',
                    validation_errors {json_type} DEFAULT '[]',
                    is_valid BOOLEAN DEFAULT TRUE,
                    is_processed BOOLEAN DEFAULT FALSE,
                    created_user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_bulk_drafts_session
                    ON onboarding_bulk_user_drafts(session_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_bulk_drafts_valid
                    ON onboarding_bulk_user_drafts(is_valid)
            """))

        # ========================================================================
        # USER AUDIT LOG TABLE
        # ========================================================================
        print("Creating onboarding_user_audit_logs table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_user_audit_logs (
                    id {serial},
                    user_id INTEGER,
                    action VARCHAR(100) NOT NULL,
                    performed_by INTEGER,
                    details {json_type} DEFAULT '{{}}',
                    ip_address VARCHAR(50),
                    user_agent TEXT,
                    created_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS onboarding_user_audit_logs (
                    id {serial},
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    action VARCHAR(100) NOT NULL,
                    performed_by INTEGER REFERENCES users(id),
                    details {json_type} DEFAULT '{{}}',
                    ip_address VARCHAR(50),
                    user_agent TEXT,
                    created_at TIMESTAMP DEFAULT {now_func}
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_audit_user
                    ON onboarding_user_audit_logs(user_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_audit_action
                    ON onboarding_user_audit_logs(action)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_onboarding_audit_created
                    ON onboarding_user_audit_logs(created_at)
            """))

        # ========================================================================
        # EMPLOYEE INVITES TABLE (if not exists)
        # ========================================================================
        print("Creating employee_invites table...")
        if is_sqlite:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS employee_invites (
                    id {serial},
                    email VARCHAR(255) NOT NULL,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    job_title VARCHAR(200),
                    permission_role VARCHAR(50) DEFAULT 'sales',
                    branch_id INTEGER,
                    invite_token VARCHAR(100) NOT NULL UNIQUE,
                    invited_by_user_id INTEGER,
                    status VARCHAR(50) DEFAULT 'pending',
                    initial_config {json_type} DEFAULT '{{}}',
                    accepted_at TIMESTAMP,
                    created_user_id INTEGER,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
        else:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS employee_invites (
                    id {serial},
                    email VARCHAR(255) NOT NULL,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    job_title VARCHAR(200),
                    permission_role VARCHAR(50) DEFAULT 'sales',
                    branch_id INTEGER,
                    invite_token VARCHAR(100) NOT NULL UNIQUE,
                    invited_by_user_id INTEGER REFERENCES users(id),
                    status VARCHAR(50) DEFAULT 'pending',
                    initial_config {json_type} DEFAULT '{{}}',
                    accepted_at TIMESTAMP,
                    created_user_id INTEGER REFERENCES users(id),
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT {now_func},
                    updated_at TIMESTAMP DEFAULT {now_func}
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_employee_invites_email
                    ON employee_invites(email)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_employee_invites_token
                    ON employee_invites(invite_token)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_employee_invites_status
                    ON employee_invites(status)
            """))

        # ========================================================================
        # SEED DEFAULT DATA
        # ========================================================================
        print("Seeding default roles...")
        roles = [
            ('Loan Officer', 'Originates and manages mortgage loans'),
            ('Processor', 'Processes loan applications and documentation'),
            ('Underwriter', 'Reviews and approves loan applications'),
            ('Closer', 'Handles loan closing and funding'),
            ('Concierge', 'Provides customer service and support'),
            ('Team Lead', 'Leads a team of loan officers'),
            ('Branch Manager', 'Manages branch operations'),
            ('Operations Manager', 'Manages processing and operations'),
            ('Sales Manager', 'Manages sales team'),
            ('Executive', 'Executive leadership'),
            ('Administrator', 'System administrator'),
            ('Marketing', 'Marketing and communications'),
            ('Compliance Officer', 'Ensures regulatory compliance'),
            ('Quality Control', 'Reviews loans for quality'),
            ('Post-Closer', 'Handles post-closing activities'),
        ]
        for name, desc in roles:
            try:
                conn.execute(text(
                    "INSERT INTO onboarding_roles (name, description) VALUES (:name, :desc)"
                ), {"name": name, "desc": desc})
            except Exception:
                pass  # Ignore duplicates

        print("Seeding default categories...")
        categories = [
            ('Lead Generation', 'Finding and qualifying new leads', 1),
            ('Pre-Qualification', 'Initial borrower qualification', 2),
            ('Borrower Engagement', 'Maintaining borrower relationships', 3),
            ('Application & Disclosure', 'Application intake and disclosures', 4),
            ('Processing & Milestones', 'Loan processing activities', 5),
            ('Underwriting Support', 'Supporting underwriting process', 6),
            ('Closing & Funding', 'Loan closing activities', 7),
            ('Post-Closing', 'Post-closing servicing', 8),
            ('Partner Management', 'Managing referral partners', 9),
            ('Team Management', 'Managing team members', 10),
            ('Compliance & Quality', 'Compliance and quality control', 11),
        ]
        for name, desc, order in categories:
            try:
                conn.execute(text(
                    "INSERT INTO onboarding_categories (name, description, sort_order) VALUES (:name, :desc, :order)"
                ), {"name": name, "desc": desc, "order": order})
            except Exception:
                pass  # Ignore duplicates

        print("Seeding default permission templates...")
        templates = [
            ('Loan Officer - Standard', 'Standard permissions for loan officers', True, 'low',
             '{"leads": {"read": true, "write": true, "delete": false}, "loans": {"read": true, "write": true, "delete": false}, "pipeline": {"read": true, "write": true}, "reports": {"read": true}, "admin": {"read": false, "write": false}}'),
            ('Processor - Standard', 'Standard permissions for processors', True, 'low',
             '{"leads": {"read": true, "write": false}, "loans": {"read": true, "write": true, "delete": false}, "documents": {"read": true, "write": true}, "conditions": {"read": true, "write": true}}'),
            ('Manager - Full', 'Full permissions for managers', True, 'medium',
             '{"leads": {"read": true, "write": true, "delete": true}, "loans": {"read": true, "write": true, "delete": true}, "team": {"read": true, "write": true}, "reports": {"read": true, "write": true}, "admin": {"read": true, "write": false}}'),
            ('Admin - Full Access', 'Full administrative access', True, 'high',
             '{"leads": {"read": true, "write": true, "delete": true}, "loans": {"read": true, "write": true, "delete": true}, "team": {"read": true, "write": true, "delete": true}, "reports": {"read": true, "write": true}, "admin": {"read": true, "write": true}, "settings": {"read": true, "write": true}}'),
            ('Read Only', 'View-only access', True, 'low',
             '{"leads": {"read": true, "write": false}, "loans": {"read": true, "write": false}, "pipeline": {"read": true, "write": false}, "reports": {"read": true}}'),
        ]
        for name, desc, is_system, risk, perms in templates:
            try:
                is_sys_val = 1 if is_sqlite else is_system
                conn.execute(text(
                    "INSERT INTO onboarding_permission_templates (name, description, is_system_template, risk_level, permissions) VALUES (:name, :desc, :is_sys, :risk, :perms)"
                ), {"name": name, "desc": desc, "is_sys": is_sys_val, "risk": risk, "perms": perms})
            except Exception:
                pass  # Ignore duplicates

        print("Migration completed successfully!")


def downgrade():
    """Rollback the migration"""
    print("Rolling back migration: Add User Creation Wizard tables...")

    with engine.begin() as conn:
        tables = [
            'onboarding_user_audit_logs',
            'onboarding_bulk_user_drafts',
            'onboarding_bulk_upload_sessions',
            'onboarding_sessions',
            'onboarding_kpi_scorecards',
            'onboarding_user_permissions',
            'onboarding_user_responsibilities',
            'onboarding_user_categories',
            'onboarding_user_profiles',
            'onboarding_role_default_responsibilities',
            'onboarding_role_default_categories',
            'onboarding_responsibilities',
            'onboarding_categories',
            'onboarding_roles',
            'onboarding_permission_templates',
            'employee_invites'
        ]

        for table in tables:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
            except Exception:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))

        print("Rollback completed!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='User Creation Wizard Migration')
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    args = parser.parse_args()

    if args.rollback:
        downgrade()
    else:
        upgrade()
