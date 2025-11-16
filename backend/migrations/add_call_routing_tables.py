"""
Migration: Add Call Routing and Transfer Tables
Creates tables for intelligent call routing, transfer logging, and staff availability
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
    """Create call routing tables"""

    sql_commands = [
        # 1. Call Routing Log Table
        """
        CREATE TABLE IF NOT EXISTS call_routing_log (
            id SERIAL PRIMARY KEY,
            call_id INTEGER REFERENCES vapi_calls(id) ON DELETE CASCADE,
            vapi_call_id VARCHAR(255),

            -- Routing Decision
            routing_decision VARCHAR(100),
            caller_type VARCHAR(50),

            -- Transfer Details
            routed_to_user_id INTEGER REFERENCES users(id),
            routed_to_role VARCHAR(50),
            routed_to_phone VARCHAR(20),

            -- Whisper Message
            whisper_message TEXT,

            -- Transfer Status
            transfer_successful BOOLEAN,
            transfer_error TEXT,

            -- Context
            caller_phone VARCHAR(20),
            caller_name VARCHAR(255),
            call_reason TEXT,
            urgency_level VARCHAR(20),

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 2. Staff Availability Table (for routing logic)
        """
        CREATE TABLE IF NOT EXISTS staff_availability (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,

            -- Availability Status
            status VARCHAR(50) DEFAULT 'available',
            available_for_calls BOOLEAN DEFAULT TRUE,

            -- Phone Numbers
            primary_phone VARCHAR(20),
            backup_phone VARCHAR(20),

            -- Role Information
            role VARCHAR(50),
            department VARCHAR(100),

            -- Working Hours (JSON: {monday: {start: '09:00', end: '17:00'}, ...})
            working_hours JSON,

            -- Current Status
            current_call_count INTEGER DEFAULT 0,
            max_concurrent_calls INTEGER DEFAULT 3,

            -- Metadata
            out_of_office BOOLEAN DEFAULT FALSE,
            out_of_office_message TEXT,
            auto_response_enabled BOOLEAN DEFAULT FALSE,

            -- Timestamps
            last_call_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 3. Call Transfer Configuration Table
        """
        CREATE TABLE IF NOT EXISTS call_transfer_config (
            id SERIAL PRIMARY KEY,

            -- Transfer Rules
            caller_type VARCHAR(50),
            default_route_to_role VARCHAR(50),

            -- Conditions (JSON)
            routing_conditions JSON,

            -- Priority
            priority_order INTEGER DEFAULT 0,

            -- Active Status
            is_active BOOLEAN DEFAULT TRUE,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # Indices for performance
        "CREATE INDEX IF NOT EXISTS idx_routing_log_call_id ON call_routing_log(call_id);",
        "CREATE INDEX IF NOT EXISTS idx_routing_log_vapi_call ON call_routing_log(vapi_call_id);",
        "CREATE INDEX IF NOT EXISTS idx_routing_log_user ON call_routing_log(routed_to_user_id);",
        "CREATE INDEX IF NOT EXISTS idx_routing_log_role ON call_routing_log(routed_to_role);",
        "CREATE INDEX IF NOT EXISTS idx_routing_log_created ON call_routing_log(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_staff_availability_user ON staff_availability(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_staff_availability_status ON staff_availability(status);",
        "CREATE INDEX IF NOT EXISTS idx_staff_availability_role ON staff_availability(role);",
        "CREATE INDEX IF NOT EXISTS idx_transfer_config_caller_type ON call_transfer_config(caller_type);",
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

        logger.info("✅ Call routing tables migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("Starting call routing tables migration...")
    success = run_migration()
    if success:
        logger.info("✅ Migration completed!")
    else:
        logger.error("❌ Migration failed!")
        sys.exit(1)
