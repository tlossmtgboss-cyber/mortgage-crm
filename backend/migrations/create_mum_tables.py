"""
Migration: Create MUM (Mortgages Under Management) Tables
"""
from sqlalchemy import create_engine, text
import os

def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL')

def upgrade():
    """Create MUM tables"""
    engine = create_engine(get_database_url())

    migration_sql = """
    -- Drop existing tables if they exist
    DROP TABLE IF EXISTS mum_transactions CASCADE;
    DROP TABLE IF EXISTS mum_clients CASCADE;

    -- Create mum_clients table
    CREATE TABLE mum_clients (
        id SERIAL PRIMARY KEY,

        -- Client Information
        client_name VARCHAR(200) NOT NULL,
        email VARCHAR(200),
        phone VARCHAR(50),

        -- Loan Information
        original_loan_amount DECIMAL(12, 2) NOT NULL,
        current_loan_amount DECIMAL(12, 2) NOT NULL,
        interest_rate DECIMAL(6, 4) NOT NULL,

        -- Loan Identifiers
        servicing_loan_number VARCHAR(100),
        origination_loan_number VARCHAR(100),

        -- Property Information
        appraisal_value_at_closing DECIMAL(12, 2) NOT NULL,
        current_property_value DECIMAL(12, 2) NOT NULL,

        -- Servicing Information
        current_servicer VARCHAR(200),
        has_escrow BOOLEAN DEFAULT FALSE,

        -- Payment Information
        current_principal_payment DECIMAL(10, 2),
        monthly_taxes DECIMAL(10, 2),
        monthly_insurance DECIMAL(10, 2),
        monthly_pmi DECIMAL(10, 2),

        -- Loan Details
        loan_type VARCHAR(100),
        is_veteran BOOLEAN DEFAULT FALSE,
        ltv DECIMAL(6, 4),

        -- Important Dates
        closing_date DATE NOT NULL,
        first_payment_date DATE NOT NULL,

        -- Engagement & Opportunities
        last_contact_date DATE,
        next_touchpoint_date DATE,
        engagement_score INTEGER DEFAULT 0,

        -- Opportunity Flags
        refinance_opportunity BOOLEAN DEFAULT FALSE,
        heloc_opportunity BOOLEAN DEFAULT FALSE,
        rate_rebound_opportunity BOOLEAN DEFAULT FALSE,
        high_equity_opportunity BOOLEAN DEFAULT FALSE,

        -- Referrals
        referrals_sent INTEGER DEFAULT 0,

        -- Status
        is_active BOOLEAN DEFAULT TRUE,
        status VARCHAR(50) DEFAULT 'active',

        -- Timestamps
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        -- Calculated fields (stored for performance)
        equity_amount DECIMAL(12, 2),
        equity_percentage DECIMAL(6, 4),
        days_since_funding INTEGER,
        portfolio_age_months INTEGER,

        -- Revenue tracking
        annual_servicing_revenue DECIMAL(10, 2),
        lifetime_value DECIMAL(10, 2)
    );

    -- Create mum_transactions table
    CREATE TABLE mum_transactions (
        id SERIAL PRIMARY KEY,
        client_id INTEGER REFERENCES mum_clients(id) ON DELETE CASCADE,

        transaction_type VARCHAR(50),
        transaction_date DATE NOT NULL,
        loan_amount DECIMAL(12, 2),

        notes TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Create indexes
    CREATE INDEX idx_mum_clients_status ON mum_clients(status);
    CREATE INDEX idx_mum_clients_closing_date ON mum_clients(closing_date);
    CREATE INDEX idx_mum_clients_is_veteran ON mum_clients(is_veteran);
    CREATE INDEX idx_mum_clients_refinance_opp ON mum_clients(refinance_opportunity);
    CREATE INDEX idx_mum_clients_heloc_opp ON mum_clients(heloc_opportunity);

    CREATE INDEX idx_mum_trans_client ON mum_transactions(client_id);
    CREATE INDEX idx_mum_trans_type ON mum_transactions(transaction_type);
    CREATE INDEX idx_mum_trans_date ON mum_transactions(transaction_date);
    """

    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()

    print("✅ MUM tables created successfully")

if __name__ == "__main__":
    print("⬆️  Creating MUM tables...")
    upgrade()
    print("Done!")
