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


def create_all_tables(Base, engine):
    """Create all ORM tables with multi-pass dependency resolution.

    Some models reference tables from factory functions that may not be
    registered in Base.metadata. This function:
    1. Drops the public schema cleanly
    2. Creates tables in multiple passes — each pass creates tables whose
       FK dependencies are now satisfied
    3. Skips tables with truly unresolvable FK references (factory models)
    """
    # First try the fast path (works when all FK targets are registered)
    try:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        return
    except Exception as e:
        logger.debug(f"Bulk create_all failed ({e}), falling back to multi-pass creation")

    # Clean slate — drop entire schema
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    # Multi-pass creation: keep iterating until no more tables can be created
    remaining = set(Base.metadata.tables.keys())
    max_passes = 10

    for pass_num in range(max_passes):
        created_this_pass = []

        for table_name in list(remaining):
            table = Base.metadata.tables[table_name]
            try:
                table.create(bind=engine, checkfirst=True)
                created_this_pass.append(table_name)
            except Exception:
                pass  # Will retry next pass

        for name in created_this_pass:
            remaining.discard(name)

        if not remaining or not created_this_pass:
            break

    if remaining:
        logger.info(
            f"Skipped {len(remaining)} tables with unresolvable FK targets: "
            f"{sorted(remaining)}"
        )
