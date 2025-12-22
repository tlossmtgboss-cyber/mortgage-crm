"""
Migration: Add Presentation Engine Tables
Creates tables for storing presentation scenarios and quote requests.
"""

from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Run the presentation tables migration."""
    if not DATABASE_URL:
        print("DATABASE_URL not set. Skipping migration.")
        return

    # Fix postgres:// to postgresql://
    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Check if main table already exists
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'presentation_scenarios'
        """))

        if result.fetchone():
            print("Presentation tables already exist. Skipping migration.")
            return

        print("Creating presentation tables...")

        # 1. Presentation Scenarios Table
        conn.execute(text("""
            CREATE TABLE presentation_scenarios (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                loan_id INTEGER NOT NULL REFERENCES loans(id),
                borrower_id INTEGER REFERENCES borrowers(id),
                created_by_user_id INTEGER REFERENCES users(id),

                -- Scenario Type
                scenario_type VARCHAR(20) NOT NULL CHECK (scenario_type IN ('refinance', 'cashOut', 'heloc', 'sell')),

                -- Base loan data at time of scenario creation
                home_value NUMERIC(12, 2) NOT NULL,
                loan_balance NUMERIC(12, 2) NOT NULL,
                current_rate NUMERIC(5, 3),
                current_payment NUMERIC(10, 2),

                -- Scenario-specific inputs (JSON)
                scenario_inputs JSONB DEFAULT '{}',

                -- Calculated results (JSON)
                calculated_results JSONB DEFAULT '{}',

                -- Metadata
                name VARCHAR(255),
                notes TEXT,
                is_favorite BOOLEAN DEFAULT false,

                -- Timestamps
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            -- Indexes for common queries
            CREATE INDEX idx_presentation_scenarios_loan ON presentation_scenarios(loan_id);
            CREATE INDEX idx_presentation_scenarios_borrower ON presentation_scenarios(borrower_id);
            CREATE INDEX idx_presentation_scenarios_type ON presentation_scenarios(scenario_type);
            CREATE INDEX idx_presentation_scenarios_favorite ON presentation_scenarios(is_favorite) WHERE is_favorite = true;
            CREATE INDEX idx_presentation_scenarios_created ON presentation_scenarios(created_at DESC);
        """))

        print("Created presentation_scenarios table")

        # 2. Quote Requests Table
        conn.execute(text("""
            CREATE TABLE presentation_quote_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                loan_id INTEGER NOT NULL REFERENCES loans(id),
                borrower_id INTEGER REFERENCES borrowers(id),
                scenario_id UUID REFERENCES presentation_scenarios(id),
                assigned_to_user_id INTEGER REFERENCES users(id),

                -- Quote Type
                quote_type VARCHAR(20) NOT NULL CHECK (quote_type IN ('refinance', 'cashOut', 'heloc', 'sell')),

                -- Status
                status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'quoted', 'accepted', 'declined', 'expired')),

                -- Request Details (JSON)
                request_data JSONB DEFAULT '{}',

                -- Quote Response (JSON) - filled by LO
                quote_data JSONB DEFAULT '{}',

                -- Contact Preferences
                preferred_contact_method VARCHAR(50),
                preferred_contact_time VARCHAR(255),
                borrower_notes TEXT,

                -- Internal Notes
                internal_notes TEXT,

                -- Timestamps
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                quoted_at TIMESTAMP,
                expires_at TIMESTAMP
            );

            -- Indexes
            CREATE INDEX idx_quote_requests_loan ON presentation_quote_requests(loan_id);
            CREATE INDEX idx_quote_requests_borrower ON presentation_quote_requests(borrower_id);
            CREATE INDEX idx_quote_requests_assigned ON presentation_quote_requests(assigned_to_user_id);
            CREATE INDEX idx_quote_requests_status ON presentation_quote_requests(status);
            CREATE INDEX idx_quote_requests_pending ON presentation_quote_requests(assigned_to_user_id, status) WHERE status IN ('pending', 'in_progress');
            CREATE INDEX idx_quote_requests_created ON presentation_quote_requests(created_at DESC);
        """))

        print("Created presentation_quote_requests table")

        # Commit the transaction
        conn.commit()

        print("Migration completed successfully!")


if __name__ == "__main__":
    run_migration()
