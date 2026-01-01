"""
Migration: Add Candidate Grading System
Creates tables for comprehensive LO candidate assessment and grading.

Features:
- 5 weighted scoring categories (Production 45%, DISC 20%, Character 15%, Skills 10%, Culture 10%)
- Traditional A+ through F grading scale
- DISC personality assessment
- AI analysis tracking
- Assessment history
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")


def run_migration():
    engine = create_engine(DATABASE_URL)

    migration_sql = """
    -- =============================================================================
    -- CANDIDATE GRADING SYSTEM TABLES
    -- =============================================================================

    -- Main assessment table storing all grading data
    CREATE TABLE IF NOT EXISTS mm_candidate_assessments (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        candidate_id INTEGER NOT NULL REFERENCES mm_candidates(id) ON DELETE CASCADE,

        -- Assessment Metadata
        assessment_version INTEGER DEFAULT 1,
        assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        assessed_by INTEGER REFERENCES users(id),
        assessment_status VARCHAR(30) DEFAULT 'draft',  -- draft, in_progress, completed, reviewed

        -- =============================================================================
        -- PRODUCTION SCORE (45% weight)
        -- =============================================================================
        production_score FLOAT,  -- 0-100
        production_grade VARCHAR(2),  -- A+, A, A-, B+, etc.
        production_breakdown JSONB DEFAULT '{}'::jsonb,
        -- Structure: {
        --   "annual_volume_score": 0-100,
        --   "annual_units_score": 0-100,
        --   "consistency_score": 0-100,
        --   "growth_trend_score": 0-100,
        --   "avg_loan_size_score": 0-100,
        --   "notes": "string"
        -- }

        -- =============================================================================
        -- PERSONALITY/DISC SCORE (20% weight)
        -- =============================================================================
        disc_d_score INTEGER DEFAULT 0,  -- Dominance 0-100
        disc_i_score INTEGER DEFAULT 0,  -- Influence 0-100
        disc_s_score INTEGER DEFAULT 0,  -- Steadiness 0-100
        disc_c_score INTEGER DEFAULT 0,  -- Conscientiousness 0-100
        disc_primary_style VARCHAR(1),   -- D, I, S, or C
        disc_secondary_style VARCHAR(1),
        disc_composite_score FLOAT,      -- Weighted combination for LO role fit
        disc_grade VARCHAR(2),
        disc_notes TEXT,
        disc_assessment_source VARCHAR(50),  -- manual, ai_inferred, formal_assessment

        -- =============================================================================
        -- CHARACTER SCORE (15% weight)
        -- =============================================================================
        character_score FLOAT,
        character_grade VARCHAR(2),
        character_breakdown JSONB DEFAULT '{}'::jsonb,
        -- Structure: {
        --   "integrity_score": 0-100,
        --   "coachability_score": 0-100,
        --   "resilience_score": 0-100,
        --   "work_ethic_score": 0-100,
        --   "notes": "string"
        -- }

        -- =============================================================================
        -- SKILLS SCORE (10% weight)
        -- =============================================================================
        skills_score FLOAT,
        skills_grade VARCHAR(2),
        skills_breakdown JSONB DEFAULT '{}'::jsonb,
        -- Structure: {
        --   "technical_score": 0-100,
        --   "product_knowledge_score": 0-100,
        --   "market_expertise_score": 0-100,
        --   "technology_proficiency_score": 0-100,
        --   "identified_skills": ["skill1", "skill2"],
        --   "skill_gaps": ["gap1", "gap2"],
        --   "notes": "string"
        -- }

        -- =============================================================================
        -- CULTURE FIT SCORE (10% weight)
        -- =============================================================================
        culture_fit_score FLOAT,
        culture_fit_grade VARCHAR(2),
        culture_fit_breakdown JSONB DEFAULT '{}'::jsonb,
        -- Structure: {
        --   "values_alignment_score": 0-100,
        --   "team_compatibility_score": 0-100,
        --   "communication_style_score": 0-100,
        --   "growth_mindset_score": 0-100,
        --   "notes": "string"
        -- }

        -- =============================================================================
        -- OVERALL COMPOSITE
        -- =============================================================================
        overall_score FLOAT,
        overall_grade VARCHAR(2),

        -- =============================================================================
        -- AI ANALYSIS DATA
        -- =============================================================================
        ai_analysis_run_at TIMESTAMP,
        ai_analysis_version VARCHAR(20),
        ai_confidence_score FLOAT,  -- 0-100 how confident AI is in analysis
        ai_raw_analysis JSONB DEFAULT '{}'::jsonb,
        -- Structure: {
        --   "resume_analysis": {...},
        --   "social_media_analysis": {...},
        --   "interview_notes_analysis": {...},
        --   "strengths_identified": [...],
        --   "weaknesses_identified": [...],
        --   "recommendations": [...],
        --   "risk_flags": [...]
        -- }

        -- =============================================================================
        -- STRENGTHS & WEAKNESSES (Human readable)
        -- =============================================================================
        strengths TEXT[],
        weaknesses TEXT[],
        recruiter_notes TEXT,
        recruiter_recommendation VARCHAR(30),  -- strong_hire, hire, maybe, no_hire, strong_no_hire

        -- =============================================================================
        -- OVERRIDE TRACKING
        -- =============================================================================
        scores_overridden BOOLEAN DEFAULT false,
        override_reason TEXT,
        override_by INTEGER REFERENCES users(id),
        override_at TIMESTAMP,
        original_scores JSONB,  -- Stores original scores before override

        -- Timestamps
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Indexes for performance
    CREATE INDEX IF NOT EXISTS ix_mm_assessment_candidate ON mm_candidate_assessments(candidate_id);
    CREATE INDEX IF NOT EXISTS ix_mm_assessment_org ON mm_candidate_assessments(organization_id);
    CREATE INDEX IF NOT EXISTS ix_mm_assessment_status ON mm_candidate_assessments(assessment_status);
    CREATE INDEX IF NOT EXISTS ix_mm_assessment_grade ON mm_candidate_assessments(overall_grade);
    CREATE INDEX IF NOT EXISTS ix_mm_assessment_assessed_at ON mm_candidate_assessments(assessed_at);

    -- =============================================================================
    -- ASSESSMENT HISTORY TABLE
    -- Track historical assessments for trend analysis
    -- =============================================================================
    CREATE TABLE IF NOT EXISTS mm_assessment_history (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        candidate_id INTEGER NOT NULL REFERENCES mm_candidates(id) ON DELETE CASCADE,
        assessment_id INTEGER REFERENCES mm_candidate_assessments(id) ON DELETE CASCADE,

        -- Snapshot of scores at this point
        snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        production_score FLOAT,
        disc_composite_score FLOAT,
        character_score FLOAT,
        skills_score FLOAT,
        culture_fit_score FLOAT,
        overall_score FLOAT,
        overall_grade VARCHAR(2),

        -- What changed
        change_type VARCHAR(50),  -- initial, update, ai_refresh, manual_override
        changed_by INTEGER REFERENCES users(id),
        change_notes TEXT,

        -- Full snapshot for detailed comparison
        full_snapshot JSONB DEFAULT '{}'::jsonb,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    );

    CREATE INDEX IF NOT EXISTS ix_mm_assessment_history_candidate ON mm_assessment_history(candidate_id);
    CREATE INDEX IF NOT EXISTS ix_mm_assessment_history_snapshot ON mm_assessment_history(snapshot_at);
    CREATE INDEX IF NOT EXISTS ix_mm_assessment_history_assessment ON mm_assessment_history(assessment_id);

    -- =============================================================================
    -- ADD COLUMNS TO mm_candidates FOR QUICK ACCESS
    -- =============================================================================
    DO $$
    BEGIN
        -- Current assessment reference
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_candidates' AND column_name = 'current_assessment_id') THEN
            ALTER TABLE mm_candidates ADD COLUMN current_assessment_id INTEGER;
        END IF;

        -- Current grade for quick filtering/sorting
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_candidates' AND column_name = 'current_grade') THEN
            ALTER TABLE mm_candidates ADD COLUMN current_grade VARCHAR(2);
        END IF;

        -- When grade was last updated
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_candidates' AND column_name = 'grade_updated_at') THEN
            ALTER TABLE mm_candidates ADD COLUMN grade_updated_at TIMESTAMP;
        END IF;

        -- DISC primary style for quick filtering
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_candidates' AND column_name = 'disc_primary_style') THEN
            ALTER TABLE mm_candidates ADD COLUMN disc_primary_style VARCHAR(1);
        END IF;
    END $$;

    -- Index for grade filtering on candidates
    CREATE INDEX IF NOT EXISTS ix_mm_candidates_grade ON mm_candidates(current_grade);
    CREATE INDEX IF NOT EXISTS ix_mm_candidates_disc ON mm_candidates(disc_primary_style);

    -- =============================================================================
    -- TRIGGER: Auto-update updated_at timestamps
    -- =============================================================================
    DO $$
    BEGIN
        -- Assessments
        DROP TRIGGER IF EXISTS update_mm_assessments_updated_at ON mm_candidate_assessments;
        CREATE TRIGGER update_mm_assessments_updated_at
            BEFORE UPDATE ON mm_candidate_assessments
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'Trigger creation note: %', SQLERRM;
    END $$;

    -- =============================================================================
    -- FUNCTION: Calculate overall grade from component scores
    -- =============================================================================
    CREATE OR REPLACE FUNCTION calculate_overall_grade(
        p_production FLOAT,
        p_disc FLOAT,
        p_character FLOAT,
        p_skills FLOAT,
        p_culture FLOAT
    ) RETURNS TABLE(score FLOAT, grade VARCHAR(2)) AS $$
    DECLARE
        v_score FLOAT;
        v_grade VARCHAR(2);
    BEGIN
        -- Weighted calculation: Production 45%, DISC 20%, Character 15%, Skills 10%, Culture 10%
        v_score := COALESCE(p_production, 0) * 0.45 +
                   COALESCE(p_disc, 0) * 0.20 +
                   COALESCE(p_character, 0) * 0.15 +
                   COALESCE(p_skills, 0) * 0.10 +
                   COALESCE(p_culture, 0) * 0.10;

        -- Grade thresholds
        v_grade := CASE
            WHEN v_score >= 95 THEN 'A+'
            WHEN v_score >= 90 THEN 'A'
            WHEN v_score >= 85 THEN 'A-'
            WHEN v_score >= 80 THEN 'B+'
            WHEN v_score >= 75 THEN 'B'
            WHEN v_score >= 70 THEN 'B-'
            WHEN v_score >= 65 THEN 'C+'
            WHEN v_score >= 60 THEN 'C'
            WHEN v_score >= 55 THEN 'C-'
            WHEN v_score >= 50 THEN 'D'
            ELSE 'F'
        END;

        RETURN QUERY SELECT ROUND(v_score::numeric, 1)::FLOAT, v_grade;
    END;
    $$ LANGUAGE plpgsql;

    -- =============================================================================
    -- FUNCTION: Get grade from score
    -- =============================================================================
    CREATE OR REPLACE FUNCTION get_grade_from_score(p_score FLOAT)
    RETURNS VARCHAR(2) AS $$
    BEGIN
        RETURN CASE
            WHEN p_score >= 95 THEN 'A+'
            WHEN p_score >= 90 THEN 'A'
            WHEN p_score >= 85 THEN 'A-'
            WHEN p_score >= 80 THEN 'B+'
            WHEN p_score >= 75 THEN 'B'
            WHEN p_score >= 70 THEN 'B-'
            WHEN p_score >= 65 THEN 'C+'
            WHEN p_score >= 60 THEN 'C'
            WHEN p_score >= 55 THEN 'C-'
            WHEN p_score >= 50 THEN 'D'
            ELSE 'F'
        END;
    END;
    $$ LANGUAGE plpgsql;

    -- =============================================================================
    -- FUNCTION: Calculate DISC composite for LO role
    -- =============================================================================
    CREATE OR REPLACE FUNCTION calculate_disc_composite(
        p_d INTEGER,
        p_i INTEGER,
        p_s INTEGER,
        p_c INTEGER
    ) RETURNS TABLE(composite FLOAT, primary_style VARCHAR(1), secondary_style VARCHAR(1)) AS $$
    DECLARE
        v_composite FLOAT;
        v_primary VARCHAR(1);
        v_secondary VARCHAR(1);
        v_scores FLOAT[];
        v_styles VARCHAR(1)[];
    BEGIN
        -- LO-weighted composite: I=40%, D=30%, S=15%, C=15%
        v_composite := COALESCE(p_i, 0) * 0.40 +
                       COALESCE(p_d, 0) * 0.30 +
                       COALESCE(p_s, 0) * 0.15 +
                       COALESCE(p_c, 0) * 0.15;

        -- Determine primary and secondary styles
        v_scores := ARRAY[COALESCE(p_d, 0)::FLOAT, COALESCE(p_i, 0)::FLOAT,
                          COALESCE(p_s, 0)::FLOAT, COALESCE(p_c, 0)::FLOAT];
        v_styles := ARRAY['D', 'I', 'S', 'C'];

        -- Find primary (highest score)
        SELECT v_styles[idx] INTO v_primary
        FROM (SELECT generate_subscripts(v_scores, 1) as idx,
                     unnest(v_scores) as val
              ORDER BY val DESC LIMIT 1) t;

        -- Find secondary (second highest)
        SELECT v_styles[idx] INTO v_secondary
        FROM (SELECT generate_subscripts(v_scores, 1) as idx,
                     unnest(v_scores) as val
              ORDER BY val DESC LIMIT 2 OFFSET 1) t;

        RETURN QUERY SELECT ROUND(v_composite::numeric, 1)::FLOAT, v_primary, v_secondary;
    END;
    $$ LANGUAGE plpgsql;
    """

    with engine.connect() as conn:
        # Execute migration
        conn.execute(text(migration_sql))
        conn.commit()
        print("Candidate Grading System tables created successfully!")

        # Verify tables
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name IN ('mm_candidate_assessments', 'mm_assessment_history')
            ORDER BY table_name
        """))
        tables = [row[0] for row in result]
        print(f"\nTables created: {tables}")

        # Verify columns added to mm_candidates
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'mm_candidates'
            AND column_name IN ('current_assessment_id', 'current_grade', 'grade_updated_at', 'disc_primary_style')
            ORDER BY column_name
        """))
        columns = [row[0] for row in result]
        print(f"Columns added to mm_candidates: {columns}")

    return {"message": "Candidate Grading System migration completed successfully"}


if __name__ == "__main__":
    run_migration()
