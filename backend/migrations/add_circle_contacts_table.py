"""
Circle Contacts Table Migration
Creates the circle_contacts table for storing borrower's trusted professionals
"""

from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL")

def run_migration():
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Create circle_contacts table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS circle_contacts (
                id SERIAL PRIMARY KEY,
                lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,

                -- Contact Information
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                phone VARCHAR(50),
                type VARCHAR(100) NOT NULL,
                notes TEXT,

                -- Rating from questionnaire
                rating VARCHAR(20),

                -- Source tracking
                source VARCHAR(50) DEFAULT 'manual',

                -- Metadata
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # Create indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_circle_contacts_lead_id ON circle_contacts(lead_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_circle_contacts_type ON circle_contacts(type)"))

        conn.commit()
        print("Circle contacts table created successfully!")

if __name__ == "__main__":
    run_migration()
