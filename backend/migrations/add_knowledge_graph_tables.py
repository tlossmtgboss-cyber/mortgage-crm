"""
Add Knowledge Graph Tables

Creates two tables for the entity relationship graph:
  - knowledge_nodes: Typed entities (lead, loan, user, referral_partner, etc.)
  - knowledge_edges: Typed relationships between nodes with weight and metadata

Usage:
    python -m migrations.add_knowledge_graph_tables
    # or
    from migrations.add_knowledge_graph_tables import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Create knowledge graph tables and indexes."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Check if pgvector is available
        has_pgvector = False
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
            has_pgvector = True
        except Exception:
            conn.rollback()
            logger.info("pgvector extension not available — embedding column will use TEXT")

        embedding_type = "vector(1536)" if has_pgvector else "TEXT"

        # ---------------------------------------------------------------
        # 1. knowledge_nodes
        # ---------------------------------------------------------------
        logger.info("Creating knowledge_nodes table...")
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                node_type VARCHAR(50) NOT NULL,
                entity_id VARCHAR(64) NOT NULL,
                label VARCHAR(255) NOT NULL,
                properties JSONB NOT NULL DEFAULT '{{}}',
                embedding {embedding_type},
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uq_knode_org_type_entity UNIQUE (organization_id, node_type, entity_id)
            )
        """))
        conn.commit()

        logger.info("Creating knowledge_nodes indexes...")
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS ix_knode_org_type ON knowledge_nodes (organization_id, node_type)",
            "CREATE INDEX IF NOT EXISTS ix_knode_org_label ON knowledge_nodes (organization_id, label)",
            "CREATE INDEX IF NOT EXISTS ix_knode_entity ON knowledge_nodes (node_type, entity_id)",
            "CREATE INDEX IF NOT EXISTS ix_knowledge_nodes_organization_id ON knowledge_nodes (organization_id)",
        ]:
            try:
                conn.execute(text(idx_sql))
                conn.commit()
            except Exception as e:
                logger.warning(f"Index creation skipped (may already exist): {e}")
                conn.rollback()

        # ---------------------------------------------------------------
        # 2. knowledge_edges
        # ---------------------------------------------------------------
        logger.info("Creating knowledge_edges table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS knowledge_edges (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                source_node_id INTEGER NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
                target_node_id INTEGER NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
                relationship_type VARCHAR(50) NOT NULL,
                properties JSONB NOT NULL DEFAULT '{}',
                weight FLOAT NOT NULL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uq_kedge_src_tgt_rel UNIQUE (source_node_id, target_node_id, relationship_type)
            )
        """))
        conn.commit()

        logger.info("Creating knowledge_edges indexes...")
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS ix_kedge_source ON knowledge_edges (source_node_id)",
            "CREATE INDEX IF NOT EXISTS ix_kedge_target ON knowledge_edges (target_node_id)",
            "CREATE INDEX IF NOT EXISTS ix_kedge_org_rel ON knowledge_edges (organization_id, relationship_type)",
            "CREATE INDEX IF NOT EXISTS ix_knowledge_edges_organization_id ON knowledge_edges (organization_id)",
        ]:
            try:
                conn.execute(text(idx_sql))
                conn.commit()
            except Exception as e:
                logger.warning(f"Index creation skipped (may already exist): {e}")
                conn.rollback()

        logger.info("Knowledge graph tables created successfully")
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
