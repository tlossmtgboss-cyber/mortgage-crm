"""
Circle of Cashflow - Database Migration
Creates tables for mortgage questionnaires, referral partners, opportunities, and tracking
"""

from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL")

def run_migration():
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Drop existing tables in reverse order (due to foreign keys)
        conn.execute(text("DROP TABLE IF EXISTS partner_touchpoints CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS referrals CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS referral_opportunities CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS referral_partners CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS mortgage_questionnaires CASCADE"))

        # Create mortgage_questionnaires table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS mortgage_questionnaires (
                id SERIAL PRIMARY KEY,
                contact_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
                submission_date TIMESTAMP DEFAULT NOW(),

                -- Basic Contact Info
                name VARCHAR(255),
                email VARCHAR(255),
                phone VARCHAR(50),

                -- Homeownership History
                is_veteran BOOLEAN DEFAULT FALSE,
                owned_home_before BOOLEAN,
                current_housing_status VARCHAR(20),
                previous_mortgage_type VARCHAR(50),
                current_monthly_payment DECIMAL(10,2),

                -- Financial Goals & Philosophy
                mortgage_priority VARCHAR(50),
                personal_goals TEXT[],
                move_timeline VARCHAR(50),
                financial_philosophy VARCHAR(50),

                -- Professional Relationships
                has_financial_planner BOOLEAN DEFAULT FALSE,
                financial_planner_rating VARCHAR(20),
                has_accountant BOOLEAN DEFAULT FALSE,
                accountant_rating VARCHAR(20),
                has_life_insurance_agent BOOLEAN DEFAULT FALSE,
                life_insurance_agent_rating VARCHAR(20),
                has_estate_planner BOOLEAN DEFAULT FALSE,
                estate_planner_rating VARCHAR(20),
                has_tax_deferred_retirement BOOLEAN DEFAULT FALSE,

                -- AI Analysis
                ai_risk_profile VARCHAR(50),
                ai_referral_urgency VARCHAR(20),
                ai_notes TEXT,

                -- Metadata
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                submitted_via VARCHAR(50) DEFAULT 'web_form'
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_questionnaire_contact ON mortgage_questionnaires(contact_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_questionnaire_date ON mortgage_questionnaires(submission_date)"))

        # Create referral_partners table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS referral_partners (
                id SERIAL PRIMARY KEY,

                -- Basic Info
                business_name VARCHAR(255) NOT NULL,
                contact_name VARCHAR(255) NOT NULL,
                category VARCHAR(50) NOT NULL,
                email VARCHAR(255),
                phone VARCHAR(50),
                website VARCHAR(500),
                calendar_link VARCHAR(500),

                -- Service Details
                service_area TEXT[],
                specialties TEXT[],
                license_number VARCHAR(100),

                -- Relationship Management
                partnership_start_date DATE,
                relationship_status VARCHAR(20) DEFAULT 'active',
                trust_score INTEGER DEFAULT 50,
                internal_notes TEXT,
                client_feedback_summary TEXT,

                -- Referral Stats
                total_referrals_sent INTEGER DEFAULT 0,
                total_referrals_received INTEGER DEFAULT 0,
                last_referral_sent_date TIMESTAMP,
                last_referral_received_date TIMESTAMP,
                conversion_rate DECIMAL(5,2),
                avg_client_satisfaction DECIMAL(3,2),

                -- Revenue Tracking
                estimated_lifetime_value DECIMAL(12,2) DEFAULT 0,
                revenue_generated DECIMAL(12,2) DEFAULT 0,

                -- Automation Settings
                auto_referral_eligible BOOLEAN DEFAULT TRUE,
                preferred_contact_method VARCHAR(20) DEFAULT 'email',

                -- Metadata
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_partner_category ON referral_partners(category)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_partner_trust ON referral_partners(trust_score DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_partner_status ON referral_partners(relationship_status)"))

        # Create referral_opportunities table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS referral_opportunities (
                id SERIAL PRIMARY KEY,
                contact_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
                questionnaire_id INTEGER REFERENCES mortgage_questionnaires(id) ON DELETE SET NULL,
                loan_id INTEGER,

                -- Opportunity Details
                category VARCHAR(50) NOT NULL,
                priority VARCHAR(20) DEFAULT 'medium',
                ai_reasoning TEXT,

                -- Status Tracking
                status VARCHAR(30) DEFAULT 'detected',
                detected_date TIMESTAMP DEFAULT NOW(),
                acknowledged_date TIMESTAMP,
                ready_to_send_date TIMESTAMP,
                sent_date TIMESTAMP,
                completed_date TIMESTAMP,

                -- Client Interaction
                client_requested BOOLEAN DEFAULT FALSE,
                client_acknowledgment_message TEXT,
                client_response TEXT,

                -- Partner Assignment
                suggested_partner_id INTEGER REFERENCES referral_partners(id),
                assigned_partner_id INTEGER REFERENCES referral_partners(id),

                -- Metadata
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunity_contact ON referral_opportunities(contact_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunity_status ON referral_opportunities(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunity_category ON referral_opportunities(category)"))

        # Create referrals table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,

                -- Referral Type
                direction VARCHAR(10) NOT NULL,

                -- Parties Involved
                contact_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
                partner_id INTEGER REFERENCES referral_partners(id) ON DELETE SET NULL,
                opportunity_id INTEGER REFERENCES referral_opportunities(id) ON DELETE SET NULL,
                loan_id INTEGER,

                -- Referral Details
                category VARCHAR(50) NOT NULL,
                referral_date DATE DEFAULT CURRENT_DATE,
                reason TEXT,
                introduction_method VARCHAR(30),

                -- Status Tracking
                status VARCHAR(30) DEFAULT 'introduced',
                contacted_date TIMESTAMP,
                scheduled_date TIMESTAMP,
                completed_date TIMESTAMP,
                outcome VARCHAR(30),

                -- Value Tracking
                estimated_value DECIMAL(10,2),
                actual_revenue DECIMAL(10,2),
                commission_paid DECIMAL(10,2),

                -- Feedback
                client_feedback TEXT,
                client_rating INTEGER,
                partner_feedback TEXT,

                -- Metadata
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_referral_direction ON referrals(direction)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_referral_contact ON referrals(contact_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_referral_partner ON referrals(partner_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_referral_status ON referrals(status)"))

        # Create partner_touchpoints table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS partner_touchpoints (
                id SERIAL PRIMARY KEY,
                partner_id INTEGER NOT NULL REFERENCES referral_partners(id) ON DELETE CASCADE,

                -- Touchpoint Details
                touchpoint_type VARCHAR(50) NOT NULL,
                touchpoint_date TIMESTAMP DEFAULT NOW(),
                method VARCHAR(30),

                -- Content
                subject VARCHAR(255),
                message TEXT,

                -- Response Tracking
                delivered BOOLEAN DEFAULT FALSE,
                opened BOOLEAN DEFAULT FALSE,
                responded BOOLEAN DEFAULT FALSE,
                response_text TEXT,

                -- Workflow
                scheduled_by VARCHAR(20) DEFAULT 'system',

                -- Metadata
                created_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_touchpoint_partner ON partner_touchpoints(partner_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_touchpoint_date ON partner_touchpoints(touchpoint_date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_touchpoint_type ON partner_touchpoints(touchpoint_type)"))

        conn.commit()
        print("Circle of Cashflow tables created successfully!")

if __name__ == "__main__":
    run_migration()
