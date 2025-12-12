#!/usr/bin/env python3
"""
PURL System Launch Script
=========================
Handles database setup, migrations, and validation for both local and production environments.

Usage:
    python scripts/launch_purl.py [--env local|production] [--skip-seed]
"""

import os
import sys
import argparse
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ANSI colors for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_banner():
    """Print launch banner"""
    print(f"""
{Colors.BLUE}╔══════════════════════════════════════════════════════════════╗
║                                                                ║
║   {Colors.BOLD}PERENNIA AI - PURL SYSTEM LAUNCHER{Colors.END}{Colors.BLUE}                        ║
║                                                                ║
║   Personalized URL System for Mortgage Applications            ║
║                                                                ║
╚══════════════════════════════════════════════════════════════╝{Colors.END}
""")


def check_environment():
    """Check environment variables"""
    logger.info("Checking environment configuration...")

    required = ['DATABASE_URL', 'SECRET_KEY']
    recommended = ['ANTHROPIC_API_KEY', 'REDIS_URL', 'SENDGRID_API_KEY']
    purl_vars = ['PURL_TOKEN_EXPIRY_DAYS', 'PURL_BASE_URL']

    missing_required = []
    missing_recommended = []

    for var in required:
        if not os.getenv(var):
            missing_required.append(var)
        else:
            logger.info(f"  {Colors.GREEN}✓{Colors.END} {var} is set")

    for var in recommended:
        if not os.getenv(var):
            missing_recommended.append(var)
            logger.warning(f"  {Colors.YELLOW}⚠{Colors.END} {var} not set (recommended)")
        else:
            logger.info(f"  {Colors.GREEN}✓{Colors.END} {var} is set")

    for var in purl_vars:
        if os.getenv(var):
            logger.info(f"  {Colors.GREEN}✓{Colors.END} {var} = {os.getenv(var)}")
        else:
            logger.info(f"  {Colors.BLUE}ℹ{Colors.END} {var} using default")

    if missing_required:
        logger.error(f"{Colors.RED}Missing required variables: {missing_required}{Colors.END}")
        return False

    return True


def check_database():
    """Check database connection"""
    logger.info("Testing database connection...")

    try:
        from sqlalchemy import create_engine, text

        db_url = os.getenv('DATABASE_URL', 'sqlite:///./test_agentic_crm.db')
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)

        is_sqlite = db_url.startswith('sqlite')
        engine = create_engine(db_url)

        with engine.connect() as conn:
            if is_sqlite:
                result = conn.execute(text("SELECT sqlite_version()"))
                version = result.fetchone()[0]
                logger.info(f"  {Colors.GREEN}✓{Colors.END} SQLite connected: v{version}")
            else:
                result = conn.execute(text("SELECT version()"))
                version = result.fetchone()[0][:50]
                logger.info(f"  {Colors.GREEN}✓{Colors.END} PostgreSQL connected: {version}...")

        return engine, is_sqlite

    except Exception as e:
        logger.error(f"{Colors.RED}Database connection failed: {e}{Colors.END}")
        return None, False


def run_purl_migrations_sqlite(engine):
    """Run SQLite-compatible PURL migrations"""
    logger.info("Running PURL migrations (SQLite mode)...")

    sql_commands = [
        # Workspaces
        """
        CREATE TABLE IF NOT EXISTS purl_workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER,
            slug VARCHAR(255) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'lead',
            display_name VARCHAR(500) NOT NULL,
            source VARCHAR(255),
            owner_user_id INTEGER,
            lead_at TIMESTAMP,
            application_at TIMESTAMP,
            active_loan_at TIMESTAMP,
            closing_at TIMESTAMP,
            post_close_at TIMESTAMP,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(organization_id, slug)
        )
        """,

        # Access Tokens
        """
        CREATE TABLE IF NOT EXISTS purl_access_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER,
            workspace_id INTEGER,
            token_prefix VARCHAR(20) NOT NULL UNIQUE,
            token_hash VARCHAR(128) NOT NULL,
            token_type VARCHAR(50) NOT NULL DEFAULT 'borrower',
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            scope TEXT DEFAULT '["read", "write"]',
            expires_at TIMESTAMP,
            last_used_at TIMESTAMP,
            use_count INTEGER DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Sessions
        """
        CREATE TABLE IF NOT EXISTS purl_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER,
            workspace_id INTEGER,
            token_id INTEGER,
            session_token VARCHAR(128) NOT NULL UNIQUE,
            ip_address VARCHAR(45),
            user_agent TEXT,
            device_fingerprint VARCHAR(128),
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity_at TIMESTAMP,
            ended_at TIMESTAMP,
            metadata TEXT DEFAULT '{}'
        )
        """,

        # Applications
        """
        CREATE TABLE IF NOT EXISTS purl_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER,
            workspace_id INTEGER,
            application_type VARCHAR(100) NOT NULL DEFAULT 'purchase',
            status VARCHAR(50) NOT NULL DEFAULT 'draft',
            form_data TEXT DEFAULT '{}',
            borrower_data TEXT DEFAULT '{}',
            property_data TEXT DEFAULT '{}',
            loan_data TEXT DEFAULT '{}',
            validation_errors TEXT DEFAULT '[]',
            submitted_at TIMESTAMP,
            los_export_at TIMESTAMP,
            los_loan_id VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Documents
        """
        CREATE TABLE IF NOT EXISTS purl_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER,
            workspace_id INTEGER,
            application_id INTEGER,
            category VARCHAR(100) NOT NULL,
            document_type VARCHAR(100) NOT NULL,
            display_name VARCHAR(500) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            storage_provider VARCHAR(50) DEFAULT 's3',
            storage_key VARCHAR(1000),
            original_filename VARCHAR(500),
            mime_type VARCHAR(100),
            file_size INTEGER,
            uploaded_by_type VARCHAR(50),
            uploaded_by_id INTEGER,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Timeline Events
        """
        CREATE TABLE IF NOT EXISTS purl_timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER,
            workspace_id INTEGER,
            event_type VARCHAR(100) NOT NULL,
            actor_type VARCHAR(50) NOT NULL,
            actor_id INTEGER,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            icon VARCHAR(50),
            color VARCHAR(50),
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Events Outbox
        """
        CREATE TABLE IF NOT EXISTS purl_events_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key VARCHAR(100) NOT NULL,
            payload TEXT NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            next_attempt_at TIMESTAMP,
            processed_at TIMESTAMP,
            error_message TEXT,
            locked_at TIMESTAMP,
            locked_by VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Audit Log
        """
        CREATE TABLE IF NOT EXISTS purl_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER,
            workspace_id INTEGER,
            action VARCHAR(100) NOT NULL,
            actor_type VARCHAR(50) NOT NULL,
            actor_id INTEGER,
            resource_type VARCHAR(100),
            resource_id INTEGER,
            old_value TEXT,
            new_value TEXT,
            ip_address VARCHAR(45),
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Create indexes
        "CREATE INDEX IF NOT EXISTS idx_purl_workspaces_slug ON purl_workspaces(slug)",
        "CREATE INDEX IF NOT EXISTS idx_purl_tokens_prefix ON purl_access_tokens(token_prefix)",
        "CREATE INDEX IF NOT EXISTS idx_purl_sessions_token ON purl_sessions(session_token)",
        "CREATE INDEX IF NOT EXISTS idx_purl_events_status ON purl_events_outbox(status)",
        "CREATE INDEX IF NOT EXISTS idx_purl_audit_workspace ON purl_audit_log(workspace_id)",
    ]

    from sqlalchemy import text

    with engine.connect() as conn:
        for sql in sql_commands:
            try:
                conn.execute(text(sql.strip()))
                conn.commit()
            except Exception as e:
                if 'already exists' not in str(e).lower():
                    logger.warning(f"  SQL warning: {e}")

    logger.info(f"  {Colors.GREEN}✓{Colors.END} PURL tables created/verified")
    return True


def run_purl_migrations_postgres(engine):
    """Run PostgreSQL PURL migrations using the full migration file"""
    logger.info("Running PURL migrations (PostgreSQL mode)...")

    try:
        # Try to import and run the existing migration
        migration_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'migrations',
            'add_purl_system.py'
        )

        if os.path.exists(migration_path):
            import importlib.util
            spec = importlib.util.spec_from_file_location("add_purl_system", migration_path)
            migration_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration_module)
            migration_module.run_migration()
            logger.info(f"  {Colors.GREEN}✓{Colors.END} PURL PostgreSQL migrations completed")
            return True
        else:
            logger.error(f"Migration file not found: {migration_path}")
            return False

    except Exception as e:
        logger.error(f"Migration error: {e}")
        return False


def verify_tables(engine, is_sqlite):
    """Verify PURL tables exist"""
    logger.info("Verifying PURL tables...")

    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    required_tables = [
        'purl_workspaces',
        'purl_access_tokens',
        'purl_sessions',
        'purl_applications',
        'purl_documents',
        'purl_timeline_events',
        'purl_events_outbox',
        'purl_audit_log'
    ]

    missing = []
    for table in required_tables:
        if table in tables:
            logger.info(f"  {Colors.GREEN}✓{Colors.END} {table}")
        else:
            logger.warning(f"  {Colors.RED}✗{Colors.END} {table} - MISSING")
            missing.append(table)

    if missing:
        logger.error(f"Missing tables: {missing}")
        return False

    return True


def seed_test_data(engine, is_sqlite):
    """Seed test data for development"""
    logger.info("Seeding test data...")

    from sqlalchemy import text
    import secrets
    import hashlib

    # Generate test token
    raw_token = f"purl_test_{secrets.token_urlsafe(24)}"
    token_prefix = raw_token[:20]
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    try:
        with engine.connect() as conn:
            # Check if test workspace exists
            result = conn.execute(text(
                "SELECT id FROM purl_workspaces WHERE slug = 'test-borrower'"
            ))
            existing = result.fetchone()

            if not existing:
                # Create test workspace
                conn.execute(text("""
                    INSERT INTO purl_workspaces
                    (slug, status, display_name, source, metadata, created_at, updated_at)
                    VALUES
                    ('test-borrower', 'lead', 'Test Borrower', 'manual', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """))
                conn.commit()

                # Get workspace ID
                result = conn.execute(text(
                    "SELECT id FROM purl_workspaces WHERE slug = 'test-borrower'"
                ))
                workspace_id = result.fetchone()[0]

                # Create test token
                conn.execute(text(f"""
                    INSERT INTO purl_access_tokens
                    (workspace_id, token_prefix, token_hash, token_type, status, scope, created_at, updated_at)
                    VALUES
                    ({workspace_id}, '{token_prefix}', '{token_hash}', 'borrower', 'active', '["read", "write"]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """))
                conn.commit()

                logger.info(f"  {Colors.GREEN}✓{Colors.END} Test workspace created")
                logger.info(f"  {Colors.BLUE}ℹ{Colors.END} Test token: {raw_token}")
            else:
                logger.info(f"  {Colors.BLUE}ℹ{Colors.END} Test workspace already exists")

        return True

    except Exception as e:
        logger.error(f"Seed error: {e}")
        return False


def print_summary(success, is_sqlite):
    """Print launch summary"""

    db_type = "SQLite (local)" if is_sqlite else "PostgreSQL (production)"

    if success:
        print(f"""
{Colors.GREEN}╔══════════════════════════════════════════════════════════════╗
║                                                                ║
║   {Colors.BOLD}PURL SYSTEM LAUNCH SUCCESSFUL{Colors.END}{Colors.GREEN}                             ║
║                                                                ║
╚══════════════════════════════════════════════════════════════╝{Colors.END}

{Colors.BOLD}Summary:{Colors.END}
  • Database: {db_type}
  • Tables: All PURL tables verified
  • Status: Ready for use

{Colors.BOLD}Next Steps:{Colors.END}
  1. Start the backend server:
     {Colors.BLUE}cd backend && uvicorn main:app --reload{Colors.END}

  2. Start the frontend:
     {Colors.BLUE}cd frontend && npm start{Colors.END}

  3. Access PURL Portal:
     {Colors.BLUE}http://localhost:3000/portal/test-borrower{Colors.END}

{Colors.BOLD}API Endpoints:{Colors.END}
  • Generate PURL: POST /api/purl/generate
  • Validate Token: GET /api/purl/validate/{{token}}
  • Portal Data: GET /api/purl/portal/{{token}}
  • Submit App: POST /api/purl/portal/{{token}}/application

{Colors.YELLOW}For production deployment, see: backend/PURL_README.md{Colors.END}
""")
    else:
        print(f"""
{Colors.RED}╔══════════════════════════════════════════════════════════════╗
║                                                                ║
║   PURL SYSTEM LAUNCH FAILED                                    ║
║                                                                ║
╚══════════════════════════════════════════════════════════════╝{Colors.END}

Please check the errors above and try again.
See backend/PURL_README.md for troubleshooting.
""")


def main():
    parser = argparse.ArgumentParser(description='Launch PURL System')
    parser.add_argument('--env', choices=['local', 'production'], default='local',
                       help='Environment to launch (default: local)')
    parser.add_argument('--skip-seed', action='store_true',
                       help='Skip seeding test data')
    args = parser.parse_args()

    print_banner()

    # Load environment
    env_file = '.env' if args.env == 'local' else '.env.production'
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), env_file)

    if os.path.exists(env_path):
        logger.info(f"Loading environment from {env_file}")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

    success = True

    # Step 1: Check environment
    if not check_environment():
        success = False

    # Step 2: Check database
    engine, is_sqlite = check_database()
    if not engine:
        success = False

    if success:
        # Step 3: Run migrations
        if is_sqlite:
            if not run_purl_migrations_sqlite(engine):
                success = False
        else:
            if not run_purl_migrations_postgres(engine):
                success = False

        # Step 4: Verify tables
        if success and not verify_tables(engine, is_sqlite):
            success = False

        # Step 5: Seed test data (optional)
        if success and not args.skip_seed:
            seed_test_data(engine, is_sqlite)

    # Print summary
    print_summary(success, is_sqlite if engine else True)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
