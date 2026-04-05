"""
Migration: Consolidate OAuth token tables into unified oauth_tokens table.

Merges data from:
  - microsoft_tokens → oauth_tokens (provider='microsoft')
  - microsoft_oauth_tokens → oauth_tokens (provider='microsoft')
  - integration_profiles → oauth_tokens (provider='salesforce')

Legacy tables are NOT dropped — they remain for backward compat during
the transition period. New code should use oauth_tokens exclusively.

Run:
    python -c "from migrations.consolidate_oauth_tokens import run_migration; run_migration()"
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    """Create oauth_tokens table and migrate data from legacy tables."""
    if engine is None:
        from database import engine as _engine
        engine = _engine

    with engine.connect() as conn:
        # 1. Create the unified table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL,

                access_token TEXT,
                refresh_token TEXT,
                token_expires_at TIMESTAMP WITH TIME ZONE,
                scopes VARCHAR(1000),

                email_address VARCHAR(255),
                instance_url VARCHAR(500),
                external_org_id VARCHAR(255),

                is_active BOOLEAN DEFAULT TRUE,
                status VARCHAR(50) DEFAULT 'connected',
                last_error TEXT,

                sync_enabled BOOLEAN DEFAULT TRUE,
                sync_folder VARCHAR(255),
                sync_frequency_minutes INTEGER DEFAULT 15,
                last_sync_at TIMESTAMP WITH TIME ZONE,

                provider_config JSONB DEFAULT '{}',

                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Unique constraint
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_oauth_user_org_provider
            ON oauth_tokens(user_id, organization_id, provider)
        """))

        # Performance indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_oauth_user_provider
            ON oauth_tokens(user_id, provider)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_oauth_org_provider
            ON oauth_tokens(organization_id, provider)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_oauth_provider_active
            ON oauth_tokens(provider, is_active)
        """))

        conn.commit()
        logger.info("oauth_tokens table created")

        # 2. Migrate microsoft_oauth_tokens (preferred — has more metadata)
        try:
            migrated = conn.execute(text("""
                INSERT INTO oauth_tokens (
                    user_id, organization_id, provider,
                    access_token, refresh_token, token_expires_at,
                    email_address, sync_enabled, sync_folder,
                    sync_frequency_minutes, last_sync_at,
                    status, is_active,
                    created_at, updated_at
                )
                SELECT
                    mot.user_id,
                    COALESCE(u.organization_id, 1),
                    'microsoft',
                    mot.access_token,
                    mot.refresh_token,
                    mot.token_expires_at,
                    mot.email_address,
                    COALESCE(mot.sync_enabled, true),
                    COALESCE(mot.sync_folder, 'Inbox'),
                    COALESCE(mot.sync_frequency_minutes, 15),
                    mot.last_sync_at,
                    'connected',
                    true,
                    mot.created_at,
                    mot.updated_at
                FROM microsoft_oauth_tokens mot
                JOIN users u ON u.id = mot.user_id
                ON CONFLICT (user_id, organization_id, provider) DO NOTHING
            """))
            conn.commit()
            logger.info(f"Migrated {migrated.rowcount} rows from microsoft_oauth_tokens")
        except Exception as e:
            logger.warning(f"microsoft_oauth_tokens migration skipped: {e}")
            conn.rollback()

        # 3. Migrate microsoft_tokens (only if not already in from microsoft_oauth_tokens)
        try:
            migrated = conn.execute(text("""
                INSERT INTO oauth_tokens (
                    user_id, organization_id, provider,
                    access_token, refresh_token, token_expires_at,
                    scopes, status, is_active,
                    created_at, updated_at
                )
                SELECT
                    mt.user_id,
                    COALESCE(u.organization_id, 1),
                    'microsoft',
                    mt.access_token,
                    mt.refresh_token,
                    mt.expires_at,
                    mt.scope,
                    'connected',
                    true,
                    mt.created_at,
                    mt.updated_at
                FROM microsoft_tokens mt
                JOIN users u ON u.id = mt.user_id
                ON CONFLICT (user_id, organization_id, provider) DO NOTHING
            """))
            conn.commit()
            logger.info(f"Migrated {migrated.rowcount} rows from microsoft_tokens")
        except Exception as e:
            logger.warning(f"microsoft_tokens migration skipped: {e}")
            conn.rollback()

        # 4. Migrate integration_profiles (Salesforce tokens)
        try:
            migrated = conn.execute(text("""
                INSERT INTO oauth_tokens (
                    user_id, organization_id, provider,
                    access_token, refresh_token,
                    instance_url, external_org_id,
                    sync_enabled, status, is_active,
                    last_sync_at,
                    created_at, updated_at
                )
                SELECT
                    ip.user_id,
                    COALESCE(u.organization_id, 1),
                    COALESCE(ip.provider, 'salesforce'),
                    ip.access_token_encrypted,
                    ip.refresh_token_encrypted,
                    ip.instance_url,
                    ip.sf_org_id,
                    COALESCE(ip.sync_enabled, false),
                    COALESCE(ip.status, 'connected'),
                    ip.status != 'disconnected',
                    ip.last_sync_at,
                    ip.created_at,
                    ip.updated_at
                FROM integration_profiles ip
                JOIN users u ON u.id = ip.user_id
                WHERE ip.access_token_encrypted IS NOT NULL
                ON CONFLICT (user_id, organization_id, provider) DO NOTHING
            """))
            conn.commit()
            logger.info(f"Migrated {migrated.rowcount} rows from integration_profiles")
        except Exception as e:
            logger.warning(f"integration_profiles migration skipped: {e}")
            conn.rollback()

        # 5. Migrate user_integrations (plaintext tokens — will be encrypted by EncryptedString on next write)
        try:
            migrated = conn.execute(text("""
                INSERT INTO oauth_tokens (
                    user_id, organization_id, provider,
                    access_token, refresh_token, token_expires_at,
                    scopes, email_address,
                    status, is_active,
                    created_at, updated_at
                )
                SELECT
                    ui.user_id,
                    COALESCE(u.organization_id, 1),
                    ui.provider,
                    ui.access_token,
                    ui.refresh_token,
                    ui.expires_at,
                    ui.scopes,
                    ui.email,
                    'connected',
                    true,
                    ui.created_at,
                    ui.updated_at
                FROM user_integrations ui
                JOIN users u ON u.id = ui.user_id
                WHERE ui.access_token IS NOT NULL
                ON CONFLICT (user_id, organization_id, provider) DO NOTHING
            """))
            conn.commit()
            logger.info(f"Migrated {migrated.rowcount} rows from user_integrations")
        except Exception as e:
            logger.warning(f"user_integrations migration skipped: {e}")
            conn.rollback()

        # 6. Migrate integration_credentials (plaintext tokens for Calendly, Zoom, DocuSign, etc.)
        try:
            migrated = conn.execute(text("""
                INSERT INTO oauth_tokens (
                    user_id, organization_id, provider,
                    access_token, refresh_token, token_expires_at,
                    status, is_active, provider_config,
                    created_at, updated_at
                )
                SELECT
                    ic.user_id,
                    COALESCE(ic.organization_id, u.organization_id, 1),
                    ic.integration_type,
                    ic.access_token,
                    ic.refresh_token,
                    ic.token_expiry,
                    CASE WHEN ic.is_active THEN 'connected' ELSE 'disconnected' END,
                    ic.is_active,
                    COALESCE(ic.integration_metadata, '{}'),
                    ic.created_at,
                    ic.updated_at
                FROM integration_credentials ic
                JOIN users u ON u.id = ic.user_id
                WHERE ic.access_token IS NOT NULL OR ic.refresh_token IS NOT NULL
                ON CONFLICT (user_id, organization_id, provider) DO NOTHING
            """))
            conn.commit()
            logger.info(f"Migrated {migrated.rowcount} rows from integration_credentials")
        except Exception as e:
            logger.warning(f"integration_credentials migration skipped: {e}")
            conn.rollback()

        logger.info("OAuth token consolidation migration complete (5 source tables → 1)")
