"""
E-Signature System Database Migration

Creates tables for the self-hosted DocuSign-style e-signature system:
- esign_envelopes: Container for signing requests
- esign_signers: Signer assignments with magic link tokens
- esign_fields: Field placements with PDF-point coordinates
- esign_field_values: Submitted values (text, signatures, dates)
- esign_audit_events: Complete audit trail
- esign_completed_documents: Final signed PDFs

Run with: python -m migrations.add_esign_tables
"""

import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text


def get_database_url():
    """Get database URL from environment."""
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def run_migration(db=None):
    """Run the e-sign tables migration."""

    if db is None:
        engine = create_engine(get_database_url())
        connection = engine.connect()
        transaction = connection.begin()
        should_close = True
    else:
        # When called from FastAPI with a Session, get the connection
        connection = db.connection()
        transaction = None  # Let FastAPI manage the transaction
        should_close = False

    try:
        print("[ESIGN] Starting e-signature system migration...")

        # Create enum types
        print("[ESIGN] Creating enum types...")

        connection.execute(text("""
            DO $$ BEGIN
                CREATE TYPE esign_envelope_status AS ENUM (
                    'draft',
                    'sent',
                    'delivered',
                    'completed',
                    'voided',
                    'declined',
                    'expired'
                );
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        """))

        connection.execute(text("""
            DO $$ BEGIN
                CREATE TYPE esign_signer_status AS ENUM (
                    'pending',
                    'sent',
                    'delivered',
                    'viewed',
                    'signed',
                    'declined'
                );
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        """))

        connection.execute(text("""
            DO $$ BEGIN
                CREATE TYPE esign_field_type AS ENUM (
                    'signature',
                    'initial',
                    'date_signed',
                    'text',
                    'checkbox',
                    'dropdown'
                );
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        """))

        connection.execute(text("""
            DO $$ BEGIN
                CREATE TYPE esign_audit_action AS ENUM (
                    'envelope_created',
                    'envelope_sent',
                    'envelope_voided',
                    'signer_viewed',
                    'signature_adopted',
                    'field_completed',
                    'signing_completed',
                    'document_generated',
                    'reminder_sent',
                    'link_accessed',
                    'envelope_declined'
                );
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        """))

        # Create esign_envelopes table
        print("[ESIGN] Creating esign_envelopes table...")
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS esign_envelopes (
                id SERIAL PRIMARY KEY,

                -- Document reference
                document_id INTEGER REFERENCES perennia_documents(id) ON DELETE SET NULL,
                loan_id INTEGER REFERENCES loans(id) ON DELETE SET NULL,
                lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,

                -- Envelope info
                name VARCHAR(500) NOT NULL,
                description TEXT,
                status VARCHAR(20) DEFAULT 'draft',

                -- PDF metadata
                pdf_storage_key VARCHAR(500) NOT NULL,
                pdf_file_name VARCHAR(500) NOT NULL,
                pdf_file_size BIGINT,
                pdf_page_count INTEGER DEFAULT 1,
                pdf_page_dimensions JSONB,  -- [{width_points, height_points}, ...]

                -- Locking
                is_locked BOOLEAN DEFAULT FALSE,
                locked_at TIMESTAMP WITH TIME ZONE,
                locked_by_user_id INTEGER REFERENCES users(id),

                -- Configuration
                expires_at TIMESTAMP WITH TIME ZONE,
                reminder_days INTEGER[] DEFAULT ARRAY[1, 3, 7],
                email_subject VARCHAR(500),
                email_message TEXT,

                -- Completion
                completed_at TIMESTAMP WITH TIME ZONE,
                signed_pdf_storage_key VARCHAR(500),
                audit_pdf_storage_key VARCHAR(500),

                -- Created by
                created_by_user_id INTEGER REFERENCES users(id),

                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """))

        # Create esign_signers table
        print("[ESIGN] Creating esign_signers table...")
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS esign_signers (
                id SERIAL PRIMARY KEY,
                envelope_id INTEGER NOT NULL REFERENCES esign_envelopes(id) ON DELETE CASCADE,

                -- Signer info
                signer_order INTEGER DEFAULT 1,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                role VARCHAR(100),  -- 'borrower', 'co-borrower', 'agent', etc.

                -- Status
                status VARCHAR(20) DEFAULT 'pending',

                -- Magic link token (stored as SHA-256 hash)
                token_hash VARCHAR(64) UNIQUE,
                token_expires_at TIMESTAMP WITH TIME ZONE,

                -- Signature adoption
                has_adopted_signature BOOLEAN DEFAULT FALSE,
                adopted_signature_text VARCHAR(255),
                adopted_signature_font VARCHAR(100),
                adopted_signature_image_key VARCHAR(500),
                adopted_at TIMESTAMP WITH TIME ZONE,

                -- Signing session
                viewed_at TIMESTAMP WITH TIME ZONE,
                signed_at TIMESTAMP WITH TIME ZONE,
                declined_at TIMESTAMP WITH TIME ZONE,
                decline_reason TEXT,

                -- Session tracking
                last_access_at TIMESTAMP WITH TIME ZONE,
                last_access_ip VARCHAR(45),
                last_access_user_agent TEXT,

                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

                CONSTRAINT unique_signer_per_envelope UNIQUE (envelope_id, email)
            );
        """))

        # Create esign_fields table
        print("[ESIGN] Creating esign_fields table...")
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS esign_fields (
                id SERIAL PRIMARY KEY,
                envelope_id INTEGER NOT NULL REFERENCES esign_envelopes(id) ON DELETE CASCADE,
                signer_id INTEGER REFERENCES esign_signers(id) ON DELETE SET NULL,

                -- Field type
                field_type VARCHAR(20) NOT NULL,  -- signature, initial, date_signed, text, checkbox, dropdown

                -- Position (PDF points, origin at bottom-left)
                page_number INTEGER NOT NULL DEFAULT 1,
                x_position_points NUMERIC(10, 2) NOT NULL,
                y_position_points NUMERIC(10, 2) NOT NULL,
                width_points NUMERIC(10, 2) NOT NULL DEFAULT 144.0,
                height_points NUMERIC(10, 2) NOT NULL DEFAULT 36.0,

                -- Field configuration
                is_required BOOLEAN DEFAULT TRUE,
                placeholder_text VARCHAR(255),
                default_value TEXT,
                validation_regex VARCHAR(255),
                max_length INTEGER,

                -- For dropdown fields
                dropdown_options JSONB,  -- ["Option 1", "Option 2"]

                -- Display
                font_name VARCHAR(100) DEFAULT 'Helvetica',
                font_size NUMERIC(5, 2) DEFAULT 12.0,
                font_color VARCHAR(20) DEFAULT '#000000',
                background_color VARCHAR(20),
                border_color VARCHAR(20) DEFAULT '#0066CC',

                -- Ordering
                tab_order INTEGER DEFAULT 0,

                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """))

        # Create esign_field_values table
        print("[ESIGN] Creating esign_field_values table...")
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS esign_field_values (
                id SERIAL PRIMARY KEY,
                field_id INTEGER NOT NULL REFERENCES esign_fields(id) ON DELETE CASCADE,
                signer_id INTEGER NOT NULL REFERENCES esign_signers(id) ON DELETE CASCADE,

                -- Value
                value_type VARCHAR(20) NOT NULL,  -- text, signature, checkbox, date
                text_value TEXT,
                boolean_value BOOLEAN,
                date_value TIMESTAMP WITH TIME ZONE,
                signature_image_key VARCHAR(500),  -- S3 key for drawn signature

                -- Completion metadata
                completed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                completed_ip VARCHAR(45),
                completed_user_agent TEXT,

                -- Server timestamp for date_signed fields
                server_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

                CONSTRAINT unique_field_value UNIQUE (field_id, signer_id)
            );
        """))

        # Create esign_audit_events table
        print("[ESIGN] Creating esign_audit_events table...")
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS esign_audit_events (
                id SERIAL PRIMARY KEY,
                envelope_id INTEGER NOT NULL REFERENCES esign_envelopes(id) ON DELETE CASCADE,
                signer_id INTEGER REFERENCES esign_signers(id) ON DELETE SET NULL,
                field_id INTEGER REFERENCES esign_fields(id) ON DELETE SET NULL,

                -- Event info
                action VARCHAR(50) NOT NULL,
                description TEXT,
                event_data JSONB,

                -- Actor info
                actor_type VARCHAR(20) NOT NULL,  -- 'staff', 'signer', 'system'
                actor_id INTEGER,  -- user_id for staff, signer_id for signers
                actor_email VARCHAR(255),

                -- Request metadata
                ip_address VARCHAR(45),
                user_agent TEXT,

                -- Timestamp (immutable)
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """))

        # Create esign_completed_documents table
        print("[ESIGN] Creating esign_completed_documents table...")
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS esign_completed_documents (
                id SERIAL PRIMARY KEY,
                envelope_id INTEGER NOT NULL REFERENCES esign_envelopes(id) ON DELETE CASCADE,

                -- Document info
                document_type VARCHAR(20) NOT NULL,  -- 'signed_pdf', 'audit_trail', 'combined'
                file_name VARCHAR(500) NOT NULL,
                storage_key VARCHAR(500) NOT NULL,
                file_size BIGINT,

                -- Integrity
                sha256_hash VARCHAR(64),

                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

                CONSTRAINT unique_doc_type_per_envelope UNIQUE (envelope_id, document_type)
            );
        """))

        # Create indexes
        print("[ESIGN] Creating indexes...")

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_esign_envelopes_status ON esign_envelopes(status)",
            "CREATE INDEX IF NOT EXISTS idx_esign_envelopes_loan ON esign_envelopes(loan_id)",
            "CREATE INDEX IF NOT EXISTS idx_esign_envelopes_lead ON esign_envelopes(lead_id)",
            "CREATE INDEX IF NOT EXISTS idx_esign_envelopes_document ON esign_envelopes(document_id)",
            "CREATE INDEX IF NOT EXISTS idx_esign_envelopes_created_by ON esign_envelopes(created_by_user_id)",
            "CREATE INDEX IF NOT EXISTS idx_esign_envelopes_expires ON esign_envelopes(expires_at)",

            "CREATE INDEX IF NOT EXISTS idx_esign_signers_envelope ON esign_signers(envelope_id)",
            "CREATE INDEX IF NOT EXISTS idx_esign_signers_email ON esign_signers(email)",
            "CREATE INDEX IF NOT EXISTS idx_esign_signers_status ON esign_signers(status)",
            "CREATE INDEX IF NOT EXISTS idx_esign_signers_token ON esign_signers(token_hash)",

            "CREATE INDEX IF NOT EXISTS idx_esign_fields_envelope ON esign_fields(envelope_id)",
            "CREATE INDEX IF NOT EXISTS idx_esign_fields_signer ON esign_fields(signer_id)",
            "CREATE INDEX IF NOT EXISTS idx_esign_fields_page ON esign_fields(envelope_id, page_number)",

            "CREATE INDEX IF NOT EXISTS idx_esign_field_values_field ON esign_field_values(field_id)",
            "CREATE INDEX IF NOT EXISTS idx_esign_field_values_signer ON esign_field_values(signer_id)",

            "CREATE INDEX IF NOT EXISTS idx_esign_audit_envelope ON esign_audit_events(envelope_id)",
            "CREATE INDEX IF NOT EXISTS idx_esign_audit_signer ON esign_audit_events(signer_id)",
            "CREATE INDEX IF NOT EXISTS idx_esign_audit_action ON esign_audit_events(action)",
            "CREATE INDEX IF NOT EXISTS idx_esign_audit_created ON esign_audit_events(created_at)",

            "CREATE INDEX IF NOT EXISTS idx_esign_completed_envelope ON esign_completed_documents(envelope_id)",
        ]

        for idx_sql in indexes:
            connection.execute(text(idx_sql))

        # Add requires_esign column to perennia_documents if not exists
        print("[ESIGN] Adding requires_esign column to perennia_documents...")
        connection.execute(text("""
            DO $$ BEGIN
                ALTER TABLE perennia_documents ADD COLUMN IF NOT EXISTS requires_esign BOOLEAN DEFAULT FALSE;
                ALTER TABLE perennia_documents ADD COLUMN IF NOT EXISTS esign_envelope_id INTEGER REFERENCES esign_envelopes(id);
            EXCEPTION
                WHEN undefined_table THEN NULL;
            END $$;
        """))

        # Commit transaction
        if transaction:
            transaction.commit()
        elif db:
            db.commit()

        print("[ESIGN] E-signature system migration completed successfully!")

        return {
            "success": True,
            "message": "E-signature tables created successfully",
            "tables_created": [
                "esign_envelopes",
                "esign_signers",
                "esign_fields",
                "esign_field_values",
                "esign_audit_events",
                "esign_completed_documents"
            ]
        }

    except Exception as e:
        print(f"[ESIGN] Migration error: {e}")
        import traceback
        traceback.print_exc()
        if transaction:
            transaction.rollback()
        elif db:
            db.rollback()
        return {
            "success": False,
            "error": "Internal server error"
        }
    finally:
        if should_close:
            connection.close()


if __name__ == "__main__":
    result = run_migration()
    if result["success"]:
        print("\n✓ Migration completed successfully!")
    else:
        print(f"\n✗ Migration failed: {result.get('error')}")
        sys.exit(1)
