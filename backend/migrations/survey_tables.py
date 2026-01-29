"""
Survey Tables Migration
Creates all tables required for the Surveying & Feedback feature.
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

SURVEY_TABLES_SQL = """
-- =============================================================================
-- Surveying & Feedback Tables
-- =============================================================================

-- Survey Templates
CREATE TABLE IF NOT EXISTS survey_templates (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL DEFAULT 1,

    -- Basic info
    name VARCHAR(255) NOT NULL,
    description TEXT,
    survey_type VARCHAR(50) NOT NULL DEFAULT 'csat',
    status VARCHAR(50) NOT NULL DEFAULT 'draft',

    -- Trigger configuration
    trigger_type VARCHAR(50) DEFAULT 'manual',
    trigger_config JSONB DEFAULT '{}',

    -- Settings
    is_anonymous BOOLEAN DEFAULT FALSE,
    expires_days INTEGER DEFAULT 30,
    reminder_enabled BOOLEAN DEFAULT TRUE,
    reminder_days INTEGER DEFAULT 3,
    max_reminders INTEGER DEFAULT 2,

    -- Branding
    intro_message TEXT,
    thank_you_message TEXT,
    logo_url VARCHAR(500),
    primary_color VARCHAR(20) DEFAULT '#319795',

    -- Metadata
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_survey_templates_org_status ON survey_templates(organization_id, status);
CREATE INDEX IF NOT EXISTS ix_survey_templates_org_type ON survey_templates(organization_id, survey_type);

-- Survey Questions
CREATE TABLE IF NOT EXISTS survey_questions (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES survey_templates(id) ON DELETE CASCADE,

    -- Question content
    question_text TEXT NOT NULL,
    question_type VARCHAR(50) NOT NULL,
    help_text TEXT,

    -- Options for choice questions
    options JSONB DEFAULT '[]',

    -- Validation
    is_required BOOLEAN DEFAULT TRUE,
    min_value INTEGER,
    max_value INTEGER,
    min_length INTEGER,
    max_length INTEGER,

    -- Display
    "order" INTEGER DEFAULT 0,
    conditional_logic JSONB,

    -- Scoring
    weight FLOAT DEFAULT 1.0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_survey_questions_template_order ON survey_questions(template_id, "order");

-- Survey Responses
CREATE TABLE IF NOT EXISTS survey_responses (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL DEFAULT 1,
    template_id INTEGER NOT NULL REFERENCES survey_templates(id),

    -- Respondent info
    borrower_id INTEGER REFERENCES leads(id),
    loan_id INTEGER,
    email VARCHAR(255),
    phone VARCHAR(50),

    -- Access
    access_token VARCHAR(100) UNIQUE,

    -- Status tracking
    status VARCHAR(50) DEFAULT 'pending',
    sent_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,

    -- Reminders
    reminder_count INTEGER DEFAULT 0,
    last_reminder_at TIMESTAMP WITH TIME ZONE,

    -- Scores (calculated after completion)
    nps_score INTEGER,
    csat_score FLOAT,
    overall_score FLOAT,
    sentiment VARCHAR(50),

    -- Context
    trigger_event VARCHAR(100),
    loan_officer_id INTEGER REFERENCES users(id),

    -- Metadata
    ip_address VARCHAR(50),
    user_agent VARCHAR(500),
    completion_time_seconds INTEGER,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_survey_responses_org_status ON survey_responses(organization_id, status);
CREATE INDEX IF NOT EXISTS ix_survey_responses_template_status ON survey_responses(template_id, status);
CREATE INDEX IF NOT EXISTS ix_survey_responses_loan ON survey_responses(loan_id);
CREATE INDEX IF NOT EXISTS ix_survey_responses_access_token ON survey_responses(access_token);

-- Survey Answers
CREATE TABLE IF NOT EXISTS survey_answers (
    id SERIAL PRIMARY KEY,
    response_id INTEGER NOT NULL REFERENCES survey_responses(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES survey_questions(id),

    -- Answer content
    answer_text TEXT,
    answer_numeric FLOAT,
    answer_json JSONB,

    -- Sentiment analysis (for text responses)
    sentiment VARCHAR(50),
    sentiment_score FLOAT,
    key_phrases JSONB DEFAULT '[]',

    answered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_survey_answers_response_question ON survey_answers(response_id, question_id);

-- Survey Analytics (daily snapshots)
CREATE TABLE IF NOT EXISTS survey_analytics (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    template_id INTEGER REFERENCES survey_templates(id),

    -- Time period
    date TIMESTAMP WITH TIME ZONE NOT NULL,

    -- Volume metrics
    sent_count INTEGER DEFAULT 0,
    started_count INTEGER DEFAULT 0,
    completed_count INTEGER DEFAULT 0,
    expired_count INTEGER DEFAULT 0,

    -- Response rate
    response_rate FLOAT,
    completion_rate FLOAT,

    -- Score metrics
    avg_nps_score FLOAT,
    avg_csat_score FLOAT,
    avg_overall_score FLOAT,

    -- NPS breakdown
    nps_promoters INTEGER DEFAULT 0,
    nps_passives INTEGER DEFAULT 0,
    nps_detractors INTEGER DEFAULT 0,
    nps_calculated FLOAT,

    -- Sentiment breakdown
    sentiment_very_positive INTEGER DEFAULT 0,
    sentiment_positive INTEGER DEFAULT 0,
    sentiment_neutral INTEGER DEFAULT 0,
    sentiment_negative INTEGER DEFAULT 0,
    sentiment_very_negative INTEGER DEFAULT 0,

    -- Timing
    avg_completion_time INTEGER,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_survey_analytics_org_date ON survey_analytics(organization_id, date);
CREATE INDEX IF NOT EXISTS ix_survey_analytics_template_date ON survey_analytics(template_id, date);

-- Savings Validation (track promised vs actual savings)
CREATE TABLE IF NOT EXISTS savings_validations (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    loan_id INTEGER NOT NULL,
    borrower_id INTEGER REFERENCES leads(id),

    -- Promised savings
    promised_monthly_savings FLOAT,
    promised_total_savings FLOAT,
    promised_rate_reduction FLOAT,
    savings_source VARCHAR(100),

    -- Actual (from survey)
    reported_monthly_savings FLOAT,
    reported_satisfied BOOLEAN,
    discrepancy_amount FLOAT,

    -- Survey link
    survey_response_id INTEGER REFERENCES survey_responses(id),

    -- Follow-up
    follow_up_required BOOLEAN DEFAULT FALSE,
    follow_up_notes TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_savings_validations_loan ON savings_validations(loan_id);
CREATE INDEX IF NOT EXISTS ix_savings_validations_org ON savings_validations(organization_id);
"""


def run_migration():
    """Run the survey tables migration."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    try:
        engine = create_engine(database_url)

        with engine.connect() as conn:
            # Execute the SQL
            conn.execute(text(SURVEY_TABLES_SQL))
            conn.commit()

        logger.info("✅ Survey tables migration completed successfully")
        return True

    except Exception as e:
        logger.error(f"❌ Survey tables migration failed: {e}")
        return False


def check_tables_exist():
    """Check if survey tables already exist."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return False

    try:
        engine = create_engine(database_url)

        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN (
                    'survey_templates', 'survey_questions', 'survey_responses',
                    'survey_answers', 'survey_analytics', 'savings_validations'
                )
            """))
            existing_tables = [row[0] for row in result.fetchall()]

        return len(existing_tables) == 6

    except Exception as e:
        logger.error(f"Error checking tables: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if check_tables_exist():
        print("Survey tables already exist.")
    else:
        print("Creating survey tables...")
        if run_migration():
            print("Migration completed successfully!")
        else:
            print("Migration failed. Check logs for details.")
