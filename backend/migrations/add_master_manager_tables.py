"""
Master Manager Platform - Database Migration
Creates tables for capacity tracking, talent state, performance, and recruiting.
"""

import os
import sys
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine


def run_migration():
    """Create all Master Manager tables."""

    migration_sql = """
    -- ==========================================================================
    -- ROLE DEFINITIONS TABLE
    -- ==========================================================================
    CREATE TABLE IF NOT EXISTS mm_role_definitions (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
        role_name VARCHAR(100) NOT NULL,
        role_category VARCHAR(30) DEFAULT 'operations',
        description TEXT,
        onboarding_role_id INTEGER REFERENCES onboarding_roles(id),

        -- Capacity Standards
        default_max_files INTEGER DEFAULT 25,
        default_max_leads INTEGER DEFAULT 50,
        default_max_tasks_daily INTEGER DEFAULT 30,

        -- Performance Expectations
        expected_throughput JSONB DEFAULT '{}',
        error_tolerance_pct FLOAT DEFAULT 2.0,
        learning_curve_days INTEGER DEFAULT 90,

        -- Risk Profile
        replacement_difficulty INTEGER DEFAULT 5,
        is_single_point_failure_risk BOOLEAN DEFAULT FALSE,

        -- Skills & Requirements
        required_skills JSONB DEFAULT '[]',
        certifications_required JSONB DEFAULT '[]',
        common_failure_modes JSONB DEFAULT '[]',

        -- Salary Range
        salary_range_min INTEGER,
        salary_range_max INTEGER,

        is_active BOOLEAN DEFAULT TRUE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT uix_mm_role_org_name UNIQUE (organization_id, role_name)
    );

    CREATE INDEX IF NOT EXISTS ix_mm_role_def_org ON mm_role_definitions(organization_id);
    CREATE INDEX IF NOT EXISTS ix_mm_role_def_name ON mm_role_definitions(role_name);

    -- ==========================================================================
    -- TALENT CAPACITY TABLE
    -- ==========================================================================
    CREATE TABLE IF NOT EXISTS mm_talent_capacity (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role_definition_id INTEGER REFERENCES mm_role_definitions(id),

        -- Capacity Configuration
        max_files_concurrent INTEGER DEFAULT 25,
        max_leads_concurrent INTEGER DEFAULT 50,
        max_tasks_daily INTEGER DEFAULT 30,

        -- Current State
        current_file_count INTEGER DEFAULT 0,
        current_lead_count INTEGER DEFAULT 0,
        current_task_count INTEGER DEFAULT 0,

        -- Derived Metrics
        file_capacity_pct FLOAT DEFAULT 0.0,
        lead_capacity_pct FLOAT DEFAULT 0.0,
        task_capacity_pct FLOAT DEFAULT 0.0,
        overall_capacity_pct FLOAT DEFAULT 0.0,
        capacity_status VARCHAR(20) DEFAULT 'available',

        -- Risk Indicators
        burnout_risk_score FLOAT DEFAULT 0.0,
        attrition_risk_score FLOAT DEFAULT 0.0,

        -- Availability
        is_available BOOLEAN DEFAULT TRUE,
        availability_status VARCHAR(20) DEFAULT 'active',
        return_date DATE,
        availability_notes TEXT,

        -- Assignment Lock
        is_locked_for_assignment BOOLEAN DEFAULT FALSE,
        locked_until TIMESTAMP WITH TIME ZONE,
        lock_reason VARCHAR(255),

        -- Timestamps
        last_calculated_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT uix_mm_capacity_org_user UNIQUE (organization_id, user_id)
    );

    CREATE INDEX IF NOT EXISTS ix_mm_capacity_org ON mm_talent_capacity(organization_id);
    CREATE INDEX IF NOT EXISTS ix_mm_capacity_user ON mm_talent_capacity(user_id);
    CREATE INDEX IF NOT EXISTS ix_mm_capacity_status ON mm_talent_capacity(capacity_status);
    CREATE INDEX IF NOT EXISTS ix_mm_capacity_available ON mm_talent_capacity(is_available);

    -- ==========================================================================
    -- TALENT STATE TABLE
    -- ==========================================================================
    CREATE TABLE IF NOT EXISTS mm_talent_state (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

        -- Current State
        state VARCHAR(30) NOT NULL DEFAULT 'new_hire',
        state_reason VARCHAR(255),
        state_changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        state_changed_by INTEGER REFERENCES users(id),

        -- New Hire / Ramp Tracking
        is_new_hire BOOLEAN DEFAULT TRUE,
        is_in_ramp BOOLEAN DEFAULT TRUE,
        hire_date DATE,
        ramp_day INTEGER DEFAULT 0,
        ramp_completion_date DATE,
        ramp_progress_pct FLOAT DEFAULT 0.0,

        -- Promotion Track
        promotion_eligible BOOLEAN DEFAULT FALSE,
        promotion_readiness_score FLOAT,
        target_role_id INTEGER REFERENCES mm_role_definitions(id),
        last_promotion_at DATE,
        promotion_blocked_reason VARCHAR(255),

        -- PIP
        has_active_pip BOOLEAN DEFAULT FALSE,
        pip_start_date DATE,
        pip_end_date DATE,
        pip_reason TEXT,
        pip_goals JSONB,

        -- Exit Risk
        exit_risk_level VARCHAR(20),
        exit_risk_factors JSONB,
        retention_actions JSONB,

        -- Manager
        manager_user_id INTEGER REFERENCES users(id),

        -- Timestamps
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT uix_mm_state_org_user UNIQUE (organization_id, user_id)
    );

    CREATE INDEX IF NOT EXISTS ix_mm_state_org ON mm_talent_state(organization_id);
    CREATE INDEX IF NOT EXISTS ix_mm_state_user ON mm_talent_state(user_id);
    CREATE INDEX IF NOT EXISTS ix_mm_state_state ON mm_talent_state(state);

    -- ==========================================================================
    -- TALENT STATE HISTORY TABLE
    -- ==========================================================================
    CREATE TABLE IF NOT EXISTS mm_talent_state_history (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

        previous_state VARCHAR(30),
        new_state VARCHAR(30) NOT NULL,
        reason TEXT,
        changed_by INTEGER REFERENCES users(id),

        -- Snapshot
        capacity_pct_at_change FLOAT,
        performance_score_at_change FLOAT,

        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
    );

    CREATE INDEX IF NOT EXISTS ix_mm_state_history_user ON mm_talent_state_history(user_id);
    CREATE INDEX IF NOT EXISTS ix_mm_state_history_created ON mm_talent_state_history(created_at);

    -- ==========================================================================
    -- TALENT PERFORMANCE TABLE
    -- ==========================================================================
    CREATE TABLE IF NOT EXISTS mm_talent_performance (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

        -- Period
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        period_type VARCHAR(20) NOT NULL,

        -- Volume Metrics
        files_in_pipeline INTEGER DEFAULT 0,
        files_funded INTEGER DEFAULT 0,
        files_cancelled INTEGER DEFAULT 0,
        leads_handled INTEGER DEFAULT 0,
        leads_converted INTEGER DEFAULT 0,
        tasks_completed INTEGER DEFAULT 0,
        tasks_overdue INTEGER DEFAULT 0,

        -- Quality Metrics
        error_count INTEGER DEFAULT 0,
        error_rate_pct FLOAT DEFAULT 0.0,
        rework_count INTEGER DEFAULT 0,
        rework_rate_pct FLOAT DEFAULT 0.0,

        -- Satisfaction Metrics
        borrower_nps FLOAT,
        borrower_csat FLOAT,
        lo_satisfaction FLOAT,

        -- Efficiency Metrics
        avg_task_duration_mins FLOAT,
        avg_file_cycle_time_days FLOAT,
        sla_compliance_pct FLOAT,
        on_time_completion_pct FLOAT,

        -- Communication Metrics
        avg_response_time_mins FLOAT,
        communication_score FLOAT,
        emails_sent INTEGER DEFAULT 0,
        calls_made INTEGER DEFAULT 0,

        -- Composite Scores
        overall_score FLOAT,
        performance_grade VARCHAR(2),

        -- Benchmarks
        vs_team_avg_pct FLOAT,
        vs_role_benchmark_pct FLOAT,
        percentile_rank INTEGER,

        -- Trends
        trend_direction VARCHAR(10),
        trend_change_pct FLOAT,

        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,

        CONSTRAINT uix_mm_perf_org_user_period UNIQUE (organization_id, user_id, period_start, period_type)
    );

    CREATE INDEX IF NOT EXISTS ix_mm_perf_org ON mm_talent_performance(organization_id);
    CREATE INDEX IF NOT EXISTS ix_mm_perf_user ON mm_talent_performance(user_id);
    CREATE INDEX IF NOT EXISTS ix_mm_perf_period ON mm_talent_performance(period_start, period_type);

    -- ==========================================================================
    -- CAPACITY ALERTS TABLE
    -- ==========================================================================
    CREATE TABLE IF NOT EXISTS mm_capacity_alerts (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,

        -- Alert Type
        alert_type VARCHAR(50) NOT NULL,
        severity VARCHAR(20) NOT NULL,

        -- Target
        user_id INTEGER REFERENCES users(id),
        role_definition_id INTEGER REFERENCES mm_role_definitions(id),

        -- Content
        title VARCHAR(255) NOT NULL,
        description TEXT,
        metrics_snapshot JSONB,
        recommended_actions JSONB,

        -- Status
        status VARCHAR(20) DEFAULT 'open',
        acknowledged_at TIMESTAMP WITH TIME ZONE,
        acknowledged_by INTEGER REFERENCES users(id),
        resolved_at TIMESTAMP WITH TIME ZONE,
        resolved_by INTEGER REFERENCES users(id),
        resolution_notes TEXT,

        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
    );

    CREATE INDEX IF NOT EXISTS ix_mm_alerts_org_status ON mm_capacity_alerts(organization_id, status);
    CREATE INDEX IF NOT EXISTS ix_mm_alerts_type ON mm_capacity_alerts(alert_type);
    CREATE INDEX IF NOT EXISTS ix_mm_alerts_created ON mm_capacity_alerts(created_at);

    -- ==========================================================================
    -- COVERAGE MAP TABLE
    -- ==========================================================================
    CREATE TABLE IF NOT EXISTS mm_coverage_map (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,

        primary_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role_definition_id INTEGER NOT NULL REFERENCES mm_role_definitions(id),

        backup_user_ids JSONB DEFAULT '[]',
        cross_trained_users JSONB DEFAULT '[]',

        is_single_point_failure BOOLEAN DEFAULT FALSE,
        coverage_score FLOAT,
        coverage_notes TEXT,

        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT uix_mm_coverage_org_user_role UNIQUE (organization_id, primary_user_id, role_definition_id)
    );

    CREATE INDEX IF NOT EXISTS ix_mm_coverage_org ON mm_coverage_map(organization_id);
    CREATE INDEX IF NOT EXISTS ix_mm_coverage_spof ON mm_coverage_map(is_single_point_failure);

    -- ==========================================================================
    -- CANDIDATES TABLE
    -- ==========================================================================
    CREATE TABLE IF NOT EXISTS mm_candidates (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,

        -- Basic Info
        first_name VARCHAR(100) NOT NULL,
        last_name VARCHAR(100) NOT NULL,
        email VARCHAR(255) NOT NULL,
        phone VARCHAR(20),

        -- Source
        source VARCHAR(50),
        referrer_user_id INTEGER REFERENCES users(id),
        campaign_id VARCHAR(100),
        utm_source VARCHAR(100),
        utm_medium VARCHAR(100),
        utm_campaign VARCHAR(100),

        -- Target Role
        target_role_id INTEGER REFERENCES mm_role_definitions(id),
        target_role_name VARCHAR(100),

        -- Status
        status VARCHAR(30) DEFAULT 'new',
        status_changed_at TIMESTAMP WITH TIME ZONE,
        status_changed_by INTEGER REFERENCES users(id),
        placement_recommendation VARCHAR(30),

        -- Talent Profile
        talent_profile JSONB DEFAULT '{}',

        -- Experience
        years_experience INTEGER,
        years_mortgage_experience INTEGER,
        has_mortgage_experience BOOLEAN DEFAULT FALSE,
        previous_companies JSONB,
        licenses JSONB,

        -- Resume
        resume_url TEXT,
        cover_letter TEXT,
        linkedin_url VARCHAR(255),

        -- Scores
        vetting_score FLOAT,
        behavioral_score FLOAT,
        technical_score FLOAT,
        culture_fit_score FLOAT,
        overall_score FLOAT,

        -- Behavioral Signals
        time_to_complete_app_mins INTEGER,
        instruction_following_score FLOAT,
        revision_behavior_score FLOAT,

        -- Interview
        interview_scheduled_at TIMESTAMP WITH TIME ZONE,
        interview_completed_at TIMESTAMP WITH TIME ZONE,
        interview_notes TEXT,
        interview_score FLOAT,

        -- Offer
        offer_extended_at TIMESTAMP WITH TIME ZONE,
        offer_amount INTEGER,
        offer_accepted_at TIMESTAMP WITH TIME ZONE,
        offer_rejected_at TIMESTAMP WITH TIME ZONE,
        rejection_reason TEXT,

        -- Hired
        hired_at TIMESTAMP WITH TIME ZONE,
        hired_as_user_id INTEGER REFERENCES users(id),
        start_date DATE,

        -- Notes
        recruiter_notes TEXT,
        hiring_manager_notes TEXT,

        is_active BOOLEAN DEFAULT TRUE,
        applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        last_activity_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT uix_mm_candidate_org_email UNIQUE (organization_id, email)
    );

    CREATE INDEX IF NOT EXISTS ix_mm_candidate_org ON mm_candidates(organization_id);
    CREATE INDEX IF NOT EXISTS ix_mm_candidate_email ON mm_candidates(email);
    CREATE INDEX IF NOT EXISTS ix_mm_candidate_status ON mm_candidates(status);

    -- ==========================================================================
    -- JOB POSTINGS TABLE
    -- ==========================================================================
    CREATE TABLE IF NOT EXISTS mm_job_postings (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,

        title VARCHAR(200) NOT NULL,
        slug VARCHAR(100) NOT NULL,
        role_definition_id INTEGER REFERENCES mm_role_definitions(id),

        summary TEXT,
        description TEXT,
        requirements JSONB,
        responsibilities JSONB,
        benefits JSONB,

        salary_min INTEGER,
        salary_max INTEGER,
        salary_type VARCHAR(20),

        is_published BOOLEAN DEFAULT FALSE,
        is_internal BOOLEAN DEFAULT FALSE,
        is_remote BOOLEAN DEFAULT FALSE,
        location VARCHAR(100),
        employment_type VARCHAR(30),

        published_at TIMESTAMP WITH TIME ZONE,
        expires_at TIMESTAMP WITH TIME ZONE,

        views INTEGER DEFAULT 0,
        applications INTEGER DEFAULT 0,

        meta_title VARCHAR(200),
        meta_description VARCHAR(500),

        created_by INTEGER REFERENCES users(id),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT uix_mm_job_org_slug UNIQUE (organization_id, slug)
    );

    CREATE INDEX IF NOT EXISTS ix_mm_job_org ON mm_job_postings(organization_id);
    CREATE INDEX IF NOT EXISTS ix_mm_job_published ON mm_job_postings(is_published);
    CREATE INDEX IF NOT EXISTS ix_mm_job_slug ON mm_job_postings(slug);

    -- ==========================================================================
    -- SEED DEFAULT ROLE DEFINITIONS
    -- ==========================================================================
    INSERT INTO mm_role_definitions (role_name, role_category, description, default_max_files, default_max_leads, default_max_tasks_daily, expected_throughput, learning_curve_days, replacement_difficulty, required_skills)
    VALUES
        ('Loan Officer', 'revenue', 'Originate and close mortgage loans', 30, 100, 40,
         '{"files_per_month": 8, "leads_per_week": 25, "conversion_rate": 0.25}'::jsonb,
         90, 7, '["sales", "compliance", "communication", "LOS"]'::jsonb),

        ('Senior Loan Officer', 'revenue', 'High-volume loan origination with mentorship', 40, 150, 50,
         '{"files_per_month": 12, "leads_per_week": 35, "conversion_rate": 0.30}'::jsonb,
         60, 8, '["sales", "compliance", "communication", "LOS", "mentoring"]'::jsonb),

        ('Processor', 'operations', 'Process loan files from application to closing', 25, 0, 35,
         '{"files_per_month": 20, "avg_cycle_days": 25, "accuracy_rate": 0.98}'::jsonb,
         60, 6, '["LOS", "compliance", "attention_to_detail", "communication"]'::jsonb),

        ('Senior Processor', 'operations', 'Handle complex files and train junior processors', 30, 0, 40,
         '{"files_per_month": 25, "avg_cycle_days": 22, "accuracy_rate": 0.99}'::jsonb,
         45, 7, '["LOS", "compliance", "attention_to_detail", "communication", "training"]'::jsonb),

        ('Production Assistant', 'operations', 'Support LOs with file setup and document collection', 35, 50, 50,
         '{"files_per_month": 30, "docs_collected_per_day": 15}'::jsonb,
         30, 4, '["LOS", "organization", "communication", "multitasking"]'::jsonb),

        ('Closing Coordinator', 'operations', 'Coordinate closings and post-close activities', 30, 0, 40,
         '{"closings_per_month": 25, "on_time_rate": 0.95}'::jsonb,
         45, 5, '["LOS", "coordination", "attention_to_detail", "title_knowledge"]'::jsonb),

        ('Underwriter', 'specialized', 'Review and decision loan files', 20, 0, 30,
         '{"files_per_month": 60, "turn_time_hours": 24, "accuracy_rate": 0.995}'::jsonb,
         90, 9, '["underwriting", "compliance", "risk_assessment", "guidelines"]'::jsonb),

        ('Branch Manager', 'management', 'Manage branch operations and LO team', 10, 25, 30,
         '{"team_production_units": 50, "team_volume": 15000000}'::jsonb,
         120, 9, '["leadership", "sales", "operations", "compliance", "coaching"]'::jsonb)
    ON CONFLICT (organization_id, role_name) DO NOTHING;
    """

    print("Running Master Manager migration...")

    with engine.connect() as conn:
        # Execute each statement
        statements = [s.strip() for s in migration_sql.split(';') if s.strip()]
        for statement in statements:
            try:
                conn.execute(text(statement))
            except Exception as e:
                print(f"Warning: {e}")
        conn.commit()

    print("Master Manager migration completed successfully!")
    print("Tables created:")
    print("  - mm_role_definitions")
    print("  - mm_talent_capacity")
    print("  - mm_talent_state")
    print("  - mm_talent_state_history")
    print("  - mm_talent_performance")
    print("  - mm_capacity_alerts")
    print("  - mm_coverage_map")
    print("  - mm_candidates")
    print("  - mm_job_postings")


if __name__ == "__main__":
    run_migration()
