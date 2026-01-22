"""
Migration: Add Phase 4 Tables
Creates tables for:
- Voice A/B Testing (experiments, variants, results)
- AI Learning (training examples, knowledge gaps)
- Continuous Learning (improvement opportunities, learning cycles)
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

# Detect database type
is_sqlite = DATABASE_URL.startswith("sqlite")


def get_sql_commands():
    """Get SQL commands appropriate for the database type."""

    if is_sqlite:
        # SQLite-compatible syntax
        return [
            # =================================================================
            # Voice A/B Testing Tables
            # =================================================================

            # 1. Voice Experiments
            """
            CREATE TABLE IF NOT EXISTS voice_experiments (
                id VARCHAR(20) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                experiment_type VARCHAR(30) NOT NULL,
                primary_metric VARCHAR(30) NOT NULL,
                secondary_metrics TEXT,
                target_percentage REAL DEFAULT 100.0,
                min_calls INTEGER DEFAULT 100,
                confidence_level REAL DEFAULT 0.95,
                target_phone_patterns TEXT,
                target_time_windows TEXT,
                status VARCHAR(20) DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                ended_at TIMESTAMP,
                winning_variant_id VARCHAR(30)
            );
            """,

            # 2. Voice Experiment Variants
            """
            CREATE TABLE IF NOT EXISTS voice_experiment_variants (
                id VARCHAR(30) PRIMARY KEY,
                experiment_id VARCHAR(20) NOT NULL,
                name VARCHAR(100) NOT NULL,
                is_control BOOLEAN DEFAULT FALSE,
                traffic_allocation REAL DEFAULT 50.0,
                config TEXT,
                greeting_text TEXT,
                voice_id VARCHAR(50),
                speech_rate REAL DEFAULT 1.0,
                pitch_adjustment REAL DEFAULT 0.0,
                script_template TEXT,
                call_flow_id VARCHAR(50),
                FOREIGN KEY (experiment_id) REFERENCES voice_experiments(id) ON DELETE CASCADE
            );
            """,

            # 3. Voice Experiment Results
            """
            CREATE TABLE IF NOT EXISTS voice_experiment_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id VARCHAR(20) NOT NULL,
                variant_id VARCHAR(30) NOT NULL,
                call_id VARCHAR(50) NOT NULL,
                caller_phone VARCHAR(20) NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                call_success BOOLEAN DEFAULT FALSE,
                booking_made BOOLEAN DEFAULT FALSE,
                transferred BOOLEAN DEFAULT FALSE,
                call_duration_seconds INTEGER DEFAULT 0,
                satisfaction_score REAL,
                voicemail_left BOOLEAN DEFAULT FALSE,
                callback_requested BOOLEAN DEFAULT FALSE,
                escalated BOOLEAN DEFAULT FALSE,
                hang_up_early BOOLEAN DEFAULT FALSE,
                time_of_day VARCHAR(20),
                day_of_week VARCHAR(15),
                caller_state VARCHAR(2),
                FOREIGN KEY (experiment_id) REFERENCES voice_experiments(id) ON DELETE CASCADE,
                FOREIGN KEY (variant_id) REFERENCES voice_experiment_variants(id) ON DELETE CASCADE
            );
            """,

            # =================================================================
            # AI Learning Tables
            # =================================================================

            # 4. Training Examples
            """
            CREATE TABLE IF NOT EXISTS ai_training_examples (
                id VARCHAR(20) PRIMARY KEY,
                data_type VARCHAR(30) NOT NULL,
                input_text TEXT NOT NULL,
                expected_output TEXT NOT NULL,
                actual_output TEXT,
                context TEXT,
                source_conversation_id VARCHAR(50),
                quality_score REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed BOOLEAN DEFAULT FALSE,
                reviewed_at TIMESTAMP,
                reviewed_by INTEGER,
                approved BOOLEAN DEFAULT FALSE,
                approved_at TIMESTAMP
            );
            """,

            # 5. Knowledge Gaps
            """
            CREATE TABLE IF NOT EXISTS ai_knowledge_gaps (
                id VARCHAR(20) PRIMARY KEY,
                topic VARCHAR(200) NOT NULL,
                description TEXT,
                frequency INTEGER DEFAULT 1,
                example_queries TEXT,
                suggested_content TEXT,
                priority VARCHAR(20) DEFAULT 'medium',
                status VARCHAR(20) DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                resolved_by INTEGER
            );
            """,

            # 6. Model Versions
            """
            CREATE TABLE IF NOT EXISTS ai_model_versions (
                version VARCHAR(30) PRIMARY KEY,
                base_model VARCHAR(50) NOT NULL,
                fine_tuned BOOLEAN DEFAULT FALSE,
                training_examples_count INTEGER DEFAULT 0,
                performance_metrics TEXT,
                deployed_at TIMESTAMP,
                status VARCHAR(20) DEFAULT 'draft',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # =================================================================
            # Continuous Learning Tables
            # =================================================================

            # 7. Improvement Opportunities
            """
            CREATE TABLE IF NOT EXISTS ai_improvement_opportunities (
                id VARCHAR(20) PRIMARY KEY,
                action_type VARCHAR(30) NOT NULL,
                priority VARCHAR(20) NOT NULL,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                impact_estimate TEXT,
                confidence REAL DEFAULT 0.0,
                evidence TEXT,
                suggested_implementation TEXT,
                auto_executable BOOLEAN DEFAULT FALSE,
                status VARCHAR(20) DEFAULT 'identified',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP,
                approved_by INTEGER,
                completed_at TIMESTAMP
            );
            """,

            # 8. Learning Cycles
            """
            CREATE TABLE IF NOT EXISTS ai_learning_cycles (
                id VARCHAR(20) PRIMARY KEY,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                period_hours INTEGER,
                total_conversations INTEGER DEFAULT 0,
                successful_conversations INTEGER DEFAULT 0,
                failed_conversations INTEGER DEFAULT 0,
                opportunities_identified INTEGER DEFAULT 0,
                actions_taken INTEGER DEFAULT 0,
                recommendations TEXT,
                next_cycle_scheduled TIMESTAMP
            );
            """,

            # 9. Conversation Analysis
            """
            CREATE TABLE IF NOT EXISTS ai_conversation_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id VARCHAR(50) NOT NULL,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                outcome VARCHAR(30),
                quality_score REAL,
                caller_satisfaction REAL,
                failure_reasons TEXT,
                knowledge_gaps TEXT,
                extracted_intents TEXT,
                recommendations TEXT
            );
            """,

            # =================================================================
            # Indices
            # =================================================================
            "CREATE INDEX IF NOT EXISTS idx_voice_exp_status ON voice_experiments(status);",
            "CREATE INDEX IF NOT EXISTS idx_voice_exp_type ON voice_experiments(experiment_type);",
            "CREATE INDEX IF NOT EXISTS idx_voice_variant_exp ON voice_experiment_variants(experiment_id);",
            "CREATE INDEX IF NOT EXISTS idx_voice_result_exp ON voice_experiment_results(experiment_id);",
            "CREATE INDEX IF NOT EXISTS idx_voice_result_variant ON voice_experiment_results(variant_id);",
            "CREATE INDEX IF NOT EXISTS idx_voice_result_ts ON voice_experiment_results(timestamp);",
            "CREATE INDEX IF NOT EXISTS idx_training_type ON ai_training_examples(data_type);",
            "CREATE INDEX IF NOT EXISTS idx_training_approved ON ai_training_examples(approved);",
            "CREATE INDEX IF NOT EXISTS idx_knowledge_gap_status ON ai_knowledge_gaps(status);",
            "CREATE INDEX IF NOT EXISTS idx_knowledge_gap_priority ON ai_knowledge_gaps(priority);",
            "CREATE INDEX IF NOT EXISTS idx_model_status ON ai_model_versions(status);",
            "CREATE INDEX IF NOT EXISTS idx_opportunity_status ON ai_improvement_opportunities(status);",
            "CREATE INDEX IF NOT EXISTS idx_opportunity_priority ON ai_improvement_opportunities(priority);",
            "CREATE INDEX IF NOT EXISTS idx_learning_cycle_date ON ai_learning_cycles(started_at);",
            "CREATE INDEX IF NOT EXISTS idx_conv_analysis_id ON ai_conversation_analysis(conversation_id);",
        ]
    else:
        # PostgreSQL syntax
        return [
            # =================================================================
            # Voice A/B Testing Tables
            # =================================================================

            # 1. Voice Experiments
            """
            CREATE TABLE IF NOT EXISTS voice_experiments (
                id VARCHAR(20) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                experiment_type VARCHAR(30) NOT NULL,
                primary_metric VARCHAR(30) NOT NULL,
                secondary_metrics TEXT[],
                target_percentage NUMERIC(5,2) DEFAULT 100.0,
                min_calls INTEGER DEFAULT 100,
                confidence_level NUMERIC(4,3) DEFAULT 0.95,
                target_phone_patterns TEXT[],
                target_time_windows JSONB,
                status VARCHAR(20) DEFAULT 'draft',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP WITH TIME ZONE,
                ended_at TIMESTAMP WITH TIME ZONE,
                winning_variant_id VARCHAR(30)
            );
            """,

            # 2. Voice Experiment Variants
            """
            CREATE TABLE IF NOT EXISTS voice_experiment_variants (
                id VARCHAR(30) PRIMARY KEY,
                experiment_id VARCHAR(20) NOT NULL REFERENCES voice_experiments(id) ON DELETE CASCADE,
                name VARCHAR(100) NOT NULL,
                is_control BOOLEAN DEFAULT FALSE,
                traffic_allocation NUMERIC(5,2) DEFAULT 50.0,
                config JSONB,
                greeting_text TEXT,
                voice_id VARCHAR(50),
                speech_rate NUMERIC(3,2) DEFAULT 1.0,
                pitch_adjustment NUMERIC(4,2) DEFAULT 0.0,
                script_template TEXT,
                call_flow_id VARCHAR(50)
            );
            """,

            # 3. Voice Experiment Results
            """
            CREATE TABLE IF NOT EXISTS voice_experiment_results (
                id SERIAL PRIMARY KEY,
                experiment_id VARCHAR(20) NOT NULL REFERENCES voice_experiments(id) ON DELETE CASCADE,
                variant_id VARCHAR(30) NOT NULL REFERENCES voice_experiment_variants(id) ON DELETE CASCADE,
                call_id VARCHAR(50) NOT NULL,
                caller_phone VARCHAR(20) NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                call_success BOOLEAN DEFAULT FALSE,
                booking_made BOOLEAN DEFAULT FALSE,
                transferred BOOLEAN DEFAULT FALSE,
                call_duration_seconds INTEGER DEFAULT 0,
                satisfaction_score NUMERIC(3,2),
                voicemail_left BOOLEAN DEFAULT FALSE,
                callback_requested BOOLEAN DEFAULT FALSE,
                escalated BOOLEAN DEFAULT FALSE,
                hang_up_early BOOLEAN DEFAULT FALSE,
                time_of_day VARCHAR(20),
                day_of_week VARCHAR(15),
                caller_state VARCHAR(2)
            );
            """,

            # =================================================================
            # AI Learning Tables
            # =================================================================

            # 4. Training Examples
            """
            CREATE TABLE IF NOT EXISTS ai_training_examples (
                id VARCHAR(20) PRIMARY KEY,
                data_type VARCHAR(30) NOT NULL,
                input_text TEXT NOT NULL,
                expected_output TEXT NOT NULL,
                actual_output TEXT,
                context JSONB,
                source_conversation_id VARCHAR(50),
                quality_score NUMERIC(4,3) DEFAULT 1.0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                reviewed BOOLEAN DEFAULT FALSE,
                reviewed_at TIMESTAMP WITH TIME ZONE,
                reviewed_by INTEGER REFERENCES users(id),
                approved BOOLEAN DEFAULT FALSE,
                approved_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 5. Knowledge Gaps
            """
            CREATE TABLE IF NOT EXISTS ai_knowledge_gaps (
                id VARCHAR(20) PRIMARY KEY,
                topic VARCHAR(200) NOT NULL,
                description TEXT,
                frequency INTEGER DEFAULT 1,
                example_queries TEXT[],
                suggested_content TEXT,
                priority VARCHAR(20) DEFAULT 'medium',
                status VARCHAR(20) DEFAULT 'open',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP WITH TIME ZONE,
                resolved_by INTEGER REFERENCES users(id)
            );
            """,

            # 6. Model Versions
            """
            CREATE TABLE IF NOT EXISTS ai_model_versions (
                version VARCHAR(30) PRIMARY KEY,
                base_model VARCHAR(50) NOT NULL,
                fine_tuned BOOLEAN DEFAULT FALSE,
                training_examples_count INTEGER DEFAULT 0,
                performance_metrics JSONB,
                deployed_at TIMESTAMP WITH TIME ZONE,
                status VARCHAR(20) DEFAULT 'draft',
                notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # =================================================================
            # Continuous Learning Tables
            # =================================================================

            # 7. Improvement Opportunities
            """
            CREATE TABLE IF NOT EXISTS ai_improvement_opportunities (
                id VARCHAR(20) PRIMARY KEY,
                action_type VARCHAR(30) NOT NULL,
                priority VARCHAR(20) NOT NULL,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                impact_estimate TEXT,
                confidence NUMERIC(4,3) DEFAULT 0.0,
                evidence JSONB,
                suggested_implementation TEXT,
                auto_executable BOOLEAN DEFAULT FALSE,
                status VARCHAR(20) DEFAULT 'identified',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP WITH TIME ZONE,
                approved_by INTEGER REFERENCES users(id),
                completed_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 8. Learning Cycles
            """
            CREATE TABLE IF NOT EXISTS ai_learning_cycles (
                id VARCHAR(20) PRIMARY KEY,
                started_at TIMESTAMP WITH TIME ZONE NOT NULL,
                completed_at TIMESTAMP WITH TIME ZONE,
                period_hours INTEGER,
                total_conversations INTEGER DEFAULT 0,
                successful_conversations INTEGER DEFAULT 0,
                failed_conversations INTEGER DEFAULT 0,
                opportunities_identified INTEGER DEFAULT 0,
                actions_taken INTEGER DEFAULT 0,
                recommendations TEXT[],
                next_cycle_scheduled TIMESTAMP WITH TIME ZONE
            );
            """,

            # 9. Conversation Analysis
            """
            CREATE TABLE IF NOT EXISTS ai_conversation_analysis (
                id SERIAL PRIMARY KEY,
                conversation_id VARCHAR(50) NOT NULL,
                analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                outcome VARCHAR(30),
                quality_score NUMERIC(4,3),
                caller_satisfaction NUMERIC(3,2),
                failure_reasons TEXT[],
                knowledge_gaps TEXT[],
                extracted_intents TEXT[],
                recommendations TEXT[]
            );
            """,

            # =================================================================
            # Indices
            # =================================================================
            "CREATE INDEX IF NOT EXISTS idx_voice_exp_status ON voice_experiments(status);",
            "CREATE INDEX IF NOT EXISTS idx_voice_exp_type ON voice_experiments(experiment_type);",
            "CREATE INDEX IF NOT EXISTS idx_voice_variant_exp ON voice_experiment_variants(experiment_id);",
            "CREATE INDEX IF NOT EXISTS idx_voice_result_exp ON voice_experiment_results(experiment_id);",
            "CREATE INDEX IF NOT EXISTS idx_voice_result_variant ON voice_experiment_results(variant_id);",
            "CREATE INDEX IF NOT EXISTS idx_voice_result_ts ON voice_experiment_results(timestamp);",
            "CREATE INDEX IF NOT EXISTS idx_training_type ON ai_training_examples(data_type);",
            "CREATE INDEX IF NOT EXISTS idx_training_approved ON ai_training_examples(approved);",
            "CREATE INDEX IF NOT EXISTS idx_knowledge_gap_status ON ai_knowledge_gaps(status);",
            "CREATE INDEX IF NOT EXISTS idx_knowledge_gap_priority ON ai_knowledge_gaps(priority);",
            "CREATE INDEX IF NOT EXISTS idx_model_status ON ai_model_versions(status);",
            "CREATE INDEX IF NOT EXISTS idx_opportunity_status ON ai_improvement_opportunities(status);",
            "CREATE INDEX IF NOT EXISTS idx_opportunity_priority ON ai_improvement_opportunities(priority);",
            "CREATE INDEX IF NOT EXISTS idx_learning_cycle_date ON ai_learning_cycles(started_at);",
            "CREATE INDEX IF NOT EXISTS idx_conv_analysis_id ON ai_conversation_analysis(conversation_id);",
        ]


def run_migration():
    """Create Phase 4 tables"""
    sql_commands = get_sql_commands()

    try:
        with engine.connect() as conn:
            for idx, sql in enumerate(sql_commands, 1):
                try:
                    logger.info(f"Executing command {idx}/{len(sql_commands)}...")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"Command {idx} executed successfully")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        logger.info(f"Command {idx} skipped (already exists)")
                    else:
                        logger.error(f"Error executing command {idx}: {e}")
                    continue

        logger.info("Phase 4 tables migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("  PHASE 4 DATABASE MIGRATION")
    logger.info("  Tables: Voice A/B Testing, AI Learning, Continuous Learning")
    logger.info("=" * 60)
    logger.info(f"Database: {'SQLite' if is_sqlite else 'PostgreSQL'}")
    logger.info("")

    success = run_migration()

    if success:
        logger.info("")
        logger.info("=" * 60)
        logger.info("  MIGRATION COMPLETE")
        logger.info("=" * 60)
        logger.info("Tables created:")
        logger.info("  Voice A/B Testing:")
        logger.info("    - voice_experiments")
        logger.info("    - voice_experiment_variants")
        logger.info("    - voice_experiment_results")
        logger.info("  AI Learning:")
        logger.info("    - ai_training_examples")
        logger.info("    - ai_knowledge_gaps")
        logger.info("    - ai_model_versions")
        logger.info("  Continuous Learning:")
        logger.info("    - ai_improvement_opportunities")
        logger.info("    - ai_learning_cycles")
        logger.info("    - ai_conversation_analysis")
        logger.info("")
    else:
        logger.error("Migration failed!")
        sys.exit(1)
