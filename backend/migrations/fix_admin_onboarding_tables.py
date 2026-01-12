"""
Migration: Fix Admin Onboarding Tables
Ensures all tables and columns exist for the admin onboarding flow.
This is an idempotent migration - safe to run multiple times.
"""

from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Run the admin onboarding tables migration."""
    if not DATABASE_URL:
        print("Error: DATABASE_URL environment variable not set")
        return False

    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)

    with engine.connect() as conn:
        print("Starting admin onboarding tables migration...")

        # 1. Create tenant_accounts table if not exists
        print("Checking tenant_accounts table...")
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'tenant_accounts'
        """))

        if not result.fetchone():
            print("Creating tenant_accounts table...")
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
                    owner_user_id INTEGER,
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

                CREATE INDEX IF NOT EXISTS idx_tenant_accounts_status ON tenant_accounts(status);
                CREATE INDEX IF NOT EXISTS idx_tenant_accounts_domain ON tenant_accounts(domain);
                CREATE INDEX IF NOT EXISTS idx_tenant_accounts_owner ON tenant_accounts(owner_user_id);
                CREATE INDEX IF NOT EXISTS idx_tenant_accounts_stripe ON tenant_accounts(stripe_customer_id);
            """))
            print("Created tenant_accounts table")
        else:
            print("tenant_accounts table already exists")

        # 2. Create subscriber_invitations table if not exists
        print("Checking subscriber_invitations table...")
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'subscriber_invitations'
        """))

        if not result.fetchone():
            print("Creating subscriber_invitations table...")
            conn.execute(text("""
                CREATE TABLE subscriber_invitations (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    token VARCHAR(255) NOT NULL UNIQUE,
                    email VARCHAR(255) NOT NULL,
                    company_name VARCHAR(255) NOT NULL,
                    contact_name VARCHAR(255),
                    plan VARCHAR(100) NOT NULL DEFAULT 'professional',
                    seats INTEGER NOT NULL DEFAULT 5,
                    promo_code VARCHAR(50),
                    personal_message TEXT,
                    status VARCHAR(30) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'accepted', 'expired', 'revoked')),
                    invited_by INTEGER,
                    invited_by_name VARCHAR(255),
                    expires_at TIMESTAMP NOT NULL,
                    accepted_at TIMESTAMP,
                    accepted_by_user_id INTEGER,
                    revoked_at TIMESTAMP,
                    revoked_by INTEGER,
                    ip_address VARCHAR(45),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_sub_invites_token ON subscriber_invitations(token);
                CREATE INDEX IF NOT EXISTS idx_sub_invites_email ON subscriber_invitations(email);
                CREATE INDEX IF NOT EXISTS idx_sub_invites_status ON subscriber_invitations(status);
                CREATE INDEX IF NOT EXISTS idx_sub_invites_expires ON subscriber_invitations(expires_at);
                CREATE INDEX IF NOT EXISTS idx_sub_invites_created ON subscriber_invitations(created_at);
            """))
            print("Created subscriber_invitations table")
        else:
            print("subscriber_invitations table already exists")

        # 3. Create admin_audit_log table if not exists
        print("Checking admin_audit_log table...")
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'admin_audit_log'
        """))

        if not result.fetchone():
            print("Creating admin_audit_log table...")
            conn.execute(text("""
                CREATE TABLE admin_audit_log (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    actor_admin_id INTEGER,
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

                CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON admin_audit_log(actor_admin_id);
                CREATE INDEX IF NOT EXISTS idx_audit_log_action ON admin_audit_log(action_type);
                CREATE INDEX IF NOT EXISTS idx_audit_log_target ON admin_audit_log(target_type, target_id);
                CREATE INDEX IF NOT EXISTS idx_audit_log_created ON admin_audit_log(created_at);
            """))
            print("Created admin_audit_log table")
        else:
            print("admin_audit_log table already exists")

        # 4. Create account_subscriptions table if not exists
        print("Checking account_subscriptions table...")
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'account_subscriptions'
        """))

        if not result.fetchone():
            print("Creating account_subscriptions table...")
            conn.execute(text("""
                CREATE TABLE account_subscriptions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    account_id UUID REFERENCES tenant_accounts(id) ON DELETE CASCADE,
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

                CREATE INDEX IF NOT EXISTS idx_subscriptions_account ON account_subscriptions(account_id);
                CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON account_subscriptions(status);
                CREATE INDEX IF NOT EXISTS idx_subscriptions_provider ON account_subscriptions(provider_subscription_id);
            """))
            print("Created account_subscriptions table")
        else:
            print("account_subscriptions table already exists")

        # 5. Add tenant_account_id column to users table if not exists
        print("Checking users.tenant_account_id column...")
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'tenant_account_id'
        """))

        if not result.fetchone():
            print("Adding tenant_account_id column to users table...")
            conn.execute(text("""
                ALTER TABLE users ADD COLUMN tenant_account_id UUID REFERENCES tenant_accounts(id);
                CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_account_id);
            """))
            print("Added tenant_account_id column")
        else:
            print("users.tenant_account_id column already exists")

        # 6. Add onboarding_completed column to users table if not exists
        print("Checking users.onboarding_completed column...")
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'onboarding_completed'
        """))

        if not result.fetchone():
            print("Adding onboarding_completed column to users table...")
            conn.execute(text("""
                ALTER TABLE users ADD COLUMN onboarding_completed BOOLEAN DEFAULT false;
            """))
            print("Added onboarding_completed column")
        else:
            print("users.onboarding_completed column already exists")

        # 7. Add headshot_url column to users table if not exists
        print("Checking users.headshot_url column...")
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'headshot_url'
        """))

        if not result.fetchone():
            print("Adding headshot_url column to users table...")
            conn.execute(text("""
                ALTER TABLE users ADD COLUMN headshot_url VARCHAR(500);
            """))
            print("Added headshot_url column")
        else:
            print("users.headshot_url column already exists")

        # 8. Create user_invitations table if not exists (for team invites)
        print("Checking user_invitations table...")
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'user_invitations'
        """))

        if not result.fetchone():
            print("Creating user_invitations table...")
            conn.execute(text("""
                CREATE TABLE user_invitations (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR(255) NOT NULL,
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    permission_role VARCHAR(100),
                    invited_by INTEGER,
                    organization_id UUID,
                    token VARCHAR(255) NOT NULL UNIQUE,
                    expires_at TIMESTAMP NOT NULL,
                    accepted_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_user_invites_email ON user_invitations(email);
                CREATE INDEX IF NOT EXISTS idx_user_invites_token ON user_invitations(token);
                CREATE INDEX IF NOT EXISTS idx_user_invites_org ON user_invitations(organization_id);
            """))
            print("Created user_invitations table")
        else:
            print("user_invitations table already exists")

        conn.commit()
        print("\nAdmin onboarding tables migration completed successfully!")
        return True


if __name__ == "__main__":
    run_migration()
