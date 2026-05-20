"""
Migration: Create AI Autonomy Tables

Creates all tables needed for the autonomous AI agent system:
- autonomous_tasks: Scheduled agent task definitions
- task_executions: Execution log for each agent run
- agent_actions: Individual actions taken by agents
- agent_feedback: User ratings on AI responses
- agent_feedback_summaries: Aggregated feedback metrics
- learning_examples: Persistent training data
- learning_patterns: Discovered behavioral patterns
- prompt_optimizations: Prompt change tracking
- agent_conversations: Conversation session records
- agent_memories: Extracted facts and preferences
- agent_contexts: Key-value agent state

Usage:
    python -m migrations.add_ai_autonomy_tables
    # or from startup:
    from migrations.add_ai_autonomy_tables import run_migration
    run_migration(engine)
"""

import logging

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Create all AI autonomy tables if they don't exist."""

    # Import all models so their tables are registered with Base.metadata
    from database.models.autonomous_task import (
        AutonomousTask, TaskExecution, AgentAction, create_tables_if_needed as create_task_tables,
    )
    from database.models.agent_feedback import (
        AgentFeedback, AgentFeedbackSummary, create_tables_if_needed as create_feedback_tables,
    )
    from database.models.learning_example import (
        LearningExample, LearningPattern, PromptOptimization, create_tables_if_needed as create_learning_tables,
    )
    from database.models.agent_memory import AgentConversation, AgentMemory, AgentContext
    from database.models.agent_metrics import AgentInvocation, create_tables_if_needed as create_metrics_tables
    from database.models.action_type_confidence import (
        ActionTypeConfidence, create_tables_if_needed as create_confidence_tables,
    )

    tables_created = []

    # Create each group of tables
    try:
        create_task_tables(engine)
        tables_created.extend(["autonomous_tasks", "task_executions", "agent_actions"])
    except Exception as e:
        logger.warning(f"Autonomous task tables: {e}")

    try:
        create_feedback_tables(engine)
        tables_created.extend(["agent_feedback", "agent_feedback_summaries"])
    except Exception as e:
        logger.warning(f"Agent feedback tables: {e}")

    try:
        create_learning_tables(engine)
        tables_created.extend(["learning_examples", "learning_patterns", "prompt_optimizations"])
    except Exception as e:
        logger.warning(f"Learning example tables: {e}")

    try:
        create_metrics_tables(engine)
        tables_created.append("agent_invocations")
    except Exception as e:
        logger.warning(f"Agent metrics tables: {e}")

    # Confidence graduation table (drives the progressive autonomy system)
    try:
        create_confidence_tables(engine)
        tables_created.append("action_type_confidence")
    except Exception as e:
        logger.warning(f"Action type confidence table: {e}")

    # Agent memory tables (use Base.metadata.create_all with specific tables)
    try:
        from db import Base
        memory_tables = [
            AgentConversation.__table__,
            AgentMemory.__table__,
            AgentContext.__table__,
        ]
        for table in memory_tables:
            table.create(engine, checkfirst=True)
            tables_created.append(table.name)
    except Exception as e:
        logger.warning(f"Agent memory tables: {e}")

    logger.info(f"AI autonomy migration complete: {len(tables_created)} tables verified ({', '.join(tables_created)})")
    return tables_created


if __name__ == "__main__":
    from db import engine
    run_migration(engine)
    print("Migration complete.")
