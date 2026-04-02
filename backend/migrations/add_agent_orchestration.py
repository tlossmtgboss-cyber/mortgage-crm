"""
Migration: Add agent orchestration tables for AI agent management.

Creates tables for:
- agents: Core agent configuration storage
- agent_executions: Track individual AI calls with token metrics
- conversation_outcomes: Track conversation results
- agent_ab_tests: A/B testing for agents
- prompt_templates: Reusable prompt components

Supports both SQLite (local dev) and PostgreSQL (production).
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")

# Detect if using SQLite or PostgreSQL
IS_SQLITE = DATABASE_URL.startswith("sqlite")


def get_sql_commands():
    """Return SQL commands appropriate for the database type."""

    if IS_SQLITE:
        return get_sqlite_commands()
    else:
        return get_postgres_commands()


def get_sqlite_commands():
    """SQLite-compatible SQL commands."""
    return [
        # ==========================================================================
        # AGENTS TABLE - Core agent configuration storage
        # ==========================================================================
        """
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id VARCHAR(100) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            role VARCHAR(255) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            version VARCHAR(20) NOT NULL DEFAULT '1.0',
            config TEXT NOT NULL DEFAULT '{}',
            persona TEXT NOT NULL DEFAULT '{}',
            rules TEXT NOT NULL DEFAULT '{}',
            prompt_components TEXT NOT NULL DEFAULT '{}',
            use_case VARCHAR(100),
            channel VARCHAR(50),
            ai_provider VARCHAR(50) DEFAULT 'claude',
            model VARCHAR(100) DEFAULT 'claude-sonnet-4-20250514',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_agents_agent_id ON agents(agent_id);",
        "CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);",
        "CREATE INDEX IF NOT EXISTS idx_agents_use_case ON agents(use_case);",

        # ==========================================================================
        # AGENT EXECUTIONS TABLE - Track individual AI calls
        # ==========================================================================
        """
        CREATE TABLE IF NOT EXISTS agent_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER,
            conversation_id VARCHAR(255) NOT NULL,
            user_id INTEGER,
            organization_id INTEGER,
            stage VARCHAR(100) NOT NULL,
            intent_detected VARCHAR(255),
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            model_used VARCHAR(100),
            input_text TEXT,
            response_text TEXT,
            prompt_used TEXT,
            metadata TEXT DEFAULT '{}',
            quality_score REAL,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_agent_id ON agent_executions(agent_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_conversation_id ON agent_executions(conversation_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_executed_at ON agent_executions(executed_at);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_stage ON agent_executions(stage);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_organization_id ON agent_executions(organization_id);",

        # ==========================================================================
        # CONVERSATION OUTCOMES TABLE - Track conversation results
        # ==========================================================================
        """
        CREATE TABLE IF NOT EXISTS conversation_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id VARCHAR(255) UNIQUE NOT NULL,
            agent_id INTEGER,
            user_id INTEGER,
            organization_id INTEGER,
            outcome_type VARCHAR(50) NOT NULL,
            total_messages INTEGER NOT NULL DEFAULT 0,
            agent_messages INTEGER NOT NULL DEFAULT 0,
            user_messages INTEGER NOT NULL DEFAULT 0,
            qualification_complete BOOLEAN DEFAULT 0,
            qualification_data TEXT DEFAULT '{}',
            booking_made BOOLEAN DEFAULT 0,
            booking_id VARCHAR(255),
            revenue_generated REAL,
            response_rate REAL,
            avg_response_time_seconds INTEGER,
            objections_handled INTEGER DEFAULT 0,
            metrics TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            duration_seconds INTEGER,
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE SET NULL
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_conversation_outcomes_agent_id ON conversation_outcomes(agent_id);",
        "CREATE INDEX IF NOT EXISTS idx_conversation_outcomes_outcome_type ON conversation_outcomes(outcome_type);",
        "CREATE INDEX IF NOT EXISTS idx_conversation_outcomes_created_at ON conversation_outcomes(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_conversation_outcomes_organization_id ON conversation_outcomes(organization_id);",

        # ==========================================================================
        # AGENT AB TESTS TABLE - Track A/B test experiments
        # ==========================================================================
        """
        CREATE TABLE IF NOT EXISTS agent_ab_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_name VARCHAR(255) NOT NULL,
            agent_id INTEGER NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            variant_a_config TEXT NOT NULL,
            variant_b_config TEXT NOT NULL,
            traffic_split REAL DEFAULT 0.50,
            variant_a_conversations INTEGER DEFAULT 0,
            variant_b_conversations INTEGER DEFAULT 0,
            variant_a_conversions INTEGER DEFAULT 0,
            variant_b_conversions INTEGER DEFAULT 0,
            statistical_significance REAL,
            winner VARCHAR(1),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
            created_by INTEGER,
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_agent_ab_tests_agent_id ON agent_ab_tests(agent_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_ab_tests_status ON agent_ab_tests(status);",

        # ==========================================================================
        # PROMPT TEMPLATES TABLE - Store reusable prompt components
        # ==========================================================================
        """
        CREATE TABLE IF NOT EXISTS prompt_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id VARCHAR(100) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(100) NOT NULL,
            priority VARCHAR(50) DEFAULT 'conditional',
            content TEXT NOT NULL,
            description TEXT,
            variables TEXT DEFAULT '[]',
            estimated_tokens INTEGER,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_prompt_templates_template_id ON prompt_templates(template_id);",
        "CREATE INDEX IF NOT EXISTS idx_prompt_templates_category ON prompt_templates(category);",
    ]


def get_postgres_commands():
    """PostgreSQL SQL commands."""
    return [
        # ==========================================================================
        # AGENTS TABLE
        # ==========================================================================
        """
        CREATE TABLE IF NOT EXISTS agents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id VARCHAR(100) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            role VARCHAR(255) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            version VARCHAR(20) NOT NULL DEFAULT '1.0',
            config JSONB NOT NULL DEFAULT '{}',
            persona JSONB NOT NULL DEFAULT '{}',
            rules JSONB NOT NULL DEFAULT '{}',
            prompt_components JSONB NOT NULL DEFAULT '{}',
            use_case VARCHAR(100),
            channel VARCHAR(50),
            ai_provider VARCHAR(50) DEFAULT 'claude',
            model VARCHAR(100) DEFAULT 'claude-sonnet-4-20250514',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_agents_agent_id ON agents(agent_id);",
        "CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);",
        "CREATE INDEX IF NOT EXISTS idx_agents_use_case ON agents(use_case);",

        # ==========================================================================
        # AGENT EXECUTIONS TABLE
        # ==========================================================================
        """
        CREATE TABLE IF NOT EXISTS agent_executions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
            conversation_id UUID NOT NULL,
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
            stage VARCHAR(100) NOT NULL,
            intent_detected VARCHAR(255),
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            model_used VARCHAR(100),
            input_text TEXT,
            response_text TEXT,
            prompt_used TEXT,
            metadata JSONB DEFAULT '{}',
            quality_score NUMERIC(5, 2),
            executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_agent_id ON agent_executions(agent_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_conversation_id ON agent_executions(conversation_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_executed_at ON agent_executions(executed_at);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_stage ON agent_executions(stage);",
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_organization_id ON agent_executions(organization_id);",

        # ==========================================================================
        # CONVERSATION OUTCOMES TABLE
        # ==========================================================================
        """
        CREATE TABLE IF NOT EXISTS conversation_outcomes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID UNIQUE NOT NULL,
            agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
            outcome_type VARCHAR(50) NOT NULL,
            total_messages INTEGER NOT NULL DEFAULT 0,
            agent_messages INTEGER NOT NULL DEFAULT 0,
            user_messages INTEGER NOT NULL DEFAULT 0,
            qualification_complete BOOLEAN DEFAULT false,
            qualification_data JSONB DEFAULT '{}',
            booking_made BOOLEAN DEFAULT false,
            booking_id UUID,
            revenue_generated NUMERIC(10, 2),
            response_rate NUMERIC(5, 2),
            avg_response_time_seconds INTEGER,
            objections_handled INTEGER DEFAULT 0,
            metrics JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            completed_at TIMESTAMP WITH TIME ZONE,
            duration_seconds INTEGER
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_conversation_outcomes_agent_id ON conversation_outcomes(agent_id);",
        "CREATE INDEX IF NOT EXISTS idx_conversation_outcomes_outcome_type ON conversation_outcomes(outcome_type);",
        "CREATE INDEX IF NOT EXISTS idx_conversation_outcomes_created_at ON conversation_outcomes(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_conversation_outcomes_organization_id ON conversation_outcomes(organization_id);",

        # ==========================================================================
        # AGENT AB TESTS TABLE
        # ==========================================================================
        """
        CREATE TABLE IF NOT EXISTS agent_ab_tests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            test_name VARCHAR(255) NOT NULL,
            agent_id UUID REFERENCES agents(id) ON DELETE CASCADE NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            variant_a_config JSONB NOT NULL,
            variant_b_config JSONB NOT NULL,
            traffic_split NUMERIC(3, 2) DEFAULT 0.50,
            variant_a_conversations INTEGER DEFAULT 0,
            variant_b_conversations INTEGER DEFAULT 0,
            variant_a_conversions INTEGER DEFAULT 0,
            variant_b_conversions INTEGER DEFAULT 0,
            statistical_significance NUMERIC(5, 4),
            winner VARCHAR(1),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            started_at TIMESTAMP WITH TIME ZONE,
            ended_at TIMESTAMP WITH TIME ZONE,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_agent_ab_tests_agent_id ON agent_ab_tests(agent_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_ab_tests_status ON agent_ab_tests(status);",

        # ==========================================================================
        # PROMPT TEMPLATES TABLE
        # ==========================================================================
        """
        CREATE TABLE IF NOT EXISTS prompt_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            template_id VARCHAR(100) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(100) NOT NULL,
            priority VARCHAR(50) DEFAULT 'conditional',
            content TEXT NOT NULL,
            description TEXT,
            variables JSONB DEFAULT '[]',
            estimated_tokens INTEGER,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_prompt_templates_template_id ON prompt_templates(template_id);",
        "CREATE INDEX IF NOT EXISTS idx_prompt_templates_category ON prompt_templates(category);",
    ]


def run_migration():
    """Create all agent orchestration tables."""
    engine = create_engine(DATABASE_URL)

    db_type = "SQLite" if IS_SQLITE else "PostgreSQL"
    print(f"Running migration for {db_type}...")
    print(f"Database: {DATABASE_URL[:50]}...")

    sql_commands = get_sql_commands()

    with engine.connect() as conn:
        try:
            for i, sql in enumerate(sql_commands):
                sql_preview = sql.strip()[:60].replace('\n', ' ')
                print(f"  Executing [{i+1}/{len(sql_commands)}]: {sql_preview}...")
                conn.execute(text(sql))

            conn.commit()
            print(f"\nSuccessfully created all agent orchestration tables for {db_type}!")
            return True

        except Exception as e:
            conn.rollback()
            print(f"Error creating tables: {e}")
            import traceback
            traceback.print_exc()
            return False


def check_tables_exist():
    """Check if the tables already exist."""
    engine = create_engine(DATABASE_URL)
    tables = ['agents', 'agent_executions', 'conversation_outcomes', 'agent_ab_tests', 'prompt_templates']
    existing = []

    with engine.connect() as conn:
        for table in tables:
            if IS_SQLITE:
                result = conn.execute(text(
                    "SELECT name FROM sqlite_master"
                    " WHERE type='table' AND name=:table_name"
                ), {"table_name": table})
            else:
                result = conn.execute(text(
                    "SELECT EXISTS ("
                    " SELECT FROM information_schema.tables"
                    " WHERE table_name = :table_name"
                    ")"
                ), {"table_name": table})

            if result.scalar():
                existing.append(table)

    return existing


if __name__ == "__main__":
    existing = check_tables_exist()
    if existing:
        print(f"The following tables already exist: {', '.join(existing)}")
        print("Running migration anyway (uses IF NOT EXISTS)...")

    success = run_migration()

    if success:
        print("\n" + "="*50)
        print("Migration complete! Tables created:")
        print("  - agents")
        print("  - agent_executions")
        print("  - conversation_outcomes")
        print("  - agent_ab_tests")
        print("  - prompt_templates")
        print("="*50)
