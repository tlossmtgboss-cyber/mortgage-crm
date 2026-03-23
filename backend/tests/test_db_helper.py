"""
Shared test database helper for standalone test files.

Provides a PostgreSQL-backed engine and session factory that matches
conftest.py's configuration. Use this instead of creating SQLite engines.

Usage:
    from tests.test_db_helper import get_test_engine, get_test_session, create_all_tables

    engine = get_test_engine()
    Session = get_test_session(engine)
"""
import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Same env var and default as conftest.py
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://localhost:5432/test_perennia",
)

if TEST_DATABASE_URL.startswith("postgres://"):
    TEST_DATABASE_URL = TEST_DATABASE_URL.replace("postgres://", "postgresql://", 1)


def get_test_engine(**kwargs):
    """Get a PostgreSQL test engine. Accepts extra create_engine kwargs."""
    return create_engine(TEST_DATABASE_URL, **kwargs)


def get_test_session(engine=None):
    """Get a sessionmaker bound to the test engine."""
    if engine is None:
        engine = get_test_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _register_factory_models(Base):
    """Register models defined in factory functions so create_all() can resolve FKs."""
    try:
        from workflow_config_models import create_workflow_config_models
        create_workflow_config_models(Base)
    except Exception as e:
        logger.debug(f"Workflow config models registration skipped: {e}")
    try:
        from models.workflow_sla import create_workflow_sla_models
        create_workflow_sla_models(Base)
    except Exception as e:
        logger.debug(f"Workflow SLA models registration skipped: {e}")


def create_all_tables(Base, engine):
    """Create all ORM tables for testing.

    1. Registers factory-defined models (workflow tables)
    2. Drops the public schema cleanly (avoids stale constraint issues)
    3. Uses create_all() for correct dependency ordering
    4. Falls back to multi-pass per-table creation if create_all() fails
    """
    _register_factory_models(Base)

    # Clean slate — drop entire schema to avoid stale constraints/indexes
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    # Try bulk create_all (handles dependency ordering)
    try:
        Base.metadata.create_all(bind=engine)
        return
    except Exception as e:
        logger.debug(f"Bulk create_all failed ({e}), falling back to multi-pass")

    # Multi-pass fallback for any remaining FK resolution issues
    remaining = set(Base.metadata.tables.keys())
    for _ in range(15):
        created = []
        for tname in list(remaining):
            table = Base.metadata.tables[tname]
            try:
                table.create(bind=engine, checkfirst=True)
                created.append(tname)
            except Exception:
                pass
        remaining -= set(created)
        if not remaining or not created:
            break

    if remaining:
        logger.info(f"Skipped {len(remaining)} tables: {sorted(remaining)[:10]}...")
