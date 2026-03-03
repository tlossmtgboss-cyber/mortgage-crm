"""
Create recruit_ai_audit_log table for AI decision audit trail.

Tracks every AI analysis invocation with:
  - Who triggered it (user)
  - Which model was used
  - Token counts and prompt hash (for reproducibility)
  - Confidence score and recommendation
  - Analysis summary (JSONB)
"""

from sqlalchemy import text
from database import engine
import logging

logger = logging.getLogger(__name__)


def run_migration():
    """Create recruit_ai_audit_log table."""
    results = {"created": False, "indexes": [], "errors": []}

    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS recruit_ai_audit_log (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    candidate_id INTEGER NOT NULL,
                    triggered_by INTEGER NOT NULL,
                    model_used VARCHAR(100) NOT NULL,
                    prompt_hash VARCHAR(64),
                    prompt_tokens INTEGER,
                    response_tokens INTEGER,
                    confidence_score FLOAT,
                    hire_recommendation VARCHAR(30),
                    analysis_summary JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            results["created"] = True
            logger.info("Created recruit_ai_audit_log table")

        except Exception as e:
            logger.error(f"Error creating table: {e}")
            results["errors"].append({"table": "recruit_ai_audit_log", "error": str(e)})

        # Indexes
        indexes = [
            ("idx_recruit_ai_audit_candidate", "candidate_id"),
            ("idx_recruit_ai_audit_org", "organization_id"),
            ("idx_recruit_ai_audit_created", "created_at"),
        ]

        for idx_name, col in indexes:
            try:
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS {idx_name}
                    ON recruit_ai_audit_log ({col})
                """))
                results["indexes"].append(idx_name)
            except Exception as e:
                logger.error(f"Error creating index {idx_name}: {e}")
                results["errors"].append({"index": idx_name, "error": str(e)})

        conn.commit()

    logger.info(f"AI audit log migration complete: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_migration()
    print(result)
