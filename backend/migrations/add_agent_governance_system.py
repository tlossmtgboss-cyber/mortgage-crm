"""
Migration: Add Agent Governance & Management System Tables
Creates comprehensive infrastructure for agent profiles, governance, gym testing,
metrics, alerts, and chat functionality.
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
    """Create Agent Governance & Management System tables"""

    sql_commands = [
        # ============================================================================
        # 1. AGENT PROFILES - Core agent metadata and configuration
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS agent_profiles (
            id SERIAL PRIMARY KEY,
            agent_name VARCHAR(100) UNIQUE NOT NULL,
            display_name VARCHAR(200),
            description TEXT,
            role TEXT,

            -- Classification
            category VARCHAR(50),  -- 'crm', 'analytics', 'communication', 'operations'
            risk_tier VARCHAR(10) DEFAULT '2',  -- '1', '2', '2-3', '3'

            -- Configuration
            tool_file VARCHAR(100),
            tool_count INTEGER DEFAULT 0,
            version VARCHAR(20) DEFAULT '1.0.0',
            config JSONB DEFAULT '{}',

            -- Status
            status VARCHAR(20) DEFAULT 'active',  -- active, paused, testing, deprecated
            health_status VARCHAR(20) DEFAULT 'unknown',  -- healthy, warning, critical, offline, unknown
            elite_status BOOLEAN DEFAULT FALSE,
            production_approved BOOLEAN DEFAULT FALSE,

            -- Deployment
            deployed_at TIMESTAMP WITH TIME ZONE,
            deployed_by VARCHAR(100),
            last_health_check TIMESTAMP WITH TIME ZONE,

            -- Thresholds
            production_threshold JSONB DEFAULT '{"task_success_rate": 90, "response_time_p95": 5000}',
            elite_threshold JSONB DEFAULT '{"task_success_rate": 97, "response_time_p95": 2000}',

            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # ============================================================================
        # 2. AGENT TOOLS - Tool registry for each agent
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS agent_tools (
            id SERIAL PRIMARY KEY,
            agent_id INTEGER REFERENCES agent_profiles(id) ON DELETE CASCADE,
            tool_name VARCHAR(100) NOT NULL,
            tool_description TEXT,

            -- Classification
            category VARCHAR(50),  -- 'query', 'action', 'analysis', 'communication', 'workflow'
            risk_level VARCHAR(20) DEFAULT 'low',  -- low, medium, high, critical

            -- Schema
            input_schema JSONB NOT NULL DEFAULT '{}',
            output_schema JSONB DEFAULT '{}',

            -- Configuration
            requires_approval BOOLEAN DEFAULT FALSE,
            requires_confirmation BOOLEAN DEFAULT FALSE,
            cooldown_seconds INTEGER DEFAULT 0,
            max_per_hour INTEGER,
            enabled BOOLEAN DEFAULT TRUE,

            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(agent_id, tool_name)
        );
        """,

        # ============================================================================
        # 3. AGENT EXECUTIONS - Detailed execution audit trail
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS agent_executions (
            id SERIAL PRIMARY KEY,
            execution_id UUID DEFAULT gen_random_uuid() UNIQUE,

            -- Agent Context
            agent_id INTEGER REFERENCES agent_profiles(id) ON DELETE SET NULL,
            agent_name VARCHAR(100) NOT NULL,
            tool_name VARCHAR(100),

            -- Request
            user_id INTEGER,
            session_id UUID,
            input_text TEXT,
            input_context JSONB,

            -- Response
            output_text TEXT,
            output_metadata JSONB,

            -- Execution Details
            trajectory JSONB,  -- Full state machine path
            tool_calls JSONB,  -- Array of tool calls with params and results
            model_calls JSONB,  -- LLM API calls made

            -- Outcome
            status VARCHAR(20) DEFAULT 'pending',  -- pending, running, completed, failed, cancelled
            success BOOLEAN,
            failure_type VARCHAR(50),
            failure_reason TEXT,
            escalated BOOLEAN DEFAULT FALSE,
            escalation_reason TEXT,

            -- Performance
            response_time_ms INTEGER,
            total_cost DECIMAL(10, 4),

            -- Cost breakdown
            cost_model_calls DECIMAL(10, 4) DEFAULT 0,
            cost_tool_execution DECIMAL(10, 4) DEFAULT 0,
            cost_retrieval DECIMAL(10, 4) DEFAULT 0,

            -- Decision Provenance
            reasoning TEXT,
            confidence_score DECIMAL(5, 2),
            evidence JSONB,

            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP WITH TIME ZONE
        );
        """,

        # ============================================================================
        # 4. GYM TEST SCENARIOS - Test case definitions
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS gym_test_scenarios (
            id SERIAL PRIMARY KEY,
            scenario_id UUID DEFAULT gen_random_uuid() UNIQUE,

            -- Target
            agent_id INTEGER REFERENCES agent_profiles(id) ON DELETE CASCADE,
            agent_name VARCHAR(100),  -- Allow null for cross-agent scenarios
            scenario_name VARCHAR(200) NOT NULL,

            -- Classification
            category VARCHAR(50) NOT NULL,  -- 'happy_path', 'edge_case', 'adversarial', 'cost_stress', 'latency_stress'
            priority VARCHAR(20) DEFAULT 'medium',  -- low, medium, high, critical
            difficulty VARCHAR(20) DEFAULT 'medium',  -- easy, medium, hard

            -- Test Definition
            input_text TEXT NOT NULL,
            input_context JSONB,
            expected_output TEXT,
            expected_behavior JSONB,

            -- Validation
            success_criteria JSONB NOT NULL DEFAULT '{"must_succeed": true}',
            max_response_time_ms INTEGER,
            max_cost DECIMAL(10, 4),

            -- Status
            enabled BOOLEAN DEFAULT TRUE,
            last_run TIMESTAMP WITH TIME ZONE,
            last_result VARCHAR(20),  -- pass, fail, error
            pass_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,

            -- Source
            created_from_failure_id INTEGER,
            tags JSONB,

            -- Metadata
            created_by VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # ============================================================================
        # 5. GYM TEST RUNS - Test execution records
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS gym_test_runs (
            id SERIAL PRIMARY KEY,
            run_id UUID DEFAULT gen_random_uuid() UNIQUE,

            -- Target
            agent_id INTEGER REFERENCES agent_profiles(id) ON DELETE SET NULL,
            agent_name VARCHAR(100),

            -- Configuration
            scenario_ids JSONB,  -- List of scenario IDs or null for all
            triggered_by VARCHAR(50),  -- manual, scheduled, deployment, on_change
            triggered_by_user_id INTEGER,

            -- Status
            status VARCHAR(20) DEFAULT 'pending',  -- pending, running, completed, failed, cancelled

            -- Results Summary
            total_scenarios INTEGER DEFAULT 0,
            passed INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0,
            pass_rate DECIMAL(5, 2),

            -- Performance
            total_duration_ms INTEGER,
            avg_response_time_ms INTEGER,
            total_cost DECIMAL(10, 4),

            -- Version Info
            agent_version VARCHAR(20),
            model_version VARCHAR(50),

            -- Deployment Gate
            deployment_gate_passed BOOLEAN,
            blocking_issues JSONB,

            -- Metadata
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # ============================================================================
        # 6. GYM TEST RESULTS - Per-scenario results
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS gym_test_results (
            id SERIAL PRIMARY KEY,
            result_id UUID DEFAULT gen_random_uuid() UNIQUE,

            -- References
            run_id UUID REFERENCES gym_test_runs(run_id) ON DELETE CASCADE,
            scenario_id UUID REFERENCES gym_test_scenarios(scenario_id) ON DELETE SET NULL,
            execution_id UUID REFERENCES agent_executions(execution_id) ON DELETE SET NULL,

            -- Result
            result VARCHAR(20) NOT NULL,  -- pass, fail, error
            passed BOOLEAN NOT NULL,
            score DECIMAL(5, 2),

            -- Details
            actual_output TEXT,
            validation_details JSONB,  -- Which criteria passed/failed

            -- Performance
            response_time_ms INTEGER,
            cost DECIMAL(10, 4),

            -- Failure Info
            failure_reason TEXT,
            error_message TEXT,

            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # ============================================================================
        # 7. AGENT ALERTS - Alerts and notifications
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS agent_alerts (
            id SERIAL PRIMARY KEY,
            alert_id UUID DEFAULT gen_random_uuid() UNIQUE,

            -- Source
            agent_id INTEGER REFERENCES agent_profiles(id) ON DELETE CASCADE,
            agent_name VARCHAR(100),

            -- Classification
            alert_type VARCHAR(50) NOT NULL,  -- metric_threshold, failure_spike, compliance_violation, cost_overrun, security
            severity VARCHAR(20) NOT NULL,  -- low, medium, high, critical

            -- Details
            title VARCHAR(500) NOT NULL,
            description TEXT NOT NULL,
            context JSONB,

            -- Metrics Context
            metric_name VARCHAR(100),
            current_value DECIMAL(10, 4),
            threshold_value DECIMAL(10, 4),

            -- Related
            related_execution_ids JSONB,  -- Array of execution UUIDs

            -- Status
            status VARCHAR(20) DEFAULT 'open',  -- open, acknowledged, investigating, resolved, false_alarm
            acknowledged_by INTEGER,
            acknowledged_at TIMESTAMP WITH TIME ZONE,
            resolved_by INTEGER,
            resolved_at TIMESTAMP WITH TIME ZONE,
            resolution_notes TEXT,

            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # ============================================================================
        # 8. AGENT METRICS TIMESERIES - Time-series metrics aggregation
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS agent_metrics_timeseries (
            id SERIAL PRIMARY KEY,

            -- Dimensions
            agent_id INTEGER REFERENCES agent_profiles(id) ON DELETE CASCADE,
            agent_name VARCHAR(100) NOT NULL,
            metric_name VARCHAR(100) NOT NULL,
            time_bucket TIMESTAMP WITH TIME ZONE NOT NULL,
            granularity VARCHAR(20) DEFAULT 'hourly',  -- minutely, hourly, daily, weekly

            -- Core Metrics
            task_success_rate DECIMAL(5, 2),
            tool_success_rate DECIMAL(5, 2),
            grounding_score DECIMAL(5, 2),
            hallucination_rate DECIMAL(5, 2),

            -- Latency
            response_time_p50 INTEGER,
            response_time_p95 INTEGER,
            response_time_p99 INTEGER,

            -- Volume
            total_tasks INTEGER DEFAULT 0,
            successful_tasks INTEGER DEFAULT 0,
            failed_tasks INTEGER DEFAULT 0,

            -- Cost
            cost_per_success DECIMAL(10, 4),
            total_cost DECIMAL(10, 4),

            -- Aggregated Values
            count INTEGER DEFAULT 0,
            sum_value DECIMAL(10, 4) DEFAULT 0,
            avg_value DECIMAL(10, 4),
            min_value DECIMAL(10, 4),
            max_value DECIMAL(10, 4),

            -- Additional Dimensions
            dimensions JSONB,

            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(agent_name, metric_name, time_bucket, granularity)
        );
        """,

        # ============================================================================
        # 9. AGENT CHAT SESSIONS - Chat session tracking
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS agent_chat_sessions (
            id SERIAL PRIMARY KEY,
            session_id UUID DEFAULT gen_random_uuid() UNIQUE,

            -- Participants
            user_id INTEGER,
            agent_id INTEGER REFERENCES agent_profiles(id) ON DELETE SET NULL,
            agent_name VARCHAR(100),  -- Specific agent or null for orchestrator

            -- Status
            status VARCHAR(20) DEFAULT 'active',  -- active, paused, ended

            -- Context
            context JSONB DEFAULT '{}',
            message_count INTEGER DEFAULT 0,

            -- Timing
            started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP WITH TIME ZONE
        );
        """,

        # ============================================================================
        # 10. AGENT CHAT MESSAGES - Chat message history
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS agent_chat_messages (
            id SERIAL PRIMARY KEY,
            message_id UUID DEFAULT gen_random_uuid() UNIQUE,

            -- Session Reference
            session_id UUID REFERENCES agent_chat_sessions(session_id) ON DELETE CASCADE,

            -- Message
            role VARCHAR(20) NOT NULL,  -- user, assistant, system
            content TEXT NOT NULL,

            -- For Assistant Messages
            agent_name VARCHAR(100),
            execution_id UUID REFERENCES agent_executions(execution_id) ON DELETE SET NULL,

            -- Performance
            response_time_ms INTEGER,
            cost DECIMAL(10, 4),
            tool_calls_count INTEGER DEFAULT 0,

            -- Feedback
            feedback_type VARCHAR(20),  -- thumbs_up, thumbs_down, none
            feedback_text TEXT,

            -- Metadata
            metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # ============================================================================
        # 11. TRAINING SCENARIOS - Agent Gym training scenarios
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS training_scenarios (
            id SERIAL PRIMARY KEY,

            -- Scenario identification
            name VARCHAR(200) NOT NULL,
            description TEXT,
            category VARCHAR(50) NOT NULL,  -- communication, processing, compliance, etc.

            -- Target agent
            target_agent_type VARCHAR(100),  -- Can be null for universal scenarios

            -- Difficulty and scoring
            difficulty VARCHAR(20) DEFAULT 'medium',  -- easy, medium, hard, expert
            max_score INTEGER DEFAULT 100,
            time_limit_seconds INTEGER,

            -- Scenario configuration
            input_data JSONB DEFAULT '{}',
            expected_output JSONB DEFAULT '{}',
            evaluation_criteria JSONB DEFAULT '[]',

            -- Status
            is_active BOOLEAN DEFAULT TRUE,

            -- Usage stats
            times_run INTEGER DEFAULT 0,
            avg_score FLOAT,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # ============================================================================
        # 12. TRAINING SESSIONS - Agent Gym session results
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS training_sessions (
            id SERIAL PRIMARY KEY,
            session_id UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,

            -- Agent reference
            agent_id INTEGER REFERENCES agent_profiles(id) ON DELETE CASCADE NOT NULL,
            agent_name VARCHAR(100) NOT NULL,

            -- Scenario reference
            scenario_id INTEGER REFERENCES training_scenarios(id) ON DELETE CASCADE NOT NULL,

            -- Results
            score FLOAT,
            max_score INTEGER DEFAULT 100,
            passed BOOLEAN,
            pass_threshold FLOAT DEFAULT 70.0,

            -- Detailed feedback
            feedback TEXT,
            detailed_results JSONB DEFAULT '{}',

            -- Performance metrics
            duration_seconds FLOAT,
            tokens_used INTEGER DEFAULT 0,
            cost DECIMAL(10, 4) DEFAULT 0,

            -- Session state
            status VARCHAR(20) DEFAULT 'completed',  -- running, completed, failed, cancelled

            -- Timestamps
            started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # ============================================================================
        # INDICES FOR PERFORMANCE
        # ============================================================================

        # Agent profiles indices
        "CREATE INDEX IF NOT EXISTS idx_agent_profiles_name ON agent_profiles(agent_name);",
        "CREATE INDEX IF NOT EXISTS idx_agent_profiles_status ON agent_profiles(status);",
        "CREATE INDEX IF NOT EXISTS idx_agent_profiles_health ON agent_profiles(health_status);",
        "CREATE INDEX IF NOT EXISTS idx_agent_profiles_tier ON agent_profiles(risk_tier);",
        "CREATE INDEX IF NOT EXISTS idx_agent_profiles_elite ON agent_profiles(elite_status);",

        # Agent tools indices
        "CREATE INDEX IF NOT EXISTS idx_agent_tools_agent ON agent_tools(agent_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_tools_name ON agent_tools(tool_name);",
        "CREATE INDEX IF NOT EXISTS idx_agent_tools_risk ON agent_tools(risk_level);",

        # Agent executions indices
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_agent ON agent_executions(agent_name, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_status ON agent_executions(status);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_success ON agent_executions(success);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_user ON agent_executions(user_id, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_session ON agent_executions(session_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_created ON agent_executions(created_at DESC);",

        # Gym scenarios indices
        "CREATE INDEX IF NOT EXISTS idx_gym_scenarios_agent ON gym_test_scenarios(agent_name);",
        "CREATE INDEX IF NOT EXISTS idx_gym_scenarios_category ON gym_test_scenarios(category);",
        "CREATE INDEX IF NOT EXISTS idx_gym_scenarios_enabled ON gym_test_scenarios(enabled);",
        "CREATE INDEX IF NOT EXISTS idx_gym_scenarios_result ON gym_test_scenarios(last_result);",

        # Gym runs indices
        "CREATE INDEX IF NOT EXISTS idx_gym_runs_agent ON gym_test_runs(agent_name, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_gym_runs_status ON gym_test_runs(status);",
        "CREATE INDEX IF NOT EXISTS idx_gym_runs_gate ON gym_test_runs(deployment_gate_passed);",

        # Gym results indices
        "CREATE INDEX IF NOT EXISTS idx_gym_results_run ON gym_test_results(run_id);",
        "CREATE INDEX IF NOT EXISTS idx_gym_results_scenario ON gym_test_results(scenario_id);",
        "CREATE INDEX IF NOT EXISTS idx_gym_results_passed ON gym_test_results(passed);",

        # Alerts indices
        "CREATE INDEX IF NOT EXISTS idx_agent_alerts_agent ON agent_alerts(agent_name, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_agent_alerts_status ON agent_alerts(status);",
        "CREATE INDEX IF NOT EXISTS idx_agent_alerts_severity ON agent_alerts(severity);",
        "CREATE INDEX IF NOT EXISTS idx_agent_alerts_type ON agent_alerts(alert_type);",

        # Metrics timeseries indices
        "CREATE INDEX IF NOT EXISTS idx_metrics_ts_agent_time ON agent_metrics_timeseries(agent_name, time_bucket DESC);",
        "CREATE INDEX IF NOT EXISTS idx_metrics_ts_metric ON agent_metrics_timeseries(metric_name, time_bucket DESC);",
        "CREATE INDEX IF NOT EXISTS idx_metrics_ts_granularity ON agent_metrics_timeseries(granularity);",

        # Chat sessions indices
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON agent_chat_sessions(user_id, started_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_agent ON agent_chat_sessions(agent_name);",
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_status ON agent_chat_sessions(status);",

        # Chat messages indices
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON agent_chat_messages(session_id, created_at);",
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_role ON agent_chat_messages(role);",

        # Training scenarios indices
        "CREATE INDEX IF NOT EXISTS idx_training_scenarios_category ON training_scenarios(category);",
        "CREATE INDEX IF NOT EXISTS idx_training_scenarios_difficulty ON training_scenarios(difficulty);",
        "CREATE INDEX IF NOT EXISTS idx_training_scenarios_agent ON training_scenarios(target_agent_type);",
        "CREATE INDEX IF NOT EXISTS idx_training_scenarios_active ON training_scenarios(is_active);",

        # Training sessions indices
        "CREATE INDEX IF NOT EXISTS idx_training_sessions_agent ON training_sessions(agent_id);",
        "CREATE INDEX IF NOT EXISTS idx_training_sessions_scenario ON training_sessions(scenario_id);",
        "CREATE INDEX IF NOT EXISTS idx_training_sessions_score ON training_sessions(score);",
        "CREATE INDEX IF NOT EXISTS idx_training_sessions_date ON training_sessions(started_at);",
        "CREATE INDEX IF NOT EXISTS idx_training_sessions_status ON training_sessions(status);",

        # ============================================================================
        # TRIGGERS FOR UPDATED_AT
        # ============================================================================
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        """,

        """
        DROP TRIGGER IF EXISTS update_agent_profiles_updated_at ON agent_profiles;
        CREATE TRIGGER update_agent_profiles_updated_at
            BEFORE UPDATE ON agent_profiles
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_agent_tools_updated_at ON agent_tools;
        CREATE TRIGGER update_agent_tools_updated_at
            BEFORE UPDATE ON agent_tools
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_gym_scenarios_updated_at ON gym_test_scenarios;
        CREATE TRIGGER update_gym_scenarios_updated_at
            BEFORE UPDATE ON gym_test_scenarios
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_agent_alerts_updated_at ON agent_alerts;
        CREATE TRIGGER update_agent_alerts_updated_at
            BEFORE UPDATE ON agent_alerts
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """,

        # ============================================================================
        # VIEWS FOR COMMON QUERIES
        # ============================================================================

        # Current agent health summary
        """
        CREATE OR REPLACE VIEW v_agent_health_current AS
        SELECT
            ap.id,
            ap.agent_name,
            ap.display_name,
            ap.category,
            ap.risk_tier,
            ap.elite_status,
            ap.health_status,
            ap.status,
            ap.tool_count,
            ap.version,
            ap.last_health_check,
            (
                SELECT COUNT(*)
                FROM agent_alerts aa
                WHERE aa.agent_id = ap.id AND aa.status IN ('open', 'acknowledged')
            ) as active_alerts,
            (
                SELECT COUNT(*)
                FROM agent_executions ae
                WHERE ae.agent_id = ap.id
                AND ae.created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            ) as executions_24h,
            (
                SELECT ROUND(AVG(CASE WHEN ae.success THEN 100 ELSE 0 END)::numeric, 2)
                FROM agent_executions ae
                WHERE ae.agent_id = ap.id
                AND ae.created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            ) as success_rate_24h
        FROM agent_profiles ap
        WHERE ap.status = 'active'
        ORDER BY ap.agent_name;
        """,

        # System health overview
        """
        CREATE OR REPLACE VIEW v_system_health_overview AS
        SELECT
            COUNT(*) as total_agents,
            COUNT(*) FILTER (WHERE health_status = 'healthy') as healthy_agents,
            COUNT(*) FILTER (WHERE health_status = 'warning') as warning_agents,
            COUNT(*) FILTER (WHERE health_status = 'critical') as critical_agents,
            COUNT(*) FILTER (WHERE health_status = 'offline') as offline_agents,
            COUNT(*) FILTER (WHERE elite_status = TRUE) as elite_agents,
            (
                SELECT COUNT(*)
                FROM agent_executions
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            ) as total_executions_24h,
            (
                SELECT ROUND(AVG(CASE WHEN success THEN 100 ELSE 0 END)::numeric, 2)
                FROM agent_executions
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            ) as overall_success_rate_24h,
            (
                SELECT COUNT(*)
                FROM agent_alerts
                WHERE status IN ('open', 'acknowledged') AND severity = 'critical'
            ) as active_critical_alerts
        FROM agent_profiles
        WHERE status = 'active';
        """,

        # ============================================================================
        # SEED DATA - Insert all 20 agents
        # ============================================================================
        """
        INSERT INTO agent_profiles (agent_name, display_name, role, description, category, tool_file, tool_count, risk_tier)
        VALUES
            ('LeadManagementAgent', 'Lead Management', 'Lead lifecycle and conversion', 'Manages lead scoring, follow-up, and conversion optimization', 'crm', 'lead_agent.py', 8, '2-3'),
            ('LoanPipelineAgent', 'Loan Pipeline', 'Active loan monitoring', 'Monitors and manages loans through the pipeline', 'crm', 'loan_agent.py', 8, '2'),
            ('TaskCalendarAgent', 'Task & Calendar', 'Scheduling and tasks', 'Handles task creation, scheduling, and calendar management', 'operations', 'task_agent.py', 8, '2'),
            ('CommunicationAgent', 'Communication', 'Email, SMS, notifications', 'Manages multi-channel communications', 'communication', 'communication_agent.py', 8, '2-3'),
            ('DocumentAgent', 'Documents', 'Document processing', 'Handles document collection, processing, and tracking', 'crm', 'document_agent.py', 8, '2-3'),
            ('AnalyticsAgent', 'Analytics', 'Reporting and insights', 'Generates reports and analytical insights', 'analytics', 'analytics_agent.py', 8, '1'),
            ('PortfolioAgent', 'Portfolio', 'Post-close management', 'Manages funded loans and client retention', 'crm', 'portfolio_agent.py', 8, '1-2'),
            ('ComplianceAgent', 'Compliance', 'Regulatory compliance', 'TRID, RESPA, fair lending compliance verification', 'operations', 'compliance_agent.py', 8, '3'),
            ('ReceptionistAgent', 'AI Receptionist', 'Voice/chat receptionist', 'Handles inbound calls and chat, routes inquiries', 'communication', 'receptionist_agent.py', 8, '2-3'),
            ('ProfitabilityAgent', 'Profitability', 'Financial analysis', 'Analyzes loan and branch profitability', 'analytics', 'profitability_agent.py', 8, '1'),
            ('SubscriptionAgent', 'Subscription', 'Billing management', 'Manages SaaS subscriptions and billing', 'operations', 'subscription_agent.py', 8, '3'),
            ('OnboardingAgent', 'Onboarding', 'User onboarding', 'Guides new users through setup and training', 'operations', 'onboarding_agent.py', 8, '2'),
            ('VoiceAgent', 'Voice OS', 'Voice commands', 'Processes voice commands and interactions', 'communication', 'voice_agent.py', 8, '2'),
            ('CoachingAgent', 'Team Coach', 'Performance coaching', 'LO performance coaching and benchmarking', 'analytics', 'coaching_agent.py', 8, '1-2'),
            ('SLAAgent', 'SLA Tracker', 'SLA monitoring', 'Tracks SLA compliance and milestones', 'operations', 'sla_agent.py', 8, '2'),
            ('EmailIntelAgent', 'Email Intelligence', 'Email processing', 'Parses emails, generates responses, handles training', 'communication', 'email_intel_agent.py', 12, '2-3'),
            ('SchedulerAgent', 'Smart Scheduler', 'Meeting scheduling', 'Intelligent meeting and calendar scheduling', 'operations', 'scheduler_agent.py', 8, '2'),
            ('VideoAgent', 'UVIP', 'Video intelligence', 'Video meeting processing and intelligence', 'communication', 'video_agent.py', 8, '1-2'),
            ('IntegrationsAgent', 'Integrations', 'Third-party integrations', 'Manages external system integrations', 'operations', 'integrations_agent.py', 8, '2-3'),
            ('RateAdvisorAgent', 'Rate Advisor', 'Rate guidance', 'Rate lock and pricing advice', 'crm', 'rate_advisor_agent.py', 8, '2-3')
        ON CONFLICT (agent_name) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            role = EXCLUDED.role,
            description = EXCLUDED.description,
            category = EXCLUDED.category,
            tool_file = EXCLUDED.tool_file,
            tool_count = EXCLUDED.tool_count,
            risk_tier = EXCLUDED.risk_tier,
            updated_at = CURRENT_TIMESTAMP;
        """
    ]

    try:
        with engine.connect() as conn:
            for idx, sql in enumerate(sql_commands, 1):
                try:
                    logger.info(f"Executing command {idx}/{len(sql_commands)}...")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"Command {idx} executed successfully")
                except Exception as e:
                    logger.error(f"Error executing command {idx}: {e}")
                    # Continue with other commands
                    continue

        logger.info("Agent Governance System migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def seed_agent_tools():
    """Seed initial tool definitions for all agents"""

    tool_definitions = [
        # LeadManagementAgent tools
        ("LeadManagementAgent", "search_leads", "Search and filter leads", "query", "low", False),
        ("LeadManagementAgent", "get_lead_details", "Get detailed lead profile", "query", "low", False),
        ("LeadManagementAgent", "update_lead_stage", "Move lead through pipeline stages", "action", "medium", False),
        ("LeadManagementAgent", "score_lead_quality", "AI-powered lead quality scoring", "analysis", "low", False),
        ("LeadManagementAgent", "assign_lead", "Assign lead to team member", "action", "medium", False),
        ("LeadManagementAgent", "get_lead_activity", "Get lead activity timeline", "query", "low", False),
        ("LeadManagementAgent", "create_lead_task", "Create task for lead", "action", "low", False),
        ("LeadManagementAgent", "analyze_lead_pipeline", "Analyze lead pipeline metrics", "analysis", "low", False),

        # LoanPipelineAgent tools
        ("LoanPipelineAgent", "get_pipeline_metrics", "Get pipeline health metrics", "query", "low", False),
        ("LoanPipelineAgent", "get_loans_by_status", "Get loans filtered by status", "query", "low", False),
        ("LoanPipelineAgent", "get_loan_details", "Get detailed loan profile", "query", "low", False),
        ("LoanPipelineAgent", "update_loan_status", "Update loan status", "action", "medium", False),
        ("LoanPipelineAgent", "get_loan_aging", "Get loan aging report", "analysis", "low", False),
        ("LoanPipelineAgent", "find_bottlenecks", "Identify pipeline bottlenecks", "analysis", "low", False),
        ("LoanPipelineAgent", "predict_closing", "Predict closing timeline", "analysis", "low", False),
        ("LoanPipelineAgent", "get_stale_loans", "Find inactive loans", "query", "low", False),

        # ComplianceAgent tools
        ("ComplianceAgent", "check_trid_compliance", "Check TRID compliance", "analysis", "high", True),
        ("ComplianceAgent", "check_respa_compliance", "Check RESPA compliance", "analysis", "high", True),
        ("ComplianceAgent", "check_fair_lending", "Check fair lending compliance", "analysis", "high", True),
        ("ComplianceAgent", "get_state_requirements", "Get state-specific requirements", "query", "low", False),
        ("ComplianceAgent", "audit_loan_file", "Comprehensive loan file audit", "analysis", "high", True),
        ("ComplianceAgent", "get_disclosure_timeline", "Get disclosure timeline", "query", "low", False),
        ("ComplianceAgent", "check_tolerance_violations", "Check fee tolerance violations", "analysis", "high", True),
        ("ComplianceAgent", "get_compliance_history", "Get compliance history", "query", "low", False),

        # SLAAgent tools
        ("SLAAgent", "get_sla_status", "Get SLA compliance status", "query", "low", False),
        ("SLAAgent", "check_milestone_compliance", "Check milestone compliance", "analysis", "low", False),
        ("SLAAgent", "get_at_risk_loans", "Get at-risk loans", "query", "low", False),
        ("SLAAgent", "calculate_sla_metrics", "Calculate SLA metrics", "analysis", "low", False),
        ("SLAAgent", "set_sla_alert", "Configure SLA alert", "action", "medium", False),
        ("SLAAgent", "get_sla_history", "Get SLA history", "query", "low", False),
        ("SLAAgent", "project_completion", "Project completion timeline", "analysis", "low", False),
        ("SLAAgent", "generate_sla_report", "Generate SLA report", "analysis", "low", False),
    ]

    insert_sql = """
        INSERT INTO agent_tools (agent_id, tool_name, tool_description, category, risk_level, requires_approval, input_schema)
        SELECT
            ap.id,
            %(tool_name)s,
            %(description)s,
            %(category)s,
            %(risk_level)s,
            %(requires_approval)s,
            '{}'::jsonb
        FROM agent_profiles ap
        WHERE ap.agent_name = %(agent_name)s
        ON CONFLICT (agent_id, tool_name) DO UPDATE SET
            tool_description = EXCLUDED.tool_description,
            category = EXCLUDED.category,
            risk_level = EXCLUDED.risk_level,
            requires_approval = EXCLUDED.requires_approval,
            updated_at = CURRENT_TIMESTAMP;
    """

    try:
        with engine.connect() as conn:
            for agent_name, tool_name, description, category, risk_level, requires_approval in tool_definitions:
                conn.execute(text(insert_sql), {
                    "agent_name": agent_name,
                    "tool_name": tool_name,
                    "description": description,
                    "category": category,
                    "risk_level": risk_level,
                    "requires_approval": requires_approval
                })
            conn.commit()
        logger.info(f"Seeded {len(tool_definitions)} tool definitions")
        return True
    except Exception as e:
        logger.error(f"Failed to seed tools: {e}")
        return False


if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("Agent Governance & Management System - Database Migration")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Creating tables:")
    logger.info("  1. agent_profiles - Agent metadata and configuration")
    logger.info("  2. agent_tools - Tool registry per agent")
    logger.info("  3. agent_executions - Execution audit trail")
    logger.info("  4. gym_test_scenarios - Test case definitions")
    logger.info("  5. gym_test_runs - Test execution records")
    logger.info("  6. gym_test_results - Per-scenario results")
    logger.info("  7. agent_alerts - Alerts and notifications")
    logger.info("  8. agent_metrics_timeseries - Time-series metrics")
    logger.info("  9. agent_chat_sessions - Chat session tracking")
    logger.info(" 10. agent_chat_messages - Chat message history")
    logger.info(" 11. training_scenarios - Agent Gym training scenarios")
    logger.info(" 12. training_sessions - Agent Gym session results")
    logger.info("")

    success = run_migration()

    if success:
        logger.info("")
        logger.info("Seeding initial data...")
        seed_agent_tools()
        logger.info("")
        logger.info("Migration completed successfully!")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Create SQLAlchemy models")
        logger.info("  2. Implement agent governance service")
        logger.info("  3. Create API routes")
        logger.info("  4. Build frontend dashboard")
    else:
        logger.error("Migration failed!")
        sys.exit(1)
