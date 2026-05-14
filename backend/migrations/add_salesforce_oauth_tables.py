"""
Salesforce OAuth Integration Tables Migration
Creates the tables needed for per-user Salesforce OAuth integration
"""
import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Create Salesforce OAuth integration tables."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    if is_sqlite:
        migrations = get_sqlite_migrations()
    else:
        migrations = get_postgres_migrations()

    with engine.connect() as conn:
        for name, migration in migrations:
            try:
                conn.execute(text(migration))
                conn.commit()
                logger.info(f"Created/verified: {name}")
            except Exception as e:
                error_msg = str(e).lower()
                if "already exists" in error_msg or "duplicate" in error_msg:
                    logger.info(f"Table/column already exists: {name}")
                    continue
                logger.error(f"Migration failed for {name}: {e}")
                continue

    logger.info("Salesforce OAuth tables migration completed")
    return True


def get_postgres_migrations():
    """PostgreSQL table creation statements."""
    return [
        ("integration_profiles", """
            CREATE TABLE IF NOT EXISTS integration_profiles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                provider VARCHAR(50) NOT NULL DEFAULT 'salesforce',
                status VARCHAR(50) NOT NULL DEFAULT 'disconnected',
                access_token_encrypted TEXT,
                refresh_token_encrypted TEXT,
                instance_url TEXT,
                sf_org_id VARCHAR(100),
                sf_user_id VARCHAR(100),
                sf_username VARCHAR(255),
                connected_at TIMESTAMP,
                last_sync_at TIMESTAMP,
                last_error TEXT,
                field_map_version INTEGER DEFAULT 1,
                sync_enabled BOOLEAN DEFAULT TRUE,
                sync_interval_minutes INTEGER DEFAULT 15,
                sync_direction VARCHAR(20) DEFAULT 'bidirectional',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, provider)
            );
        """),
        ("integration_profiles_index", """
            CREATE INDEX IF NOT EXISTS idx_integration_profiles_user_provider
            ON integration_profiles(user_id, provider);
        """),
        ("integration_profiles_add_cdc_webhook_secret", """
            ALTER TABLE integration_profiles ADD COLUMN IF NOT EXISTS cdc_webhook_secret VARCHAR(255);
        """),
        ("integration_profiles_add_sync_metadata", """
            ALTER TABLE integration_profiles ADD COLUMN IF NOT EXISTS sync_metadata JSONB;
        """),
        ("sf_user_schemas", """
            CREATE TABLE IF NOT EXISTS sf_user_schemas (
                id SERIAL PRIMARY KEY,
                integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                object_name VARCHAR(100) NOT NULL,
                fields JSONB NOT NULL,
                record_types JSONB,
                picklist_values JSONB,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_validated_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(integration_profile_id, object_name)
            );
        """),
        ("field_mappings", """
            CREATE TABLE IF NOT EXISTS field_mappings (
                id SERIAL PRIMARY KEY,
                integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                source_object VARCHAR(100) NOT NULL,
                source_field VARCHAR(255) NOT NULL,
                target_entity VARCHAR(100) NOT NULL,
                target_field VARCHAR(255) NOT NULL,
                transform_type VARCHAR(50),
                transform_config JSONB,
                data_type VARCHAR(50),
                required BOOLEAN DEFAULT FALSE,
                default_value TEXT,
                sync_direction VARCHAR(20) DEFAULT 'bidirectional',
                enabled BOOLEAN DEFAULT TRUE,
                validation_status VARCHAR(50) DEFAULT 'pending',
                validation_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(integration_profile_id, source_object, source_field)
            );
        """),
        ("integration_events", """
            CREATE TABLE IF NOT EXISTS integration_events (
                id SERIAL PRIMARY KEY,
                integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                event_type VARCHAR(100) NOT NULL,
                direction VARCHAR(20),
                source_object VARCHAR(100),
                source_record_id VARCHAR(100),
                target_entity VARCHAR(100),
                target_record_id INTEGER,
                records_processed INTEGER,
                records_succeeded INTEGER,
                records_failed INTEGER,
                status VARCHAR(50) NOT NULL,
                error_message TEXT,
                error_details JSONB,
                duration_ms INTEGER,
                event_data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """),
        ("sync_queue", """
            CREATE TABLE IF NOT EXISTS sync_queue (
                id SERIAL PRIMARY KEY,
                integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                operation VARCHAR(50) NOT NULL,
                direction VARCHAR(20) NOT NULL,
                source_object VARCHAR(100),
                source_record_id VARCHAR(100),
                priority INTEGER DEFAULT 5,
                status VARCHAR(50) DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                scheduled_for TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                result JSONB,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """),
        ("oauth_states", """
            CREATE TABLE IF NOT EXISTS oauth_states (
                id SERIAL PRIMARY KEY,
                state_token VARCHAR(255) UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                provider VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                return_url TEXT,
                state_metadata JSONB
            );
        """),
        ("oauth_states_index", """
            CREATE INDEX IF NOT EXISTS idx_oauth_states_token ON oauth_states(state_token);
        """),
        ("oauth_pkce_store", """
            CREATE TABLE IF NOT EXISTS oauth_pkce_store (
                id SERIAL PRIMARY KEY,
                state VARCHAR(255) UNIQUE NOT NULL,
                code_verifier TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            );
        """),
        ("oauth_pkce_store_index", """
            CREATE INDEX IF NOT EXISTS idx_oauth_pkce_expires ON oauth_pkce_store(expires_at);
        """),
        ("integration_record_tracking", """
            CREATE TABLE IF NOT EXISTS integration_record_tracking (
                id SERIAL PRIMARY KEY,
                integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                source_object VARCHAR(100) NOT NULL,
                source_record_id VARCHAR(100) NOT NULL,
                target_entity VARCHAR(100) NOT NULL,
                target_record_id INTEGER,
                last_synced_at TIMESTAMP NOT NULL,
                sync_hash VARCHAR(64),
                sync_status VARCHAR(50) DEFAULT 'synced',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(integration_profile_id, source_object, source_record_id)
            );
        """),
        ("calendar_sync_settings", """
            CREATE TABLE IF NOT EXISTS calendar_sync_settings (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE,
                sync_enabled BOOLEAN DEFAULT TRUE,
                sync_direction VARCHAR(50) DEFAULT 'bidirectional',
                conflict_policy VARCHAR(50) DEFAULT 'last_write_wins',
                delete_policy VARCHAR(50) DEFAULT 'soft_cancel',
                echo_ignore_window_seconds INTEGER DEFAULT 60,
                polling_enabled BOOLEAN DEFAULT TRUE,
                polling_interval_seconds INTEGER DEFAULT 120,
                batch_size INTEGER DEFAULT 50,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """),
    ]


def get_sqlite_migrations():
    """SQLite table creation statements."""
    return [
        ("integration_profiles", """
            CREATE TABLE IF NOT EXISTS integration_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider VARCHAR(50) NOT NULL DEFAULT 'salesforce',
                status VARCHAR(50) NOT NULL DEFAULT 'disconnected',
                access_token_encrypted TEXT,
                refresh_token_encrypted TEXT,
                instance_url TEXT,
                sf_org_id VARCHAR(100),
                sf_user_id VARCHAR(100),
                sf_username VARCHAR(255),
                connected_at TIMESTAMP,
                last_sync_at TIMESTAMP,
                last_error TEXT,
                field_map_version INTEGER DEFAULT 1,
                sync_enabled BOOLEAN DEFAULT 1,
                sync_interval_minutes INTEGER DEFAULT 15,
                sync_direction VARCHAR(20) DEFAULT 'bidirectional',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, provider)
            );
        """),
        ("sf_user_schemas", """
            CREATE TABLE IF NOT EXISTS sf_user_schemas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                object_name VARCHAR(100) NOT NULL,
                fields TEXT NOT NULL,
                record_types TEXT,
                picklist_values TEXT,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_validated_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(integration_profile_id, object_name)
            );
        """),
        ("field_mappings", """
            CREATE TABLE IF NOT EXISTS field_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                source_object VARCHAR(100) NOT NULL,
                source_field VARCHAR(255) NOT NULL,
                target_entity VARCHAR(100) NOT NULL,
                target_field VARCHAR(255) NOT NULL,
                transform_type VARCHAR(50),
                transform_config TEXT,
                data_type VARCHAR(50),
                required BOOLEAN DEFAULT 0,
                default_value TEXT,
                sync_direction VARCHAR(20) DEFAULT 'bidirectional',
                enabled BOOLEAN DEFAULT 1,
                validation_status VARCHAR(50) DEFAULT 'pending',
                validation_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(integration_profile_id, source_object, source_field)
            );
        """),
        ("integration_events", """
            CREATE TABLE IF NOT EXISTS integration_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                event_type VARCHAR(100) NOT NULL,
                direction VARCHAR(20),
                source_object VARCHAR(100),
                source_record_id VARCHAR(100),
                target_entity VARCHAR(100),
                target_record_id INTEGER,
                records_processed INTEGER,
                records_succeeded INTEGER,
                records_failed INTEGER,
                status VARCHAR(50) NOT NULL,
                error_message TEXT,
                error_details TEXT,
                duration_ms INTEGER,
                event_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """),
        ("sync_queue", """
            CREATE TABLE IF NOT EXISTS sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                operation VARCHAR(50) NOT NULL,
                direction VARCHAR(20) NOT NULL,
                source_object VARCHAR(100),
                source_record_id VARCHAR(100),
                priority INTEGER DEFAULT 5,
                status VARCHAR(50) DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                scheduled_for TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                result TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """),
        ("oauth_states", """
            CREATE TABLE IF NOT EXISTS oauth_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state_token VARCHAR(255) UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                provider VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT 0,
                return_url TEXT,
                state_metadata TEXT
            );
        """),
        ("oauth_pkce_store", """
            CREATE TABLE IF NOT EXISTS oauth_pkce_store (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state VARCHAR(255) UNIQUE NOT NULL,
                code_verifier TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            );
        """),
        ("integration_record_tracking", """
            CREATE TABLE IF NOT EXISTS integration_record_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                source_object VARCHAR(100) NOT NULL,
                source_record_id VARCHAR(100) NOT NULL,
                target_entity VARCHAR(100) NOT NULL,
                target_record_id INTEGER,
                last_synced_at TIMESTAMP NOT NULL,
                sync_hash VARCHAR(64),
                sync_status VARCHAR(50) DEFAULT 'synced',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(integration_profile_id, source_object, source_record_id)
            );
        """),
        ("calendar_sync_settings", """
            CREATE TABLE IF NOT EXISTS calendar_sync_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                sync_enabled BOOLEAN DEFAULT 1,
                sync_direction VARCHAR(50) DEFAULT 'bidirectional',
                conflict_policy VARCHAR(50) DEFAULT 'last_write_wins',
                delete_policy VARCHAR(50) DEFAULT 'soft_cancel',
                echo_ignore_window_seconds INTEGER DEFAULT 60,
                polling_enabled BOOLEAN DEFAULT 1,
                polling_interval_seconds INTEGER DEFAULT 120,
                batch_size INTEGER DEFAULT 50,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """),
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
