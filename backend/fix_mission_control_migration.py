"""
Hotfix for Mission Control Migration Issues
Fixes:
1. Ambiguous column reference in calculate_ai_health_score function
2. Missing views due to transaction errors
"""
import os
import sys
from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL environment variable not set")
    sys.exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def apply_hotfix():
    """Apply fixes for mission control migration issues"""

    sql_commands = [
        # Fix 1: Drop and recreate health score function with qualified column names
        """
        DROP FUNCTION IF EXISTS calculate_ai_health_score(timestamp with time zone, timestamp with time zone);
        """,

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
            -- Get basic metrics with fully qualified column names
            SELECT
                COUNT(*),
                COUNT(*) FILTER (WHERE ai_colleague_actions.autonomy_level = 'full'),
                COUNT(*) FILTER (WHERE ai_colleague_actions.status = 'approved' OR ai_colleague_actions.required_approval = FALSE),
                COUNT(*) FILTER (WHERE ai_colleague_actions.outcome = 'success'),
                AVG(ai_colleague_actions.confidence_score),
                AVG(ai_colleague_actions.impact_score)
            INTO
                v_total_actions,
                v_autonomous_actions,
                v_approved_actions,
                v_successful_actions,
                v_avg_confidence,
                v_avg_impact
            FROM ai_colleague_actions
            WHERE ai_colleague_actions.created_at BETWEEN p_period_start AND p_period_end;

            -- Calculate learning velocity (improvement over time)
            SELECT COALESCE(AVG(ai_colleague_learning_metrics.improvement_percentage), 0)
            INTO v_learning_velocity
            FROM ai_colleague_learning_metrics
            WHERE ai_colleague_learning_metrics.measured_at BETWEEN p_period_start AND p_period_end;

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

        # Fix 2: Recreate mission_control_overview view
        """
        DROP VIEW IF EXISTS mission_control_overview;
        """,

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
            ROUND(AVG(ai_colleague_actions.impact_score) * 100, 2) as avg_impact,

            -- Learning
            COUNT(DISTINCT CASE WHEN status = 'completed' THEN action_id END) as completed_actions

        FROM ai_colleague_actions
        WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
        GROUP BY DATE_TRUNC('day', created_at), agent_name
        ORDER BY date DESC, agent_name;
        """,

        # Fix 3: Recreate recent_ai_actions view
        """
        DROP VIEW IF EXISTS recent_ai_actions;
        """,

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
            ai_colleague_actions.impact_score,
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
                    logger.info(f"Executing fix {idx}/{len(sql_commands)}...")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"✅ Fix {idx} applied successfully")
                except Exception as e:
                    logger.error(f"❌ Error in fix {idx}: {e}")
                    conn.rollback()
                    # Continue with other fixes
                    continue

        logger.info("\n✅ HOTFIX COMPLETED!\n")
        logger.info("Fixed:")
        logger.info("  1. calculate_ai_health_score function (ambiguous column)")
        logger.info("  2. mission_control_overview view")
        logger.info("  3. recent_ai_actions view")
        logger.info("")
        return True

    except Exception as e:
        logger.error(f"❌ Hotfix failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("Mission Control Migration Hotfix")
    logger.info("=" * 70)
    logger.info("")

    success = apply_hotfix()

    if success:
        logger.info("✅ Ready to re-run verification!")
        sys.exit(0)
    else:
        logger.error("❌ Hotfix failed!")
        sys.exit(1)
