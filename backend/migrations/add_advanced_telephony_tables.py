"""
Advanced Telephony Tables Migration
Creates tables for: IVR, Call Queues, Conference Rooms, Transfers, Hold Music
"""
import os
import sys
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def get_db_type():
    """Determine if using SQLite or PostgreSQL"""
    return "postgresql" if "postgresql" in DATABASE_URL else "sqlite"


def run_migration():
    """Run the advanced telephony migration"""
    print("=" * 60)
    print("Advanced Telephony Tables Migration")
    print("=" * 60)

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    db_type = get_db_type()
    is_postgres = db_type == "postgresql"

    # Type mappings for SQLite vs PostgreSQL
    serial = "SERIAL" if is_postgres else "INTEGER"
    timestamp_tz = "TIMESTAMP WITH TIME ZONE" if is_postgres else "TIMESTAMP"
    jsonb = "JSONB" if is_postgres else "TEXT"
    auto_increment = "" if is_postgres else "PRIMARY KEY AUTOINCREMENT"
    pk = "PRIMARY KEY" if is_postgres else ""

    try:
        # ============================================================
        # 1. HOLD MUSIC TABLE
        # ============================================================
        print("\n[1/9] Creating hold_music table...")
        session.execute(text(f"""
            CREATE TABLE IF NOT EXISTS hold_music (
                id {serial} {pk} {auto_increment},
                name VARCHAR(100) NOT NULL,
                description TEXT,
                source_type VARCHAR(50) NOT NULL DEFAULT 'url',
                audio_url VARCHAR(512),
                twilio_music_name VARCHAR(100),
                duration_seconds INTEGER,
                is_default BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                comfort_messages {jsonb},
                comfort_message_interval INTEGER DEFAULT 30,
                created_by INTEGER,
                created_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                updated_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("  hold_music table created")

        # ============================================================
        # 2. IVR MENUS TABLE
        # ============================================================
        print("\n[2/9] Creating ivr_menus table...")
        session.execute(text(f"""
            CREATE TABLE IF NOT EXISTS ivr_menus (
                id {serial} {pk} {auto_increment},
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                is_default BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                greeting_text TEXT,
                greeting_audio_url VARCHAR(512),
                timeout_seconds INTEGER DEFAULT 10,
                max_attempts INTEGER DEFAULT 3,
                timeout_action VARCHAR(50) DEFAULT 'transfer_receptionist',
                created_by INTEGER,
                created_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                updated_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("  ivr_menus table created")

        # ============================================================
        # 3. IVR MENU OPTIONS TABLE
        # ============================================================
        print("\n[3/9] Creating ivr_menu_options table...")
        session.execute(text(f"""
            CREATE TABLE IF NOT EXISTS ivr_menu_options (
                id {serial} {pk} {auto_increment},
                menu_id INTEGER NOT NULL,
                dtmf_digit CHAR(1) NOT NULL,
                label VARCHAR(100) NOT NULL,
                action_type VARCHAR(50) NOT NULL,
                action_target VARCHAR(255),
                announcement_text TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                display_order INTEGER DEFAULT 0,
                created_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (menu_id) REFERENCES ivr_menus(id) ON DELETE CASCADE,
                UNIQUE(menu_id, dtmf_digit)
            )
        """))
        print("  ivr_menu_options table created")

        # ============================================================
        # 4. CALL QUEUES TABLE
        # ============================================================
        print("\n[4/9] Creating call_queues table...")
        session.execute(text(f"""
            CREATE TABLE IF NOT EXISTS call_queues (
                id {serial} {pk} {auto_increment},
                name VARCHAR(100) NOT NULL UNIQUE,
                friendly_name VARCHAR(255),
                description TEXT,
                max_wait_time_seconds INTEGER DEFAULT 600,
                max_queue_size INTEGER DEFAULT 20,
                announce_position BOOLEAN DEFAULT TRUE,
                announce_wait_time BOOLEAN DEFAULT TRUE,
                position_announcement_interval INTEGER DEFAULT 60,
                hold_music_id INTEGER,
                hold_music_url VARCHAR(512),
                comfort_message TEXT,
                comfort_message_interval INTEGER DEFAULT 30,
                overflow_action VARCHAR(50) DEFAULT 'voicemail',
                overflow_target VARCHAR(255),
                twilio_queue_sid VARCHAR(50),
                is_active BOOLEAN DEFAULT TRUE,
                created_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                updated_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (hold_music_id) REFERENCES hold_music(id)
            )
        """))
        print("  call_queues table created")

        # ============================================================
        # 5. QUEUE MEMBERS TABLE
        # ============================================================
        print("\n[5/9] Creating queue_members table...")
        session.execute(text(f"""
            CREATE TABLE IF NOT EXISTS queue_members (
                id {serial} {pk} {auto_increment},
                queue_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                priority INTEGER DEFAULT 0,
                wrap_up_time INTEGER DEFAULT 30,
                is_active BOOLEAN DEFAULT TRUE,
                joined_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (queue_id) REFERENCES call_queues(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(queue_id, user_id)
            )
        """))
        print("  queue_members table created")

        # ============================================================
        # 6. QUEUE ENTRIES TABLE
        # ============================================================
        print("\n[6/9] Creating queue_entries table...")
        session.execute(text(f"""
            CREATE TABLE IF NOT EXISTS queue_entries (
                id {serial} {pk} {auto_increment},
                queue_id INTEGER NOT NULL,
                call_sid VARCHAR(100) NOT NULL UNIQUE,
                caller_phone VARCHAR(20),
                caller_name VARCHAR(255),
                position INTEGER NOT NULL,
                entered_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                estimated_wait_seconds INTEGER,
                actual_wait_seconds INTEGER,
                status VARCHAR(50) DEFAULT 'waiting',
                connected_to_user_id INTEGER,
                connected_at {timestamp_tz},
                ivr_path TEXT,
                priority INTEGER DEFAULT 0,
                extra_data {jsonb},
                created_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                updated_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (queue_id) REFERENCES call_queues(id) ON DELETE CASCADE,
                FOREIGN KEY (connected_to_user_id) REFERENCES users(id)
            )
        """))
        print("  queue_entries table created")

        # ============================================================
        # 7. CONFERENCE ROOMS TABLE
        # ============================================================
        print("\n[7/9] Creating conference_rooms table...")
        session.execute(text(f"""
            CREATE TABLE IF NOT EXISTS conference_rooms (
                id {serial} {pk} {auto_increment},
                room_name VARCHAR(100) NOT NULL UNIQUE,
                friendly_name VARCHAR(255),
                max_participants INTEGER DEFAULT 50,
                start_on_enter BOOLEAN DEFAULT TRUE,
                end_on_exit BOOLEAN DEFAULT FALSE,
                mute_on_entry BOOLEAN DEFAULT FALSE,
                record_conference BOOLEAN DEFAULT FALSE,
                pin_required BOOLEAN DEFAULT FALSE,
                host_pin VARCHAR(10),
                participant_pin VARCHAR(10),
                current_conference_sid VARCHAR(50),
                status VARCHAR(50) DEFAULT 'available',
                started_at {timestamp_tz},
                ended_at {timestamp_tz},
                created_by INTEGER,
                is_active BOOLEAN DEFAULT TRUE,
                created_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                updated_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """))
        print("  conference_rooms table created")

        # ============================================================
        # 8. CONFERENCE PARTICIPANTS TABLE
        # ============================================================
        print("\n[8/9] Creating conference_participants table...")
        session.execute(text(f"""
            CREATE TABLE IF NOT EXISTS conference_participants (
                id {serial} {pk} {auto_increment},
                conference_id INTEGER NOT NULL,
                call_sid VARCHAR(100) NOT NULL,
                user_id INTEGER,
                phone_number VARCHAR(20),
                name VARCHAR(255),
                role VARCHAR(50) DEFAULT 'participant',
                status VARCHAR(50) DEFAULT 'ringing',
                is_muted BOOLEAN DEFAULT FALSE,
                is_on_hold BOOLEAN DEFAULT FALSE,
                joined_at {timestamp_tz},
                left_at {timestamp_tz},
                duration_seconds INTEGER,
                created_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                updated_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conference_id) REFERENCES conference_rooms(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """))
        print("  conference_participants table created")

        # ============================================================
        # 9. CALL TRANSFERS TABLE
        # ============================================================
        print("\n[9/9] Creating call_transfers table...")
        session.execute(text(f"""
            CREATE TABLE IF NOT EXISTS call_transfers (
                id {serial} {pk} {auto_increment},
                original_call_sid VARCHAR(100) NOT NULL,
                transfer_call_sid VARCHAR(100),
                transfer_type VARCHAR(50) NOT NULL,
                initiator_user_id INTEGER,
                from_user_id INTEGER,
                to_user_id INTEGER,
                to_phone VARCHAR(20),
                announce_to_recipient BOOLEAN DEFAULT TRUE,
                whisper_message TEXT,
                consultation_call_sid VARCHAR(100),
                consultation_started_at {timestamp_tz},
                consultation_ended_at {timestamp_tz},
                status VARCHAR(50) DEFAULT 'initiated',
                failure_reason TEXT,
                initiated_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                completed_at {timestamp_tz},
                caller_phone VARCHAR(20),
                caller_name VARCHAR(255),
                transfer_reason TEXT,
                extra_data {jsonb},
                created_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                updated_at {timestamp_tz} DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (initiator_user_id) REFERENCES users(id),
                FOREIGN KEY (from_user_id) REFERENCES users(id),
                FOREIGN KEY (to_user_id) REFERENCES users(id)
            )
        """))
        print("  call_transfers table created")

        # ============================================================
        # CREATE INDEXES
        # ============================================================
        print("\n[Indexes] Creating indexes...")

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_ivr_menu_options_menu ON ivr_menu_options(menu_id)",
            "CREATE INDEX IF NOT EXISTS idx_queue_entries_queue_status ON queue_entries(queue_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_queue_entries_call_sid ON queue_entries(call_sid)",
            "CREATE INDEX IF NOT EXISTS idx_conference_participants_conf ON conference_participants(conference_id)",
            "CREATE INDEX IF NOT EXISTS idx_conference_participants_call ON conference_participants(call_sid)",
            "CREATE INDEX IF NOT EXISTS idx_call_transfers_original ON call_transfers(original_call_sid)",
            "CREATE INDEX IF NOT EXISTS idx_call_transfers_status ON call_transfers(status)",
        ]

        for idx_sql in indexes:
            try:
                session.execute(text(idx_sql))
            except Exception as e:
                print(f"  Index may already exist: {e}")

        print("  Indexes created")

        # ============================================================
        # INSERT DEFAULT DATA
        # ============================================================
        print("\n[Defaults] Inserting default data...")

        # Default hold music
        session.execute(text("""
            INSERT INTO hold_music (name, description, source_type, audio_url, is_default, is_active)
            SELECT 'Classical Hold Music', 'Default Twilio classical music', 'url',
                   'http://com.twilio.music.classical.s3.amazonaws.com/BussyStrings.mp3',
                   TRUE, TRUE
            WHERE NOT EXISTS (SELECT 1 FROM hold_music WHERE is_default = TRUE)
        """))

        # Default sales queue
        session.execute(text("""
            INSERT INTO call_queues (name, friendly_name, description, is_active)
            SELECT 'sales', 'Sales Queue', 'Queue for new loan inquiries', TRUE
            WHERE NOT EXISTS (SELECT 1 FROM call_queues WHERE name = 'sales')
        """))

        # Default support queue
        session.execute(text("""
            INSERT INTO call_queues (name, friendly_name, description, is_active)
            SELECT 'support', 'Support Queue', 'Queue for existing loan support', TRUE
            WHERE NOT EXISTS (SELECT 1 FROM call_queues WHERE name = 'support')
        """))

        print("  Default data inserted")

        session.commit()

        print("\n" + "=" * 60)
        print("Migration completed successfully!")
        print("=" * 60)
        print("\nTables created:")
        print("  - hold_music")
        print("  - ivr_menus")
        print("  - ivr_menu_options")
        print("  - call_queues")
        print("  - queue_members")
        print("  - queue_entries")
        print("  - conference_rooms")
        print("  - conference_participants")
        print("  - call_transfers")

    except Exception as e:
        session.rollback()
        print(f"\nError during migration: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run_migration()
