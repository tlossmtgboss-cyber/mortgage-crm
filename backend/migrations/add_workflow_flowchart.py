"""
Migration: Add Workflow Flowchart System

Creates tables for the flowchart-based workflow builder:
- workflow_definitions: org-scoped workflow definitions
- workflow_nodes: flowchart nodes with position, channels, AI guidance
- workflow_edges: connections between nodes
- workflow_lead_movements: append-only lead movement history
- workflow_ai_actions: AI action plans, outcomes, confidence tracking

Adds columns to leads table:
- workflow_definition_id: which workflow the lead is in
- workflow_node_id: which node within the workflow

Seeds 10 default workflow definitions per org.

Run with:
    python -m migrations.add_workflow_flowchart

Or import and call run_migration(db) from startup.
"""

import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DEFAULT_WORKFLOWS = [
    {"key": "prospect", "name": "Prospect", "color": "#3b82f6", "sort_order": 0},
    {"key": "prequal", "name": "PreQual", "color": "#B8924A", "sort_order": 1},
    {"key": "pre_approved", "name": "Pre-Approval", "color": "#2D7A52", "sort_order": 2},
    {"key": "under_contract", "name": "Under Contract", "color": "#f59e0b", "sort_order": 3},
    {"key": "lead_purchase", "name": "Lead Purchase", "color": "#ec4899", "sort_order": 4},
    {"key": "theme_day", "name": "Theme Day", "color": "#06b6d4", "sort_order": 5},
    {"key": "last_mile", "name": "Last Mile", "color": "#14b8a6", "sort_order": 6},
    {"key": "post_close", "name": "Post Close", "color": "#22c55e", "sort_order": 7},
    {"key": "credit_repair", "name": "Credit Repair", "color": "#f97316", "sort_order": 8},
    {"key": "nurture", "name": "Nurture", "color": "#8b5cf6", "sort_order": 9},
]


def run_migration(db: Session = None) -> dict:
    results = {"tables_created": [], "columns_added": [], "workflows_seeded": 0}

    if db:
        conn = db.connection()
    else:
        engine = create_engine(DATABASE_URL)
        conn = engine.connect()

    try:
        # -- workflow_definitions --
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_definitions (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                key VARCHAR(100) NOT NULL,
                name VARCHAR(200) NOT NULL,
                color VARCHAR(7) NOT NULL DEFAULT '#3b82f6',
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(organization_id, key)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_workflow_def_org_active ON workflow_definitions(organization_id, is_active)"))
        results["tables_created"].append("workflow_definitions")
        logger.info("Created workflow_definitions table")

        # -- workflow_nodes --
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_nodes (
                id VARCHAR(36) PRIMARY KEY,
                workflow_definition_id VARCHAR(36) NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
                type VARCHAR(20) NOT NULL DEFAULT 'task',
                label VARCHAR(200) NOT NULL,
                description TEXT,
                x FLOAT NOT NULL DEFAULT 0.0,
                y FLOAT NOT NULL DEFAULT 0.0,
                channels JSON,
                role VARCHAR(50),
                day_label VARCHAR(50),
                time_of_day VARCHAR(10),
                repeat_weekly BOOLEAN NOT NULL DEFAULT FALSE,
                status VARCHAR(20) NOT NULL DEFAULT 'healthy',
                config JSON,
                ai_guidance JSON,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_workflow_node_def ON workflow_nodes(workflow_definition_id)"))
        results["tables_created"].append("workflow_nodes")
        logger.info("Created workflow_nodes table")

        # -- workflow_edges --
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_edges (
                id VARCHAR(36) PRIMARY KEY,
                workflow_definition_id VARCHAR(36) NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
                from_node_id VARCHAR(36) NOT NULL REFERENCES workflow_nodes(id) ON DELETE CASCADE,
                to_node_id VARCHAR(36) NOT NULL REFERENCES workflow_nodes(id) ON DELETE CASCADE,
                label VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_workflow_edge_def ON workflow_edges(workflow_definition_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_workflow_edge_from ON workflow_edges(from_node_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_workflow_edge_to ON workflow_edges(to_node_id)"))
        results["tables_created"].append("workflow_edges")
        logger.info("Created workflow_edges table")

        # -- workflow_lead_movements --
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_lead_movements (
                id VARCHAR(36) PRIMARY KEY,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                from_node_id VARCHAR(36) REFERENCES workflow_nodes(id) ON DELETE SET NULL,
                to_node_id VARCHAR(36) NOT NULL REFERENCES workflow_nodes(id) ON DELETE SET NULL,
                moved_at TIMESTAMP DEFAULT NOW(),
                moved_by INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wlm_lead ON workflow_lead_movements(lead_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wlm_to_node ON workflow_lead_movements(to_node_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wlm_moved_at ON workflow_lead_movements(moved_at)"))
        results["tables_created"].append("workflow_lead_movements")
        logger.info("Created workflow_lead_movements table")

        # -- workflow_ai_actions --
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_ai_actions (
                id VARCHAR(36) PRIMARY KEY,
                workflow_node_id VARCHAR(36) NOT NULL REFERENCES workflow_nodes(id) ON DELETE CASCADE,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                channel VARCHAR(20) NOT NULL,
                autonomy_level VARCHAR(20) NOT NULL,
                action_plan JSON,
                human_review JSON,
                execution_result JSON,
                outcome VARCHAR(20),
                confidence_before FLOAT,
                confidence_after FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_waia_node ON workflow_ai_actions(workflow_node_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_waia_lead ON workflow_ai_actions(lead_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_waia_created ON workflow_ai_actions(created_at)"))
        results["tables_created"].append("workflow_ai_actions")
        logger.info("Created workflow_ai_actions table")

        # -- Add columns to leads --
        for col, col_type in [("workflow_definition_id", "VARCHAR(36)"), ("workflow_node_id", "VARCHAR(36)")]:
            try:
                conn.execute(text(f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col} {col_type}"))
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_leads_{col} ON leads({col})"))
                results["columns_added"].append(f"leads.{col}")
                logger.info(f"Added leads.{col}")
            except Exception as e:
                logger.warning(f"Column leads.{col} may already exist: {e}")

        # -- Seed default workflows for all orgs --
        orgs = conn.execute(text("SELECT id FROM organizations")).fetchall()
        import uuid as uuid_mod
        for org in orgs:
            org_id = org[0]
            for wf in DEFAULT_WORKFLOWS:
                existing = conn.execute(text(
                    "SELECT id FROM workflow_definitions WHERE organization_id = :org_id AND key = :key"
                ), {"org_id": org_id, "key": wf["key"]}).fetchone()
                if not existing:
                    conn.execute(text("""
                        INSERT INTO workflow_definitions (id, organization_id, key, name, color, sort_order, is_active)
                        VALUES (:id, :org_id, :key, :name, :color, :sort_order, TRUE)
                    """), {
                        "id": str(uuid_mod.uuid4()),
                        "org_id": org_id,
                        "key": wf["key"],
                        "name": wf["name"],
                        "color": wf["color"],
                        "sort_order": wf["sort_order"],
                    })
                    results["workflows_seeded"] += 1

        if not db:
            conn.commit()
        else:
            db.flush()

        logger.info(f"Migration complete: {results}")
        return results

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        if not db:
            conn.rollback()
        raise
    finally:
        if not db:
            conn.close()


if __name__ == "__main__":
    result = run_migration()
    print(f"Migration results: {result}")
