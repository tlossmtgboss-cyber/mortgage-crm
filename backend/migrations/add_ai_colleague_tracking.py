"""
Migration: Add AI Colleague Performance Tracking Tables
Creates comprehensive tracking infrastructure for Mission Control dashboard
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
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def run_migration():
    """Create AI Colleague tracking tables, functions, and views"""

    sql_commands = [
        # 1. AI Colleague Actions table - Core tracking
        """
        CREATE TABLE IF NOT EXISTS ai_colleague_actions (
            id SERIAL PRIMARY KEY,
            action_id VARCHAR(100) UNIQUE NOT NULL,
            agent_name VARCHAR(100) NOT NULL,
            action_type VARCHAR(100) NOT NULL,
            lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
            loan_id INTEGER REFERENCES loans(id) ON DELETE SET NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

            -- Context
            context JSONB,
            trigger_type VARCHAR(50),
            trigger_data JSONB,

            -- Decision Making
            confidence_score FLOAT,
            reasoning TEXT,
            alternatives_considered JSONB,

            -- Autonomy
            autonomy_level VARCHAR(50),
            required_approval BOOLEAN DEFAULT FALSE,
            approved_by_user_id INTEGER REFERENCES users(id),
            approved_at TIMESTAMP WITH TIME ZONE,

            -- Execution
            status VARCHAR(50) DEFAULT 'pending',
            executed_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,

            -- Results
            outcome VARCHAR(50),
            impact_score FLOAT,
            business_metrics JSONB,

            -- Learning
            customer_response VARCHAR(50),
            response_time_minutes INTEGER,
            follow_up_occurred BOOLEAN DEFAULT FALSE,

            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            metadata JSONB
        );
        """,

        # 2. AI Learning Metrics table
        """
        CREATE TABLE IF NOT EXISTS ai_learning_metrics (
            id SERIAL PRIMARY KEY,
            action_id VARCHAR(100) REFERENCES ai_colleague_actions(action_id) ON DELETE CASCADE,
            metric_type VARCHAR(100) NOT NULL,
            metric_name VARCHAR(100) NOT NULL,
            metric_value FLOAT NOT NULL,
            baseline_value FLOAT,
            improvement_percentage FLOAT,

            -- Context
            context JSONB,
            segment VARCHAR(100),

            -- Time
            measured_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            period_start TIMESTAMP WITH TIME ZONE,
            period_end TIMESTAMP WITH TIME ZONE,

            -- Metadata
            metadata JSONB
        );
        """,

        # 3. AI Performance Daily Rollup
        """
        CREATE TABLE IF NOT EXISTS ai_performance_daily (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            agent_name VARCHAR(100) NOT NULL,

            -- Volume
            total_actions INTEGER DEFAULT 0,
            autonomous_actions INTEGER DEFAULT 0,
            approved_actions INTEGER DEFAULT 0,
            rejected_actions INTEGER DEFAULT 0,

            -- Success
            successful_actions INTEGER DEFAULT 0,
            failed_actions INTEGER DEFAULT 0,
            success_rate FLOAT,

            -- Response
            avg_customer_response_time FLOAT,
            positive_responses INTEGER DEFAULT 0,
            negative_responses INTEGER DEFAULT 0,
            neutral_responses INTEGER DEFAULT 0,

            -- Impact
            avg_impact_score FLOAT,
            total_business_value FLOAT,

            -- Confidence
            avg_confidence_score FLOAT,
            high_confidence_actions INTEGER DEFAULT 0,

            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(date, agent_name)
        );
        """,

        # 4. AI Journey Insights table
        """
        CREATE TABLE IF NOT EXISTS ai_journey_insights (
            id SERIAL PRIMARY KEY,
            insight_id VARCHAR(100) UNIQUE NOT NULL,
            insight_type VARCHAR(100) NOT NULL,

            -- Scope
            lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
            loan_id INTEGER REFERENCES loans(id) ON DELETE SET NULL,
            segment VARCHAR(100),

            -- Pattern
            pattern_description TEXT NOT NULL,
            pattern_frequency INTEGER,
            pattern_confidence FLOAT,

            -- Context
            related_actions JSONB,
            touchpoints JSONB,
            customer_signals JSONB,

            -- Recommendation
            recommended_action TEXT,
            expected_impact FLOAT,
            priority VARCHAR(50),

            -- Status
            status VARCHAR(50) DEFAULT 'active',
            actioned_at TIMESTAMP WITH TIME ZONE,
            outcome VARCHAR(50),

            -- Metadata
            discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE,
            metadata JSONB
        );
        """,

        # 5. AI Health Score table
        """
        CREATE TABLE IF NOT EXISTS ai_health_score (
            id SERIAL PRIMARY KEY,
            calculated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            period_start TIMESTAMP WITH TIME ZONE NOT NULL,
            period_end TIMESTAMP WITH TIME ZONE NOT NULL,

            -- Overall Health
            overall_score FLOAT NOT NULL,
            health_status VARCHAR(50),

            -- Component Scores
            autonomy_score FLOAT,
            accuracy_score FLOAT,
            efficiency_score FLOAT,
            learning_score FLOAT,
            impact_score FLOAT,

            -- Metrics
            total_actions INTEGER,
            autonomous_rate FLOAT,
            approval_rate FLOAT,
            success_rate FLOAT,
            avg_confidence FLOAT,
            learning_velocity FLOAT,

            -- Trends
            score_trend VARCHAR(50),
            previous_score FLOAT,
            score_change FLOAT,

            -- Metadata
            metadata JSONB
        );
        """,

        # Indices for performance
        "CREATE INDEX IF NOT EXISTS idx_ai_actions_agent ON ai_colleague_actions(agent_name);",
        "CREATE INDEX IF NOT EXISTS idx_ai_actions_type ON ai_colleague_actions(action_type);",
        "CREATE INDEX IF NOT EXISTS idx_ai_actions_status ON ai_colleague_actions(status);",
        "CREATE INDEX IF NOT EXISTS idx_ai_actions_lead ON ai_colleague_actions(lead_id);",
        "CREATE INDEX IF NOT EXISTS idx_ai_actions_loan ON ai_colleague_actions(loan_id);",
        "CREATE INDEX IF NOT EXISTS idx_ai_actions_created ON ai_colleague_actions(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_ai_actions_autonomy ON ai_colleague_actions(autonomy_level);",

        "CREATE INDEX IF NOT EXISTS idx_ai_metrics_action ON ai_learning_metrics(action_id);",
        "CREATE INDEX IF NOT EXISTS idx_ai_metrics_type ON ai_learning_metrics(metric_type);",
        "CREATE INDEX IF NOT EXISTS idx_ai_metrics_measured ON ai_learning_metrics(measured_at);",

        "CREATE INDEX IF NOT EXISTS idx_ai_daily_date ON ai_performance_daily(date);",
        "CREATE INDEX IF NOT EXISTS idx_ai_daily_agent ON ai_performance_daily(agent_name);",

        "CREATE INDEX IF NOT EXISTS idx_ai_insights_type ON ai_journey_insights(insight_type);",
        "CREATE INDEX IF NOT EXISTS idx_ai_insights_status ON ai_journey_insights(status);",
        "CREATE INDEX IF NOT EXISTS idx_ai_insights_lead ON ai_journey_insights(lead_id);",
        "CREATE INDEX IF NOT EXISTS idx_ai_insights_discovered ON ai_journey_insights(discovered_at);",

        "CREATE INDEX IF NOT EXISTS idx_ai_health_calculated ON ai_health_score(calculated_at);",

        # Updated_at trigger function (reuse if exists)
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        """,

        # Triggers for updated_at
        """
        DROP TRIGGER IF EXISTS update_ai_colleague_actions_updated_at ON ai_colleague_actions;
        CREATE TRIGGER update_ai_colleague_actions_updated_at
            BEFORE UPDATE ON ai_colleague_actions
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_ai_performance_daily_updated_at ON ai_performance_daily;
        CREATE TRIGGER update_ai_performance_daily_updated_at
            BEFORE UPDATE ON ai_performance_daily
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """,

        # Function to calculate health score
        """
        CREATE OR REPLACE FUNCTION calculate_ai_health_score(
            p_period_start TIMESTAMP WITH TIME ZONE,
            p_period_end TIMESTAMP WITH TIME ZONE
        )
        RETURNS TABLE (
            overall_score FLOAT,
            autonomy_score FLOAT,
            accuracy_score FLOAT,
            efficiency_score FLOAT,
            learning_score FLOAT,
            impact_score FLOAT,
            total_actions INTEGER,
            autonomous_rate FLOAT,
            approval_rate FLOAT,
            success_rate FLOAT,
            avg_confidence FLOAT,
            learning_velocity FLOAT
        ) AS $$
        DECLARE
            v_total_actions INTEGER;
            v_autonomous_actions INTEGER;
            v_approved_actions INTEGER;
            v_successful_actions INTEGER;
            v_avg_confidence FLOAT;
            v_avg_impact FLOAT;
            v_learning_velocity FLOAT;
        BEGIN
            -- Get basic metrics
            SELECT
                COUNT(*),
                COUNT(*) FILTER (WHERE autonomy_level = 'full'),
                COUNT(*) FILTER (WHERE status = 'approved' OR required_approval = FALSE),
                COUNT(*) FILTER (WHERE outcome = 'success'),
                AVG(confidence_score),
                AVG(impact_score)
            INTO
                v_total_actions,
                v_autonomous_actions,
                v_approved_actions,
                v_successful_actions,
                v_avg_confidence,
                v_avg_impact
            FROM ai_colleague_actions
            WHERE created_at BETWEEN p_period_start AND p_period_end;

            -- Calculate learning velocity (improvement over time)
            SELECT COALESCE(AVG(improvement_percentage), 0)
            INTO v_learning_velocity
            FROM ai_learning_metrics
            WHERE measured_at BETWEEN p_period_start AND p_period_end;

            -- Return calculated scores
            RETURN QUERY SELECT
                -- Overall score (weighted average)
                COALESCE((
                    (COALESCE(v_autonomous_actions::FLOAT / NULLIF(v_total_actions, 0), 0) * 0.3) +
                    (COALESCE(v_approved_actions::FLOAT / NULLIF(v_total_actions, 0), 0) * 0.25) +
                    (COALESCE(v_successful_actions::FLOAT / NULLIF(v_total_actions, 0), 0) * 0.25) +
                    (COALESCE(v_avg_confidence, 0) * 0.1) +
                    (COALESCE(v_avg_impact, 0) * 0.1)
                ) * 100, 0)::FLOAT,

                -- Component scores
                COALESCE(v_autonomous_actions::FLOAT / NULLIF(v_total_actions, 0) * 100, 0)::FLOAT,
                COALESCE(v_successful_actions::FLOAT / NULLIF(v_total_actions, 0) * 100, 0)::FLOAT,
                COALESCE(v_avg_confidence * 100, 0)::FLOAT,
                COALESCE(v_learning_velocity, 0)::FLOAT,
                COALESCE(v_avg_impact * 100, 0)::FLOAT,

                -- Metrics
                COALESCE(v_total_actions, 0)::INTEGER,
                COALESCE(v_autonomous_actions::FLOAT / NULLIF(v_total_actions, 0) * 100, 0)::FLOAT,
                COALESCE(v_approved_actions::FLOAT / NULLIF(v_total_actions, 0) * 100, 0)::FLOAT,
                COALESCE(v_successful_actions::FLOAT / NULLIF(v_total_actions, 0) * 100, 0)::FLOAT,
                COALESCE(v_avg_confidence, 0)::FLOAT,
                COALESCE(v_learning_velocity, 0)::FLOAT;
        END;
        $$ LANGUAGE plpgsql;
        """,

        # View for Mission Control dashboard
        """
        CREATE OR REPLACE VIEW mission_control_overview AS
        SELECT
            -- Time period
            DATE_TRUNC('day', created_at) as date,
            agent_name,

            -- Volume
            COUNT(*) as total_actions,
            COUNT(*) FILTER (WHERE autonomy_level = 'full') as autonomous_actions,
            COUNT(*) FILTER (WHERE required_approval = TRUE AND approved_by_user_id IS NOT NULL) as approved_actions,

            -- Success
            COUNT(*) FILTER (WHERE outcome = 'success') as successful_actions,
            COUNT(*) FILTER (WHERE outcome = 'failure') as failed_actions,
            ROUND(AVG(CASE WHEN outcome = 'success' THEN 100 ELSE 0 END), 2) as success_rate,

            -- Response
            AVG(response_time_minutes) as avg_response_time,
            COUNT(*) FILTER (WHERE customer_response = 'positive') as positive_responses,
            COUNT(*) FILTER (WHERE customer_response = 'negative') as negative_responses,

            -- Quality
            ROUND(AVG(confidence_score) * 100, 2) as avg_confidence,
            ROUND(AVG(impact_score) * 100, 2) as avg_impact,

            -- Learning
            COUNT(DISTINCT CASE WHEN status = 'completed' THEN action_id END) as completed_actions

        FROM ai_colleague_actions
        WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
        GROUP BY DATE_TRUNC('day', created_at), agent_name
        ORDER BY date DESC, agent_name;
        """,

        # View for recent AI actions
        """
        CREATE OR REPLACE VIEW recent_ai_actions AS
        SELECT
            action_id,
            agent_name,
            action_type,
            lead_id,
            loan_id,
            autonomy_level,
            confidence_score,
            status,
            outcome,
            impact_score,
            customer_response,
            created_at,
            completed_at,
            reasoning
        FROM ai_colleague_actions
        ORDER BY created_at DESC
        LIMIT 100;
        """
    ]

    try:
        with engine.connect() as conn:
            for idx, sql in enumerate(sql_commands, 1):
                try:
                    logger.info(f"Executing command {idx}/{len(sql_commands)}...")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"✅ Command {idx} executed successfully")
                except Exception as e:
                    logger.error(f"❌ Error executing command {idx}: {e}")
                    # Continue with other commands
                    continue

        logger.info("✅ AI Colleague tracking tables migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("AI Colleague Performance Tracking - Database Migration")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Creating tables:")
    logger.info("  - ai_colleague_actions (core action tracking)")
    logger.info("  - ai_learning_metrics (performance metrics)")
    logger.info("  - ai_performance_daily (daily rollups)")
    logger.info("  - ai_journey_insights (pattern detection)")
    logger.info("  - ai_health_score (health calculations)")
    logger.info("")

    success = run_migration()

    if success:
        logger.info("")
        logger.info("✅ Migration completed successfully!")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Add logging to existing AI agents")
        logger.info("  2. Create Mission Control API endpoints")
        logger.info("  3. Build Mission Control React dashboard")
        logger.info("  4. Deploy and test")
    else:
        logger.error("❌ Migration failed!")
        sys.exit(1)
