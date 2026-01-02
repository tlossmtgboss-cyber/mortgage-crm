"""
Migration: Add DISC + Motivators Assessment System

Creates tables for:
- disc_assessments: Assessment configuration
- disc_questions: Question bank (DISC + Motivators)
- disc_assessment_sessions: Candidate assessment sessions
- disc_responses: Individual question responses
- disc_results: Computed DISC scores (Adapted + Natural styles)
- motivator_results: 7-dimension Motivator scores
- disc_reports: Generated PDF reports
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine


def run_migration():
    """Run the migration to add DISC + Motivators assessment tables."""

    migration_sql = """
    -- =========================================================================
    -- DISC ASSESSMENT CONFIGURATION
    -- =========================================================================

    CREATE TABLE IF NOT EXISTS disc_assessments (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        version VARCHAR(20) DEFAULT '1.0',
        description TEXT,
        is_active BOOLEAN DEFAULT true,
        scoring_method VARCHAR(20) DEFAULT 'ipsative',  -- ipsative or normative
        total_disc_questions INTEGER DEFAULT 24,
        total_motivator_questions INTEGER DEFAULT 28,
        time_limit_minutes INTEGER,
        instructions TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    -- =========================================================================
    -- DISC QUESTION BANK
    -- =========================================================================

    CREATE TABLE IF NOT EXISTS disc_questions (
        id SERIAL PRIMARY KEY,
        assessment_id INTEGER REFERENCES disc_assessments(id) ON DELETE CASCADE,
        question_order INTEGER NOT NULL,
        question_section VARCHAR(20) NOT NULL,  -- 'disc' or 'motivator'
        question_type VARCHAR(20) DEFAULT 'forced_choice',  -- forced_choice, likert, ranking
        prompt TEXT NOT NULL,
        options JSONB NOT NULL,  -- [{text, dimension, weight, position}]
        dimension_measured VARCHAR(20),  -- D, I, S, C, or motivator dimension
        is_calibration BOOLEAN DEFAULT false,
        is_reverse_keyed BOOLEAN DEFAULT false,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_disc_questions_assessment
        ON disc_questions(assessment_id, question_order);
    CREATE INDEX IF NOT EXISTS idx_disc_questions_section
        ON disc_questions(assessment_id, question_section);

    -- =========================================================================
    -- DISC ASSESSMENT SESSIONS
    -- =========================================================================

    CREATE TABLE IF NOT EXISTS disc_assessment_sessions (
        id SERIAL PRIMARY KEY,
        candidate_id INTEGER NOT NULL,
        assessment_id INTEGER REFERENCES disc_assessments(id),
        status VARCHAR(20) DEFAULT 'not_started',  -- not_started, in_progress, completed, expired
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        current_question INTEGER DEFAULT 0,
        time_spent_seconds INTEGER DEFAULT 0,
        ip_address VARCHAR(45),
        user_agent TEXT,
        invite_token VARCHAR(100) UNIQUE,
        invite_sent_at TIMESTAMP,
        invite_expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT fk_disc_session_candidate FOREIGN KEY (candidate_id)
            REFERENCES mm_candidates(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_disc_sessions_candidate
        ON disc_assessment_sessions(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_disc_sessions_status
        ON disc_assessment_sessions(status) WHERE status = 'in_progress';
    CREATE INDEX IF NOT EXISTS idx_disc_sessions_token
        ON disc_assessment_sessions(invite_token) WHERE invite_token IS NOT NULL;

    -- =========================================================================
    -- DISC RESPONSES (Individual Answers)
    -- =========================================================================

    CREATE TABLE IF NOT EXISTS disc_responses (
        id SERIAL PRIMARY KEY,
        session_id INTEGER NOT NULL,
        question_id INTEGER REFERENCES disc_questions(id),
        response_value JSONB NOT NULL,  -- {most: option_id, least: option_id} or {value: 1-5}
        response_time_ms INTEGER,
        answered_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT fk_disc_response_session FOREIGN KEY (session_id)
            REFERENCES disc_assessment_sessions(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_disc_responses_session
        ON disc_responses(session_id);

    -- =========================================================================
    -- DISC RESULTS (Computed Scores)
    -- =========================================================================

    CREATE TABLE IF NOT EXISTS disc_results (
        id SERIAL PRIMARY KEY,
        session_id INTEGER UNIQUE,
        candidate_id INTEGER NOT NULL,

        -- Adapted Style (Graph I - how they behave at work)
        adapted_d INTEGER NOT NULL DEFAULT 0,  -- 0-100
        adapted_i INTEGER NOT NULL DEFAULT 0,
        adapted_s INTEGER NOT NULL DEFAULT 0,
        adapted_c INTEGER NOT NULL DEFAULT 0,
        adapted_style VARCHAR(10),  -- e.g., "ISc", "DI", "Cd"

        -- Natural Style (Graph II - natural tendencies)
        natural_d INTEGER NOT NULL DEFAULT 0,
        natural_i INTEGER NOT NULL DEFAULT 0,
        natural_s INTEGER NOT NULL DEFAULT 0,
        natural_c INTEGER NOT NULL DEFAULT 0,
        natural_style VARCHAR(10),

        -- Combined style notation (e.g., "ISc/CI")
        combined_style VARCHAR(20),

        -- Behavioral Pattern View (wheel position)
        wheel_zone INTEGER,  -- 1-8
        wheel_position INTEGER,  -- 1-81
        wheel_zone_name VARCHAR(50),

        -- Quality metrics
        calibration_score DECIMAL(3,2),  -- 0.00-1.00
        consistency_score DECIMAL(3,2),
        response_time_score DECIMAL(3,2),
        quality_tier VARCHAR(10),  -- HIGH, MEDIUM, LOW
        quality_notes TEXT,

        -- AI-generated content (cached)
        characteristics TEXT,
        word_sketch JSONB,
        communication_tips JSONB,
        wants_and_needs JSONB,
        strengths JSONB,  -- Array of strings
        stress_behaviors JSONB,
        areas_for_improvement JSONB,
        integrated_styles JSONB,  -- 12 style relationships

        computed_at TIMESTAMP DEFAULT NOW(),
        ai_content_generated_at TIMESTAMP,

        CONSTRAINT fk_disc_result_session FOREIGN KEY (session_id)
            REFERENCES disc_assessment_sessions(id) ON DELETE CASCADE,
        CONSTRAINT fk_disc_result_candidate FOREIGN KEY (candidate_id)
            REFERENCES mm_candidates(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_disc_results_candidate
        ON disc_results(candidate_id);

    -- =========================================================================
    -- MOTIVATOR RESULTS (7 Dimensions)
    -- =========================================================================

    CREATE TABLE IF NOT EXISTS motivator_results (
        id SERIAL PRIMARY KEY,
        session_id INTEGER UNIQUE,
        candidate_id INTEGER NOT NULL,

        -- 7 Motivator Dimensions (0-100 scale)
        aesthetic INTEGER NOT NULL DEFAULT 50,       -- Beauty, balance, harmony
        economic INTEGER NOT NULL DEFAULT 50,        -- ROI, practicality, results
        individualistic INTEGER NOT NULL DEFAULT 50, -- Independence, uniqueness
        political INTEGER NOT NULL DEFAULT 50,       -- Control, influence, power
        altruistic INTEGER NOT NULL DEFAULT 50,      -- Service, helping others
        regulatory INTEGER NOT NULL DEFAULT 50,      -- Order, structure, tradition
        theoretical INTEGER NOT NULL DEFAULT 50,     -- Knowledge, learning, truth

        -- Ranked order (1=highest, 7=lowest)
        ranking JSONB,  -- {"economic": 1, "theoretical": 2, ...}

        -- Top motivators summary
        top_motivator VARCHAR(20),
        second_motivator VARCHAR(20),
        lowest_motivator VARCHAR(20),

        -- AI-generated insights per dimension
        dimension_insights JSONB,
        overall_summary TEXT,

        computed_at TIMESTAMP DEFAULT NOW(),
        ai_content_generated_at TIMESTAMP,

        CONSTRAINT fk_motivator_result_session FOREIGN KEY (session_id)
            REFERENCES disc_assessment_sessions(id) ON DELETE CASCADE,
        CONSTRAINT fk_motivator_result_candidate FOREIGN KEY (candidate_id)
            REFERENCES mm_candidates(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_motivator_results_candidate
        ON motivator_results(candidate_id);

    -- =========================================================================
    -- DISC REPORTS (Generated PDFs)
    -- =========================================================================

    CREATE TABLE IF NOT EXISTS disc_reports (
        id SERIAL PRIMARY KEY,
        candidate_id INTEGER NOT NULL,
        disc_result_id INTEGER REFERENCES disc_results(id),
        motivator_result_id INTEGER REFERENCES motivator_results(id),
        report_type VARCHAR(20) DEFAULT 'full',  -- full, disc_only, summary
        s3_key VARCHAR(255),
        s3_url TEXT,
        file_size_bytes INTEGER,
        page_count INTEGER,
        generated_at TIMESTAMP DEFAULT NOW(),
        expires_at TIMESTAMP,
        CONSTRAINT fk_disc_report_candidate FOREIGN KEY (candidate_id)
            REFERENCES mm_candidates(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_disc_reports_candidate
        ON disc_reports(candidate_id);

    -- =========================================================================
    -- UPDATE mm_candidates TABLE
    -- =========================================================================

    -- Add DISC session reference to candidates
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'mm_candidates' AND column_name = 'disc_session_id') THEN
            ALTER TABLE mm_candidates ADD COLUMN disc_session_id INTEGER
                REFERENCES disc_assessment_sessions(id) ON DELETE SET NULL;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'mm_candidates' AND column_name = 'disc_completed_at') THEN
            ALTER TABLE mm_candidates ADD COLUMN disc_completed_at TIMESTAMP;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'mm_candidates' AND column_name = 'disc_style') THEN
            ALTER TABLE mm_candidates ADD COLUMN disc_style VARCHAR(20);
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'mm_candidates' AND column_name = 'top_motivator') THEN
            ALTER TABLE mm_candidates ADD COLUMN top_motivator VARCHAR(20);
        END IF;
    END $$;
    """

    # Seed default assessment and questions
    seed_sql = """
    -- Insert default DISC + Motivators assessment
    INSERT INTO disc_assessments (name, version, description, instructions)
    SELECT
        'DISC + Motivators Assessment',
        '1.0',
        'Comprehensive behavioral assessment combining DISC personality profile with 7-dimension Motivators analysis',
        'This assessment will help us understand your behavioral style and what motivates you. Answer honestly - there are no right or wrong answers. The assessment takes approximately 15-20 minutes to complete.'
    WHERE NOT EXISTS (SELECT 1 FROM disc_assessments WHERE name = 'DISC + Motivators Assessment');

    -- Insert DISC forced-choice questions (24 questions)
    INSERT INTO disc_questions (assessment_id, question_order, question_section, question_type, prompt, options, dimension_measured)
    SELECT
        (SELECT id FROM disc_assessments WHERE name = 'DISC + Motivators Assessment' LIMIT 1),
        q.question_order,
        'disc',
        'forced_choice',
        'Select which describes you MOST and which describes you LEAST:',
        q.options::jsonb,
        NULL
    FROM (VALUES
        (1, '[{"id": "1a", "text": "Takes charge and leads decisively", "dimension": "D", "weight": 1}, {"id": "1b", "text": "Enjoys socializing and meeting new people", "dimension": "I", "weight": 1}, {"id": "1c", "text": "Remains patient and supportive of others", "dimension": "S", "weight": 1}, {"id": "1d", "text": "Analyzes details carefully before acting", "dimension": "C", "weight": 1}]'),
        (2, '[{"id": "2a", "text": "Competitive and driven to win", "dimension": "D", "weight": 1}, {"id": "2b", "text": "Enthusiastic and optimistic", "dimension": "I", "weight": 1}, {"id": "2c", "text": "Calm and easy-going", "dimension": "S", "weight": 1}, {"id": "2d", "text": "Precise and detail-oriented", "dimension": "C", "weight": 1}]'),
        (3, '[{"id": "3a", "text": "Direct and to the point", "dimension": "D", "weight": 1}, {"id": "3b", "text": "Persuasive and inspiring", "dimension": "I", "weight": 1}, {"id": "3c", "text": "Reliable and consistent", "dimension": "S", "weight": 1}, {"id": "3d", "text": "Systematic and organized", "dimension": "C", "weight": 1}]'),
        (4, '[{"id": "4a", "text": "Makes quick decisions", "dimension": "D", "weight": 1}, {"id": "4b", "text": "Trusts gut feelings", "dimension": "I", "weight": 1}, {"id": "4c", "text": "Prefers proven methods", "dimension": "S", "weight": 1}, {"id": "4d", "text": "Researches thoroughly", "dimension": "C", "weight": 1}]'),
        (5, '[{"id": "5a", "text": "Assertive and confident", "dimension": "D", "weight": 1}, {"id": "5b", "text": "Expressive and animated", "dimension": "I", "weight": 1}, {"id": "5c", "text": "Thoughtful and considerate", "dimension": "S", "weight": 1}, {"id": "5d", "text": "Logical and analytical", "dimension": "C", "weight": 1}]'),
        (6, '[{"id": "6a", "text": "Focuses on results above all", "dimension": "D", "weight": 1}, {"id": "6b", "text": "Builds relationships naturally", "dimension": "I", "weight": 1}, {"id": "6c", "text": "Values team harmony", "dimension": "S", "weight": 1}, {"id": "6d", "text": "Ensures quality standards", "dimension": "C", "weight": 1}]'),
        (7, '[{"id": "7a", "text": "Thrives under pressure", "dimension": "D", "weight": 1}, {"id": "7b", "text": "Energized by excitement", "dimension": "I", "weight": 1}, {"id": "7c", "text": "Prefers stable environments", "dimension": "S", "weight": 1}, {"id": "7d", "text": "Works best with clear rules", "dimension": "C", "weight": 1}]'),
        (8, '[{"id": "8a", "text": "Challenges the status quo", "dimension": "D", "weight": 1}, {"id": "8b", "text": "Generates creative ideas", "dimension": "I", "weight": 1}, {"id": "8c", "text": "Maintains traditions", "dimension": "S", "weight": 1}, {"id": "8d", "text": "Follows established procedures", "dimension": "C", "weight": 1}]'),
        (9, '[{"id": "9a", "text": "Takes control of situations", "dimension": "D", "weight": 1}, {"id": "9b", "text": "Motivates and encourages others", "dimension": "I", "weight": 1}, {"id": "9c", "text": "Listens more than speaks", "dimension": "S", "weight": 1}, {"id": "9d", "text": "Questions and verifies information", "dimension": "C", "weight": 1}]'),
        (10, '[{"id": "10a", "text": "Driven by achievement", "dimension": "D", "weight": 1}, {"id": "10b", "text": "Driven by recognition", "dimension": "I", "weight": 1}, {"id": "10c", "text": "Driven by security", "dimension": "S", "weight": 1}, {"id": "10d", "text": "Driven by accuracy", "dimension": "C", "weight": 1}]'),
        (11, '[{"id": "11a", "text": "Impatient with slow progress", "dimension": "D", "weight": 1}, {"id": "11b", "text": "Dislikes routine work", "dimension": "I", "weight": 1}, {"id": "11c", "text": "Uncomfortable with change", "dimension": "S", "weight": 1}, {"id": "11d", "text": "Critical of poor quality", "dimension": "C", "weight": 1}]'),
        (12, '[{"id": "12a", "text": "Demands results from self and others", "dimension": "D", "weight": 1}, {"id": "12b", "text": "Seeks approval and applause", "dimension": "I", "weight": 1}, {"id": "12c", "text": "Seeks stability and predictability", "dimension": "S", "weight": 1}, {"id": "12d", "text": "Seeks perfection in work", "dimension": "C", "weight": 1}]'),
        (13, '[{"id": "13a", "text": "Bold and fearless", "dimension": "D", "weight": 1}, {"id": "13b", "text": "Fun-loving and playful", "dimension": "I", "weight": 1}, {"id": "13c", "text": "Gentle and accommodating", "dimension": "S", "weight": 1}, {"id": "13d", "text": "Careful and cautious", "dimension": "C", "weight": 1}]'),
        (14, '[{"id": "14a", "text": "Likes to be in charge", "dimension": "D", "weight": 1}, {"id": "14b", "text": "Likes to be the center of attention", "dimension": "I", "weight": 1}, {"id": "14c", "text": "Likes to help behind the scenes", "dimension": "S", "weight": 1}, {"id": "14d", "text": "Likes to work independently", "dimension": "C", "weight": 1}]'),
        (15, '[{"id": "15a", "text": "Handles conflict directly", "dimension": "D", "weight": 1}, {"id": "15b", "text": "Uses humor to diffuse tension", "dimension": "I", "weight": 1}, {"id": "15c", "text": "Avoids confrontation when possible", "dimension": "S", "weight": 1}, {"id": "15d", "text": "Addresses issues with facts and logic", "dimension": "C", "weight": 1}]'),
        (16, '[{"id": "16a", "text": "Sets ambitious goals", "dimension": "D", "weight": 1}, {"id": "16b", "text": "Dreams big possibilities", "dimension": "I", "weight": 1}, {"id": "16c", "text": "Sets realistic expectations", "dimension": "S", "weight": 1}, {"id": "16d", "text": "Plans detailed action steps", "dimension": "C", "weight": 1}]'),
        (17, '[{"id": "17a", "text": "Speaks with authority", "dimension": "D", "weight": 1}, {"id": "17b", "text": "Speaks with enthusiasm", "dimension": "I", "weight": 1}, {"id": "17c", "text": "Speaks with warmth", "dimension": "S", "weight": 1}, {"id": "17d", "text": "Speaks with precision", "dimension": "C", "weight": 1}]'),
        (18, '[{"id": "18a", "text": "Focuses on the bottom line", "dimension": "D", "weight": 1}, {"id": "18b", "text": "Focuses on the big picture", "dimension": "I", "weight": 1}, {"id": "18c", "text": "Focuses on the team", "dimension": "S", "weight": 1}, {"id": "18d", "text": "Focuses on the details", "dimension": "C", "weight": 1}]'),
        (19, '[{"id": "19a", "text": "Risk-taker", "dimension": "D", "weight": 1}, {"id": "19b", "text": "Optimist", "dimension": "I", "weight": 1}, {"id": "19c", "text": "Peacemaker", "dimension": "S", "weight": 1}, {"id": "19d", "text": "Perfectionist", "dimension": "C", "weight": 1}]'),
        (20, '[{"id": "20a", "text": "Gets frustrated by inefficiency", "dimension": "D", "weight": 1}, {"id": "20b", "text": "Gets bored by routine", "dimension": "I", "weight": 1}, {"id": "20c", "text": "Gets stressed by conflict", "dimension": "S", "weight": 1}, {"id": "20d", "text": "Gets anxious about mistakes", "dimension": "C", "weight": 1}]'),
        (21, '[{"id": "21a", "text": "Delegates tasks easily", "dimension": "D", "weight": 1}, {"id": "21b", "text": "Delegates to build relationships", "dimension": "I", "weight": 1}, {"id": "21c", "text": "Prefers to do it yourself", "dimension": "S", "weight": 1}, {"id": "21d", "text": "Delegates only with clear instructions", "dimension": "C", "weight": 1}]'),
        (22, '[{"id": "22a", "text": "Values efficiency and speed", "dimension": "D", "weight": 1}, {"id": "22b", "text": "Values creativity and fun", "dimension": "I", "weight": 1}, {"id": "22c", "text": "Values loyalty and dependability", "dimension": "S", "weight": 1}, {"id": "22d", "text": "Values accuracy and quality", "dimension": "C", "weight": 1}]'),
        (23, '[{"id": "23a", "text": "Makes things happen", "dimension": "D", "weight": 1}, {"id": "23b", "text": "Makes things exciting", "dimension": "I", "weight": 1}, {"id": "23c", "text": "Makes things smooth", "dimension": "S", "weight": 1}, {"id": "23d", "text": "Makes things right", "dimension": "C", "weight": 1}]'),
        (24, '[{"id": "24a", "text": "Wants authority and autonomy", "dimension": "D", "weight": 1}, {"id": "24b", "text": "Wants appreciation and influence", "dimension": "I", "weight": 1}, {"id": "24c", "text": "Wants security and appreciation", "dimension": "S", "weight": 1}, {"id": "24d", "text": "Wants quality and correctness", "dimension": "C", "weight": 1}]')
    ) AS q(question_order, options)
    WHERE NOT EXISTS (SELECT 1 FROM disc_questions WHERE question_section = 'disc');

    -- Insert Motivator questions (28 questions, 4 per dimension)
    INSERT INTO disc_questions (assessment_id, question_order, question_section, question_type, prompt, options, dimension_measured)
    SELECT
        (SELECT id FROM disc_assessments WHERE name = 'DISC + Motivators Assessment' LIMIT 1),
        25 + q.question_order - 1,
        'motivator',
        'likert',
        q.prompt,
        '[{"value": 1, "label": "Strongly Disagree"}, {"value": 2, "label": "Disagree"}, {"value": 3, "label": "Slightly Disagree"}, {"value": 4, "label": "Neutral"}, {"value": 5, "label": "Slightly Agree"}, {"value": 6, "label": "Agree"}, {"value": 7, "label": "Strongly Agree"}]'::jsonb,
        q.dimension
    FROM (VALUES
        -- Aesthetic (beauty, balance, form)
        (1, 'I find great satisfaction in creating or experiencing beautiful things.', 'aesthetic'),
        (2, 'Artistic expression and creativity are essential to my well-being.', 'aesthetic'),
        (3, 'I am drawn to experiences that engage my senses and emotions.', 'aesthetic'),
        (4, 'I appreciate design, aesthetics, and visual harmony in my surroundings.', 'aesthetic'),

        -- Economic (ROI, practicality)
        (5, 'I evaluate decisions primarily based on practical return on investment.', 'economic'),
        (6, 'Efficiency and tangible results matter more to me than abstract ideas.', 'economic'),
        (7, 'I am motivated by financial success and wealth accumulation.', 'economic'),
        (8, 'I prefer practical solutions that deliver measurable outcomes.', 'economic'),

        -- Individualistic (independence, uniqueness)
        (9, 'I value being recognized for my unique contributions and talents.', 'individualistic'),
        (10, 'Standing out from the crowd is important to me.', 'individualistic'),
        (11, 'I prefer to carve my own path rather than follow others.', 'individualistic'),
        (12, 'Personal achievement and self-expression drive me.', 'individualistic'),

        -- Political (control, influence, power)
        (13, 'I enjoy being in positions of authority and influence.', 'political'),
        (14, 'Having control over my environment and decisions is important to me.', 'political'),
        (15, 'I am motivated by opportunities to lead and direct others.', 'political'),
        (16, 'Building power and influence is a key driver for me.', 'political'),

        -- Altruistic (service, helping others)
        (17, 'Helping others succeed brings me great satisfaction.', 'altruistic'),
        (18, 'I am motivated by opportunities to serve and support others.', 'altruistic'),
        (19, 'Making a positive difference in people''s lives is my priority.', 'altruistic'),
        (20, 'I often put others'' needs before my own.', 'altruistic'),

        -- Regulatory (order, structure, tradition)
        (21, 'I value following established rules and traditions.', 'regulatory'),
        (22, 'Structure and order are essential for me to function effectively.', 'regulatory'),
        (23, 'I believe in upholding standards and maintaining systems.', 'regulatory'),
        (24, 'Predictability and clear expectations are important to me.', 'regulatory'),

        -- Theoretical (knowledge, learning, truth)
        (25, 'I have a strong desire to understand how things work.', 'theoretical'),
        (26, 'Learning new concepts and ideas is deeply satisfying to me.', 'theoretical'),
        (27, 'I am driven by the pursuit of knowledge and truth.', 'theoretical'),
        (28, 'I enjoy analyzing problems and discovering underlying principles.', 'theoretical')
    ) AS q(question_order, prompt, dimension)
    WHERE NOT EXISTS (SELECT 1 FROM disc_questions WHERE question_section = 'motivator');
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

        # Run seed data
        for statement in seed_sql.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    conn.execute(text(statement))
                except Exception as e:
                    print(f"Warning seeding: {e}")

        conn.commit()

    print("Migration completed: DISC + Motivators assessment tables created and seeded")


if __name__ == "__main__":
    run_migration()
