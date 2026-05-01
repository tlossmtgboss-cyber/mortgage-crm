"""
Add SSO Configuration Tables

Creates the sso_configurations table for per-organization SAML/OIDC
SSO configuration with encrypted certificate storage.

This is separate from the existing sso_configs table (used by the
legacy SSOConfig model). Both tables can coexist; sso_configurations
is the new canonical table for the enterprise SSO feature.

Usage:
    python -m migrations.add_sso_tables
    # or
    from migrations.add_sso_tables import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


# Table and column definitions
SSO_CONFIGURATIONS_COLUMNS = [
    ("id", "VARCHAR(36)", None, True),  # (name, type, default, is_primary_key)
    ("organization_id", "INTEGER NOT NULL UNIQUE", None, False),
    ("provider", "VARCHAR(50) NOT NULL DEFAULT 'custom'", None, False),
    ("entity_id", "VARCHAR(500)", None, False),
    ("sso_url", "VARCHAR(1000)", None, False),
    ("slo_url", "VARCHAR(1000)", None, False),
    ("x509_cert", "TEXT", None, False),
    ("sp_entity_id", "VARCHAR(500)", None, False),
    ("attribute_mapping", "JSONB DEFAULT '{}'::jsonb", None, False),
    ("default_role", "VARCHAR(50) DEFAULT 'loan_officer'", None, False),
    ("default_permission_role", "VARCHAR(50) DEFAULT 'sales'", None, False),
    ("enforce_sso", "BOOLEAN DEFAULT FALSE", None, False),
    ("auto_provision", "BOOLEAN DEFAULT TRUE", None, False),
    ("is_active", "BOOLEAN DEFAULT TRUE", None, False),
    ("oidc_discovery_url", "VARCHAR(1000)", None, False),
    ("oidc_client_id", "VARCHAR(500)", None, False),
    ("oidc_client_secret", "TEXT", None, False),
    ("created_at", "TIMESTAMP DEFAULT NOW()", None, False),
    ("updated_at", "TIMESTAMP DEFAULT NOW()", None, False),
]

# Columns to add to the existing sso_configs table (if it exists)
# to keep it in sync with new features
SSO_CONFIGS_NEW_COLUMNS = [
    ("enforce_sso", "BOOLEAN", "FALSE"),
]

# Columns to add to the organizations table (if not already present)
ORG_NEW_COLUMNS = [
    ("sso_enforced", "BOOLEAN", "FALSE"),
]

# Columns to add to the users table (if not already present)
USER_NEW_COLUMNS = [
    ("sso_provider", "VARCHAR(50)", None),
    ("sso_subject_id", "VARCHAR(255)", None),
]


def run_migration():
    """Run the SSO tables migration."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        total_created = 0
        total_skipped = 0

        # =====================================================================
        # 1. Create sso_configurations table
        # =====================================================================
        logger.info("Creating sso_configurations table...")

        if is_sqlite:
            # SQLite version
            cols = []
            for name, col_type, default, is_pk in SSO_CONFIGURATIONS_COLUMNS:
                if is_pk:
                    cols.append(f"{name} {col_type} PRIMARY KEY")
                else:
                    cols.append(f"{name} {col_type.replace('JSONB', 'TEXT').replace('::jsonb', '')}")

            create_sql = f"CREATE TABLE IF NOT EXISTS sso_configurations ({', '.join(cols)})"
            try:
                conn.execute(text(create_sql))
                total_created += 1
                logger.info("  Created sso_configurations table (SQLite)")
            except Exception as e:
                if "already exists" in str(e).lower():
                    total_skipped += 1
                    logger.info("  sso_configurations table already exists")
                else:
                    logger.error(f"  Failed to create sso_configurations: {e}")
        else:
            # PostgreSQL version
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS sso_configurations (
                        id VARCHAR(36) PRIMARY KEY,
                        organization_id INTEGER NOT NULL UNIQUE
                            REFERENCES organizations(id) ON DELETE CASCADE,
                        provider VARCHAR(50) NOT NULL DEFAULT 'custom',
                        entity_id VARCHAR(500),
                        sso_url VARCHAR(1000),
                        slo_url VARCHAR(1000),
                        x509_cert TEXT,
                        sp_entity_id VARCHAR(500),
                        attribute_mapping JSONB DEFAULT '{}'::jsonb,
                        default_role VARCHAR(50) DEFAULT 'loan_officer',
                        default_permission_role VARCHAR(50) DEFAULT 'sales',
                        enforce_sso BOOLEAN DEFAULT FALSE,
                        auto_provision BOOLEAN DEFAULT TRUE,
                        is_active BOOLEAN DEFAULT TRUE,
                        oidc_discovery_url VARCHAR(1000),
                        oidc_client_id VARCHAR(500),
                        oidc_client_secret TEXT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                total_created += 1
                logger.info("  Created sso_configurations table (PostgreSQL)")
            except Exception as e:
                if "already exists" in str(e).lower():
                    total_skipped += 1
                    logger.info("  sso_configurations table already exists")
                else:
                    logger.error(f"  Failed to create sso_configurations: {e}")

        # =====================================================================
        # 2. Create indexes on sso_configurations
        # =====================================================================
        indexes = [
            ("ix_sso_configurations_org_id", "sso_configurations", "organization_id"),
            ("ix_sso_configurations_org_active", "sso_configurations", "organization_id, is_active"),
        ]

        for idx_name, table, columns in indexes:
            try:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({columns})"
                ))
                logger.info(f"  Created index {idx_name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(f"  Index {idx_name} already exists")
                else:
                    logger.warning(f"  Could not create index {idx_name}: {e}")

        # =====================================================================
        # 3. Add new columns to existing sso_configs table (if it exists)
        # =====================================================================
        logger.info("Adding new columns to sso_configs (if table exists)...")

        for col_name, col_type, default_value in SSO_CONFIGS_NEW_COLUMNS:
            try:
                default_clause = f" DEFAULT {default_value}" if default_value else ""
                if is_sqlite:
                    conn.execute(text(
                        f"ALTER TABLE sso_configs ADD COLUMN {col_name} {col_type}{default_clause}"
                    ))
                else:
                    conn.execute(text(
                        f"ALTER TABLE sso_configs ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause}"
                    ))
                logger.info(f"  Added {col_name} to sso_configs")
            except Exception as e:
                if "no such table" in str(e).lower():
                    logger.info("  sso_configs table does not exist, skipping")
                    break
                elif "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    logger.info(f"  {col_name} already exists on sso_configs")
                else:
                    logger.warning(f"  Could not add {col_name} to sso_configs: {e}")

        # =====================================================================
        # 4. Add SSO columns to organizations table
        # =====================================================================
        logger.info("Adding SSO columns to organizations table...")

        for col_name, col_type, default_value in ORG_NEW_COLUMNS:
            try:
                default_clause = f" DEFAULT {default_value}" if default_value else ""
                if is_sqlite:
                    conn.execute(text(
                        f"ALTER TABLE organizations ADD COLUMN {col_name} {col_type}{default_clause}"
                    ))
                else:
                    conn.execute(text(
                        f"ALTER TABLE organizations ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause}"
                    ))
                logger.info(f"  Added {col_name} to organizations")
            except Exception as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    logger.info(f"  {col_name} already exists on organizations")
                else:
                    logger.warning(f"  Could not add {col_name} to organizations: {e}")

        # =====================================================================
        # 5. Add SSO columns to users table
        # =====================================================================
        logger.info("Adding SSO columns to users table...")

        for col_name, col_type, default_value in USER_NEW_COLUMNS:
            try:
                default_clause = f" DEFAULT {default_value}" if default_value else ""
                if is_sqlite:
                    conn.execute(text(
                        f"ALTER TABLE users ADD COLUMN {col_name} {col_type}{default_clause}"
                    ))
                else:
                    conn.execute(text(
                        f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause}"
                    ))
                logger.info(f"  Added {col_name} to users")
            except Exception as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    logger.info(f"  {col_name} already exists on users")
                else:
                    logger.warning(f"  Could not add {col_name} to users: {e}")

        conn.commit()

    logger.info(
        f"SSO migration complete: {total_created} tables created, "
        f"{total_skipped} skipped"
    )
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("SSO migration completed successfully")
    else:
        print("SSO migration failed")
        exit(1)
