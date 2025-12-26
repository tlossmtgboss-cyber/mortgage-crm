-- Conversation Intelligence Platform Database Schema
-- Enables call recording, transcription, QA scoring, real-time assist, and coaching

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- Call Recordings (main table for recorded calls)
CREATE TABLE IF NOT EXISTS ci_call_recordings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Call identification
    external_call_id VARCHAR(100) UNIQUE,  -- From phone system
    call_type VARCHAR(20) NOT NULL DEFAULT 'inbound',  -- inbound, outbound, internal
    direction VARCHAR(10) NOT NULL DEFAULT 'inbound',  -- inbound, outbound

    -- Participants
    agent_user_id INTEGER REFERENCES users(id),  -- Loan officer/agent
    contact_id INTEGER,  -- Borrower/contact (references contacts table)
    loan_id INTEGER,  -- Associated loan if applicable
    lead_id INTEGER,  -- Associated lead if applicable

    -- Call metadata
    phone_from VARCHAR(20),
    phone_to VARCHAR(20),
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,

    -- Recording info
    recording_url TEXT,
    recording_storage_path TEXT,  -- S3 path
    recording_size_bytes BIGINT,
    recording_format VARCHAR(20) DEFAULT 'mp3',

    -- Processing status
    status VARCHAR(30) NOT NULL DEFAULT 'recorded',  -- recorded, processing, transcribed, analyzed, failed
    transcription_status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    analysis_status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    qa_status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed

    -- Metadata
    metadata JSONB DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_recordings_agent ON ci_call_recordings(agent_user_id);
CREATE INDEX IF NOT EXISTS idx_ci_recordings_contact ON ci_call_recordings(contact_id);
CREATE INDEX IF NOT EXISTS idx_ci_recordings_loan ON ci_call_recordings(loan_id);
CREATE INDEX IF NOT EXISTS idx_ci_recordings_started ON ci_call_recordings(started_at);
CREATE INDEX IF NOT EXISTS idx_ci_recordings_status ON ci_call_recordings(status);


-- Call Transcriptions
CREATE TABLE IF NOT EXISTS ci_call_transcriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recording_id UUID NOT NULL REFERENCES ci_call_recordings(id) ON DELETE CASCADE,

    -- Transcription provider info
    provider VARCHAR(30) NOT NULL DEFAULT 'deepgram',  -- deepgram, assemblyai, whisper
    provider_job_id VARCHAR(100),
    model_version VARCHAR(50),

    -- Full transcription
    full_text TEXT,
    confidence_score NUMERIC(5,4),  -- 0.0000 to 1.0000

    -- Transcription metadata
    language VARCHAR(10) DEFAULT 'en',
    word_count INTEGER,
    duration_seconds NUMERIC(10,2),

    -- Processing info
    processing_time_ms INTEGER,
    cost_cents INTEGER,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_transcriptions_recording ON ci_call_transcriptions(recording_id);


-- Transcription Segments (speaker-diarized segments)
CREATE TABLE IF NOT EXISTS ci_transcription_segments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transcription_id UUID NOT NULL REFERENCES ci_call_transcriptions(id) ON DELETE CASCADE,

    -- Segment info
    segment_index INTEGER NOT NULL,
    speaker VARCHAR(20) NOT NULL,  -- agent, customer, unknown
    speaker_label VARCHAR(50),  -- SPEAKER_0, SPEAKER_1, etc.

    -- Timing
    start_time_ms INTEGER NOT NULL,
    end_time_ms INTEGER NOT NULL,

    -- Content
    text TEXT NOT NULL,
    confidence NUMERIC(5,4),

    -- Word-level timing (optional detailed data)
    words JSONB,  -- Array of {word, start_ms, end_ms, confidence}

    -- Detected info
    sentiment VARCHAR(20),  -- positive, neutral, negative
    intent VARCHAR(50),  -- question, statement, objection, agreement, etc.

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_segments_transcription ON ci_transcription_segments(transcription_id);
CREATE INDEX IF NOT EXISTS idx_ci_segments_speaker ON ci_transcription_segments(speaker);


-- =============================================================================
-- ANALYSIS TABLES
-- =============================================================================

-- Call Analysis (AI-generated insights)
CREATE TABLE IF NOT EXISTS ci_call_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recording_id UUID NOT NULL REFERENCES ci_call_recordings(id) ON DELETE CASCADE,

    -- Analysis provider
    analysis_model VARCHAR(50) DEFAULT 'claude-3-sonnet',
    analysis_version VARCHAR(20) DEFAULT '1.0',

    -- Summary
    summary TEXT,
    summary_bullets JSONB,  -- Array of key points

    -- Call outcome
    call_disposition VARCHAR(50),  -- completed, voicemail, callback_scheduled, etc.
    call_purpose VARCHAR(50),  -- rate_inquiry, application_followup, document_request, etc.
    call_outcome VARCHAR(50),  -- successful, needs_followup, escalation_required, etc.

    -- Extracted information
    topics_discussed JSONB,  -- Array of topics with confidence
    action_items JSONB,  -- Array of {item, assignee, due_date}
    follow_ups_needed JSONB,  -- Array of follow-up items

    -- Customer insights
    customer_sentiment VARCHAR(20),  -- positive, neutral, negative, mixed
    customer_intent VARCHAR(50),  -- ready_to_proceed, exploring_options, concerned, etc.
    objections_raised JSONB,  -- Array of objections detected
    questions_asked JSONB,  -- Array of customer questions

    -- Agent performance insights
    agent_performance JSONB,  -- Detailed performance metrics
    coaching_opportunities JSONB,  -- Areas for improvement

    -- Compliance checks
    compliance_flags JSONB,  -- Any compliance concerns detected
    required_disclosures_given JSONB,  -- Which required disclosures were given

    -- Mortgage-specific extraction
    loan_details_discussed JSONB,  -- Rates, terms, amounts discussed
    property_details JSONB,  -- Property info mentioned
    borrower_info_collected JSONB,  -- Info collected during call

    -- Processing metadata
    processing_time_ms INTEGER,
    tokens_used INTEGER,
    cost_cents INTEGER,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_analyses_recording ON ci_call_analyses(recording_id);
CREATE INDEX IF NOT EXISTS idx_ci_analyses_disposition ON ci_call_analyses(call_disposition);


-- =============================================================================
-- QA SCORING TABLES
-- =============================================================================

-- QA Rubrics (scoring criteria templates)
CREATE TABLE IF NOT EXISTS ci_qa_rubrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Rubric identification
    name VARCHAR(100) NOT NULL,
    description TEXT,
    category VARCHAR(50) NOT NULL,  -- greeting, discovery, presentation, objection_handling, closing, compliance

    -- Scoring configuration
    max_points INTEGER NOT NULL DEFAULT 10,
    weight NUMERIC(5,2) NOT NULL DEFAULT 1.0,  -- Weight in overall score

    -- Scoring criteria
    criteria JSONB NOT NULL,  -- Detailed scoring criteria
    scoring_guide TEXT,  -- How to score this rubric

    -- Auto-scoring configuration
    auto_score_enabled BOOLEAN DEFAULT false,
    auto_score_keywords JSONB,  -- Keywords/phrases to detect
    auto_score_rules JSONB,  -- Rules for automatic scoring

    -- Applicability
    call_types TEXT[] DEFAULT '{inbound,outbound}',  -- Which call types this applies to
    required BOOLEAN DEFAULT false,  -- Is this a required rubric

    -- Status
    is_active BOOLEAN DEFAULT true,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_rubrics_category ON ci_qa_rubrics(category);
CREATE INDEX IF NOT EXISTS idx_ci_rubrics_active ON ci_qa_rubrics(is_active);


-- QA Scorecards (per-call scoring)
CREATE TABLE IF NOT EXISTS ci_qa_scorecards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recording_id UUID NOT NULL REFERENCES ci_call_recordings(id) ON DELETE CASCADE,

    -- Scoring metadata
    scored_by INTEGER REFERENCES users(id),  -- NULL if auto-scored
    scoring_method VARCHAR(20) NOT NULL DEFAULT 'auto',  -- auto, manual, hybrid

    -- Overall scores
    total_score NUMERIC(6,2),
    max_possible_score NUMERIC(6,2),
    percentage_score NUMERIC(5,2),
    grade VARCHAR(2),  -- A, B, C, D, F

    -- Category scores
    category_scores JSONB,  -- {category: {score, max, percentage}}

    -- Flags and issues
    critical_failures JSONB,  -- Any critical failures (auto-fail items)
    improvement_areas JSONB,  -- Areas needing improvement
    strengths JSONB,  -- Areas of strength

    -- Review status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, in_review, completed, disputed
    reviewed_at TIMESTAMP WITH TIME ZONE,
    reviewer_id INTEGER REFERENCES users(id),

    -- Agent acknowledgment
    agent_acknowledged BOOLEAN DEFAULT false,
    agent_acknowledged_at TIMESTAMP WITH TIME ZONE,
    agent_comments TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_scorecards_recording ON ci_qa_scorecards(recording_id);
CREATE INDEX IF NOT EXISTS idx_ci_scorecards_scored_by ON ci_qa_scorecards(scored_by);
CREATE INDEX IF NOT EXISTS idx_ci_scorecards_grade ON ci_qa_scorecards(grade);


-- QA Scorecard Items (individual rubric scores)
CREATE TABLE IF NOT EXISTS ci_qa_scorecard_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scorecard_id UUID NOT NULL REFERENCES ci_qa_scorecards(id) ON DELETE CASCADE,
    rubric_id UUID NOT NULL REFERENCES ci_qa_rubrics(id),

    -- Score
    score NUMERIC(5,2),
    max_score NUMERIC(5,2),
    percentage NUMERIC(5,2),

    -- Evidence
    evidence_text TEXT,  -- Transcript excerpt supporting score
    evidence_timestamps JSONB,  -- [{start_ms, end_ms}] for relevant parts

    -- Scoring details
    auto_score NUMERIC(5,2),  -- Score from auto-scoring
    manual_score NUMERIC(5,2),  -- Score from manual review
    final_score NUMERIC(5,2),  -- Final determined score

    -- Feedback
    evaluator_notes TEXT,
    improvement_suggestions TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_scorecard_items_scorecard ON ci_qa_scorecard_items(scorecard_id);
CREATE INDEX IF NOT EXISTS idx_ci_scorecard_items_rubric ON ci_qa_scorecard_items(rubric_id);


-- =============================================================================
-- REAL-TIME ASSIST TABLES
-- =============================================================================

-- Real-Time Sessions
CREATE TABLE IF NOT EXISTS ci_realtime_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recording_id UUID REFERENCES ci_call_recordings(id),  -- May be created before recording

    -- Session info
    agent_user_id INTEGER NOT NULL REFERENCES users(id),
    call_id VARCHAR(100),  -- External call ID

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, completed, disconnected
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP WITH TIME ZONE,

    -- WebSocket connection
    connection_id VARCHAR(100),

    -- Metadata
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_realtime_agent ON ci_realtime_sessions(agent_user_id);
CREATE INDEX IF NOT EXISTS idx_ci_realtime_status ON ci_realtime_sessions(status);


-- Real-Time Suggestions (coaching prompts during live calls)
CREATE TABLE IF NOT EXISTS ci_realtime_suggestions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES ci_realtime_sessions(id) ON DELETE CASCADE,

    -- Suggestion info
    suggestion_type VARCHAR(30) NOT NULL,  -- tip, warning, script, objection_response, compliance_alert
    priority VARCHAR(10) DEFAULT 'normal',  -- low, normal, high, critical

    -- Content
    title VARCHAR(200),
    content TEXT NOT NULL,

    -- Context
    triggered_by TEXT,  -- What triggered this suggestion
    trigger_timestamp_ms INTEGER,

    -- Agent interaction
    was_displayed BOOLEAN DEFAULT false,
    displayed_at TIMESTAMP WITH TIME ZONE,
    was_dismissed BOOLEAN DEFAULT false,
    was_helpful BOOLEAN,  -- Agent feedback

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_suggestions_session ON ci_realtime_suggestions(session_id);
CREATE INDEX IF NOT EXISTS idx_ci_suggestions_type ON ci_realtime_suggestions(suggestion_type);


-- =============================================================================
-- COACHING TABLES
-- =============================================================================

-- Coaching Clips (excerpts from calls for training)
CREATE TABLE IF NOT EXISTS ci_coaching_clips (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recording_id UUID NOT NULL REFERENCES ci_call_recordings(id) ON DELETE CASCADE,

    -- Clip info
    title VARCHAR(200) NOT NULL,
    description TEXT,

    -- Timing
    start_time_ms INTEGER NOT NULL,
    end_time_ms INTEGER NOT NULL,

    -- Content
    transcript_excerpt TEXT,

    -- Classification
    clip_type VARCHAR(30) NOT NULL,  -- example, improvement, compliance_issue, objection_handled
    skill_tags TEXT[] DEFAULT '{}',  -- Skills demonstrated or needed
    rubric_id UUID REFERENCES ci_qa_rubrics(id),  -- Related rubric if applicable

    -- Usage
    is_public BOOLEAN DEFAULT false,  -- Shared with team
    view_count INTEGER DEFAULT 0,

    -- Creator
    created_by INTEGER REFERENCES users(id),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_clips_recording ON ci_coaching_clips(recording_id);
CREATE INDEX IF NOT EXISTS idx_ci_clips_type ON ci_coaching_clips(clip_type);
CREATE INDEX IF NOT EXISTS idx_ci_clips_creator ON ci_coaching_clips(created_by);


-- Coaching Assignments
CREATE TABLE IF NOT EXISTS ci_coaching_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Assignment target
    agent_user_id INTEGER NOT NULL REFERENCES users(id),
    assigned_by UUID NOT NULL REFERENCES users(id),

    -- Content
    title VARCHAR(200) NOT NULL,
    description TEXT,
    assignment_type VARCHAR(30) NOT NULL,  -- review_call, watch_clip, practice_skill, complete_quiz

    -- Related items
    recording_id UUID REFERENCES ci_call_recordings(id),
    clip_id UUID REFERENCES ci_coaching_clips(id),
    rubric_id UUID REFERENCES ci_qa_rubrics(id),

    -- Due date
    due_date TIMESTAMP WITH TIME ZONE,

    -- Status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, in_progress, completed, overdue

    -- Completion
    completed_at TIMESTAMP WITH TIME ZONE,
    agent_notes TEXT,

    -- Manager review
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    review_notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_assignments_agent ON ci_coaching_assignments(agent_user_id);
CREATE INDEX IF NOT EXISTS idx_ci_assignments_assigned_by ON ci_coaching_assignments(assigned_by);
CREATE INDEX IF NOT EXISTS idx_ci_assignments_status ON ci_coaching_assignments(status);
CREATE INDEX IF NOT EXISTS idx_ci_assignments_due ON ci_coaching_assignments(due_date);


-- Coaching Comments (on calls or clips)
CREATE TABLE IF NOT EXISTS ci_coaching_comments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Comment target (one of these)
    recording_id UUID REFERENCES ci_call_recordings(id) ON DELETE CASCADE,
    clip_id UUID REFERENCES ci_coaching_clips(id) ON DELETE CASCADE,
    scorecard_id UUID REFERENCES ci_qa_scorecards(id) ON DELETE CASCADE,

    -- Comment info
    user_id UUID NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,

    -- Timestamp reference (optional)
    timestamp_ms INTEGER,  -- Where in the call this comment refers to

    -- Threading
    parent_comment_id UUID REFERENCES ci_coaching_comments(id),

    -- Visibility
    is_private BOOLEAN DEFAULT false,  -- Only visible to author and managers

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_comments_recording ON ci_coaching_comments(recording_id);
CREATE INDEX IF NOT EXISTS idx_ci_comments_clip ON ci_coaching_comments(clip_id);
CREATE INDEX IF NOT EXISTS idx_ci_comments_user ON ci_coaching_comments(user_id);


-- =============================================================================
-- COMPLIANCE MONITORING TABLES
-- =============================================================================

-- Compliance Rules
CREATE TABLE IF NOT EXISTS ci_compliance_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Rule identification
    name VARCHAR(100) NOT NULL,
    description TEXT,
    category VARCHAR(50) NOT NULL,  -- disclosure, fair_lending, privacy, state_specific

    -- Rule definition
    rule_type VARCHAR(30) NOT NULL,  -- keyword_required, keyword_prohibited, pattern_match
    rule_config JSONB NOT NULL,  -- Rule-specific configuration

    -- Severity
    severity VARCHAR(20) DEFAULT 'medium',  -- low, medium, high, critical
    is_auto_fail BOOLEAN DEFAULT false,  -- Does violation auto-fail QA

    -- Applicability
    states TEXT[],  -- Which states this applies to (null = all)
    loan_types TEXT[],  -- Which loan types (null = all)
    call_types TEXT[] DEFAULT '{inbound,outbound}',

    -- Status
    is_active BOOLEAN DEFAULT true,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_compliance_rules_category ON ci_compliance_rules(category);
CREATE INDEX IF NOT EXISTS idx_ci_compliance_rules_active ON ci_compliance_rules(is_active);


-- Compliance Violations (detected issues)
CREATE TABLE IF NOT EXISTS ci_compliance_violations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recording_id UUID NOT NULL REFERENCES ci_call_recordings(id) ON DELETE CASCADE,
    rule_id UUID NOT NULL REFERENCES ci_compliance_rules(id),

    -- Violation details
    violation_type VARCHAR(50) NOT NULL,
    description TEXT,
    evidence_text TEXT,
    timestamp_ms INTEGER,

    -- Severity
    severity VARCHAR(20) NOT NULL,

    -- Resolution
    status VARCHAR(20) DEFAULT 'open',  -- open, reviewed, false_positive, resolved
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_violations_recording ON ci_compliance_violations(recording_id);
CREATE INDEX IF NOT EXISTS idx_ci_violations_rule ON ci_compliance_violations(rule_id);
CREATE INDEX IF NOT EXISTS idx_ci_violations_status ON ci_compliance_violations(status);


-- =============================================================================
-- METRICS AND REPORTING
-- =============================================================================

-- Agent Call Metrics (aggregated stats)
CREATE TABLE IF NOT EXISTS ci_agent_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_user_id INTEGER NOT NULL REFERENCES users(id),

    -- Time period
    period_type VARCHAR(10) NOT NULL,  -- daily, weekly, monthly
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,

    -- Call volume
    total_calls INTEGER DEFAULT 0,
    inbound_calls INTEGER DEFAULT 0,
    outbound_calls INTEGER DEFAULT 0,

    -- Duration
    total_talk_time_seconds INTEGER DEFAULT 0,
    avg_call_duration_seconds INTEGER DEFAULT 0,

    -- QA scores
    calls_scored INTEGER DEFAULT 0,
    avg_qa_score NUMERIC(5,2),
    calls_grade_a INTEGER DEFAULT 0,
    calls_grade_b INTEGER DEFAULT 0,
    calls_grade_c INTEGER DEFAULT 0,
    calls_grade_d INTEGER DEFAULT 0,
    calls_grade_f INTEGER DEFAULT 0,

    -- Outcomes
    successful_calls INTEGER DEFAULT 0,
    callbacks_scheduled INTEGER DEFAULT 0,
    escalations INTEGER DEFAULT 0,

    -- Compliance
    compliance_violations INTEGER DEFAULT 0,

    -- Coaching
    coaching_assignments_completed INTEGER DEFAULT 0,
    coaching_assignments_pending INTEGER DEFAULT 0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(agent_user_id, period_type, period_start)
);

CREATE INDEX IF NOT EXISTS idx_ci_metrics_agent ON ci_agent_metrics(agent_user_id);
CREATE INDEX IF NOT EXISTS idx_ci_metrics_period ON ci_agent_metrics(period_type, period_start);


-- =============================================================================
-- AUDIT LOG (PARTITIONED)
-- =============================================================================

CREATE TABLE IF NOT EXISTS ci_audit_log (
    id UUID DEFAULT uuid_generate_v4(),

    -- What changed
    table_name VARCHAR(100) NOT NULL,
    record_id UUID NOT NULL,
    action VARCHAR(20) NOT NULL,  -- create, update, delete

    -- Who changed it
    user_id UUID,

    -- Change details
    old_values JSONB,
    new_values JSONB,

    -- Context
    ip_address INET,
    user_agent TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Create partitions for audit log (monthly)
CREATE TABLE IF NOT EXISTS ci_audit_log_2024_12 PARTITION OF ci_audit_log
    FOR VALUES FROM ('2024-12-01') TO ('2025-01-01');

CREATE TABLE IF NOT EXISTS ci_audit_log_2025_01 PARTITION OF ci_audit_log
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE IF NOT EXISTS ci_audit_log_2025_02 PARTITION OF ci_audit_log
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

CREATE TABLE IF NOT EXISTS ci_audit_log_2025_03 PARTITION OF ci_audit_log
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');

CREATE INDEX IF NOT EXISTS idx_ci_audit_table ON ci_audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_ci_audit_record ON ci_audit_log(record_id);
CREATE INDEX IF NOT EXISTS idx_ci_audit_user ON ci_audit_log(user_id);


-- =============================================================================
-- FUNCTIONS AND TRIGGERS
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION ci_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at triggers to all tables
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name LIKE 'ci_%'
        AND table_name NOT LIKE 'ci_audit%'
    LOOP
        EXECUTE format('
            DROP TRIGGER IF EXISTS %I ON %I;
            CREATE TRIGGER %I
            BEFORE UPDATE ON %I
            FOR EACH ROW EXECUTE FUNCTION ci_update_timestamp();
        ', 'trigger_' || t || '_updated_at', t, 'trigger_' || t || '_updated_at', t);
    END LOOP;
END;
$$ LANGUAGE plpgsql;


-- Function to calculate call duration
CREATE OR REPLACE FUNCTION ci_calculate_duration()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.ended_at IS NOT NULL AND NEW.started_at IS NOT NULL THEN
        NEW.duration_seconds = EXTRACT(EPOCH FROM (NEW.ended_at - NEW.started_at))::INTEGER;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_ci_recordings_duration
BEFORE INSERT OR UPDATE ON ci_call_recordings
FOR EACH ROW EXECUTE FUNCTION ci_calculate_duration();


-- Function to update agent metrics after scorecard completion
CREATE OR REPLACE FUNCTION ci_update_agent_metrics_on_scorecard()
RETURNS TRIGGER AS $$
DECLARE
    v_agent_id INTEGER;
    v_period_start DATE;
BEGIN
    -- Get agent ID from recording
    SELECT agent_user_id INTO v_agent_id
    FROM ci_call_recordings
    WHERE id = NEW.recording_id;

    IF v_agent_id IS NULL THEN
        RETURN NEW;
    END IF;

    -- Calculate period start (daily)
    v_period_start = CURRENT_DATE;

    -- Upsert metrics
    INSERT INTO ci_agent_metrics (
        agent_user_id, period_type, period_start, period_end,
        calls_scored, avg_qa_score,
        calls_grade_a, calls_grade_b, calls_grade_c, calls_grade_d, calls_grade_f
    )
    VALUES (
        v_agent_id, 'daily', v_period_start, v_period_start,
        1, NEW.percentage_score,
        CASE WHEN NEW.grade = 'A' THEN 1 ELSE 0 END,
        CASE WHEN NEW.grade = 'B' THEN 1 ELSE 0 END,
        CASE WHEN NEW.grade = 'C' THEN 1 ELSE 0 END,
        CASE WHEN NEW.grade = 'D' THEN 1 ELSE 0 END,
        CASE WHEN NEW.grade = 'F' THEN 1 ELSE 0 END
    )
    ON CONFLICT (agent_user_id, period_type, period_start)
    DO UPDATE SET
        calls_scored = ci_agent_metrics.calls_scored + 1,
        avg_qa_score = (ci_agent_metrics.avg_qa_score * ci_agent_metrics.calls_scored + NEW.percentage_score) / (ci_agent_metrics.calls_scored + 1),
        calls_grade_a = ci_agent_metrics.calls_grade_a + CASE WHEN NEW.grade = 'A' THEN 1 ELSE 0 END,
        calls_grade_b = ci_agent_metrics.calls_grade_b + CASE WHEN NEW.grade = 'B' THEN 1 ELSE 0 END,
        calls_grade_c = ci_agent_metrics.calls_grade_c + CASE WHEN NEW.grade = 'C' THEN 1 ELSE 0 END,
        calls_grade_d = ci_agent_metrics.calls_grade_d + CASE WHEN NEW.grade = 'D' THEN 1 ELSE 0 END,
        calls_grade_f = ci_agent_metrics.calls_grade_f + CASE WHEN NEW.grade = 'F' THEN 1 ELSE 0 END,
        updated_at = CURRENT_TIMESTAMP;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_ci_scorecard_metrics
AFTER INSERT ON ci_qa_scorecards
FOR EACH ROW
WHEN (NEW.status = 'completed')
EXECUTE FUNCTION ci_update_agent_metrics_on_scorecard();


-- =============================================================================
-- VIEWS
-- =============================================================================

-- View for call summary with analysis
CREATE OR REPLACE VIEW ci_call_summary AS
SELECT
    r.id,
    r.external_call_id,
    r.call_type,
    r.direction,
    r.agent_user_id,
    u.email as agent_email,
    u.first_name || ' ' || u.last_name as agent_name,
    r.contact_id,
    r.loan_id,
    r.phone_from,
    r.phone_to,
    r.started_at,
    r.ended_at,
    r.duration_seconds,
    r.status,
    a.summary,
    a.call_disposition,
    a.call_outcome,
    a.customer_sentiment,
    s.percentage_score as qa_score,
    s.grade as qa_grade,
    r.created_at
FROM ci_call_recordings r
LEFT JOIN users u ON r.agent_user_id = u.id
LEFT JOIN ci_call_analyses a ON r.id = a.recording_id
LEFT JOIN ci_qa_scorecards s ON r.id = s.recording_id
ORDER BY r.started_at DESC;


-- View for agent performance dashboard
CREATE OR REPLACE VIEW ci_agent_performance AS
SELECT
    u.id as agent_id,
    u.email,
    u.first_name || ' ' || u.last_name as name,
    m.period_type,
    m.period_start,
    m.total_calls,
    m.total_talk_time_seconds,
    m.avg_call_duration_seconds,
    m.calls_scored,
    m.avg_qa_score,
    m.calls_grade_a,
    m.calls_grade_b,
    m.calls_grade_c,
    m.calls_grade_d,
    m.calls_grade_f,
    m.compliance_violations,
    m.coaching_assignments_completed,
    m.coaching_assignments_pending
FROM users u
LEFT JOIN ci_agent_metrics m ON u.id = m.agent_user_id
WHERE m.period_type = 'daily'
ORDER BY m.period_start DESC, m.avg_qa_score DESC NULLS LAST;


-- View for coaching queue
CREATE OR REPLACE VIEW ci_coaching_queue AS
SELECT
    a.id,
    a.agent_user_id,
    u.first_name || ' ' || u.last_name as agent_name,
    a.title,
    a.assignment_type,
    a.due_date,
    a.status,
    a.assigned_by,
    assigner.first_name || ' ' || assigner.last_name as assigned_by_name,
    r.external_call_id as related_call_id,
    c.title as related_clip_title,
    a.created_at
FROM ci_coaching_assignments a
JOIN users u ON a.agent_user_id = u.id
JOIN users assigner ON a.assigned_by = assigner.id
LEFT JOIN ci_call_recordings r ON a.recording_id = r.id
LEFT JOIN ci_coaching_clips c ON a.clip_id = c.id
WHERE a.status IN ('pending', 'in_progress')
ORDER BY
    CASE a.status WHEN 'in_progress' THEN 0 ELSE 1 END,
    a.due_date ASC NULLS LAST,
    a.created_at ASC;
