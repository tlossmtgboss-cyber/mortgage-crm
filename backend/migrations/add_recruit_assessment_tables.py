"""
Migration: Add Recruiting Assessment Quiz Tables + Candidate Portal

Creates tables for:
- recruit_quiz_templates: Question templates by disposition stage
- recruit_quiz_responses: User responses to quiz questions
- recruit_assessment_scores: Computed assessment scores
- recruit_calculator_config: Production calculator configuration
- recruiting_tasks: Workflow tasks for recruiters
- recruiting_call_history: Click-to-call history
- recruit_portal_workspaces: Candidate PURL portals
- recruit_portal_tokens: Portal access tokens
- recruit_company_updates: Company propaganda/updates
- recruit_portal_messages: AI chat messages
- recruit_portal_appointments: Scheduled appointments
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from database import engine


def run_migration():
    """Run the migration to add recruiting assessment tables."""

    migration_sql = """
    -- Quiz question templates by disposition stage
    CREATE TABLE IF NOT EXISTS recruit_quiz_templates (
        id SERIAL PRIMARY KEY,
        disposition VARCHAR(50) NOT NULL,
        question_text TEXT NOT NULL,
        question_type VARCHAR(20) DEFAULT 'likert',
        category VARCHAR(50) NOT NULL,
        weight DECIMAL(3,2) DEFAULT 1.0,
        display_order INTEGER DEFAULT 0,
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    -- Create index on disposition for faster lookups
    CREATE INDEX IF NOT EXISTS idx_quiz_templates_disposition
        ON recruit_quiz_templates(disposition) WHERE is_active = true;

    -- User responses to quiz questions
    CREATE TABLE IF NOT EXISTS recruit_quiz_responses (
        id SERIAL PRIMARY KEY,
        candidate_id INTEGER NOT NULL,
        template_id INTEGER REFERENCES recruit_quiz_templates(id),
        disposition VARCHAR(50) NOT NULL,
        response_value TEXT,
        numeric_score DECIMAL(3,1),
        responded_by INTEGER,
        responded_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT fk_candidate FOREIGN KEY (candidate_id)
            REFERENCES mm_candidates(id) ON DELETE CASCADE
    );

    -- Create indexes for quiz responses
    CREATE INDEX IF NOT EXISTS idx_quiz_responses_candidate
        ON recruit_quiz_responses(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_quiz_responses_disposition
        ON recruit_quiz_responses(candidate_id, disposition);

    -- Computed assessment scores (updated after each quiz)
    CREATE TABLE IF NOT EXISTS recruit_assessment_scores (
        id SERIAL PRIMARY KEY,
        candidate_id INTEGER NOT NULL UNIQUE,
        production_score DECIMAL(3,1),
        disc_score DECIMAL(3,1),
        character_score DECIMAL(3,1),
        skills_score DECIMAL(3,1),
        culture_fit_score DECIMAL(3,1),
        overall_score DECIMAL(3,1),
        last_quiz_disposition VARCHAR(50),
        quiz_count INTEGER DEFAULT 0,
        last_updated TIMESTAMP DEFAULT NOW(),
        CONSTRAINT fk_candidate_scores FOREIGN KEY (candidate_id)
            REFERENCES mm_candidates(id) ON DELETE CASCADE
    );

    -- Production calculator configuration
    CREATE TABLE IF NOT EXISTS recruit_calculator_config (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER,
        lead_conversion_lift DECIMAL(4,2) DEFAULT 1.25,
        avg_deal_size_lift DECIMAL(4,2) DEFAULT 1.15,
        closing_speed_factor DECIMAL(4,2) DEFAULT 0.85,
        tech_efficiency_gain DECIMAL(4,2) DEFAULT 1.20,
        marketing_lead_boost DECIMAL(4,2) DEFAULT 1.30,
        comp_percentage DECIMAL(5,4) DEFAULT 0.0125,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    -- Insert default calculator config if not exists
    INSERT INTO recruit_calculator_config (organization_id)
    SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM recruit_calculator_config WHERE organization_id = 1);

    -- Recruiting workflow tasks table
    CREATE TABLE IF NOT EXISTS recruiting_tasks (
        id SERIAL PRIMARY KEY,
        candidate_id INTEGER NOT NULL,
        title VARCHAR(200) NOT NULL,
        description TEXT,
        due_date TIMESTAMP,
        priority VARCHAR(20) DEFAULT 'medium',
        route_to VARCHAR(50) DEFAULT 'task_list',
        status VARCHAR(20) DEFAULT 'pending',
        assigned_to INTEGER,
        organization_id INTEGER DEFAULT 1,
        skip_reason TEXT,
        completed_at TIMESTAMP,
        completed_by INTEGER,
        created_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT fk_candidate_tasks FOREIGN KEY (candidate_id)
            REFERENCES mm_candidates(id) ON DELETE CASCADE
    );

    -- Create indexes for recruiting tasks
    CREATE INDEX IF NOT EXISTS idx_recruiting_tasks_candidate
        ON recruiting_tasks(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_recruiting_tasks_status
        ON recruiting_tasks(status) WHERE status = 'pending';
    CREATE INDEX IF NOT EXISTS idx_recruiting_tasks_assigned
        ON recruiting_tasks(assigned_to, status);
    CREATE INDEX IF NOT EXISTS idx_recruiting_tasks_dialer
        ON recruiting_tasks(route_to, status) WHERE route_to = 'dialer_queue';

    -- Recruiting call history table
    CREATE TABLE IF NOT EXISTS recruiting_call_history (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        candidate_id INTEGER NOT NULL,
        caller_user_id INTEGER,
        direction VARCHAR(20) DEFAULT 'outbound',
        phone_from VARCHAR(20),
        phone_to VARCHAR(20),
        whisper_context TEXT,
        duration_seconds INTEGER,
        status VARCHAR(20) DEFAULT 'initiated',
        outcome VARCHAR(50),
        notes TEXT,
        recording_url TEXT,
        called_at TIMESTAMP DEFAULT NOW(),
        completed_at TIMESTAMP,
        CONSTRAINT fk_call_candidate FOREIGN KEY (candidate_id)
            REFERENCES mm_candidates(id) ON DELETE CASCADE
    );

    -- Create indexes for call history
    CREATE INDEX IF NOT EXISTS idx_call_history_candidate
        ON recruiting_call_history(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_call_history_caller
        ON recruiting_call_history(caller_user_id);
    CREATE INDEX IF NOT EXISTS idx_call_history_status
        ON recruiting_call_history(status);

    -- =========================================================================
    -- CANDIDATE PURL PORTAL TABLES
    -- =========================================================================

    -- Portal workspaces for candidates
    CREATE TABLE IF NOT EXISTS recruit_portal_workspaces (
        id SERIAL PRIMARY KEY,
        candidate_id INTEGER NOT NULL UNIQUE,
        slug VARCHAR(100) UNIQUE NOT NULL,
        is_active BOOLEAN DEFAULT true,
        theme_config JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT fk_portal_candidate FOREIGN KEY (candidate_id)
            REFERENCES mm_candidates(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_portal_workspaces_slug
        ON recruit_portal_workspaces(slug) WHERE is_active = true;

    -- Portal access tokens
    CREATE TABLE IF NOT EXISTS recruit_portal_tokens (
        id SERIAL PRIMARY KEY,
        workspace_id INTEGER NOT NULL,
        token VARCHAR(100) UNIQUE NOT NULL,
        scope VARCHAR(20) DEFAULT 'full',
        expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT fk_token_workspace FOREIGN KEY (workspace_id)
            REFERENCES recruit_portal_workspaces(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_portal_tokens_token
        ON recruit_portal_tokens(token);

    -- Company updates/propaganda content
    CREATE TABLE IF NOT EXISTS recruit_company_updates (
        id SERIAL PRIMARY KEY,
        title VARCHAR(200) NOT NULL,
        content TEXT NOT NULL,
        media_url TEXT,
        category VARCHAR(50) DEFAULT 'news',
        is_featured BOOLEAN DEFAULT false,
        is_active BOOLEAN DEFAULT true,
        published_at TIMESTAMP DEFAULT NOW(),
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_company_updates_category
        ON recruit_company_updates(category, is_active) WHERE is_active = true;
    CREATE INDEX IF NOT EXISTS idx_company_updates_featured
        ON recruit_company_updates(is_featured) WHERE is_featured = true AND is_active = true;

    -- Portal chat messages
    CREATE TABLE IF NOT EXISTS recruit_portal_messages (
        id SERIAL PRIMARY KEY,
        workspace_id INTEGER NOT NULL,
        role VARCHAR(20) NOT NULL,
        content TEXT NOT NULL,
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT fk_message_workspace FOREIGN KEY (workspace_id)
            REFERENCES recruit_portal_workspaces(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_portal_messages_workspace
        ON recruit_portal_messages(workspace_id, created_at DESC);

    -- Portal scheduled appointments
    CREATE TABLE IF NOT EXISTS recruit_portal_appointments (
        id SERIAL PRIMARY KEY,
        workspace_id INTEGER NOT NULL,
        appointment_type VARCHAR(50) NOT NULL,
        scheduled_at TIMESTAMP NOT NULL,
        duration_minutes INTEGER DEFAULT 30,
        notes TEXT,
        status VARCHAR(20) DEFAULT 'scheduled',
        recruiter_id INTEGER,
        calendar_event_id VARCHAR(100),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT fk_appointment_workspace FOREIGN KEY (workspace_id)
            REFERENCES recruit_portal_workspaces(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_portal_appointments_workspace
        ON recruit_portal_appointments(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_portal_appointments_scheduled
        ON recruit_portal_appointments(scheduled_at) WHERE status = 'scheduled';

    -- Insert sample company updates if none exist
    INSERT INTO recruit_company_updates (title, content, category, is_featured)
    SELECT * FROM (VALUES
        ('Welcome to Perennia!', 'We are excited you are considering joining our team. At Perennia, we provide loan officers with cutting-edge technology, superior leads, and unmatched support to help you close more loans.', 'welcome', true),
        ('Record-Breaking Q4 Results', 'Our team achieved record-breaking production in Q4, with an average of 15% growth per loan officer. See how our technology and support made the difference.', 'success_stories', false),
        ('New AI-Powered Lead System', 'We just launched our new AI-powered lead qualification system that pre-screens prospects and delivers only the highest quality leads to your pipeline.', 'news', false),
        ('Why Top Producers Choose Perennia', 'Hear from our top producers about why they made the switch and how it transformed their business.', 'culture', false),
        ('Comprehensive Training Program', 'Our industry-leading training program includes 1-on-1 coaching, weekly mastermind sessions, and on-demand learning resources.', 'benefits', false)
    ) AS v(title, content, category, is_featured)
    WHERE NOT EXISTS (SELECT 1 FROM recruit_company_updates LIMIT 1);
    """

    # Seed quiz questions
    seed_questions_sql = """
    -- Screening stage questions
    INSERT INTO recruit_quiz_templates (disposition, question_text, question_type, category, weight, display_order)
    SELECT * FROM (VALUES
        ('screening', 'How would you rate the candidate''s production volume based on their stated history?', 'likert', 'production', 1.0, 1),
        ('screening', 'Does the candidate have all required licenses and certifications?', 'yes_no', 'skills', 1.0, 2),
        ('screening', 'How consistent does their production history appear?', 'likert', 'production', 0.8, 3),
        ('screening', 'Rate the candidate''s initial enthusiasm about the opportunity', 'likert', 'culture_fit', 0.7, 4),
        ('screening', 'Does the candidate have experience with the loan types we focus on?', 'likert', 'skills', 0.9, 5)
    ) AS v(disposition, question_text, question_type, category, weight, display_order)
    WHERE NOT EXISTS (SELECT 1 FROM recruit_quiz_templates WHERE disposition = 'screening');

    -- Phone screen stage questions
    INSERT INTO recruit_quiz_templates (disposition, question_text, question_type, category, weight, display_order)
    SELECT * FROM (VALUES
        ('phone_screen', 'How would you rate the candidate''s communication skills?', 'likert', 'skills', 1.0, 1),
        ('phone_screen', 'Rate the candidate''s level of enthusiasm during the call', 'likert', 'culture_fit', 0.9, 2),
        ('phone_screen', 'How coachable does the candidate appear to be?', 'likert', 'character', 1.0, 3),
        ('phone_screen', 'Rate the candidate''s professionalism', 'likert', 'character', 0.9, 4),
        ('phone_screen', 'How well did they articulate their production strategy?', 'likert', 'production', 0.8, 5),
        ('phone_screen', 'Does the candidate align with our company values?', 'likert', 'culture_fit', 1.0, 6)
    ) AS v(disposition, question_text, question_type, category, weight, display_order)
    WHERE NOT EXISTS (SELECT 1 FROM recruit_quiz_templates WHERE disposition = 'phone_screen');

    -- Interview stage questions
    INSERT INTO recruit_quiz_templates (disposition, question_text, question_type, category, weight, display_order)
    SELECT * FROM (VALUES
        ('interview', 'Rate the candidate''s Dominance (D) personality trait', 'likert', 'disc', 1.0, 1),
        ('interview', 'Rate the candidate''s Influence (I) personality trait', 'likert', 'disc', 1.0, 2),
        ('interview', 'Rate the candidate''s Steadiness (S) personality trait', 'likert', 'disc', 1.0, 3),
        ('interview', 'Rate the candidate''s Conscientiousness (C) personality trait', 'likert', 'disc', 1.0, 4),
        ('interview', 'How would you rate the candidate''s integrity?', 'likert', 'character', 1.0, 5),
        ('interview', 'Rate the candidate''s resilience and ability to handle rejection', 'likert', 'character', 0.9, 6),
        ('interview', 'How strong is their work ethic?', 'likert', 'character', 1.0, 7),
        ('interview', 'Rate their technical knowledge of mortgage products', 'likert', 'skills', 1.0, 8),
        ('interview', 'How well do they understand the local market?', 'likert', 'skills', 0.8, 9),
        ('interview', 'Would they be a good cultural fit for the team?', 'likert', 'culture_fit', 1.0, 10)
    ) AS v(disposition, question_text, question_type, category, weight, display_order)
    WHERE NOT EXISTS (SELECT 1 FROM recruit_quiz_templates WHERE disposition = 'interview');

    -- Assessment stage questions
    INSERT INTO recruit_quiz_templates (disposition, question_text, question_type, category, weight, display_order)
    SELECT * FROM (VALUES
        ('assessment', 'How did the candidate perform on the technical assessment?', 'likert', 'skills', 1.0, 1),
        ('assessment', 'Rate their product knowledge depth', 'likert', 'skills', 1.0, 2),
        ('assessment', 'How well did they handle scenario-based questions?', 'likert', 'skills', 0.9, 3),
        ('assessment', 'Rate their problem-solving abilities', 'likert', 'character', 0.9, 4),
        ('assessment', 'How realistic are their production projections?', 'likert', 'production', 1.0, 5)
    ) AS v(disposition, question_text, question_type, category, weight, display_order)
    WHERE NOT EXISTS (SELECT 1 FROM recruit_quiz_templates WHERE disposition = 'assessment');

    -- Offer stage questions
    INSERT INTO recruit_quiz_templates (disposition, question_text, question_type, category, weight, display_order)
    SELECT * FROM (VALUES
        ('offer', 'Final assessment: Values alignment', 'likert', 'culture_fit', 1.0, 1),
        ('offer', 'Final assessment: Team compatibility', 'likert', 'culture_fit', 1.0, 2),
        ('offer', 'Final assessment: Growth potential', 'likert', 'production', 1.0, 3),
        ('offer', 'Final assessment: Leadership potential', 'likert', 'character', 0.8, 4),
        ('offer', 'Overall recommendation for hire', 'likert', 'culture_fit', 1.0, 5)
    ) AS v(disposition, question_text, question_type, category, weight, display_order)
    WHERE NOT EXISTS (SELECT 1 FROM recruit_quiz_templates WHERE disposition = 'offer');
    """

    with engine.connect() as conn:
        # Run main migration
        for statement in migration_sql.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    conn.execute(text(statement))
                except Exception as e:
                    print(f"Warning: {e}")

        # Seed quiz questions
        for statement in seed_questions_sql.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    conn.execute(text(statement))
                except Exception as e:
                    print(f"Warning seeding: {e}")

        conn.commit()

    print("Migration completed: Recruiting assessment tables created and seeded")


if __name__ == "__main__":
    run_migration()
