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
"""

from sqlalchemy import create_engine, text
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


def upgrade():
    """Apply the migration"""
    print("Starting migration: Add User Creation Wizard tables...")

    with engine.begin() as conn:
        # ========================================================================
        # PERMISSION TEMPLATES TABLE (must be created first due to FK references)
        # ========================================================================
        print("Creating onboarding_permission_templates table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_permission_templates (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                permissions JSONB DEFAULT '{}',
                is_system_template BOOLEAN DEFAULT FALSE,
                risk_level VARCHAR(20) DEFAULT 'medium',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_permission_templates_name
                ON onboarding_permission_templates(name);
            CREATE INDEX IF NOT EXISTS idx_onboarding_permission_templates_active
                ON onboarding_permission_templates(is_active);
        """))

        # ========================================================================
        # ROLES TABLE
        # ========================================================================
        print("Creating onboarding_roles table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_roles (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                default_permission_template_id INTEGER REFERENCES onboarding_permission_templates(id),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_roles_name ON onboarding_roles(name);
            CREATE INDEX IF NOT EXISTS idx_onboarding_roles_active ON onboarding_roles(is_active);
        """))

        # ========================================================================
        # CATEGORIES TABLE
        # ========================================================================
        print("Creating onboarding_categories table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                sort_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_categories_name ON onboarding_categories(name);
            CREATE INDEX IF NOT EXISTS idx_onboarding_categories_active ON onboarding_categories(is_active);
        """))

        # ========================================================================
        # RESPONSIBILITIES TABLE
        # ========================================================================
        print("Creating onboarding_responsibilities table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_responsibilities (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                category_id INTEGER NOT NULL REFERENCES onboarding_categories(id) ON DELETE CASCADE,
                applicable_role_ids JSONB DEFAULT '[]',
                kpi_mapping JSONB,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_responsibilities_name
                ON onboarding_responsibilities(name);
            CREATE INDEX IF NOT EXISTS idx_onboarding_responsibilities_category
                ON onboarding_responsibilities(category_id);
            CREATE INDEX IF NOT EXISTS idx_onboarding_responsibilities_active
                ON onboarding_responsibilities(is_active);
        """))

        # ========================================================================
        # ROLE DEFAULT CATEGORIES (Junction)
        # ========================================================================
        print("Creating onboarding_role_default_categories table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_role_default_categories (
                id SERIAL PRIMARY KEY,
                role_id INTEGER NOT NULL REFERENCES onboarding_roles(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES onboarding_categories(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uix_onboarding_role_default_category UNIQUE (role_id, category_id)
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_role_default_categories_role
                ON onboarding_role_default_categories(role_id);
        """))

        # ========================================================================
        # ROLE DEFAULT RESPONSIBILITIES (Junction)
        # ========================================================================
        print("Creating onboarding_role_default_responsibilities table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_role_default_responsibilities (
                id SERIAL PRIMARY KEY,
                role_id INTEGER NOT NULL REFERENCES onboarding_roles(id) ON DELETE CASCADE,
                responsibility_id INTEGER NOT NULL REFERENCES onboarding_responsibilities(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uix_onboarding_role_default_responsibility UNIQUE (role_id, responsibility_id)
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_role_default_responsibilities_role
                ON onboarding_role_default_responsibilities(role_id);
        """))

        # ========================================================================
        # USER PROFILES TABLE
        # ========================================================================
        print("Creating onboarding_user_profiles table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_user_profiles (
                id SERIAL PRIMARY KEY,
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
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT unique_onboarding_user UNIQUE (user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_user_profiles_user
                ON onboarding_user_profiles(user_id);
            CREATE INDEX IF NOT EXISTS idx_onboarding_user_profiles_role
                ON onboarding_user_profiles(role_id);
            CREATE INDEX IF NOT EXISTS idx_onboarding_user_profiles_status
                ON onboarding_user_profiles(status);
            CREATE INDEX IF NOT EXISTS idx_onboarding_user_profiles_token
                ON onboarding_user_profiles(activation_token);
        """))

        # ========================================================================
        # USER CATEGORIES (Junction)
        # ========================================================================
        print("Creating onboarding_user_categories table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_user_categories (
                id SERIAL PRIMARY KEY,
                user_profile_id INTEGER NOT NULL REFERENCES onboarding_user_profiles(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES onboarding_categories(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uix_onboarding_user_category UNIQUE (user_profile_id, category_id)
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_user_categories_profile
                ON onboarding_user_categories(user_profile_id);
        """))

        # ========================================================================
        # USER RESPONSIBILITIES (Junction)
        # ========================================================================
        print("Creating onboarding_user_responsibilities table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_user_responsibilities (
                id SERIAL PRIMARY KEY,
                user_profile_id INTEGER NOT NULL REFERENCES onboarding_user_profiles(id) ON DELETE CASCADE,
                responsibility_id INTEGER NOT NULL REFERENCES onboarding_responsibilities(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uix_onboarding_user_responsibility UNIQUE (user_profile_id, responsibility_id)
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_user_responsibilities_profile
                ON onboarding_user_responsibilities(user_profile_id);
        """))

        # ========================================================================
        # USER PERMISSIONS TABLE
        # ========================================================================
        print("Creating onboarding_user_permissions table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_user_permissions (
                id SERIAL PRIMARY KEY,
                user_profile_id INTEGER NOT NULL REFERENCES onboarding_user_profiles(id) ON DELETE CASCADE,
                permissions JSONB DEFAULT '{}',
                source VARCHAR(50) DEFAULT 'template',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT unique_onboarding_user_permissions UNIQUE (user_profile_id)
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_user_permissions_profile
                ON onboarding_user_permissions(user_profile_id);
        """))

        # ========================================================================
        # KPI SCORECARDS TABLE
        # ========================================================================
        print("Creating onboarding_kpi_scorecards table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_kpi_scorecards (
                id SERIAL PRIMARY KEY,
                user_profile_id INTEGER NOT NULL REFERENCES onboarding_user_profiles(id) ON DELETE CASCADE,
                scorecard_config JSONB DEFAULT '{}',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT unique_onboarding_kpi_scorecard UNIQUE (user_profile_id)
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_kpi_scorecards_profile
                ON onboarding_kpi_scorecards(user_profile_id);
        """))

        # ========================================================================
        # ONBOARDING SESSIONS TABLE
        # ========================================================================
        print("Creating onboarding_sessions table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                session_type VARCHAR(50) DEFAULT 'single',
                current_step INTEGER DEFAULT 1,
                session_data JSONB DEFAULT '{}',
                status VARCHAR(50) DEFAULT 'in_progress',
                created_by INTEGER REFERENCES users(id),
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_user
                ON onboarding_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_status
                ON onboarding_sessions(status);
        """))

        # ========================================================================
        # BULK UPLOAD SESSIONS TABLE
        # ========================================================================
        print("Creating onboarding_bulk_upload_sessions table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_bulk_upload_sessions (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255),
                original_headers JSONB DEFAULT '[]',
                column_mapping JSONB DEFAULT '{}',
                total_rows INTEGER DEFAULT 0,
                valid_rows INTEGER DEFAULT 0,
                error_rows INTEGER DEFAULT 0,
                status VARCHAR(50) DEFAULT 'pending',
                created_by INTEGER REFERENCES users(id),
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_bulk_sessions_status
                ON onboarding_bulk_upload_sessions(status);
            CREATE INDEX IF NOT EXISTS idx_onboarding_bulk_sessions_created_by
                ON onboarding_bulk_upload_sessions(created_by);
        """))

        # ========================================================================
        # BULK USER DRAFTS TABLE
        # ========================================================================
        print("Creating onboarding_bulk_user_drafts table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_bulk_user_drafts (
                id SERIAL PRIMARY KEY,
                session_id INTEGER NOT NULL REFERENCES onboarding_bulk_upload_sessions(id) ON DELETE CASCADE,
                row_number INTEGER NOT NULL,
                raw_data JSONB DEFAULT '{}',
                parsed_data JSONB DEFAULT '{}',
                validation_errors JSONB DEFAULT '[]',
                is_valid BOOLEAN DEFAULT TRUE,
                is_processed BOOLEAN DEFAULT FALSE,
                created_user_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_bulk_drafts_session
                ON onboarding_bulk_user_drafts(session_id);
            CREATE INDEX IF NOT EXISTS idx_onboarding_bulk_drafts_valid
                ON onboarding_bulk_user_drafts(is_valid);
        """))

        # ========================================================================
        # USER AUDIT LOG TABLE
        # ========================================================================
        print("Creating onboarding_user_audit_logs table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_user_audit_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action VARCHAR(100) NOT NULL,
                performed_by INTEGER REFERENCES users(id),
                details JSONB DEFAULT '{}',
                ip_address VARCHAR(50),
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_onboarding_audit_user
                ON onboarding_user_audit_logs(user_id);
            CREATE INDEX IF NOT EXISTS idx_onboarding_audit_action
                ON onboarding_user_audit_logs(action);
            CREATE INDEX IF NOT EXISTS idx_onboarding_audit_created
                ON onboarding_user_audit_logs(created_at);
        """))

        # ========================================================================
        # EMPLOYEE INVITES TABLE (if not exists)
        # ========================================================================
        print("Creating employee_invites table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS employee_invites (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                job_title VARCHAR(200),
                permission_role VARCHAR(50) DEFAULT 'sales',
                branch_id INTEGER,
                invite_token VARCHAR(100) NOT NULL UNIQUE,
                invited_by_user_id INTEGER REFERENCES users(id),
                status VARCHAR(50) DEFAULT 'pending',
                initial_config JSONB DEFAULT '{}',
                accepted_at TIMESTAMP,
                created_user_id INTEGER REFERENCES users(id),
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_employee_invites_email
                ON employee_invites(email);
            CREATE INDEX IF NOT EXISTS idx_employee_invites_token
                ON employee_invites(invite_token);
            CREATE INDEX IF NOT EXISTS idx_employee_invites_status
                ON employee_invites(status);
        """))

        # ========================================================================
        # SEED DEFAULT DATA
        # ========================================================================
        print("Seeding default roles...")
        conn.execute(text("""
            INSERT INTO onboarding_roles (name, description) VALUES
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
                ('Post-Closer', 'Handles post-closing activities')
            ON CONFLICT (name) DO NOTHING;
        """))

        print("Seeding default categories...")
        conn.execute(text("""
            INSERT INTO onboarding_categories (name, description, sort_order) VALUES
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
                ('Compliance & Quality', 'Compliance and quality control', 11)
            ON CONFLICT (name) DO NOTHING;
        """))

        print("Seeding default responsibilities...")
        conn.execute(text("""
            INSERT INTO onboarding_responsibilities (name, description, category_id, kpi_mapping)
            SELECT
                r.name, r.description, c.id, r.kpi_mapping::jsonb
            FROM (VALUES
                ('Lead Response', 'Respond to new leads within SLA', 'Lead Generation', '{"metric": "speed_to_lead", "target": 5, "unit": "minutes"}'),
                ('Lead Qualification', 'Qualify leads for loan products', 'Lead Generation', '{"metric": "leads_qualified", "target": 10, "unit": "per_day"}'),
                ('Credit Review', 'Review borrower credit reports', 'Pre-Qualification', '{"metric": "credit_reviews", "target": 5, "unit": "per_day"}'),
                ('Pre-Qual Letters', 'Issue pre-qualification letters', 'Pre-Qualification', '{"metric": "preqauls_issued", "target": 3, "unit": "per_day"}'),
                ('Borrower Follow-up', 'Follow up with borrowers regularly', 'Borrower Engagement', '{"metric": "followups", "target": 10, "unit": "per_day"}'),
                ('Status Updates', 'Provide loan status updates', 'Borrower Engagement', '{"metric": "updates_sent", "target": 5, "unit": "per_day"}'),
                ('Application Intake', 'Take loan applications', 'Application & Disclosure', '{"metric": "apps_taken", "target": 2, "unit": "per_day"}'),
                ('Disclosure Delivery', 'Deliver required disclosures', 'Application & Disclosure', '{"metric": "disclosures_sent", "target": 2, "unit": "per_day"}'),
                ('Document Collection', 'Collect required documents', 'Processing & Milestones', '{"metric": "docs_collected", "target": 10, "unit": "per_day"}'),
                ('Condition Clearing', 'Clear underwriting conditions', 'Processing & Milestones', '{"metric": "conditions_cleared", "target": 5, "unit": "per_day"}'),
                ('UW Communication', 'Communicate with underwriters', 'Underwriting Support', '{"metric": "uw_communications", "target": 5, "unit": "per_day"}'),
                ('Closing Coordination', 'Coordinate loan closings', 'Closing & Funding', '{"metric": "closings_coordinated", "target": 2, "unit": "per_day"}'),
                ('Funding Review', 'Review funding packages', 'Closing & Funding', '{"metric": "fundings_reviewed", "target": 2, "unit": "per_day"}'),
                ('Post-Close QC', 'Post-closing quality control', 'Post-Closing', '{"metric": "qc_reviews", "target": 3, "unit": "per_day"}'),
                ('Partner Outreach', 'Reach out to referral partners', 'Partner Management', '{"metric": "partner_contacts", "target": 5, "unit": "per_day"}'),
                ('Team Coaching', 'Coach team members', 'Team Management', '{"metric": "coaching_sessions", "target": 2, "unit": "per_week"}'),
                ('Compliance Review', 'Review files for compliance', 'Compliance & Quality', '{"metric": "compliance_reviews", "target": 3, "unit": "per_day"}')
            ) AS r(name, description, category_name, kpi_mapping)
            JOIN onboarding_categories c ON c.name = r.category_name
            ON CONFLICT DO NOTHING;
        """))

        print("Seeding default permission templates...")
        conn.execute(text("""
            INSERT INTO onboarding_permission_templates (name, description, is_system_template, risk_level, permissions) VALUES
                ('Loan Officer - Standard', 'Standard permissions for loan officers', true, 'low',
                 '{"leads": {"read": true, "write": true, "delete": false}, "loans": {"read": true, "write": true, "delete": false}, "pipeline": {"read": true, "write": true}, "reports": {"read": true}, "admin": {"read": false, "write": false}}'),
                ('Processor - Standard', 'Standard permissions for processors', true, 'low',
                 '{"leads": {"read": true, "write": false}, "loans": {"read": true, "write": true, "delete": false}, "documents": {"read": true, "write": true}, "conditions": {"read": true, "write": true}}'),
                ('Manager - Full', 'Full permissions for managers', true, 'medium',
                 '{"leads": {"read": true, "write": true, "delete": true}, "loans": {"read": true, "write": true, "delete": true}, "team": {"read": true, "write": true}, "reports": {"read": true, "write": true}, "admin": {"read": true, "write": false}}'),
                ('Admin - Full Access', 'Full administrative access', true, 'high',
                 '{"leads": {"read": true, "write": true, "delete": true}, "loans": {"read": true, "write": true, "delete": true}, "team": {"read": true, "write": true, "delete": true}, "reports": {"read": true, "write": true}, "admin": {"read": true, "write": true}, "settings": {"read": true, "write": true}}'),
                ('Read Only', 'View-only access', true, 'low',
                 '{"leads": {"read": true, "write": false}, "loans": {"read": true, "write": false}, "pipeline": {"read": true, "write": false}, "reports": {"read": true}}')
            ON CONFLICT (name) DO NOTHING;
        """))

        conn.commit()
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
            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))

        conn.commit()
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
