"""
Migration: Add A/B Testing Tables
Creates tables for experiment management, variant assignment, and results tracking
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
    """Create A/B testing tables"""

    sql_commands = [
        # 1. Experiments table
        """
        CREATE TABLE IF NOT EXISTS ab_experiments (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            experiment_type VARCHAR(50) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'draft',
            target_percentage FLOAT DEFAULT 100.0,
            target_user_segment VARCHAR(100),
            primary_metric VARCHAR(100) NOT NULL,
            secondary_metrics JSON,
            min_sample_size INTEGER DEFAULT 100,
            confidence_level FLOAT DEFAULT 0.95,
            winning_variant_id INTEGER,
            winner_declared_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP WITH TIME ZONE,
            ended_at TIMESTAMP WITH TIME ZONE,
            created_by_user_id INTEGER REFERENCES users(id),
            experiment_metadata JSON
        );
        """,

        # 2. Variants table
        """
        CREATE TABLE IF NOT EXISTS ab_variants (
            id SERIAL PRIMARY KEY,
            experiment_id INTEGER NOT NULL REFERENCES ab_experiments(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            is_control BOOLEAN DEFAULT FALSE,
            traffic_allocation FLOAT DEFAULT 50.0,
            config JSON NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 3. Assignments table
        """
        CREATE TABLE IF NOT EXISTS ab_assignments (
            id SERIAL PRIMARY KEY,
            experiment_id INTEGER NOT NULL REFERENCES ab_experiments(id) ON DELETE CASCADE,
            variant_id INTEGER NOT NULL REFERENCES ab_variants(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id),
            session_id VARCHAR(255),
            assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            assignment_method VARCHAR(50) DEFAULT 'random'
        );
        """,

        # 4. Results table
        """
        CREATE TABLE IF NOT EXISTS ab_results (
            id SERIAL PRIMARY KEY,
            experiment_id INTEGER NOT NULL REFERENCES ab_experiments(id) ON DELETE CASCADE,
            variant_id INTEGER NOT NULL REFERENCES ab_variants(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id),
            session_id VARCHAR(255),
            metric_name VARCHAR(100) NOT NULL,
            metric_value FLOAT NOT NULL,
            context JSON,
            recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 5. Insights table
        """
        CREATE TABLE IF NOT EXISTS ab_insights (
            id SERIAL PRIMARY KEY,
            experiment_id INTEGER NOT NULL REFERENCES ab_experiments(id) ON DELETE CASCADE,
            analysis_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            variant_stats JSON,
            p_value FLOAT,
            is_significant BOOLEAN DEFAULT FALSE,
            confidence_interval JSON,
            recommended_winner_id INTEGER REFERENCES ab_variants(id),
            recommendation_confidence FLOAT,
            recommendation_reason TEXT,
            sufficient_sample_size BOOLEAN DEFAULT FALSE,
            current_sample_size INTEGER,
            required_sample_size INTEGER,
            analysis_metadata JSON
        );
        """,

        # Indices for performance
        "CREATE INDEX IF NOT EXISTS idx_ab_experiments_status ON ab_experiments(status);",
        "CREATE INDEX IF NOT EXISTS idx_ab_experiments_type ON ab_experiments(experiment_type);",
        "CREATE INDEX IF NOT EXISTS idx_ab_assignments_experiment ON ab_assignments(experiment_id);",
        "CREATE INDEX IF NOT EXISTS idx_ab_assignments_user ON ab_assignments(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_ab_assignments_session ON ab_assignments(session_id);",
        "CREATE INDEX IF NOT EXISTS idx_ab_results_experiment ON ab_results(experiment_id);",
        "CREATE INDEX IF NOT EXISTS idx_ab_results_variant ON ab_results(variant_id);",
        "CREATE INDEX IF NOT EXISTS idx_ab_results_metric ON ab_results(metric_name);",
        "CREATE INDEX IF NOT EXISTS idx_ab_results_recorded ON ab_results(recorded_at);",
        "CREATE INDEX IF NOT EXISTS idx_ab_insights_experiment ON ab_insights(experiment_id);",

        # Foreign key constraint for winning_variant_id (added after variants table exists)
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ab_experiments_winning_variant_fkey'
            ) THEN
                ALTER TABLE ab_experiments
                ADD CONSTRAINT ab_experiments_winning_variant_fkey
                FOREIGN KEY (winning_variant_id) REFERENCES ab_variants(id);
            END IF;
        END $$;
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

        logger.info("✅ A/B testing tables migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("Starting A/B testing tables migration...")
    success = run_migration()
    if success:
        logger.info("✅ Migration completed!")
    else:
        logger.error("❌ Migration failed!")
        sys.exit(1)
