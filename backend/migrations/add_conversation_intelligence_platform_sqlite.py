"""
Migration: Add Conversation Intelligence Platform Tables (SQLite-compatible)
Creates essential CI tables for local development with SQLite.

Usage:
    cd backend
    python migrations/add_conversation_intelligence_platform_sqlite.py
"""
import sys
sys.path.append('..')

from sqlalchemy import create_engine, text
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
engine = create_engine(DATABASE_URL)


def run_migration():
    """Create Conversation Intelligence tables (SQLite-compatible)"""

    sql_commands = [
        # =============================================================================
        # CORE TABLES
        # =============================================================================

        # Call Recordings (main table for recorded calls)
        """
        CREATE TABLE IF NOT EXISTS ci_call_recordings (
            id TEXT PRIMARY KEY,
            external_call_id VARCHAR(100) UNIQUE,
            call_type VARCHAR(20) NOT NULL DEFAULT 'inbound',
            direction VARCHAR(10) NOT NULL DEFAULT 'inbound',
            agent_user_id INTEGER,
            contact_id TEXT,
            loan_id TEXT,
            lead_id TEXT,
            phone_from VARCHAR(20),
            phone_to VARCHAR(20),
            started_at TIMESTAMP NOT NULL,
            ended_at TIMESTAMP,
            duration_seconds INTEGER,
            recording_url TEXT,
            recording_storage_path TEXT,
            recording_size_bytes BIGINT,
            recording_format VARCHAR(20) DEFAULT 'mp3',
            status VARCHAR(30) NOT NULL DEFAULT 'recorded',
            transcription_status VARCHAR(20) DEFAULT 'pending',
            analysis_status VARCHAR(20) DEFAULT 'pending',
            qa_status VARCHAR(20) DEFAULT 'pending',
            metadata TEXT DEFAULT '{}',
            tags TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_user_id) REFERENCES users(id)
        );
        """,

        # Call Transcriptions
        """
        CREATE TABLE IF NOT EXISTS ci_call_transcriptions (
            id TEXT PRIMARY KEY,
            recording_id TEXT NOT NULL,
            provider VARCHAR(30) NOT NULL DEFAULT 'deepgram',
            provider_job_id VARCHAR(100),
            model_version VARCHAR(50),
            full_text TEXT,
            confidence_score DECIMAL(5,4),
            language VARCHAR(10) DEFAULT 'en',
            word_count INTEGER,
            duration_seconds DECIMAL(10,2),
            processing_time_ms INTEGER,
            cost_cents INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recording_id) REFERENCES ci_call_recordings(id) ON DELETE CASCADE
        );
        """,

        # Transcription Segments (speaker-diarized segments)
        """
        CREATE TABLE IF NOT EXISTS ci_transcription_segments (
            id TEXT PRIMARY KEY,
            transcription_id TEXT NOT NULL,
            segment_index INTEGER NOT NULL,
            speaker VARCHAR(20) NOT NULL,
            speaker_label VARCHAR(50),
            start_time_ms INTEGER NOT NULL,
            end_time_ms INTEGER NOT NULL,
            text TEXT NOT NULL,
            confidence DECIMAL(5,4),
            words TEXT,
            sentiment VARCHAR(20),
            intent VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transcription_id) REFERENCES ci_call_transcriptions(id) ON DELETE CASCADE
        );
        """,

        # =============================================================================
        # ANALYSIS TABLES
        # =============================================================================

        # Call Analysis (AI-generated insights)
        """
        CREATE TABLE IF NOT EXISTS ci_call_analyses (
            id TEXT PRIMARY KEY,
            recording_id TEXT NOT NULL,
            analysis_model VARCHAR(50) DEFAULT 'claude-3-sonnet',
            analysis_version VARCHAR(20) DEFAULT '1.0',
            summary TEXT,
            summary_bullets TEXT,
            call_disposition VARCHAR(50),
            call_purpose VARCHAR(50),
            call_outcome VARCHAR(50),
            topics_discussed TEXT,
            action_items TEXT,
            follow_ups_needed TEXT,
            customer_sentiment VARCHAR(20),
            customer_intent VARCHAR(50),
            objections_raised TEXT,
            questions_asked TEXT,
            agent_performance TEXT,
            coaching_opportunities TEXT,
            compliance_flags TEXT,
            required_disclosures_given TEXT,
            loan_details_discussed TEXT,
            property_details TEXT,
            borrower_info_collected TEXT,
            processing_time_ms INTEGER,
            tokens_used INTEGER,
            cost_cents INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recording_id) REFERENCES ci_call_recordings(id) ON DELETE CASCADE
        );
        """,

        # =============================================================================
        # QA SCORING TABLES
        # =============================================================================

        # QA Rubrics (scoring criteria templates)
        """
        CREATE TABLE IF NOT EXISTS ci_qa_rubrics (
            id TEXT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            category VARCHAR(50) NOT NULL,
            max_points INTEGER NOT NULL DEFAULT 10,
            weight DECIMAL(5,2) NOT NULL DEFAULT 1.0,
            criteria TEXT NOT NULL,
            scoring_guide TEXT,
            auto_score_enabled BOOLEAN DEFAULT 0,
            auto_score_keywords TEXT,
            auto_score_rules TEXT,
            call_types TEXT DEFAULT '["inbound","outbound"]',
            required BOOLEAN DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # QA Scorecards (per-call scoring)
        """
        CREATE TABLE IF NOT EXISTS ci_qa_scorecards (
            id TEXT PRIMARY KEY,
            recording_id TEXT NOT NULL,
            scored_by INTEGER,
            scoring_method VARCHAR(20) NOT NULL DEFAULT 'auto',
            total_score DECIMAL(6,2),
            max_possible_score DECIMAL(6,2),
            percentage_score DECIMAL(5,2),
            grade VARCHAR(2),
            category_scores TEXT,
            critical_failures TEXT,
            improvement_areas TEXT,
            strengths TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            reviewed_at TIMESTAMP,
            reviewer_id INTEGER,
            agent_acknowledged BOOLEAN DEFAULT 0,
            agent_acknowledged_at TIMESTAMP,
            agent_comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recording_id) REFERENCES ci_call_recordings(id) ON DELETE CASCADE,
            FOREIGN KEY (scored_by) REFERENCES users(id),
            FOREIGN KEY (reviewer_id) REFERENCES users(id)
        );
        """,

        # QA Scorecard Items (individual rubric scores)
        """
        CREATE TABLE IF NOT EXISTS ci_qa_scorecard_items (
            id TEXT PRIMARY KEY,
            scorecard_id TEXT NOT NULL,
            rubric_id TEXT NOT NULL,
            score DECIMAL(5,2),
            max_score DECIMAL(5,2),
            percentage DECIMAL(5,2),
            evidence_text TEXT,
            evidence_timestamps TEXT,
            auto_score DECIMAL(5,2),
            manual_score DECIMAL(5,2),
            final_score DECIMAL(5,2),
            evaluator_notes TEXT,
            improvement_suggestions TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scorecard_id) REFERENCES ci_qa_scorecards(id) ON DELETE CASCADE,
            FOREIGN KEY (rubric_id) REFERENCES ci_qa_rubrics(id)
        );
        """,

        # =============================================================================
        # REAL-TIME ASSIST TABLES
        # =============================================================================

        # Real-Time Sessions
        """
        CREATE TABLE IF NOT EXISTS ci_realtime_sessions (
            id TEXT PRIMARY KEY,
            recording_id TEXT,
            agent_user_id INTEGER NOT NULL,
            call_id VARCHAR(100),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            connection_id VARCHAR(100),
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recording_id) REFERENCES ci_call_recordings(id),
            FOREIGN KEY (agent_user_id) REFERENCES users(id)
        );
        """,

        # Real-Time Suggestions
        """
        CREATE TABLE IF NOT EXISTS ci_realtime_suggestions (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            suggestion_type VARCHAR(30) NOT NULL,
            priority VARCHAR(10) DEFAULT 'normal',
            title VARCHAR(200),
            content TEXT NOT NULL,
            triggered_by TEXT,
            trigger_timestamp_ms INTEGER,
            was_displayed BOOLEAN DEFAULT 0,
            displayed_at TIMESTAMP,
            was_dismissed BOOLEAN DEFAULT 0,
            was_helpful BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES ci_realtime_sessions(id) ON DELETE CASCADE
        );
        """,

        # =============================================================================
        # COACHING TABLES
        # =============================================================================

        # Coaching Clips
        """
        CREATE TABLE IF NOT EXISTS ci_coaching_clips (
            id TEXT PRIMARY KEY,
            recording_id TEXT NOT NULL,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            start_time_ms INTEGER NOT NULL,
            end_time_ms INTEGER NOT NULL,
            transcript_excerpt TEXT,
            clip_type VARCHAR(30) NOT NULL,
            skill_tags TEXT DEFAULT '[]',
            rubric_id TEXT,
            is_public BOOLEAN DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recording_id) REFERENCES ci_call_recordings(id) ON DELETE CASCADE,
            FOREIGN KEY (rubric_id) REFERENCES ci_qa_rubrics(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        );
        """,

        # Coaching Assignments
        """
        CREATE TABLE IF NOT EXISTS ci_coaching_assignments (
            id TEXT PRIMARY KEY,
            agent_user_id INTEGER NOT NULL,
            assigned_by INTEGER NOT NULL,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            assignment_type VARCHAR(30) NOT NULL,
            recording_id TEXT,
            clip_id TEXT,
            rubric_id TEXT,
            due_date TIMESTAMP,
            status VARCHAR(20) DEFAULT 'pending',
            completed_at TIMESTAMP,
            agent_notes TEXT,
            reviewed_by INTEGER,
            reviewed_at TIMESTAMP,
            review_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_user_id) REFERENCES users(id),
            FOREIGN KEY (assigned_by) REFERENCES users(id),
            FOREIGN KEY (recording_id) REFERENCES ci_call_recordings(id),
            FOREIGN KEY (clip_id) REFERENCES ci_coaching_clips(id),
            FOREIGN KEY (rubric_id) REFERENCES ci_qa_rubrics(id),
            FOREIGN KEY (reviewed_by) REFERENCES users(id)
        );
        """,

        # Coaching Comments
        """
        CREATE TABLE IF NOT EXISTS ci_coaching_comments (
            id TEXT PRIMARY KEY,
            recording_id TEXT,
            clip_id TEXT,
            scorecard_id TEXT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            timestamp_ms INTEGER,
            parent_comment_id TEXT,
            is_private BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recording_id) REFERENCES ci_call_recordings(id) ON DELETE CASCADE,
            FOREIGN KEY (clip_id) REFERENCES ci_coaching_clips(id) ON DELETE CASCADE,
            FOREIGN KEY (scorecard_id) REFERENCES ci_qa_scorecards(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (parent_comment_id) REFERENCES ci_coaching_comments(id)
        );
        """,

        # =============================================================================
        # COMPLIANCE MONITORING TABLES
        # =============================================================================

        # Compliance Rules
        """
        CREATE TABLE IF NOT EXISTS ci_compliance_rules (
            id TEXT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            category VARCHAR(50) NOT NULL,
            rule_type VARCHAR(30) NOT NULL,
            rule_config TEXT NOT NULL,
            severity VARCHAR(20) DEFAULT 'medium',
            is_auto_fail BOOLEAN DEFAULT 0,
            states TEXT,
            loan_types TEXT,
            call_types TEXT DEFAULT '["inbound","outbound"]',
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # Compliance Violations
        """
        CREATE TABLE IF NOT EXISTS ci_compliance_violations (
            id TEXT PRIMARY KEY,
            recording_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            violation_type VARCHAR(50) NOT NULL,
            description TEXT,
            evidence_text TEXT,
            timestamp_ms INTEGER,
            severity VARCHAR(20) NOT NULL,
            status VARCHAR(20) DEFAULT 'open',
            reviewed_by INTEGER,
            reviewed_at TIMESTAMP,
            resolution_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recording_id) REFERENCES ci_call_recordings(id) ON DELETE CASCADE,
            FOREIGN KEY (rule_id) REFERENCES ci_compliance_rules(id),
            FOREIGN KEY (reviewed_by) REFERENCES users(id)
        );
        """,

        # =============================================================================
        # METRICS AND REPORTING
        # =============================================================================

        # Agent Call Metrics (aggregated stats)
        """
        CREATE TABLE IF NOT EXISTS ci_agent_metrics (
            id TEXT PRIMARY KEY,
            agent_user_id INTEGER NOT NULL,
            period_type VARCHAR(10) NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            total_calls INTEGER DEFAULT 0,
            inbound_calls INTEGER DEFAULT 0,
            outbound_calls INTEGER DEFAULT 0,
            total_talk_time_seconds INTEGER DEFAULT 0,
            avg_call_duration_seconds INTEGER DEFAULT 0,
            calls_scored INTEGER DEFAULT 0,
            avg_qa_score DECIMAL(5,2),
            calls_grade_a INTEGER DEFAULT 0,
            calls_grade_b INTEGER DEFAULT 0,
            calls_grade_c INTEGER DEFAULT 0,
            calls_grade_d INTEGER DEFAULT 0,
            calls_grade_f INTEGER DEFAULT 0,
            successful_calls INTEGER DEFAULT 0,
            callbacks_scheduled INTEGER DEFAULT 0,
            escalations INTEGER DEFAULT 0,
            compliance_violations INTEGER DEFAULT 0,
            coaching_assignments_completed INTEGER DEFAULT 0,
            coaching_assignments_pending INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_user_id) REFERENCES users(id),
            UNIQUE(agent_user_id, period_type, period_start)
        );
        """,

        # =============================================================================
        # INDEXES
        # =============================================================================
        "CREATE INDEX IF NOT EXISTS idx_ci_recordings_agent ON ci_call_recordings(agent_user_id);",
        "CREATE INDEX IF NOT EXISTS idx_ci_recordings_contact ON ci_call_recordings(contact_id);",
        "CREATE INDEX IF NOT EXISTS idx_ci_recordings_loan ON ci_call_recordings(loan_id);",
        "CREATE INDEX IF NOT EXISTS idx_ci_recordings_started ON ci_call_recordings(started_at);",
        "CREATE INDEX IF NOT EXISTS idx_ci_recordings_status ON ci_call_recordings(status);",
        "CREATE INDEX IF NOT EXISTS idx_ci_transcriptions_recording ON ci_call_transcriptions(recording_id);",
        "CREATE INDEX IF NOT EXISTS idx_ci_segments_transcription ON ci_transcription_segments(transcription_id);",
        "CREATE INDEX IF NOT EXISTS idx_ci_analyses_recording ON ci_call_analyses(recording_id);",
        "CREATE INDEX IF NOT EXISTS idx_ci_rubrics_category ON ci_qa_rubrics(category);",
        "CREATE INDEX IF NOT EXISTS idx_ci_rubrics_active ON ci_qa_rubrics(is_active);",
        "CREATE INDEX IF NOT EXISTS idx_ci_scorecards_recording ON ci_qa_scorecards(recording_id);",
        "CREATE INDEX IF NOT EXISTS idx_ci_scorecards_grade ON ci_qa_scorecards(grade);",
        "CREATE INDEX IF NOT EXISTS idx_ci_realtime_agent ON ci_realtime_sessions(agent_user_id);",
        "CREATE INDEX IF NOT EXISTS idx_ci_realtime_status ON ci_realtime_sessions(status);",
        "CREATE INDEX IF NOT EXISTS idx_ci_clips_recording ON ci_coaching_clips(recording_id);",
        "CREATE INDEX IF NOT EXISTS idx_ci_clips_type ON ci_coaching_clips(clip_type);",
        "CREATE INDEX IF NOT EXISTS idx_ci_assignments_agent ON ci_coaching_assignments(agent_user_id);",
        "CREATE INDEX IF NOT EXISTS idx_ci_assignments_status ON ci_coaching_assignments(status);",
        "CREATE INDEX IF NOT EXISTS idx_ci_violations_recording ON ci_compliance_violations(recording_id);",
        "CREATE INDEX IF NOT EXISTS idx_ci_violations_status ON ci_compliance_violations(status);",
        "CREATE INDEX IF NOT EXISTS idx_ci_metrics_agent ON ci_agent_metrics(agent_user_id);",
    ]

    with engine.connect() as conn:
        for i, sql in enumerate(sql_commands):
            try:
                conn.execute(text(sql))
                logger.info(f"Statement {i+1}/{len(sql_commands)}: OK")
            except Exception as e:
                logger.warning(f"Statement {i+1}/{len(sql_commands)}: {str(e)[:80]}")
        conn.commit()

    logger.info("=" * 60)
    logger.info("Conversation Intelligence tables created!")
    logger.info("=" * 60)


def seed_qa_rubrics():
    """Seed default QA rubrics for mortgage industry."""
    import uuid

    rubrics = [
        {
            "id": str(uuid.uuid4()),
            "name": "Professional Greeting",
            "description": "Agent provides a professional greeting including company name and their name",
            "category": "greeting",
            "max_points": 10,
            "weight": 1.0,
            "criteria": '{"must_include": ["company name", "agent name", "offer to help"], "tone": "warm and professional"}',
            "scoring_guide": "10pts: All elements present with warm tone. 7pts: Missing one element. 5pts: Missing two elements. 0pts: No proper greeting.",
            "auto_score_enabled": True,
            "auto_score_keywords": '["thank you for calling", "my name is", "how can I help", "how may I assist"]',
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Needs Discovery",
            "description": "Agent asks probing questions to understand customer needs",
            "category": "discovery",
            "max_points": 15,
            "weight": 1.5,
            "criteria": '{"questions_to_ask": ["loan purpose", "timeline", "property type", "credit situation", "income stability"]}',
            "scoring_guide": "15pts: Asked 5+ discovery questions. 10pts: Asked 3-4 questions. 5pts: Asked 1-2 questions. 0pts: No discovery.",
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Rate and Product Explanation",
            "description": "Agent clearly explains rates, terms, and product options",
            "category": "presentation",
            "max_points": 15,
            "weight": 1.5,
            "criteria": '{"must_explain": ["interest rate", "APR", "loan term", "monthly payment", "closing costs"]}',
            "scoring_guide": "15pts: Clear explanation of all key terms. 10pts: Explained most terms. 5pts: Minimal explanation. 0pts: No explanation.",
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Objection Handling",
            "description": "Agent effectively addresses customer concerns and objections",
            "category": "objection_handling",
            "max_points": 15,
            "weight": 1.5,
            "criteria": '{"techniques": ["acknowledge concern", "empathize", "provide solution", "confirm resolution"]}',
            "scoring_guide": "15pts: Expertly handled objections with empathy. 10pts: Adequately addressed. 5pts: Partially addressed. 0pts: Ignored or dismissed.",
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Closing and Next Steps",
            "description": "Agent clearly establishes next steps and timeline",
            "category": "closing",
            "max_points": 10,
            "weight": 1.0,
            "criteria": '{"must_include": ["clear next steps", "timeline", "contact information", "follow-up commitment"]}',
            "scoring_guide": "10pts: Clear next steps with timeline. 7pts: Next steps but vague timeline. 5pts: Unclear next steps. 0pts: No closing.",
        },
        {
            "id": str(uuid.uuid4()),
            "name": "TILA-RESPA Compliance",
            "description": "Agent provides required disclosures and doesn't make prohibited statements",
            "category": "compliance",
            "max_points": 20,
            "weight": 2.0,
            "criteria": '{"prohibited": ["guaranteed approval", "specific rate without disclosure", "pressure tactics"], "required": ["right to shop", "estimate disclaimer"]}',
            "scoring_guide": "20pts: Full compliance. 10pts: Minor omissions. 0pts: Compliance violation (auto-fail).",
            "auto_score_enabled": True,
            "auto_score_keywords": '["guaranteed", "100% approved", "no matter what"]',
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Fair Lending Practices",
            "description": "Agent treats all customers fairly without discrimination",
            "category": "compliance",
            "max_points": 20,
            "weight": 2.0,
            "criteria": '{"prohibited_topics": ["race", "religion", "national origin", "familial status", "disability"]}',
            "scoring_guide": "20pts: No fair lending concerns. 0pts: Any discriminatory language or treatment (auto-fail).",
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Active Listening",
            "description": "Agent demonstrates active listening through acknowledgment and clarification",
            "category": "communication",
            "max_points": 10,
            "weight": 1.0,
            "criteria": '{"techniques": ["verbal acknowledgment", "paraphrasing", "clarifying questions", "avoiding interruptions"]}',
            "scoring_guide": "10pts: Excellent active listening. 7pts: Good listening. 5pts: Adequate. 0pts: Poor listening.",
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Product Knowledge",
            "description": "Agent demonstrates thorough knowledge of mortgage products",
            "category": "knowledge",
            "max_points": 15,
            "weight": 1.5,
            "criteria": '{"areas": ["loan programs", "guidelines", "rates", "fees", "process timeline"]}',
            "scoring_guide": "15pts: Expert knowledge. 10pts: Good knowledge. 5pts: Basic knowledge. 0pts: Knowledge gaps.",
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Documentation Requirements",
            "description": "Agent clearly explains required documentation",
            "category": "process",
            "max_points": 10,
            "weight": 1.0,
            "criteria": '{"must_cover": ["income docs", "asset docs", "ID requirements", "property docs"]}',
            "scoring_guide": "10pts: Comprehensive doc explanation. 7pts: Most docs covered. 5pts: Basic list. 0pts: No doc discussion.",
        },
    ]

    with engine.connect() as conn:
        for rubric in rubrics:
            try:
                conn.execute(text("""
                    INSERT INTO ci_qa_rubrics (id, name, description, category, max_points, weight, criteria, scoring_guide, auto_score_enabled, auto_score_keywords)
                    VALUES (:id, :name, :description, :category, :max_points, :weight, :criteria, :scoring_guide, :auto_score_enabled, :auto_score_keywords)
                """), rubric)
                logger.info(f"Seeded rubric: {rubric['name']}")
            except Exception as e:
                logger.warning(f"Rubric {rubric['name']}: {str(e)[:50]}")
        conn.commit()

    logger.info("QA Rubrics seeded!")


if __name__ == "__main__":
    run_migration()
    seed_qa_rubrics()
    print("\n✅ Conversation Intelligence Platform migration complete!")
