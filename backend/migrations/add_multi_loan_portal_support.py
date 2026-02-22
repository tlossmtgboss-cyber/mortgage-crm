"""
Multi-Loan Client Portal Support Migration

Creates infrastructure for:
- Portal mode tracking (transaction vs servicing)
- Loan chaining (refinanced_from relationship)
- Loan lifecycle tracking (paid off status)
- Portal session management

Based on the Multi-Loan Client Portal Enhancement specification.
"""

import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_migration(db: Session):
    """Run the multi-loan portal support migration."""

    logger.info("🚀 Starting Multi-Loan Portal Support migration...")

    # =============================================================================
    # PURL_LOANS TABLE MODIFICATIONS
    # Add new columns for portal mode, loan chaining, and lifecycle tracking
    # =============================================================================

    # Add portal_mode column - determines UI/feature set shown to borrower
    try:
        db.execute(text("""
            ALTER TABLE purl_loans
            ADD COLUMN IF NOT EXISTS portal_mode VARCHAR(20) DEFAULT 'transaction'
            CHECK (portal_mode IN ('transaction', 'servicing'))
        """))
        logger.info("✅ Added portal_mode column to purl_loans")
    except Exception as e:
        logger.warning(f"portal_mode column may already exist or error: {e}")

    # Add refinanced_from_loan_id - links new loans to their predecessor
    try:
        db.execute(text("""
            ALTER TABLE purl_loans
            ADD COLUMN IF NOT EXISTS refinanced_from_loan_id INTEGER
            REFERENCES purl_loans(id) ON DELETE SET NULL
        """))
        logger.info("✅ Added refinanced_from_loan_id column to purl_loans")
    except Exception as e:
        logger.warning(f"refinanced_from_loan_id column may already exist or error: {e}")

    # Add paid_off_date - when the loan was paid off (for servicing history)
    try:
        db.execute(text("""
            ALTER TABLE purl_loans
            ADD COLUMN IF NOT EXISTS paid_off_date TIMESTAMP WITH TIME ZONE
        """))
        logger.info("✅ Added paid_off_date column to purl_loans")
    except Exception as e:
        logger.warning(f"paid_off_date column may already exist or error: {e}")

    # Add paid_off_reason - why the loan was paid off
    try:
        db.execute(text("""
            ALTER TABLE purl_loans
            ADD COLUMN IF NOT EXISTS paid_off_reason VARCHAR(50)
            CHECK (paid_off_reason IN ('refinanced', 'sold', 'paid_in_full', 'foreclosure', 'other'))
        """))
        logger.info("✅ Added paid_off_reason column to purl_loans")
    except Exception as e:
        logger.warning(f"paid_off_reason column may already exist or error: {e}")

    # =============================================================================
    # LOAN_PORTAL_SESSIONS TABLE
    # Tracks borrower's current portal context and session history
    # =============================================================================

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loan_portal_sessions (
            id SERIAL PRIMARY KEY,

            -- Session identification
            session_id UUID NOT NULL DEFAULT gen_random_uuid(),

            -- User context
            borrower_profile_id UUID NOT NULL,
            workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,

            -- Current loan context
            current_loan_id INTEGER REFERENCES purl_loans(id) ON DELETE SET NULL,
            portal_mode VARCHAR(20) NOT NULL DEFAULT 'transaction'
                CHECK (portal_mode IN ('transaction', 'servicing')),

            -- Session state
            is_active BOOLEAN DEFAULT true,
            last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            -- Session metadata
            device_info JSONB,
            ip_address VARCHAR(45),
            user_agent TEXT,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP WITH TIME ZONE
        )
    """))
    logger.info("✅ Created loan_portal_sessions table")

    # =============================================================================
    # LOAN_PORTAL_ACTIVITY TABLE
    # Tracks actions taken by borrower in portal for analytics and audit
    # =============================================================================

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loan_portal_activity (
            id SERIAL PRIMARY KEY,

            -- Context
            session_id UUID NOT NULL,
            borrower_profile_id UUID NOT NULL,
            loan_id INTEGER REFERENCES purl_loans(id) ON DELETE SET NULL,

            -- Activity details
            activity_type VARCHAR(50) NOT NULL,
            activity_data JSONB,
            page_path VARCHAR(255),

            -- Timestamp
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """))
    logger.info("✅ Created loan_portal_activity table")

    # =============================================================================
    # LOAN_SWITCH_HISTORY TABLE
    # Tracks when borrowers switch between loans for analytics
    # =============================================================================

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loan_switch_history (
            id SERIAL PRIMARY KEY,

            -- Context
            session_id UUID NOT NULL,
            borrower_profile_id UUID NOT NULL,

            -- Switch details
            from_loan_id INTEGER REFERENCES purl_loans(id) ON DELETE SET NULL,
            to_loan_id INTEGER REFERENCES purl_loans(id) ON DELETE SET NULL,
            from_mode VARCHAR(20),
            to_mode VARCHAR(20),

            -- Reason (optional)
            switch_reason VARCHAR(100),

            -- Timestamp
            switched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """))
    logger.info("✅ Created loan_switch_history table")

    # =============================================================================
    # INDEXES FOR PERFORMANCE
    # =============================================================================

    indexes = [
        # purl_loans indexes for portal queries
        "CREATE INDEX IF NOT EXISTS idx_purl_loans_portal_mode ON purl_loans(portal_mode)",
        "CREATE INDEX IF NOT EXISTS idx_purl_loans_refinanced_from ON purl_loans(refinanced_from_loan_id)",
        "CREATE INDEX IF NOT EXISTS idx_purl_loans_paid_off ON purl_loans(paid_off_date) WHERE paid_off_date IS NOT NULL",

        # Portal sessions indexes
        "CREATE INDEX IF NOT EXISTS idx_portal_sessions_borrower ON loan_portal_sessions(borrower_profile_id)",
        "CREATE INDEX IF NOT EXISTS idx_portal_sessions_workspace ON loan_portal_sessions(workspace_id)",
        "CREATE INDEX IF NOT EXISTS idx_portal_sessions_active ON loan_portal_sessions(is_active) WHERE is_active = true",
        "CREATE INDEX IF NOT EXISTS idx_portal_sessions_session ON loan_portal_sessions(session_id)",

        # Portal activity indexes
        "CREATE INDEX IF NOT EXISTS idx_portal_activity_session ON loan_portal_activity(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_portal_activity_borrower ON loan_portal_activity(borrower_profile_id)",
        "CREATE INDEX IF NOT EXISTS idx_portal_activity_loan ON loan_portal_activity(loan_id)",
        "CREATE INDEX IF NOT EXISTS idx_portal_activity_type ON loan_portal_activity(activity_type)",
        "CREATE INDEX IF NOT EXISTS idx_portal_activity_created ON loan_portal_activity(created_at)",

        # Switch history indexes
        "CREATE INDEX IF NOT EXISTS idx_switch_history_session ON loan_switch_history(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_switch_history_borrower ON loan_switch_history(borrower_profile_id)",
    ]

    for idx_sql in indexes:
        try:
            db.execute(text(idx_sql))
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")

    db.commit()
    logger.info("✅ Multi-Loan Portal Support migration completed successfully!")

    return True


def run_migration_sqlite(db: Session):
    """Run migration for SQLite (local development)."""

    logger.info("🚀 Starting Multi-Loan Portal Support migration (SQLite)...")

    # SQLite doesn't support IF NOT EXISTS for ALTER TABLE
    # Check if columns exist before adding

    try:
        db.execute(text("SELECT portal_mode FROM purl_loans LIMIT 1"))
        logger.info("portal_mode column already exists")
    except Exception as e:
        logger.error(f"Error checking portal_mode column, will add: {e}")
        db.execute(text("""
            ALTER TABLE purl_loans ADD COLUMN portal_mode VARCHAR(20) DEFAULT 'transaction'
        """))
        logger.info("✅ Added portal_mode column to purl_loans")

    try:
        db.execute(text("SELECT refinanced_from_loan_id FROM purl_loans LIMIT 1"))
        logger.info("refinanced_from_loan_id column already exists")
    except Exception as e:
        logger.error(f"Error checking refinanced_from_loan_id column, will add: {e}")
        db.execute(text("""
            ALTER TABLE purl_loans ADD COLUMN refinanced_from_loan_id INTEGER
        """))
        logger.info("✅ Added refinanced_from_loan_id column to purl_loans")

    try:
        db.execute(text("SELECT paid_off_date FROM purl_loans LIMIT 1"))
        logger.info("paid_off_date column already exists")
    except Exception as e:
        logger.error(f"Error checking paid_off_date column, will add: {e}")
        db.execute(text("""
            ALTER TABLE purl_loans ADD COLUMN paid_off_date TIMESTAMP
        """))
        logger.info("✅ Added paid_off_date column to purl_loans")

    try:
        db.execute(text("SELECT paid_off_reason FROM purl_loans LIMIT 1"))
        logger.info("paid_off_reason column already exists")
    except Exception as e:
        logger.error(f"Error checking paid_off_reason column, will add: {e}")
        db.execute(text("""
            ALTER TABLE purl_loans ADD COLUMN paid_off_reason VARCHAR(50)
        """))
        logger.info("✅ Added paid_off_reason column to purl_loans")

    # Create portal sessions table
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loan_portal_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            borrower_profile_id TEXT NOT NULL,
            workspace_id INTEGER NOT NULL,
            current_loan_id INTEGER,
            portal_mode VARCHAR(20) NOT NULL DEFAULT 'transaction',
            is_active INTEGER DEFAULT 1,
            last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            device_info TEXT,
            ip_address VARCHAR(45),
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            FOREIGN KEY (current_loan_id) REFERENCES purl_loans(id) ON DELETE SET NULL
        )
    """))
    logger.info("✅ Created loan_portal_sessions table")

    # Create portal activity table
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loan_portal_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            borrower_profile_id TEXT NOT NULL,
            loan_id INTEGER,
            activity_type VARCHAR(50) NOT NULL,
            activity_data TEXT,
            page_path VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (loan_id) REFERENCES purl_loans(id) ON DELETE SET NULL
        )
    """))
    logger.info("✅ Created loan_portal_activity table")

    # Create loan switch history table
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loan_switch_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            borrower_profile_id TEXT NOT NULL,
            from_loan_id INTEGER,
            to_loan_id INTEGER,
            from_mode VARCHAR(20),
            to_mode VARCHAR(20),
            switch_reason VARCHAR(100),
            switched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_loan_id) REFERENCES purl_loans(id) ON DELETE SET NULL,
            FOREIGN KEY (to_loan_id) REFERENCES purl_loans(id) ON DELETE SET NULL
        )
    """))
    logger.info("✅ Created loan_switch_history table")

    # Create indexes (SQLite syntax)
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_purl_loans_portal_mode ON purl_loans(portal_mode)",
        "CREATE INDEX IF NOT EXISTS idx_purl_loans_refinanced_from ON purl_loans(refinanced_from_loan_id)",
        "CREATE INDEX IF NOT EXISTS idx_portal_sessions_borrower ON loan_portal_sessions(borrower_profile_id)",
        "CREATE INDEX IF NOT EXISTS idx_portal_sessions_workspace ON loan_portal_sessions(workspace_id)",
        "CREATE INDEX IF NOT EXISTS idx_portal_sessions_session ON loan_portal_sessions(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_portal_activity_session ON loan_portal_activity(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_portal_activity_borrower ON loan_portal_activity(borrower_profile_id)",
        "CREATE INDEX IF NOT EXISTS idx_portal_activity_loan ON loan_portal_activity(loan_id)",
        "CREATE INDEX IF NOT EXISTS idx_switch_history_session ON loan_switch_history(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_switch_history_borrower ON loan_switch_history(borrower_profile_id)",
    ]

    for idx_sql in indexes:
        try:
            db.execute(text(idx_sql))
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")

    db.commit()
    logger.info("✅ Multi-Loan Portal Support migration (SQLite) completed successfully!")

    return True


if __name__ == "__main__":
    import os
    from database import SessionLocal, DATABASE_URL

    db = SessionLocal()
    try:
        if DATABASE_URL.startswith("sqlite"):
            run_migration_sqlite(db)
        else:
            run_migration(db)
    finally:
        db.close()
