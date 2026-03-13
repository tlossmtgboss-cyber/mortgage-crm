"""
Migration: Add AI Benchmark Tables

Creates tables for the AI classification benchmarking framework:
- ai_benchmark_datasets: Named collections of labeled samples
- ai_benchmark_samples: Individual labeled samples with ground-truth doc types

Run: python -m migrations.add_ai_benchmark_tables
"""

import logging
import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    """Run the AI benchmark tables migration."""
    if engine is None:
        database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(database_url)

    with engine.connect() as conn:
        logger.info("Starting AI benchmark tables migration...")
        print("[AI_BENCHMARK] Starting AI benchmark tables migration...")

        # =================================================================
        # AI BENCHMARK DATASETS
        # =================================================================

        print("[AI_BENCHMARK] Creating ai_benchmark_datasets table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_benchmark_datasets (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                description VARCHAR(1000),
                sample_count INTEGER NOT NULL DEFAULT 0,
                last_benchmark_accuracy FLOAT,
                last_benchmark_date TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # Indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ai_bench_ds_org_id
            ON ai_benchmark_datasets (organization_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ai_bench_ds_name
            ON ai_benchmark_datasets (name)
        """))

        # =================================================================
        # AI BENCHMARK SAMPLES
        # =================================================================

        print("[AI_BENCHMARK] Creating ai_benchmark_samples table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_benchmark_samples (
                id SERIAL PRIMARY KEY,
                dataset_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                document_hash VARCHAR(64) NOT NULL,
                actual_doc_type VARCHAR(50) NOT NULL,
                actual_category VARCHAR(50),
                source VARCHAR(20) NOT NULL DEFAULT 'human_correction',
                metadata JSON,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))

        # Indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ai_bench_sample_ds_id
            ON ai_benchmark_samples (dataset_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ai_bench_sample_org_id
            ON ai_benchmark_samples (organization_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ai_bench_sample_doc_hash
            ON ai_benchmark_samples (document_hash)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ai_bench_sample_doc_type
            ON ai_benchmark_samples (actual_doc_type)
        """))

        conn.commit()
        print("[AI_BENCHMARK] AI benchmark tables migration complete.")
        logger.info("AI benchmark tables migration complete.")


if __name__ == "__main__":
    run_migration()
