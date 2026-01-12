"""
Migration: Add Subscriber Invitations Table
Creates a dedicated table for storing subscription invitation tokens.
This provides proper storage and validation for the admin onboarding flow.
"""

from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Run the subscriber invitations table migration."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'subscriber_invitations'
        """))

        if result.fetchone():
            print("subscriber_invitations table already exists. Skipping migration.")
            return

        print("Creating subscriber_invitations table...")

        # Create subscriber invitations table
        conn.execute(text("""
            CREATE TABLE subscriber_invitations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                token VARCHAR(255) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL,
                company_name VARCHAR(255) NOT NULL,
                contact_name VARCHAR(255),
                plan VARCHAR(100) NOT NULL DEFAULT 'professional',
                seats INTEGER NOT NULL DEFAULT 5,
                promo_code VARCHAR(50),
                personal_message TEXT,
                status VARCHAR(30) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'accepted', 'expired', 'revoked')),
                invited_by INTEGER REFERENCES users(id),
                invited_by_name VARCHAR(255),
                expires_at TIMESTAMP NOT NULL,
                accepted_at TIMESTAMP,
                accepted_by_user_id INTEGER REFERENCES users(id),
                revoked_at TIMESTAMP,
                revoked_by INTEGER REFERENCES users(id),
                ip_address VARCHAR(45),
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_sub_invites_token ON subscriber_invitations(token);
            CREATE INDEX idx_sub_invites_email ON subscriber_invitations(email);
            CREATE INDEX idx_sub_invites_status ON subscriber_invitations(status);
            CREATE INDEX idx_sub_invites_expires ON subscriber_invitations(expires_at);
            CREATE INDEX idx_sub_invites_created ON subscriber_invitations(created_at);
        """))

        conn.commit()
        print("subscriber_invitations table created successfully!")


if __name__ == "__main__":
    run_migration()
