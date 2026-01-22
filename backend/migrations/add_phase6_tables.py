"""
Migration: Add Phase 6 Tables
Creates tables for:
- Advanced Workflow Orchestration
- Predictive AI & Recommendations
- AI Agent Coordination
- Self-Healing System
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
            # Workflow Orchestration Tables
            # =================================================================

            # 1. Workflow Definitions
            """
            CREATE TABLE IF NOT EXISTS workflow_definitions (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                version INTEGER DEFAULT 1,
                description TEXT,
                start_step_id VARCHAR(50),
                input_schema TEXT,
                output_schema TEXT,
                max_duration_seconds INTEGER DEFAULT 86400,
                max_concurrent_instances INTEGER DEFAULT 100,
                is_active BOOLEAN DEFAULT FALSE,
                tags TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 2. Workflow Steps
            """
            CREATE TABLE IF NOT EXISTS workflow_steps (
                id VARCHAR(50) PRIMARY KEY,
                workflow_id VARCHAR(50) NOT NULL,
                name VARCHAR(100) NOT NULL,
                step_type VARCHAR(30) NOT NULL,
                config TEXT,
                next_steps TEXT,
                on_success VARCHAR(50),
                on_failure VARCHAR(50),
                on_timeout VARCHAR(50),
                branches TEXT,
                retry_count INTEGER DEFAULT 0,
                retry_delay_seconds INTEGER DEFAULT 60,
                timeout_seconds INTEGER DEFAULT 300,
                description TEXT,
                tags TEXT,
                FOREIGN KEY (workflow_id) REFERENCES workflow_definitions(id) ON DELETE CASCADE
            );
            """,

            # 3. Workflow Instances
            """
            CREATE TABLE IF NOT EXISTS workflow_instances (
                id VARCHAR(50) PRIMARY KEY,
                workflow_id VARCHAR(50) NOT NULL,
                workflow_version INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                current_step_id VARCHAR(50),
                input_data TEXT,
                context TEXT,
                output_data TEXT,
                trigger_type VARCHAR(20) DEFAULT 'manual',
                trigger_data TEXT,
                error TEXT,
                error_step_id VARCHAR(50),
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                paused_at TIMESTAMP,
                FOREIGN KEY (workflow_id) REFERENCES workflow_definitions(id)
            );
            """,

            # 4. Step Executions
            """
            CREATE TABLE IF NOT EXISTS workflow_step_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id VARCHAR(50) NOT NULL,
                step_id VARCHAR(50) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                input_data TEXT,
                output_data TEXT,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (instance_id) REFERENCES workflow_instances(id) ON DELETE CASCADE
            );
            """,

            # =================================================================
            # Predictive AI Tables
            # =================================================================

            # 5. Predictions
            """
            CREATE TABLE IF NOT EXISTS ai_predictions (
                id VARCHAR(50) PRIMARY KEY,
                prediction_type VARCHAR(30) NOT NULL,
                entity_type VARCHAR(30) NOT NULL,
                entity_id VARCHAR(50) NOT NULL,
                predicted_value TEXT,
                probability REAL,
                confidence REAL DEFAULT 0.0,
                contributing_factors TEXT,
                explanation TEXT,
                model_version VARCHAR(30) DEFAULT '1.0',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            );
            """,

            # 6. Recommendations
            """
            CREATE TABLE IF NOT EXISTS ai_recommendations (
                id VARCHAR(50) PRIMARY KEY,
                recommendation_type VARCHAR(30) NOT NULL,
                entity_type VARCHAR(30) NOT NULL,
                entity_id VARCHAR(50) NOT NULL,
                action VARCHAR(50) NOT NULL,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                priority VARCHAR(20) DEFAULT 'medium',
                expected_impact TEXT,
                impact_score REAL DEFAULT 0.0,
                confidence REAL DEFAULT 0.0,
                context TEXT,
                supporting_data TEXT,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                acted_on_at TIMESTAMP
            );
            """,

            # 7. Proactive Alerts
            """
            CREATE TABLE IF NOT EXISTS ai_proactive_alerts (
                id VARCHAR(50) PRIMARY KEY,
                user_id INTEGER NOT NULL,
                alert_type VARCHAR(50) NOT NULL,
                title VARCHAR(200) NOT NULL,
                message TEXT,
                priority VARCHAR(20) DEFAULT 'medium',
                entity_type VARCHAR(30),
                entity_id VARCHAR(50),
                is_read BOOLEAN DEFAULT FALSE,
                is_dismissed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read_at TIMESTAMP
            );
            """,

            # =================================================================
            # AI Agent Coordination Tables
            # =================================================================

            # 8. AI Agents
            """
            CREATE TABLE IF NOT EXISTS ai_agents (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                agent_type VARCHAR(30) NOT NULL,
                status VARCHAR(20) DEFAULT 'offline',
                capabilities TEXT,
                specializations TEXT,
                max_load INTEGER DEFAULT 10,
                current_load INTEGER DEFAULT 0,
                total_tasks_completed INTEGER DEFAULT 0,
                total_tasks_failed INTEGER DEFAULT 0,
                avg_response_time_ms REAL DEFAULT 0.0,
                success_rate REAL DEFAULT 1.0,
                priority_weight REAL DEFAULT 1.0,
                context TEXT,
                last_active_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 9. Agent Tasks
            """
            CREATE TABLE IF NOT EXISTS ai_agent_tasks (
                id VARCHAR(50) PRIMARY KEY,
                task_type VARCHAR(50) NOT NULL,
                priority INTEGER DEFAULT 3,
                status VARCHAR(20) DEFAULT 'pending',
                input_data TEXT,
                output_data TEXT,
                context TEXT,
                assigned_agent_id VARCHAR(50),
                required_capabilities TEXT,
                preferred_agent_type VARCHAR(30),
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                error TEXT,
                parent_task_id VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                deadline TIMESTAMP,
                FOREIGN KEY (assigned_agent_id) REFERENCES ai_agents(id)
            );
            """,

            # 10. Agent Messages
            """
            CREATE TABLE IF NOT EXISTS ai_agent_messages (
                id VARCHAR(50) PRIMARY KEY,
                message_type VARCHAR(20) NOT NULL,
                from_agent_id VARCHAR(50) NOT NULL,
                to_agent_id VARCHAR(50),
                subject VARCHAR(200),
                payload TEXT,
                context TEXT,
                correlation_id VARCHAR(50),
                requires_response BOOLEAN DEFAULT FALSE,
                response_deadline TIMESTAMP,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read_at TIMESTAMP
            );
            """,

            # 11. Collaboration Sessions
            """
            CREATE TABLE IF NOT EXISTS ai_collaboration_sessions (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                goal TEXT,
                participating_agents TEXT,
                lead_agent_id VARCHAR(50),
                current_phase VARCHAR(50) DEFAULT 'initialization',
                shared_context TEXT,
                decisions TEXT,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
            """,

            # =================================================================
            # Self-Healing System Tables
            # =================================================================

            # 12. System Components
            """
            CREATE TABLE IF NOT EXISTS system_components (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                component_type VARCHAR(30) NOT NULL,
                critical BOOLEAN DEFAULT FALSE,
                dependencies TEXT,
                health_check_config TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 13. Health Checks
            """
            CREATE TABLE IF NOT EXISTS health_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                component_id VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL,
                message TEXT,
                response_time_ms REAL DEFAULT 0.0,
                error_rate REAL DEFAULT 0.0,
                last_error TEXT,
                details TEXT,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (component_id) REFERENCES system_components(id) ON DELETE CASCADE
            );
            """,

            # 14. Incidents
            """
            CREATE TABLE IF NOT EXISTS system_incidents (
                id VARCHAR(50) PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                severity VARCHAR(20) NOT NULL,
                status VARCHAR(20) DEFAULT 'detected',
                affected_components TEXT,
                error_type VARCHAR(100),
                error_message TEXT,
                stack_trace TEXT,
                healing_attempts INTEGER DEFAULT 0,
                healing_actions_taken TEXT,
                auto_healed BOOLEAN DEFAULT FALSE,
                escalated_to VARCHAR(100),
                resolution TEXT,
                root_cause TEXT,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                acknowledged_at TIMESTAMP,
                resolved_at TIMESTAMP,
                escalated_at TIMESTAMP
            );
            """,

            # 15. Circuit Breakers
            """
            CREATE TABLE IF NOT EXISTS circuit_breakers (
                component_id VARCHAR(50) PRIMARY KEY,
                state VARCHAR(20) DEFAULT 'closed',
                failure_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failure_threshold INTEGER DEFAULT 5,
                recovery_timeout_seconds INTEGER DEFAULT 60,
                success_threshold INTEGER DEFAULT 3,
                last_failure_at TIMESTAMP,
                opened_at TIMESTAMP,
                half_open_at TIMESTAMP,
                FOREIGN KEY (component_id) REFERENCES system_components(id) ON DELETE CASCADE
            );
            """,

            # 16. Healing Playbooks
            """
            CREATE TABLE IF NOT EXISTS healing_playbooks (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                trigger_error_types TEXT,
                trigger_component_types TEXT,
                actions TEXT,
                max_retries INTEGER DEFAULT 3,
                retry_delay_seconds INTEGER DEFAULT 10,
                escalate_on_failure BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 17. Healing Actions Log
            """
            CREATE TABLE IF NOT EXISTS healing_actions_log (
                id VARCHAR(50) PRIMARY KEY,
                incident_id VARCHAR(50) NOT NULL,
                action_type VARCHAR(30) NOT NULL,
                target_component VARCHAR(50),
                parameters TEXT,
                status VARCHAR(20) DEFAULT 'pending',
                result TEXT,
                error TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (incident_id) REFERENCES system_incidents(id) ON DELETE CASCADE
            );
            """,

            # =================================================================
            # Indices
            # =================================================================
            "CREATE INDEX IF NOT EXISTS idx_wf_instances_workflow ON workflow_instances(workflow_id);",
            "CREATE INDEX IF NOT EXISTS idx_wf_instances_status ON workflow_instances(status);",
            "CREATE INDEX IF NOT EXISTS idx_wf_steps_workflow ON workflow_steps(workflow_id);",
            "CREATE INDEX IF NOT EXISTS idx_step_exec_instance ON workflow_step_executions(instance_id);",
            "CREATE INDEX IF NOT EXISTS idx_predictions_entity ON ai_predictions(entity_type, entity_id);",
            "CREATE INDEX IF NOT EXISTS idx_predictions_type ON ai_predictions(prediction_type);",
            "CREATE INDEX IF NOT EXISTS idx_recommendations_entity ON ai_recommendations(entity_type, entity_id);",
            "CREATE INDEX IF NOT EXISTS idx_recommendations_status ON ai_recommendations(status);",
            "CREATE INDEX IF NOT EXISTS idx_alerts_user ON ai_proactive_alerts(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_alerts_read ON ai_proactive_alerts(is_read);",
            "CREATE INDEX IF NOT EXISTS idx_agents_type ON ai_agents(agent_type);",
            "CREATE INDEX IF NOT EXISTS idx_agents_status ON ai_agents(status);",
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON ai_agent_tasks(status);",
            "CREATE INDEX IF NOT EXISTS idx_tasks_agent ON ai_agent_tasks(assigned_agent_id);",
            "CREATE INDEX IF NOT EXISTS idx_messages_to ON ai_agent_messages(to_agent_id);",
            "CREATE INDEX IF NOT EXISTS idx_collab_status ON ai_collaboration_sessions(status);",
            "CREATE INDEX IF NOT EXISTS idx_health_component ON health_checks(component_id);",
            "CREATE INDEX IF NOT EXISTS idx_incidents_status ON system_incidents(status);",
            "CREATE INDEX IF NOT EXISTS idx_incidents_severity ON system_incidents(severity);",
        ]
    else:
        # PostgreSQL syntax
        return [
            # =================================================================
            # Workflow Orchestration Tables
            # =================================================================

            # 1. Workflow Definitions
            """
            CREATE TABLE IF NOT EXISTS workflow_definitions (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                version INTEGER DEFAULT 1,
                description TEXT,
                start_step_id VARCHAR(50),
                input_schema JSONB,
                output_schema JSONB,
                max_duration_seconds INTEGER DEFAULT 86400,
                max_concurrent_instances INTEGER DEFAULT 100,
                is_active BOOLEAN DEFAULT FALSE,
                tags TEXT[],
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 2. Workflow Steps
            """
            CREATE TABLE IF NOT EXISTS workflow_steps (
                id VARCHAR(50) PRIMARY KEY,
                workflow_id VARCHAR(50) NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
                name VARCHAR(100) NOT NULL,
                step_type VARCHAR(30) NOT NULL,
                config JSONB,
                next_steps TEXT[],
                on_success VARCHAR(50),
                on_failure VARCHAR(50),
                on_timeout VARCHAR(50),
                branches JSONB,
                retry_count INTEGER DEFAULT 0,
                retry_delay_seconds INTEGER DEFAULT 60,
                timeout_seconds INTEGER DEFAULT 300,
                description TEXT,
                tags TEXT[]
            );
            """,

            # 3. Workflow Instances
            """
            CREATE TABLE IF NOT EXISTS workflow_instances (
                id VARCHAR(50) PRIMARY KEY,
                workflow_id VARCHAR(50) NOT NULL REFERENCES workflow_definitions(id),
                workflow_version INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                current_step_id VARCHAR(50),
                input_data JSONB,
                context JSONB,
                output_data JSONB,
                trigger_type VARCHAR(20) DEFAULT 'manual',
                trigger_data JSONB,
                error TEXT,
                error_step_id VARCHAR(50),
                started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP WITH TIME ZONE,
                paused_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 4. Step Executions
            """
            CREATE TABLE IF NOT EXISTS workflow_step_executions (
                id SERIAL PRIMARY KEY,
                instance_id VARCHAR(50) NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
                step_id VARCHAR(50) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                input_data JSONB,
                output_data JSONB,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # =================================================================
            # Predictive AI Tables
            # =================================================================

            # 5. Predictions
            """
            CREATE TABLE IF NOT EXISTS ai_predictions (
                id VARCHAR(50) PRIMARY KEY,
                prediction_type VARCHAR(30) NOT NULL,
                entity_type VARCHAR(30) NOT NULL,
                entity_id VARCHAR(50) NOT NULL,
                predicted_value JSONB,
                probability NUMERIC(4,3),
                confidence NUMERIC(4,3) DEFAULT 0.0,
                contributing_factors JSONB,
                explanation TEXT,
                model_version VARCHAR(30) DEFAULT '1.0',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 6. Recommendations
            """
            CREATE TABLE IF NOT EXISTS ai_recommendations (
                id VARCHAR(50) PRIMARY KEY,
                recommendation_type VARCHAR(30) NOT NULL,
                entity_type VARCHAR(30) NOT NULL,
                entity_id VARCHAR(50) NOT NULL,
                action VARCHAR(50) NOT NULL,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                priority VARCHAR(20) DEFAULT 'medium',
                expected_impact TEXT,
                impact_score NUMERIC(4,3) DEFAULT 0.0,
                confidence NUMERIC(4,3) DEFAULT 0.0,
                context JSONB,
                supporting_data JSONB,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP WITH TIME ZONE,
                acted_on_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 7. Proactive Alerts
            """
            CREATE TABLE IF NOT EXISTS ai_proactive_alerts (
                id VARCHAR(50) PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                alert_type VARCHAR(50) NOT NULL,
                title VARCHAR(200) NOT NULL,
                message TEXT,
                priority VARCHAR(20) DEFAULT 'medium',
                entity_type VARCHAR(30),
                entity_id VARCHAR(50),
                is_read BOOLEAN DEFAULT FALSE,
                is_dismissed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                read_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # =================================================================
            # AI Agent Coordination Tables
            # =================================================================

            # 8. AI Agents
            """
            CREATE TABLE IF NOT EXISTS ai_agents (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                agent_type VARCHAR(30) NOT NULL,
                status VARCHAR(20) DEFAULT 'offline',
                capabilities JSONB,
                specializations TEXT[],
                max_load INTEGER DEFAULT 10,
                current_load INTEGER DEFAULT 0,
                total_tasks_completed INTEGER DEFAULT 0,
                total_tasks_failed INTEGER DEFAULT 0,
                avg_response_time_ms NUMERIC(10,2) DEFAULT 0.0,
                success_rate NUMERIC(4,3) DEFAULT 1.0,
                priority_weight NUMERIC(4,2) DEFAULT 1.0,
                context JSONB,
                last_active_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 9. Agent Tasks
            """
            CREATE TABLE IF NOT EXISTS ai_agent_tasks (
                id VARCHAR(50) PRIMARY KEY,
                task_type VARCHAR(50) NOT NULL,
                priority INTEGER DEFAULT 3,
                status VARCHAR(20) DEFAULT 'pending',
                input_data JSONB,
                output_data JSONB,
                context JSONB,
                assigned_agent_id VARCHAR(50) REFERENCES ai_agents(id),
                required_capabilities TEXT[],
                preferred_agent_type VARCHAR(30),
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                error TEXT,
                parent_task_id VARCHAR(50),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                assigned_at TIMESTAMP WITH TIME ZONE,
                started_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE,
                deadline TIMESTAMP WITH TIME ZONE
            );
            """,

            # 10. Agent Messages
            """
            CREATE TABLE IF NOT EXISTS ai_agent_messages (
                id VARCHAR(50) PRIMARY KEY,
                message_type VARCHAR(20) NOT NULL,
                from_agent_id VARCHAR(50) NOT NULL,
                to_agent_id VARCHAR(50),
                subject VARCHAR(200),
                payload JSONB,
                context JSONB,
                correlation_id VARCHAR(50),
                requires_response BOOLEAN DEFAULT FALSE,
                response_deadline TIMESTAMP WITH TIME ZONE,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                read_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 11. Collaboration Sessions
            """
            CREATE TABLE IF NOT EXISTS ai_collaboration_sessions (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                goal TEXT,
                participating_agents TEXT[],
                lead_agent_id VARCHAR(50),
                current_phase VARCHAR(50) DEFAULT 'initialization',
                shared_context JSONB,
                decisions JSONB,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # =================================================================
            # Self-Healing System Tables
            # =================================================================

            # 12. System Components
            """
            CREATE TABLE IF NOT EXISTS system_components (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                component_type VARCHAR(30) NOT NULL,
                critical BOOLEAN DEFAULT FALSE,
                dependencies TEXT[],
                health_check_config JSONB,
                registered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 13. Health Checks
            """
            CREATE TABLE IF NOT EXISTS health_checks (
                id SERIAL PRIMARY KEY,
                component_id VARCHAR(50) NOT NULL REFERENCES system_components(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL,
                message TEXT,
                response_time_ms NUMERIC(10,2) DEFAULT 0.0,
                error_rate NUMERIC(5,4) DEFAULT 0.0,
                last_error TEXT,
                details JSONB,
                checked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 14. Incidents
            """
            CREATE TABLE IF NOT EXISTS system_incidents (
                id VARCHAR(50) PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                severity VARCHAR(20) NOT NULL,
                status VARCHAR(20) DEFAULT 'detected',
                affected_components TEXT[],
                error_type VARCHAR(100),
                error_message TEXT,
                stack_trace TEXT,
                healing_attempts INTEGER DEFAULT 0,
                healing_actions_taken JSONB,
                auto_healed BOOLEAN DEFAULT FALSE,
                escalated_to VARCHAR(100),
                resolution TEXT,
                root_cause TEXT,
                detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                acknowledged_at TIMESTAMP WITH TIME ZONE,
                resolved_at TIMESTAMP WITH TIME ZONE,
                escalated_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 15. Circuit Breakers
            """
            CREATE TABLE IF NOT EXISTS circuit_breakers (
                component_id VARCHAR(50) PRIMARY KEY REFERENCES system_components(id) ON DELETE CASCADE,
                state VARCHAR(20) DEFAULT 'closed',
                failure_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failure_threshold INTEGER DEFAULT 5,
                recovery_timeout_seconds INTEGER DEFAULT 60,
                success_threshold INTEGER DEFAULT 3,
                last_failure_at TIMESTAMP WITH TIME ZONE,
                opened_at TIMESTAMP WITH TIME ZONE,
                half_open_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 16. Healing Playbooks
            """
            CREATE TABLE IF NOT EXISTS healing_playbooks (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                trigger_error_types TEXT[],
                trigger_component_types TEXT[],
                actions JSONB,
                max_retries INTEGER DEFAULT 3,
                retry_delay_seconds INTEGER DEFAULT 10,
                escalate_on_failure BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 17. Healing Actions Log
            """
            CREATE TABLE IF NOT EXISTS healing_actions_log (
                id VARCHAR(50) PRIMARY KEY,
                incident_id VARCHAR(50) NOT NULL REFERENCES system_incidents(id) ON DELETE CASCADE,
                action_type VARCHAR(30) NOT NULL,
                target_component VARCHAR(50),
                parameters JSONB,
                status VARCHAR(20) DEFAULT 'pending',
                result TEXT,
                error TEXT,
                started_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # =================================================================
            # Indices
            # =================================================================
            "CREATE INDEX IF NOT EXISTS idx_wf_instances_workflow ON workflow_instances(workflow_id);",
            "CREATE INDEX IF NOT EXISTS idx_wf_instances_status ON workflow_instances(status);",
            "CREATE INDEX IF NOT EXISTS idx_wf_steps_workflow ON workflow_steps(workflow_id);",
            "CREATE INDEX IF NOT EXISTS idx_step_exec_instance ON workflow_step_executions(instance_id);",
            "CREATE INDEX IF NOT EXISTS idx_predictions_entity ON ai_predictions(entity_type, entity_id);",
            "CREATE INDEX IF NOT EXISTS idx_predictions_type ON ai_predictions(prediction_type);",
            "CREATE INDEX IF NOT EXISTS idx_recommendations_entity ON ai_recommendations(entity_type, entity_id);",
            "CREATE INDEX IF NOT EXISTS idx_recommendations_status ON ai_recommendations(status);",
            "CREATE INDEX IF NOT EXISTS idx_alerts_user ON ai_proactive_alerts(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_alerts_read ON ai_proactive_alerts(is_read);",
            "CREATE INDEX IF NOT EXISTS idx_agents_type ON ai_agents(agent_type);",
            "CREATE INDEX IF NOT EXISTS idx_agents_status ON ai_agents(status);",
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON ai_agent_tasks(status);",
            "CREATE INDEX IF NOT EXISTS idx_tasks_agent ON ai_agent_tasks(assigned_agent_id);",
            "CREATE INDEX IF NOT EXISTS idx_messages_to ON ai_agent_messages(to_agent_id);",
            "CREATE INDEX IF NOT EXISTS idx_collab_status ON ai_collaboration_sessions(status);",
            "CREATE INDEX IF NOT EXISTS idx_health_component ON health_checks(component_id);",
            "CREATE INDEX IF NOT EXISTS idx_incidents_status ON system_incidents(status);",
            "CREATE INDEX IF NOT EXISTS idx_incidents_severity ON system_incidents(severity);",
        ]


def run_migration():
    """Create Phase 6 tables"""
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

        logger.info("Phase 6 tables migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("  PHASE 6 DATABASE MIGRATION")
    logger.info("  Tables: Workflow, Predictive AI, Agent Coordination, Self-Healing")
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
        logger.info("  Workflow Orchestration:")
        logger.info("    - workflow_definitions")
        logger.info("    - workflow_steps")
        logger.info("    - workflow_instances")
        logger.info("    - workflow_step_executions")
        logger.info("  Predictive AI:")
        logger.info("    - ai_predictions")
        logger.info("    - ai_recommendations")
        logger.info("    - ai_proactive_alerts")
        logger.info("  Agent Coordination:")
        logger.info("    - ai_agents")
        logger.info("    - ai_agent_tasks")
        logger.info("    - ai_agent_messages")
        logger.info("    - ai_collaboration_sessions")
        logger.info("  Self-Healing:")
        logger.info("    - system_components")
        logger.info("    - health_checks")
        logger.info("    - system_incidents")
        logger.info("    - circuit_breakers")
        logger.info("    - healing_playbooks")
        logger.info("    - healing_actions_log")
        logger.info("")
    else:
        logger.error("Migration failed!")
        sys.exit(1)
