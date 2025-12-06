"""
Email Response Training Tables Migration
Creates tables for AI email response learning and pattern matching.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(db=None):
    """
    Run the email response training migration.
    Creates:
    - email_response_patterns - Tracks learned response behaviors
    - email_response_log - Tracks all email response actions
    - email_response_queue - Pending responses awaiting review
    - Views for analytics
    - Trigger for confidence calculation
    """
    try:
        if db is None:
            from database import SessionLocal
            db = SessionLocal()
            should_close = True
        else:
            should_close = False

        logger.info("Starting email response training tables migration...")

        # Create email_response_patterns table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS email_response_patterns (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),

                -- Pattern identification
                pattern_type VARCHAR(50) NOT NULL,
                pattern_value VARCHAR(500) NOT NULL,

                -- Response behavior
                response_type VARCHAR(50) NOT NULL,
                response_template_id INTEGER,
                response_config JSONB,

                -- Confidence tracking
                approval_count INTEGER DEFAULT 1,
                rejection_count INTEGER DEFAULT 0,
                confidence_score NUMERIC(3,2) DEFAULT 0.50,

                -- Auto-execution settings
                is_active BOOLEAN DEFAULT FALSE,
                auto_execute_threshold NUMERIC(3,2) DEFAULT 0.95,
                requires_entity_match BOOLEAN DEFAULT TRUE,

                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_matched_at TIMESTAMP WITH TIME ZONE,
                last_approved_at TIMESTAMP WITH TIME ZONE,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        logger.info("Created email_response_patterns table")

        # Create indexes for email_response_patterns
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_email_response_patterns_user
            ON email_response_patterns(user_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_email_response_patterns_type
            ON email_response_patterns(pattern_type, pattern_value)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_email_response_patterns_active
            ON email_response_patterns(is_active, confidence_score)
        """))

        # Create unique index (catch duplicate error if exists)
        try:
            db.execute(text("""
                CREATE UNIQUE INDEX idx_email_response_patterns_unique
                ON email_response_patterns(user_id, pattern_type, pattern_value, response_type)
            """))
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning(f"Index creation warning: {e}")

        # Create email_response_log table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS email_response_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),

                -- Email reference
                email_id VARCHAR(500) NOT NULL,
                extracted_data_id INTEGER,
                incoming_event_id INTEGER,

                -- Email metadata
                sender_email VARCHAR(255),
                sender_domain VARCHAR(255),
                subject VARCHAR(500),
                email_intent VARCHAR(100),
                matched_entity_type VARCHAR(50),
                matched_entity_id INTEGER,

                -- Response details
                response_type VARCHAR(50) NOT NULL,
                response_pattern_id INTEGER REFERENCES email_response_patterns(id),
                was_auto_executed BOOLEAN DEFAULT FALSE,

                -- AI recommendation
                ai_recommended_action VARCHAR(50),
                ai_confidence NUMERIC(3,2),
                ai_reasoning TEXT,

                -- User decision
                user_action VARCHAR(50),
                user_modifications JSONB,

                -- Result
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT,

                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                responded_at TIMESTAMP WITH TIME ZONE
            )
        """))
        logger.info("Created email_response_log table")

        # Create indexes for email_response_log
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_email_response_log_user
            ON email_response_log(user_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_email_response_log_email
            ON email_response_log(email_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_email_response_log_sender
            ON email_response_log(sender_domain)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_email_response_log_created
            ON email_response_log(created_at)
        """))

        # Create email_response_queue table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS email_response_queue (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),

                -- Email reference
                email_id VARCHAR(500) NOT NULL,
                incoming_event_id INTEGER,
                extracted_data_id INTEGER,

                -- Email content
                sender_email VARCHAR(255),
                sender_name VARCHAR(255),
                subject VARCHAR(500),
                body_preview TEXT,
                received_at TIMESTAMP WITH TIME ZONE,

                -- Classification
                email_intent VARCHAR(100),
                intent_confidence NUMERIC(3,2),
                matched_entity_type VARCHAR(50),
                matched_entity_id INTEGER,
                matched_entity_name VARCHAR(255),

                -- AI Recommendation
                recommended_action VARCHAR(50) NOT NULL,
                recommended_response TEXT,
                recommendation_reasoning TEXT,
                recommendation_confidence NUMERIC(3,2),

                -- Matched pattern
                matched_pattern_id INTEGER REFERENCES email_response_patterns(id),
                pattern_confidence NUMERIC(3,2),

                -- Status
                status VARCHAR(50) DEFAULT 'pending',
                priority VARCHAR(20) DEFAULT 'normal',

                -- Processing
                reviewed_by INTEGER REFERENCES users(id),
                reviewed_at TIMESTAMP WITH TIME ZONE,
                executed_at TIMESTAMP WITH TIME ZONE,

                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                expires_at TIMESTAMP WITH TIME ZONE
            )
        """))
        logger.info("Created email_response_queue table")

        # Create indexes for email_response_queue
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_email_response_queue_user
            ON email_response_queue(user_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_email_response_queue_status
            ON email_response_queue(status)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_email_response_queue_priority
            ON email_response_queue(priority, created_at)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_email_response_queue_email
            ON email_response_queue(email_id)
        """))

        # Create confidence calculation function and trigger
        db.execute(text("""
            CREATE OR REPLACE FUNCTION update_pattern_confidence()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.confidence_score := CASE
                    WHEN (NEW.approval_count + NEW.rejection_count) > 0
                    THEN ROUND(
                        (NEW.approval_count::NUMERIC / (NEW.approval_count + NEW.rejection_count)) *
                        LEAST(1.0, (NEW.approval_count::NUMERIC / 10.0)),
                        2
                    )
                    ELSE 0.50
                END;
                NEW.updated_at := NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))

        # Drop and recreate trigger
        db.execute(text("""
            DROP TRIGGER IF EXISTS trigger_update_pattern_confidence ON email_response_patterns
        """))
        db.execute(text("""
            CREATE TRIGGER trigger_update_pattern_confidence
                BEFORE UPDATE OF approval_count, rejection_count ON email_response_patterns
                FOR EACH ROW
                EXECUTE FUNCTION update_pattern_confidence()
        """))
        logger.info("Created confidence calculation trigger")

        # Create analytics views
        db.execute(text("""
            CREATE OR REPLACE VIEW email_pattern_effectiveness AS
            SELECT
                erp.id,
                erp.user_id,
                erp.pattern_type,
                erp.pattern_value,
                erp.response_type,
                erp.approval_count,
                erp.rejection_count,
                erp.confidence_score,
                erp.is_active,
                CASE
                    WHEN (erp.approval_count + erp.rejection_count) > 0
                    THEN ROUND(erp.approval_count::NUMERIC / (erp.approval_count + erp.rejection_count) * 100, 1)
                    ELSE 0
                END as approval_rate,
                erp.last_approved_at,
                erp.created_at
            FROM email_response_patterns erp
            ORDER BY erp.confidence_score DESC
        """))

        db.execute(text("""
            CREATE OR REPLACE VIEW user_email_response_stats AS
            SELECT
                erl.user_id,
                DATE(erl.created_at) as date,
                COUNT(*) as total_emails,
                COUNT(CASE WHEN erl.user_action = 'approved' THEN 1 END) as approved,
                COUNT(CASE WHEN erl.user_action = 'rejected' THEN 1 END) as rejected,
                COUNT(CASE WHEN erl.was_auto_executed THEN 1 END) as auto_executed,
                AVG(erl.ai_confidence) as avg_ai_confidence
            FROM email_response_log erl
            WHERE erl.created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY erl.user_id, DATE(erl.created_at)
            ORDER BY date DESC
        """))

        db.execute(text("""
            CREATE OR REPLACE VIEW pending_email_responses AS
            SELECT
                erq.user_id,
                COUNT(*) as pending_count,
                COUNT(CASE WHEN erq.priority = 'urgent' THEN 1 END) as urgent_count,
                COUNT(CASE WHEN erq.priority = 'high' THEN 1 END) as high_count,
                MIN(erq.created_at) as oldest_pending
            FROM email_response_queue erq
            WHERE erq.status = 'pending'
            GROUP BY erq.user_id
        """))
        logger.info("Created analytics views")

        db.commit()
        logger.info("Email response training migration completed successfully")

        if should_close:
            db.close()

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        if db:
            db.rollback()
        raise e


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
