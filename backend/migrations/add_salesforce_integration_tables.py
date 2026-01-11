"""
Migration: Add Salesforce Integration Tables
Creates tables for per-user Salesforce integration with OAuth, schema discovery,
field mappings, sync tracking, and audit trail.
"""
import sys
sys.path.append('..')

from sqlalchemy import create_engine, text
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def run_migration():
    """Create Salesforce integration tables"""

    sql_commands = [
        # 1. Integration Profiles - Per-user Salesforce connections
        """
        CREATE TABLE IF NOT EXISTS integration_profiles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL DEFAULT 'salesforce',
            status VARCHAR(50) NOT NULL DEFAULT 'disconnected',

            -- OAuth Credentials (encrypted)
            access_token_encrypted TEXT,
            refresh_token_encrypted TEXT,
            instance_url TEXT,

            -- Salesforce Specifics
            sf_org_id VARCHAR(100),
            sf_user_id VARCHAR(100),
            sf_username VARCHAR(255),

            -- Metadata
            connected_at TIMESTAMP WITH TIME ZONE,
            last_sync_at TIMESTAMP WITH TIME ZONE,
            last_error TEXT,
            field_map_version INTEGER DEFAULT 1,

            -- Settings
            sync_enabled BOOLEAN DEFAULT TRUE,
            sync_interval_minutes INTEGER DEFAULT 15,
            sync_direction VARCHAR(20) DEFAULT 'bidirectional',

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(user_id, provider)
        );
        """,

        # 2. Salesforce User Schemas - Discovered schema per user's org
        """
        CREATE TABLE IF NOT EXISTS sf_user_schemas (
            id SERIAL PRIMARY KEY,
            integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
            object_name VARCHAR(100) NOT NULL,

            -- Raw schema from Salesforce
            fields JSON NOT NULL,
            record_types JSON,
            picklist_values JSON,

            -- Metadata
            discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            last_validated_at TIMESTAMP WITH TIME ZONE,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(integration_profile_id, object_name)
        );
        """,

        # 3. Field Mappings - User's field transformation rules
        """
        CREATE TABLE IF NOT EXISTS field_mappings (
            id SERIAL PRIMARY KEY,
            integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,

            -- Source (Salesforce side)
            source_object VARCHAR(100) NOT NULL,
            source_field VARCHAR(255) NOT NULL,

            -- Target (CRM side)
            target_entity VARCHAR(100) NOT NULL,
            target_field VARCHAR(255) NOT NULL,

            -- Transformation Rules
            transform_type VARCHAR(50),
            transform_config JSON,

            -- Validation
            data_type VARCHAR(50),
            required BOOLEAN DEFAULT FALSE,
            default_value TEXT,

            -- Sync Direction
            sync_direction VARCHAR(20) DEFAULT 'bidirectional',

            -- Status
            enabled BOOLEAN DEFAULT TRUE,
            validation_status VARCHAR(50) DEFAULT 'pending',
            validation_message TEXT,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(integration_profile_id, source_object, source_field)
        );
        """,

        # 4. Integration Events - Audit trail
        """
        CREATE TABLE IF NOT EXISTS integration_events (
            id SERIAL PRIMARY KEY,
            integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,

            event_type VARCHAR(100) NOT NULL,
            direction VARCHAR(20),

            -- Context
            source_object VARCHAR(100),
            source_record_id VARCHAR(100),
            target_entity VARCHAR(100),
            target_record_id INTEGER,

            -- Details
            records_processed INTEGER,
            records_succeeded INTEGER,
            records_failed INTEGER,

            -- Error Tracking
            status VARCHAR(50) NOT NULL,
            error_message TEXT,
            error_details JSON,

            -- Performance
            duration_ms INTEGER,

            -- Full Event Data
            event_data JSON,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 5. Sync Queue - Async job queue
        """
        CREATE TABLE IF NOT EXISTS sync_queue (
            id SERIAL PRIMARY KEY,
            integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,

            operation VARCHAR(50) NOT NULL,
            direction VARCHAR(20) NOT NULL,

            -- Payload
            source_object VARCHAR(100),
            source_record_id VARCHAR(100),
            priority INTEGER DEFAULT 5,

            -- Status
            status VARCHAR(50) DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,

            -- Timing
            scheduled_for TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,

            -- Results
            result JSON,
            error_message TEXT,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 6. OAuth States - CSRF protection
        """
        CREATE TABLE IF NOT EXISTS oauth_states (
            id SERIAL PRIMARY KEY,
            state_token VARCHAR(255) UNIQUE NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL,

            -- Security
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            used BOOLEAN DEFAULT FALSE,

            -- Context
            return_url TEXT,
            state_metadata JSON
        );
        """,

        # 7. Integration Record Tracking - Change detection
        """
        CREATE TABLE IF NOT EXISTS integration_record_tracking (
            id SERIAL PRIMARY KEY,
            integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,

            -- Source (Salesforce)
            source_object VARCHAR(100) NOT NULL,
            source_record_id VARCHAR(100) NOT NULL,

            -- Target (CRM)
            target_entity VARCHAR(100) NOT NULL,
            target_record_id INTEGER,

            -- Sync Metadata
            last_synced_at TIMESTAMP WITH TIME ZONE NOT NULL,
            sync_hash VARCHAR(64),
            sync_status VARCHAR(50) DEFAULT 'synced',

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(integration_profile_id, source_object, source_record_id)
        );
        """,

        # Indices for performance
        "CREATE INDEX IF NOT EXISTS idx_integration_profiles_user ON integration_profiles(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_integration_profiles_status ON integration_profiles(status);",
        "CREATE INDEX IF NOT EXISTS idx_integration_profiles_sync ON integration_profiles(sync_enabled, last_sync_at) WHERE status = 'active';",

        "CREATE INDEX IF NOT EXISTS idx_sf_user_schemas_profile ON sf_user_schemas(integration_profile_id);",

        "CREATE INDEX IF NOT EXISTS idx_field_mappings_profile ON field_mappings(integration_profile_id);",
        "CREATE INDEX IF NOT EXISTS idx_field_mappings_entity ON field_mappings(target_entity, target_field);",
        "CREATE INDEX IF NOT EXISTS idx_field_mappings_enabled ON field_mappings(enabled) WHERE enabled = TRUE;",

        "CREATE INDEX IF NOT EXISTS idx_integration_events_profile ON integration_events(integration_profile_id);",
        "CREATE INDEX IF NOT EXISTS idx_integration_events_created ON integration_events(created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_integration_events_type ON integration_events(event_type);",
        "CREATE INDEX IF NOT EXISTS idx_integration_events_status ON integration_events(status) WHERE status = 'error';",

        "CREATE INDEX IF NOT EXISTS idx_sync_queue_pending ON sync_queue(scheduled_for, priority DESC) WHERE status = 'pending';",
        "CREATE INDEX IF NOT EXISTS idx_sync_queue_profile ON sync_queue(integration_profile_id);",

        "CREATE INDEX IF NOT EXISTS idx_oauth_states_expiry ON oauth_states(expires_at) WHERE NOT used;",

        "CREATE INDEX IF NOT EXISTS idx_integration_record_tracking_profile ON integration_record_tracking(integration_profile_id);",
        "CREATE INDEX IF NOT EXISTS idx_integration_record_tracking_target ON integration_record_tracking(target_entity, target_record_id);",
    ]

    try:
        with engine.connect() as conn:
            for idx, sql in enumerate(sql_commands, 1):
                try:
                    logger.info(f"Executing command {idx}/{len(sql_commands)}...")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"✅ Command {idx} executed successfully")
                except Exception as e:
                    logger.error(f"❌ Error executing command {idx}: {e}")
                    # Continue with other commands
                    continue

        logger.info("✅ Salesforce integration tables migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("Starting Salesforce integration tables migration...")
    success = run_migration()
    if success:
        logger.info("✅ Migration completed!")
    else:
        logger.error("❌ Migration failed!")
        sys.exit(1)
