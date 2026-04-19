"""
Database Migration: Aria Memory & RAG (Phase A)

Extends agent_memories with borrower memory columns.
Creates memory_staging, memory_audit_events, memory_topic_config,
and memory_exclusion_rules tables.
Creates partial unique indexes for structural dedup.

Run with: python -m migrations.add_memory_columns
"""

import logging
from sqlalchemy import text
from db import engine
from database.models.agent_memory import AgentMemory
from database.models.memory_staging import MemoryStaging
from database.models.memory_audit import MemoryAuditEvent
from database.models.memory_topic_config import MemoryTopicConfig, MemoryExclusionRule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    logger.info("Starting Aria Memory & RAG migration (Phase A)...")

    # 1. Ensure pgvector extension exists
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    logger.info("pgvector extension verified")

    # 2. Create new tables
    MemoryStaging.__table__.create(engine, checkfirst=True)
    logger.info("memory_staging table created")

    MemoryAuditEvent.__table__.create(engine, checkfirst=True)
    logger.info("memory_audit_events table created")

    MemoryTopicConfig.__table__.create(engine, checkfirst=True)
    logger.info("memory_topic_config table created")

    MemoryExclusionRule.__table__.create(engine, checkfirst=True)
    logger.info("memory_exclusion_rules table created")

    # 3. Add new columns to agent_memories
    alter_statements = [
        "ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS borrower_id INTEGER REFERENCES leads(id) ON DELETE CASCADE",
        "ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS embedding vector(1536)",
        "ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS topic VARCHAR(100)",
        "ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS source_call_id VARCHAR(255)",
        "ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS transcript_span TEXT",
        "ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'utc')",
        "ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS superseded_by INTEGER REFERENCES agent_memories(id) ON DELETE SET NULL",
        "ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS fact_key VARCHAR(255)",
        "ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(100) DEFAULT 'text-embedding-3-small'",
        "ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS embedding_version VARCHAR(50)",
        "ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS content_hash VARCHAR(32)",
    ]

    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_agent_mem_borrower ON agent_memories (borrower_id)",
        "CREATE INDEX IF NOT EXISTS ix_agent_mem_topic ON agent_memories (topic)",
        "CREATE INDEX IF NOT EXISTS ix_agent_mem_fact_key ON agent_memories (fact_key)",
        "CREATE INDEX IF NOT EXISTS ix_agent_mem_verified ON agent_memories (last_verified_at)",
        "CREATE INDEX IF NOT EXISTS ix_agent_mem_superseded ON agent_memories (superseded_by)",
        "CREATE INDEX IF NOT EXISTS ix_agent_mem_hash ON agent_memories (content_hash)",
    ]

    dedup_indexes = [
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_mem_pref_active
           ON agent_memories (borrower_id, fact_key)
           WHERE fact_key IS NOT NULL AND superseded_by IS NULL""",
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_mem_episodic_active
           ON agent_memories (borrower_id, content_hash)
           WHERE fact_key IS NULL AND content_hash IS NOT NULL AND superseded_by IS NULL""",
    ]

    staging_dedup_indexes = [
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_pref
           ON memory_staging (borrower_id, fact_key, source_call_id)
           WHERE fact_key IS NOT NULL AND status = 'pending_review'""",
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_episodic
           ON memory_staging (borrower_id, content_hash, source_call_id)
           WHERE fact_key IS NULL AND status = 'pending_review'""",
    ]

    with engine.connect() as conn:
        for stmt in alter_statements + index_statements + dedup_indexes + staging_dedup_indexes:
            conn.execute(text(stmt))
        conn.commit()
    logger.info("agent_memories columns and indexes added")

    # 4. Seed default topic configs
    _seed_topic_configs()

    # 5. Seed default exclusion rules
    _seed_exclusion_rules()

    logger.info("Aria Memory & RAG migration complete")


def _seed_topic_configs():
    from database import get_db
    db = next(get_db())
    try:
        existing = db.query(MemoryTopicConfig).count()
        if existing > 0:
            logger.info("Topic configs already seeded, skipping")
            return

        defaults = [
            MemoryTopicConfig(call_trigger="inbound_call", loan_stage="PROCESSING",
                              topics=["documents", "timeline", "conditions"], priority=10),
            MemoryTopicConfig(call_trigger="inbound_call", loan_stage="UNDERWRITING",
                              topics=["conditions", "timeline", "income"], priority=10),
            MemoryTopicConfig(call_trigger="inbound_call", loan_stage="APPLICATION",
                              topics=["qualification", "documents", "preferences"], priority=10),
            MemoryTopicConfig(call_trigger="outbound_followup", loan_stage=None,
                              topics=["qualification", "documents", "preferences"], priority=5),
            MemoryTopicConfig(call_trigger="scheduled_callback", loan_stage=None,
                              topics=["last_call_context", "open_questions"], priority=5),
            MemoryTopicConfig(call_trigger="inbound_call", loan_stage=None,
                              topics=["general", "preferences"], priority=0),
        ]
        db.add_all(defaults)
        db.commit()
        logger.info("Seeded %d default topic configs", len(defaults))
    finally:
        db.close()


def _seed_exclusion_rules():
    from database import get_db
    db = next(get_db())
    try:
        existing = db.query(MemoryExclusionRule).count()
        if existing > 0:
            logger.info("Exclusion rules already seeded, skipping")
            return

        rules = [
            MemoryExclusionRule(
                category="protected_class",
                pattern="Race, ethnicity, religion, national origin, sex, familial status, disability, age beyond qualification thresholds",
            ),
            MemoryExclusionRule(
                category="emotional_inference",
                pattern="Emotional state inferences: frustrated, anxious, angry, upset, confused. Route to qa_signal instead.",
            ),
            MemoryExclusionRule(
                category="unverified_financial",
                pattern="Unverified financial attributes: 'probably makes', 'seems like they earn', estimated income without explicit statement",
            ),
            MemoryExclusionRule(
                category="relational_inference",
                pattern="Relational inferences: divorce, separation, relationship status not explicitly described by borrower",
            ),
            MemoryExclusionRule(
                category="competitive_intel",
                pattern="Competitive intelligence: offers from other lenders, competitor names, competitor rates. Route to pipeline_intel instead.",
            ),
            MemoryExclusionRule(
                category="proxy_national_origin",
                pattern="Language spoken at home, accent descriptions, country of origin inferences",
                transformation="If borrower explicitly requests communication in a specific language, store as preference with fact_key='language_preference'",
            ),
            MemoryExclusionRule(
                category="proxy_race",
                pattern="Neighborhood or zip code as standalone fact, area demographics",
            ),
            MemoryExclusionRule(
                category="proxy_familial",
                pattern="Number of children, family size, pregnancy status",
            ),
        ]
        db.add_all(rules)
        db.commit()
        logger.info("Seeded %d default exclusion rules", len(rules))
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()
    print("\nAria Memory & RAG migration complete (Phase A)")
