"""
Migration: Add Business Operations Dashboard Tables
Creates tables for revenue tracking, service costs, marketing, forecasting, and KPIs.
Supports both SQLite and PostgreSQL.
"""

from sqlalchemy import create_engine, text, inspect
import os
import uuid

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")


def is_sqlite(url):
    """Check if the database is SQLite."""
    return url.startswith("sqlite")


def run_migration():
    """Run the business operations tables migration."""
    engine = create_engine(DATABASE_URL)
    is_sqlite_db = is_sqlite(DATABASE_URL)

    with engine.connect() as conn:
        # Check if main table already exists
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        if 'service_providers' in existing_tables:
            print("Business operations tables already exist. Skipping migration.")
            return

        print(f"Creating business operations tables... (SQLite mode: {is_sqlite_db})")

        if is_sqlite_db:
            run_sqlite_migration(conn)
        else:
            run_postgres_migration(conn)

        # Commit all changes
        conn.commit()
        print("\nAll business operations tables created successfully!")

        # Seed default service providers
        seed_service_providers(conn, is_sqlite_db)


def run_sqlite_migration(conn):
    """Create tables with SQLite-compatible syntax."""

    # 1. Service Providers (registry of external services)
    conn.execute(text("""
        CREATE TABLE service_providers (
            id TEXT PRIMARY KEY,
            organization_id INTEGER NOT NULL,

            name TEXT NOT NULL,
            display_name TEXT,
            category TEXT NOT NULL,
            provider_type TEXT NOT NULL,
            description TEXT,
            website_url TEXT,

            api_key_env_var TEXT,
            api_endpoint TEXT,
            has_usage_api INTEGER DEFAULT 0,
            auto_fetch_enabled INTEGER DEFAULT 0,
            last_fetched_at TEXT,
            fetch_error TEXT,

            pricing_model TEXT NOT NULL,
            base_cost REAL DEFAULT 0,
            unit_type TEXT,
            unit_cost REAL,
            percentage_rate REAL,
            billing_cycle TEXT DEFAULT 'monthly',

            monthly_budget REAL,
            alert_threshold_percent INTEGER DEFAULT 80,
            alert_email TEXT,

            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(organization_id, provider_type)
        )
    """))
    conn.execute(text("CREATE INDEX idx_service_providers_org ON service_providers(organization_id)"))
    conn.execute(text("CREATE INDEX idx_service_providers_category ON service_providers(category)"))
    conn.execute(text("CREATE INDEX idx_service_providers_type ON service_providers(provider_type)"))
    print("  Created: service_providers")

    # 2. Service Usage Records (daily usage tracking)
    conn.execute(text("""
        CREATE TABLE service_usage_records (
            id TEXT PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            service_provider_id TEXT NOT NULL REFERENCES service_providers(id) ON DELETE CASCADE,

            usage_date TEXT NOT NULL,
            usage_type TEXT,
            quantity REAL NOT NULL,
            unit_type TEXT,

            unit_cost REAL,
            total_cost REAL NOT NULL,

            metadata_json TEXT,
            source TEXT DEFAULT 'manual',
            external_id TEXT,

            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX idx_usage_org_date ON service_usage_records(organization_id, usage_date)"))
    conn.execute(text("CREATE INDEX idx_usage_provider_date ON service_usage_records(service_provider_id, usage_date)"))
    conn.execute(text("CREATE INDEX idx_usage_source ON service_usage_records(source)"))
    print("  Created: service_usage_records")

    # 3. Service Invoices (monthly invoice tracking)
    conn.execute(text("""
        CREATE TABLE service_invoices (
            id TEXT PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            service_provider_id TEXT NOT NULL REFERENCES service_providers(id) ON DELETE CASCADE,

            invoice_date TEXT NOT NULL,
            invoice_period_start TEXT NOT NULL,
            invoice_period_end TEXT NOT NULL,

            subtotal REAL NOT NULL,
            taxes REAL DEFAULT 0,
            credits REAL DEFAULT 0,
            total_amount REAL NOT NULL,

            external_invoice_id TEXT,
            external_invoice_url TEXT,

            status TEXT DEFAULT 'pending',
            paid_at TEXT,

            source TEXT DEFAULT 'manual',
            raw_data TEXT,

            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX idx_invoice_org_date ON service_invoices(organization_id, invoice_date)"))
    conn.execute(text("CREATE INDEX idx_invoice_provider ON service_invoices(service_provider_id)"))
    conn.execute(text("CREATE INDEX idx_invoice_status ON service_invoices(status)"))
    print("  Created: service_invoices")

    # 4. Subscription Revenue (MRR/ARR tracking)
    conn.execute(text("""
        CREATE TABLE subscription_revenue (
            id TEXT PRIMARY KEY,
            organization_id INTEGER NOT NULL,

            customer_id INTEGER,
            customer_name TEXT NOT NULL,
            customer_email TEXT,
            customer_segment TEXT,

            subscription_tier TEXT NOT NULL,
            billing_cycle TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            renewal_date TEXT,

            mrr REAL NOT NULL,
            arr REAL,
            discount_percent REAL DEFAULT 0,

            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,

            status TEXT DEFAULT 'active',
            churn_date TEXT,
            churn_reason TEXT,

            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX idx_subscription_org ON subscription_revenue(organization_id)"))
    conn.execute(text("CREATE INDEX idx_subscription_status ON subscription_revenue(organization_id, status)"))
    conn.execute(text("CREATE INDEX idx_subscription_customer ON subscription_revenue(customer_id)"))
    conn.execute(text("CREATE INDEX idx_subscription_stripe ON subscription_revenue(stripe_subscription_id)"))
    print("  Created: subscription_revenue")

    # 5. Usage Revenue (per-loan, API calls, overages)
    conn.execute(text("""
        CREATE TABLE usage_revenue (
            id TEXT PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            customer_id INTEGER,

            revenue_date TEXT NOT NULL,
            revenue_type TEXT NOT NULL,

            quantity REAL,
            unit_price REAL,
            amount REAL NOT NULL,

            description TEXT,

            reference_type TEXT,
            reference_id TEXT,

            stripe_invoice_id TEXT,
            stripe_line_item_id TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX idx_usage_revenue_org_date ON usage_revenue(organization_id, revenue_date)"))
    conn.execute(text("CREATE INDEX idx_usage_revenue_customer ON usage_revenue(customer_id)"))
    conn.execute(text("CREATE INDEX idx_usage_revenue_type ON usage_revenue(revenue_type)"))
    print("  Created: usage_revenue")

    # 6. Marketing Campaigns
    conn.execute(text("""
        CREATE TABLE marketing_campaigns (
            id TEXT PRIMARY KEY,
            organization_id INTEGER NOT NULL,

            name TEXT NOT NULL,
            channel TEXT NOT NULL,
            campaign_type TEXT,

            budget REAL,
            spend_to_date REAL DEFAULT 0,

            start_date TEXT NOT NULL,
            end_date TEXT,
            status TEXT DEFAULT 'active',

            target_audience TEXT,
            external_campaign_id TEXT,

            description TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX idx_campaigns_org ON marketing_campaigns(organization_id)"))
    conn.execute(text("CREATE INDEX idx_campaigns_status ON marketing_campaigns(status)"))
    conn.execute(text("CREATE INDEX idx_campaigns_channel ON marketing_campaigns(channel)"))
    print("  Created: marketing_campaigns")

    # 7. Marketing Metrics (daily performance)
    conn.execute(text("""
        CREATE TABLE marketing_metrics (
            id TEXT PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            campaign_id TEXT REFERENCES marketing_campaigns(id) ON DELETE SET NULL,

            metric_date TEXT NOT NULL,
            channel TEXT,

            impressions INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            leads_generated INTEGER DEFAULT 0,
            trials_started INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0,

            spend REAL DEFAULT 0,
            cpc REAL,
            cpl REAL,
            cac REAL,

            attributed_revenue REAL DEFAULT 0,
            attributed_mrr REAL DEFAULT 0,
            roas REAL,

            source TEXT DEFAULT 'manual',
            raw_data TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX idx_marketing_org_date ON marketing_metrics(organization_id, metric_date)"))
    conn.execute(text("CREATE INDEX idx_marketing_campaign ON marketing_metrics(campaign_id)"))
    conn.execute(text("CREATE INDEX idx_marketing_channel ON marketing_metrics(channel)"))
    print("  Created: marketing_metrics")

    # 8. Business Forecasts (projections and scenarios)
    conn.execute(text("""
        CREATE TABLE business_forecasts (
            id TEXT PRIMARY KEY,
            organization_id INTEGER NOT NULL,

            forecast_name TEXT NOT NULL,
            forecast_type TEXT NOT NULL,
            description TEXT,

            base_month TEXT NOT NULL,
            projection_months INTEGER DEFAULT 12,

            parameters TEXT NOT NULL,
            monthly_projections TEXT,
            summary TEXT,

            created_by INTEGER,
            is_primary INTEGER DEFAULT 0,
            is_scenario INTEGER DEFAULT 0,
            parent_forecast_id TEXT REFERENCES business_forecasts(id),

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX idx_forecasts_org ON business_forecasts(organization_id)"))
    conn.execute(text("CREATE INDEX idx_forecasts_type ON business_forecasts(forecast_type)"))
    print("  Created: business_forecasts")

    # 9. Business KPIs (daily snapshots)
    conn.execute(text("""
        CREATE TABLE business_kpis (
            id TEXT PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            snapshot_date TEXT NOT NULL,

            mrr REAL,
            arr REAL,
            total_revenue_mtd REAL,
            revenue_growth_rate REAL,

            total_customers INTEGER,
            new_customers_mtd INTEGER,
            churned_customers_mtd INTEGER,
            churn_rate REAL,
            net_revenue_retention REAL,

            total_monthly_costs REAL,
            service_costs REAL,
            employee_costs REAL,
            marketing_costs REAL,
            other_costs REAL,

            gross_profit REAL,
            gross_margin REAL,
            net_profit REAL,
            net_margin REAL,

            cash_balance REAL,
            burn_rate REAL,
            cash_runway_months REAL,

            cac REAL,
            ltv REAL,
            ltv_cac_ratio REAL,
            arpu REAL,

            service_cost_breakdown TEXT,
            data_json TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(organization_id, snapshot_date)
        )
    """))
    conn.execute(text("CREATE INDEX idx_kpis_org_date ON business_kpis(organization_id, snapshot_date)"))
    print("  Created: business_kpis")

    # 10. Budget Alerts
    conn.execute(text("""
        CREATE TABLE budget_alerts (
            id TEXT PRIMARY KEY,
            organization_id INTEGER NOT NULL,

            alert_type TEXT NOT NULL,
            service_provider_id TEXT REFERENCES service_providers(id) ON DELETE CASCADE,
            category TEXT,

            threshold_percent INTEGER NOT NULL,
            current_spend REAL NOT NULL,
            budget_amount REAL NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,

            status TEXT DEFAULT 'active',
            acknowledged_by INTEGER,
            acknowledged_at TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX idx_alerts_org ON budget_alerts(organization_id)"))
    conn.execute(text("CREATE INDEX idx_alerts_status ON budget_alerts(status)"))
    conn.execute(text("CREATE INDEX idx_alerts_provider ON budget_alerts(service_provider_id)"))
    print("  Created: budget_alerts")


def run_postgres_migration(conn):
    """Create tables with PostgreSQL-specific syntax."""

    # 1. Service Providers (registry of external services)
    conn.execute(text("""
        CREATE TABLE service_providers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,

            name VARCHAR(100) NOT NULL,
            display_name VARCHAR(150),
            category VARCHAR(50) NOT NULL CHECK (category IN ('ai', 'communications', 'storage', 'hosting', 'payments', 'crm', 'monitoring', 'email', 'other')),
            provider_type VARCHAR(50) NOT NULL,
            description TEXT,
            website_url VARCHAR(500),

            api_key_env_var VARCHAR(100),
            api_endpoint VARCHAR(500),
            has_usage_api BOOLEAN DEFAULT false,
            auto_fetch_enabled BOOLEAN DEFAULT false,
            last_fetched_at TIMESTAMP,
            fetch_error TEXT,

            pricing_model VARCHAR(30) NOT NULL CHECK (pricing_model IN ('per_unit', 'tiered', 'subscription', 'usage_based', 'percentage', 'hybrid')),
            base_cost NUMERIC(12, 4) DEFAULT 0,
            unit_type VARCHAR(50),
            unit_cost NUMERIC(12, 8),
            percentage_rate NUMERIC(6, 4),
            billing_cycle VARCHAR(20) DEFAULT 'monthly',

            monthly_budget NUMERIC(12, 2),
            alert_threshold_percent INTEGER DEFAULT 80,
            alert_email VARCHAR(255),

            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),

            UNIQUE(organization_id, provider_type)
        );

        CREATE INDEX idx_service_providers_org ON service_providers(organization_id);
        CREATE INDEX idx_service_providers_category ON service_providers(category);
        CREATE INDEX idx_service_providers_type ON service_providers(provider_type);
    """))
    print("  Created: service_providers")

    # 2. Service Usage Records (daily usage tracking)
    conn.execute(text("""
        CREATE TABLE service_usage_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,
            service_provider_id UUID NOT NULL REFERENCES service_providers(id) ON DELETE CASCADE,

            usage_date DATE NOT NULL,
            usage_type VARCHAR(50),
            quantity NUMERIC(18, 6) NOT NULL,
            unit_type VARCHAR(50),

            unit_cost NUMERIC(12, 8),
            total_cost NUMERIC(12, 4) NOT NULL,

            metadata_json JSONB,
            source VARCHAR(20) DEFAULT 'manual' CHECK (source IN ('api', 'manual', 'csv_import')),
            external_id VARCHAR(100),

            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_usage_org_date ON service_usage_records(organization_id, usage_date);
        CREATE INDEX idx_usage_provider_date ON service_usage_records(service_provider_id, usage_date);
        CREATE INDEX idx_usage_source ON service_usage_records(source);
    """))
    print("  Created: service_usage_records")

    # 3. Service Invoices (monthly invoice tracking)
    conn.execute(text("""
        CREATE TABLE service_invoices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,
            service_provider_id UUID NOT NULL REFERENCES service_providers(id) ON DELETE CASCADE,

            invoice_date DATE NOT NULL,
            invoice_period_start DATE NOT NULL,
            invoice_period_end DATE NOT NULL,

            subtotal NUMERIC(12, 2) NOT NULL,
            taxes NUMERIC(12, 2) DEFAULT 0,
            credits NUMERIC(12, 2) DEFAULT 0,
            total_amount NUMERIC(12, 2) NOT NULL,

            external_invoice_id VARCHAR(100),
            external_invoice_url VARCHAR(500),

            status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'overdue', 'cancelled')),
            paid_at TIMESTAMP,

            source VARCHAR(20) DEFAULT 'manual',
            raw_data JSONB,

            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_invoice_org_date ON service_invoices(organization_id, invoice_date);
        CREATE INDEX idx_invoice_provider ON service_invoices(service_provider_id);
        CREATE INDEX idx_invoice_status ON service_invoices(status);
    """))
    print("  Created: service_invoices")

    # 4. Subscription Revenue (MRR/ARR tracking)
    conn.execute(text("""
        CREATE TABLE subscription_revenue (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,

            customer_id INTEGER,
            customer_name VARCHAR(255) NOT NULL,
            customer_email VARCHAR(255),
            customer_segment VARCHAR(50),

            subscription_tier VARCHAR(50) NOT NULL,
            billing_cycle VARCHAR(20) NOT NULL CHECK (billing_cycle IN ('monthly', 'annual', 'quarterly')),
            start_date DATE NOT NULL,
            end_date DATE,
            renewal_date DATE,

            mrr NUMERIC(12, 2) NOT NULL,
            arr NUMERIC(12, 2),
            discount_percent NUMERIC(5, 2) DEFAULT 0,

            stripe_customer_id VARCHAR(100),
            stripe_subscription_id VARCHAR(100),

            status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('trial', 'active', 'paused', 'churned', 'cancelled')),
            churn_date DATE,
            churn_reason VARCHAR(255),

            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_subscription_org ON subscription_revenue(organization_id);
        CREATE INDEX idx_subscription_status ON subscription_revenue(organization_id, status);
        CREATE INDEX idx_subscription_customer ON subscription_revenue(customer_id);
        CREATE INDEX idx_subscription_stripe ON subscription_revenue(stripe_subscription_id);
    """))
    print("  Created: subscription_revenue")

    # 5. Usage Revenue (per-loan, API calls, overages)
    conn.execute(text("""
        CREATE TABLE usage_revenue (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,
            customer_id INTEGER,

            revenue_date DATE NOT NULL,
            revenue_type VARCHAR(50) NOT NULL CHECK (revenue_type IN ('per_loan', 'api_calls', 'overage', 'addon', 'setup_fee', 'consulting', 'other')),

            quantity NUMERIC(15, 4),
            unit_price NUMERIC(12, 4),
            amount NUMERIC(12, 2) NOT NULL,

            description TEXT,

            reference_type VARCHAR(50),
            reference_id VARCHAR(100),

            stripe_invoice_id VARCHAR(100),
            stripe_line_item_id VARCHAR(100),

            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_usage_revenue_org_date ON usage_revenue(organization_id, revenue_date);
        CREATE INDEX idx_usage_revenue_customer ON usage_revenue(customer_id);
        CREATE INDEX idx_usage_revenue_type ON usage_revenue(revenue_type);
    """))
    print("  Created: usage_revenue")

    # 6. Marketing Campaigns
    conn.execute(text("""
        CREATE TABLE marketing_campaigns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,

            name VARCHAR(255) NOT NULL,
            channel VARCHAR(50) NOT NULL CHECK (channel IN ('google_ads', 'facebook', 'linkedin', 'email', 'referral', 'organic', 'content', 'events', 'direct', 'other')),
            campaign_type VARCHAR(50),

            budget NUMERIC(12, 2),
            spend_to_date NUMERIC(12, 2) DEFAULT 0,

            start_date DATE NOT NULL,
            end_date DATE,
            status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('draft', 'active', 'paused', 'completed')),

            target_audience JSONB,
            external_campaign_id VARCHAR(100),

            description TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_campaigns_org ON marketing_campaigns(organization_id);
        CREATE INDEX idx_campaigns_status ON marketing_campaigns(status);
        CREATE INDEX idx_campaigns_channel ON marketing_campaigns(channel);
    """))
    print("  Created: marketing_campaigns")

    # 7. Marketing Metrics (daily performance)
    conn.execute(text("""
        CREATE TABLE marketing_metrics (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,
            campaign_id UUID REFERENCES marketing_campaigns(id) ON DELETE SET NULL,

            metric_date DATE NOT NULL,
            channel VARCHAR(50),

            impressions INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            leads_generated INTEGER DEFAULT 0,
            trials_started INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0,

            spend NUMERIC(12, 2) DEFAULT 0,
            cpc NUMERIC(10, 4),
            cpl NUMERIC(10, 2),
            cac NUMERIC(10, 2),

            attributed_revenue NUMERIC(12, 2) DEFAULT 0,
            attributed_mrr NUMERIC(12, 2) DEFAULT 0,
            roas NUMERIC(8, 4),

            source VARCHAR(20) DEFAULT 'manual',
            raw_data JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_marketing_org_date ON marketing_metrics(organization_id, metric_date);
        CREATE INDEX idx_marketing_campaign ON marketing_metrics(campaign_id);
        CREATE INDEX idx_marketing_channel ON marketing_metrics(channel);
    """))
    print("  Created: marketing_metrics")

    # 8. Business Forecasts (projections and scenarios)
    conn.execute(text("""
        CREATE TABLE business_forecasts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,

            forecast_name VARCHAR(255) NOT NULL,
            forecast_type VARCHAR(50) NOT NULL CHECK (forecast_type IN ('revenue', 'expense', 'combined', 'scenario')),
            description TEXT,

            base_month DATE NOT NULL,
            projection_months INTEGER DEFAULT 12,

            parameters JSONB NOT NULL,
            monthly_projections JSONB,
            summary JSONB,

            created_by INTEGER,
            is_primary BOOLEAN DEFAULT false,
            is_scenario BOOLEAN DEFAULT false,
            parent_forecast_id UUID REFERENCES business_forecasts(id),

            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_forecasts_org ON business_forecasts(organization_id);
        CREATE INDEX idx_forecasts_type ON business_forecasts(forecast_type);
    """))
    print("  Created: business_forecasts")

    # 9. Business KPIs (daily snapshots)
    conn.execute(text("""
        CREATE TABLE business_kpis (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,
            snapshot_date DATE NOT NULL,

            mrr NUMERIC(12, 2),
            arr NUMERIC(12, 2),
            total_revenue_mtd NUMERIC(12, 2),
            revenue_growth_rate NUMERIC(8, 4),

            total_customers INTEGER,
            new_customers_mtd INTEGER,
            churned_customers_mtd INTEGER,
            churn_rate NUMERIC(8, 4),
            net_revenue_retention NUMERIC(8, 4),

            total_monthly_costs NUMERIC(12, 2),
            service_costs NUMERIC(12, 2),
            employee_costs NUMERIC(12, 2),
            marketing_costs NUMERIC(12, 2),
            other_costs NUMERIC(12, 2),

            gross_profit NUMERIC(12, 2),
            gross_margin NUMERIC(8, 4),
            net_profit NUMERIC(12, 2),
            net_margin NUMERIC(8, 4),

            cash_balance NUMERIC(14, 2),
            burn_rate NUMERIC(12, 2),
            cash_runway_months NUMERIC(6, 2),

            cac NUMERIC(10, 2),
            ltv NUMERIC(12, 2),
            ltv_cac_ratio NUMERIC(8, 4),
            arpu NUMERIC(10, 2),

            service_cost_breakdown JSONB,
            data_json JSONB,

            created_at TIMESTAMP DEFAULT NOW(),

            UNIQUE(organization_id, snapshot_date)
        );

        CREATE INDEX idx_kpis_org_date ON business_kpis(organization_id, snapshot_date);
    """))
    print("  Created: business_kpis")

    # 10. Budget Alerts
    conn.execute(text("""
        CREATE TABLE budget_alerts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,

            alert_type VARCHAR(50) NOT NULL CHECK (alert_type IN ('service_budget', 'category_budget', 'total_budget')),
            service_provider_id UUID REFERENCES service_providers(id) ON DELETE CASCADE,
            category VARCHAR(50),

            threshold_percent INTEGER NOT NULL,
            current_spend NUMERIC(12, 2) NOT NULL,
            budget_amount NUMERIC(12, 2) NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,

            status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'acknowledged', 'resolved')),
            acknowledged_by INTEGER,
            acknowledged_at TIMESTAMP,

            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_alerts_org ON budget_alerts(organization_id);
        CREATE INDEX idx_alerts_status ON budget_alerts(status);
        CREATE INDEX idx_alerts_provider ON budget_alerts(service_provider_id);
    """))
    print("  Created: budget_alerts")


def seed_service_providers(conn, is_sqlite_db):
    """Seed the default service providers."""
    print("\nSeeding default service providers...")

    services = [
        # AI Services
        ("Anthropic Claude", "ai", "anthropic", "per_unit", "ANTHROPIC_API_KEY", True, "token", 0.000003),
        ("OpenAI", "ai", "openai", "per_unit", "OPENAI_API_KEY", True, "token", 0.00003),
        ("Pinecone", "ai", "pinecone", "subscription", "PINECONE_API_KEY", False, None, None),

        # Communications
        ("Twilio", "communications", "twilio", "per_unit", "TWILIO_AUTH_TOKEN", True, "message", 0.0075),
        ("Vapi.ai", "communications", "vapi", "per_unit", None, False, "minute", 0.05),
        ("Recall.ai", "communications", "recallai", "subscription", "RECALLAI_API_KEY", False, None, None),
        ("Deepgram", "communications", "deepgram", "per_unit", "DEEPGRAM_API_KEY", True, "minute", 0.0043),

        # Email
        ("SendGrid", "email", "sendgrid", "tiered", "SENDGRID_API_KEY", True, "email", 0.001),
        ("Microsoft Graph", "email", "microsoft_graph", "subscription", "MICROSOFT_CLIENT_ID", False, None, None),

        # CRM
        ("Salesforce", "crm", "salesforce", "subscription", "SALESFORCE_CLIENT_ID", False, None, None),

        # Payments
        ("Stripe", "payments", "stripe", "percentage", "STRIPE_SECRET_KEY", True, "transaction", None),

        # Storage
        ("AWS S3", "storage", "aws_s3", "per_unit", "AWS_ACCESS_KEY_ID", True, "gb", 0.023),

        # Hosting
        ("Railway", "hosting", "railway", "usage_based", None, False, None, None),
        ("Vercel", "hosting", "vercel", "subscription", None, False, None, None),

        # Monitoring
        ("Sentry", "monitoring", "sentry", "subscription", "SENTRY_DSN", False, None, None),
    ]

    for name, category, provider_type, pricing_model, api_key_env, has_api, unit_type, unit_cost in services:
        new_id = str(uuid.uuid4())

        if is_sqlite_db:
            # SQLite: check if exists first
            existing = conn.execute(text("""
                SELECT id FROM service_providers
                WHERE organization_id = 1 AND provider_type = :provider_type
            """), {"provider_type": provider_type}).fetchone()

            if not existing:
                conn.execute(text("""
                    INSERT INTO service_providers (
                        id, organization_id, name, display_name, category, provider_type,
                        pricing_model, api_key_env_var, has_usage_api, unit_type, unit_cost,
                        is_active
                    ) VALUES (
                        :id, 1, :name, :name, :category, :provider_type,
                        :pricing_model, :api_key_env, :has_api, :unit_type, :unit_cost, 1
                    )
                """), {
                    "id": new_id,
                    "name": name,
                    "category": category,
                    "provider_type": provider_type,
                    "pricing_model": pricing_model,
                    "api_key_env": api_key_env,
                    "has_api": 1 if has_api else 0,
                    "unit_type": unit_type,
                    "unit_cost": unit_cost
                })
        else:
            # PostgreSQL with ON CONFLICT
            conn.execute(text("""
                INSERT INTO service_providers (
                    organization_id, name, display_name, category, provider_type,
                    pricing_model, api_key_env_var, has_usage_api, unit_type, unit_cost,
                    is_active
                ) VALUES (
                    1, :name, :name, :category, :provider_type,
                    :pricing_model, :api_key_env, :has_api, :unit_type, :unit_cost,
                    true
                )
                ON CONFLICT (organization_id, provider_type) DO NOTHING
            """), {
                "name": name,
                "category": category,
                "provider_type": provider_type,
                "pricing_model": pricing_model,
                "api_key_env": api_key_env,
                "has_api": has_api,
                "unit_type": unit_type,
                "unit_cost": unit_cost
            })

    conn.commit()
    print(f"  Seeded {len(services)} service providers")


if __name__ == "__main__":
    run_migration()
