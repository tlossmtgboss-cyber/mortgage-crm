"""
Migration: Add Account Management Tables
Creates all tables needed for the Master Administrator Account Management system.
Includes: Accounts/Tenants, Subscriptions, Cost Tracking, Audit Logs, Login Events
"""

from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Run the account management tables migration."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if main table already exists
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'tenant_accounts'
        """))

        if result.fetchone():
            print("Account management tables already exist. Skipping migration.")
            return

        print("Creating account management tables...")

        # 1. Tenant Accounts (Business Accounts)
        conn.execute(text("""
            CREATE TABLE tenant_accounts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                domain VARCHAR(255),
                status VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'canceled')),
                plan_id VARCHAR(100),
                plan_name VARCHAR(100),
                billing_interval VARCHAR(20) DEFAULT 'monthly'
                    CHECK (billing_interval IN ('monthly', 'annually')),
                seats_purchased INTEGER DEFAULT 1,
                stripe_customer_id VARCHAR(255),
                stripe_subscription_id VARCHAR(255),
                owner_user_id INTEGER REFERENCES users(id),
                internal_notes TEXT,
                add_ons JSONB DEFAULT '[]',
                settings JSONB DEFAULT '{}',
                suspended_at TIMESTAMP,
                suspended_reason TEXT,
                canceled_at TIMESTAMP,
                canceled_reason TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                is_deleted BOOLEAN DEFAULT false
            );

            CREATE INDEX idx_tenant_accounts_status ON tenant_accounts(status);
            CREATE INDEX idx_tenant_accounts_domain ON tenant_accounts(domain);
            CREATE INDEX idx_tenant_accounts_owner ON tenant_accounts(owner_user_id);
            CREATE INDEX idx_tenant_accounts_stripe ON tenant_accounts(stripe_customer_id);
        """))
        print("Created tenant_accounts table")

        # 2. Subscriptions (detailed subscription info)
        conn.execute(text("""
            CREATE TABLE account_subscriptions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id UUID NOT NULL REFERENCES tenant_accounts(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL DEFAULT 'stripe',
                provider_subscription_id VARCHAR(255),
                status VARCHAR(30) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'unpaid', 'incomplete')),
                plan_id VARCHAR(100),
                plan_name VARCHAR(100),
                price_amount NUMERIC(10, 2),
                price_currency VARCHAR(3) DEFAULT 'USD',
                quantity INTEGER DEFAULT 1,
                current_period_start TIMESTAMP,
                current_period_end TIMESTAMP,
                cancel_at_period_end BOOLEAN DEFAULT false,
                cancel_at TIMESTAMP,
                trial_start TIMESTAMP,
                trial_end TIMESTAMP,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_subscriptions_account ON account_subscriptions(account_id);
            CREATE INDEX idx_subscriptions_status ON account_subscriptions(status);
            CREATE INDEX idx_subscriptions_provider ON account_subscriptions(provider_subscription_id);
        """))
        print("Created account_subscriptions table")

        # 3. Subscription Events (timeline)
        conn.execute(text("""
            CREATE TABLE subscription_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id UUID NOT NULL REFERENCES tenant_accounts(id) ON DELETE CASCADE,
                event_type VARCHAR(50) NOT NULL
                    CHECK (event_type IN ('created', 'upgraded', 'downgraded', 'suspended',
                           'reinstated', 'canceled', 'renewed', 'payment_failed', 'payment_succeeded',
                           'trial_started', 'trial_ended', 'seats_changed')),
                from_plan VARCHAR(100),
                to_plan VARCHAR(100),
                from_seats INTEGER,
                to_seats INTEGER,
                amount NUMERIC(10, 2),
                actor_id INTEGER REFERENCES users(id),
                actor_name VARCHAR(255),
                reason TEXT,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_sub_events_account ON subscription_events(account_id);
            CREATE INDEX idx_sub_events_type ON subscription_events(event_type);
            CREATE INDEX idx_sub_events_created ON subscription_events(created_at);
        """))
        print("Created subscription_events table")

        # 4. Account Invoices
        conn.execute(text("""
            CREATE TABLE account_invoices (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id UUID NOT NULL REFERENCES tenant_accounts(id) ON DELETE CASCADE,
                stripe_invoice_id VARCHAR(255),
                invoice_number VARCHAR(100),
                amount NUMERIC(12, 2) NOT NULL,
                amount_due NUMERIC(12, 2),
                amount_paid NUMERIC(12, 2),
                currency VARCHAR(3) DEFAULT 'USD',
                status VARCHAR(30) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'open', 'paid', 'void', 'uncollectible')),
                description TEXT,
                invoice_url VARCHAR(500),
                invoice_pdf VARCHAR(500),
                period_start TIMESTAMP,
                period_end TIMESTAMP,
                due_date TIMESTAMP,
                paid_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_invoices_account ON account_invoices(account_id);
            CREATE INDEX idx_invoices_status ON account_invoices(status);
            CREATE INDEX idx_invoices_stripe ON account_invoices(stripe_invoice_id);
            CREATE INDEX idx_invoices_created ON account_invoices(created_at);
        """))
        print("Created account_invoices table")

        # 5. Cost Ledger (monthly cost tracking)
        conn.execute(text("""
            CREATE TABLE cost_ledger_monthly (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id UUID NOT NULL REFERENCES tenant_accounts(id) ON DELETE CASCADE,
                month VARCHAR(7) NOT NULL,
                cost_category VARCHAR(50) NOT NULL
                    CHECK (cost_category IN ('ai_usage', 'telephony', 'sms', 'email',
                           'storage', 'compute', 'support', 'third_party_api', 'other')),
                vendor VARCHAR(100),
                amount NUMERIC(12, 4) NOT NULL DEFAULT 0,
                units NUMERIC(12, 4),
                unit_type VARCHAR(50),
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(account_id, month, cost_category, vendor)
            );

            CREATE INDEX idx_cost_ledger_account ON cost_ledger_monthly(account_id);
            CREATE INDEX idx_cost_ledger_month ON cost_ledger_monthly(month);
            CREATE INDEX idx_cost_ledger_category ON cost_ledger_monthly(cost_category);
        """))
        print("Created cost_ledger_monthly table")

        # 6. Usage Events (granular tracking)
        conn.execute(text("""
            CREATE TABLE usage_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id UUID REFERENCES tenant_accounts(id) ON DELETE SET NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                event_type VARCHAR(100) NOT NULL,
                category VARCHAR(50),
                units NUMERIC(12, 4) NOT NULL DEFAULT 1,
                unit_type VARCHAR(50),
                cost_estimate NUMERIC(12, 6),
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_usage_events_account ON usage_events(account_id);
            CREATE INDEX idx_usage_events_user ON usage_events(user_id);
            CREATE INDEX idx_usage_events_type ON usage_events(event_type);
            CREATE INDEX idx_usage_events_created ON usage_events(created_at);
        """))
        print("Created usage_events table")

        # 7. Login Events
        conn.execute(text("""
            CREATE TABLE login_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                account_id UUID REFERENCES tenant_accounts(id) ON DELETE SET NULL,
                result VARCHAR(20) NOT NULL CHECK (result IN ('success', 'failed')),
                failure_reason VARCHAR(255),
                ip_address VARCHAR(45),
                user_agent TEXT,
                device VARCHAR(100),
                browser VARCHAR(100),
                os VARCHAR(100),
                location VARCHAR(255),
                country VARCHAR(100),
                city VARCHAR(100),
                session_id VARCHAR(255),
                session_duration_seconds INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_login_events_user ON login_events(user_id);
            CREATE INDEX idx_login_events_account ON login_events(account_id);
            CREATE INDEX idx_login_events_result ON login_events(result);
            CREATE INDEX idx_login_events_created ON login_events(created_at);
        """))
        print("Created login_events table")

        # 8. Admin Audit Log
        conn.execute(text("""
            CREATE TABLE admin_audit_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                actor_admin_id INTEGER NOT NULL REFERENCES users(id),
                actor_name VARCHAR(255),
                action_type VARCHAR(100) NOT NULL,
                target_type VARCHAR(50) NOT NULL,
                target_id VARCHAR(255),
                target_name VARCHAR(255),
                ip_address VARCHAR(45),
                user_agent TEXT,
                old_values JSONB,
                new_values JSONB,
                reason TEXT,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_audit_log_actor ON admin_audit_log(actor_admin_id);
            CREATE INDEX idx_audit_log_action ON admin_audit_log(action_type);
            CREATE INDEX idx_audit_log_target ON admin_audit_log(target_type, target_id);
            CREATE INDEX idx_audit_log_created ON admin_audit_log(created_at);
        """))
        print("Created admin_audit_log table")

        # 9. Impersonation Sessions
        conn.execute(text("""
            CREATE TABLE impersonation_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                admin_user_id INTEGER NOT NULL REFERENCES users(id),
                target_user_id INTEGER NOT NULL REFERENCES users(id),
                account_id UUID REFERENCES tenant_accounts(id),
                reason TEXT NOT NULL,
                acknowledgment_checked BOOLEAN DEFAULT false,
                started_at TIMESTAMP DEFAULT NOW(),
                ended_at TIMESTAMP,
                actions_taken JSONB DEFAULT '[]',
                ip_address VARCHAR(45),
                user_agent TEXT,
                is_active BOOLEAN DEFAULT true
            );

            CREATE INDEX idx_impersonation_admin ON impersonation_sessions(admin_user_id);
            CREATE INDEX idx_impersonation_target ON impersonation_sessions(target_user_id);
            CREATE INDEX idx_impersonation_active ON impersonation_sessions(is_active);
            CREATE INDEX idx_impersonation_started ON impersonation_sessions(started_at);
        """))
        print("Created impersonation_sessions table")

        # 10. User Activity Stats (aggregated)
        conn.execute(text("""
            CREATE TABLE user_activity_stats (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                account_id UUID REFERENCES tenant_accounts(id) ON DELETE SET NULL,
                period VARCHAR(7) NOT NULL,
                tasks_completed INTEGER DEFAULT 0,
                calls_placed INTEGER DEFAULT 0,
                calls_received INTEGER DEFAULT 0,
                texts_sent INTEGER DEFAULT 0,
                emails_sent INTEGER DEFAULT 0,
                notes_created INTEGER DEFAULT 0,
                leads_created INTEGER DEFAULT 0,
                loans_created INTEGER DEFAULT 0,
                documents_uploaded INTEGER DEFAULT 0,
                ai_actions_triggered INTEGER DEFAULT 0,
                active_minutes INTEGER DEFAULT 0,
                login_count INTEGER DEFAULT 0,
                last_activity_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, period)
            );

            CREATE INDEX idx_activity_stats_user ON user_activity_stats(user_id);
            CREATE INDEX idx_activity_stats_account ON user_activity_stats(account_id);
            CREATE INDEX idx_activity_stats_period ON user_activity_stats(period);
        """))
        print("Created user_activity_stats table")

        # 11. Account KPI Snapshots (for historical trends)
        conn.execute(text("""
            CREATE TABLE account_kpi_snapshots (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                snapshot_date DATE NOT NULL,
                total_active_accounts INTEGER DEFAULT 0,
                total_suspended_accounts INTEGER DEFAULT 0,
                total_canceled_accounts INTEGER DEFAULT 0,
                total_mrr NUMERIC(14, 2) DEFAULT 0,
                total_arr NUMERIC(14, 2) DEFAULT 0,
                total_seats_purchased INTEGER DEFAULT 0,
                total_seats_used INTEGER DEFAULT 0,
                avg_cost_per_user NUMERIC(10, 2) DEFAULT 0,
                avg_margin_percent NUMERIC(5, 2) DEFAULT 0,
                accounts_at_risk INTEGER DEFAULT 0,
                churn_rate NUMERIC(5, 2) DEFAULT 0,
                mrr_growth_percent NUMERIC(8, 2) DEFAULT 0,
                new_accounts INTEGER DEFAULT 0,
                churned_accounts INTEGER DEFAULT 0,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(snapshot_date)
            );

            CREATE INDEX idx_kpi_snapshots_date ON account_kpi_snapshots(snapshot_date);
        """))
        print("Created account_kpi_snapshots table")

        # 12. User Roles Junction (for account-specific roles)
        conn.execute(text("""
            CREATE TABLE account_user_roles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                account_id UUID NOT NULL REFERENCES tenant_accounts(id) ON DELETE CASCADE,
                role VARCHAR(100) NOT NULL,
                assigned_at TIMESTAMP DEFAULT NOW(),
                assigned_by INTEGER REFERENCES users(id),
                UNIQUE(user_id, account_id, role)
            );

            CREATE INDEX idx_user_roles_user ON account_user_roles(user_id);
            CREATE INDEX idx_user_roles_account ON account_user_roles(account_id);
            CREATE INDEX idx_user_roles_role ON account_user_roles(role);
        """))
        print("Created account_user_roles table")

        # Add tenant_account_id to users table if not exists
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'tenant_account_id'
                ) THEN
                    ALTER TABLE users ADD COLUMN tenant_account_id UUID REFERENCES tenant_accounts(id);
                    CREATE INDEX idx_users_tenant ON users(tenant_account_id);
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'last_activity_at'
                ) THEN
                    ALTER TABLE users ADD COLUMN last_activity_at TIMESTAMP;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'mfa_enabled'
                ) THEN
                    ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN DEFAULT false;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'active_sessions_count'
                ) THEN
                    ALTER TABLE users ADD COLUMN active_sessions_count INTEGER DEFAULT 0;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'device_count'
                ) THEN
                    ALTER TABLE users ADD COLUMN device_count INTEGER DEFAULT 0;
                END IF;
            END $$;
        """))
        print("Added tenant_account_id and activity columns to users table")

        conn.commit()
        print("Account management tables created successfully!")


if __name__ == "__main__":
    run_migration()
