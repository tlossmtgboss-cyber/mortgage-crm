"""
Database migration for Deal Alerts system.
Creates tables for storing proactive deal alerts.
"""

import logging
from datetime import datetime
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Run the deal alerts migration."""

    # Detect database type
    db_url = str(engine.url)
    is_sqlite = 'sqlite' in db_url
    is_postgres = 'postgresql' in db_url

    logger.info(f"Running deal alerts migration (SQLite: {is_sqlite}, PostgreSQL: {is_postgres})")

    with engine.connect() as conn:
        # Create deal_alerts table
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS deal_alerts (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'medium',
                    status TEXT NOT NULL DEFAULT 'active',
                    loan_id INTEGER REFERENCES loans(id),
                    loan_number TEXT,
                    borrower_name TEXT,
                    title TEXT NOT NULL,
                    message TEXT,
                    details TEXT,
                    recommended_action TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    acknowledged_at TIMESTAMP,
                    acknowledged_by INTEGER REFERENCES users(id),
                    resolved_at TIMESTAMP,
                    resolved_by INTEGER REFERENCES users(id),
                    resolution_note TEXT,
                    snoozed_until TIMESTAMP,
                    due_date TIMESTAMP,
                    organization_id INTEGER,
                    user_id INTEGER REFERENCES users(id)
                )
            """))

            # Create indexes
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_status ON deal_alerts(status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_priority ON deal_alerts(priority)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_loan_id ON deal_alerts(loan_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_type ON deal_alerts(type)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_org ON deal_alerts(organization_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_user ON deal_alerts(user_id)"))

        else:
            # PostgreSQL
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS deal_alerts (
                    id VARCHAR(50) PRIMARY KEY,
                    type VARCHAR(50) NOT NULL,
                    priority VARCHAR(20) NOT NULL DEFAULT 'medium',
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    loan_id INTEGER REFERENCES loans(id),
                    loan_number VARCHAR(50),
                    borrower_name VARCHAR(255),
                    title VARCHAR(500) NOT NULL,
                    message TEXT,
                    details JSONB DEFAULT '{}',
                    recommended_action TEXT,
                    tags JSONB DEFAULT '[]',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    acknowledged_at TIMESTAMP WITH TIME ZONE,
                    acknowledged_by INTEGER REFERENCES users(id),
                    resolved_at TIMESTAMP WITH TIME ZONE,
                    resolved_by INTEGER REFERENCES users(id),
                    resolution_note TEXT,
                    snoozed_until TIMESTAMP WITH TIME ZONE,
                    due_date TIMESTAMP WITH TIME ZONE,
                    organization_id INTEGER,
                    user_id INTEGER REFERENCES users(id)
                )
            """))

            # Create indexes
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_status ON deal_alerts(status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_priority ON deal_alerts(priority)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_loan_id ON deal_alerts(loan_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_type ON deal_alerts(type)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_org ON deal_alerts(organization_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_user ON deal_alerts(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_created ON deal_alerts(created_at DESC)"))

            # Create updated_at trigger function if not exists
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION update_deal_alerts_updated_at()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """))

            # Drop trigger if exists and recreate
            conn.execute(text("DROP TRIGGER IF EXISTS trigger_deal_alerts_updated_at ON deal_alerts"))
            conn.execute(text("""
                CREATE TRIGGER trigger_deal_alerts_updated_at
                BEFORE UPDATE ON deal_alerts
                FOR EACH ROW
                EXECUTE FUNCTION update_deal_alerts_updated_at()
            """))

        # Create whisper_sessions table for Live Call Whisper
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS whisper_sessions (
                    id TEXT PRIMARY KEY,
                    call_id TEXT,
                    user_id INTEGER REFERENCES users(id),
                    contact_id INTEGER,
                    contact_name TEXT,
                    contact_type TEXT,
                    status TEXT DEFAULT 'active',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP,
                    duration_seconds INTEGER,
                    whisper_count INTEGER DEFAULT 0,
                    ai_suggestions_count INTEGER DEFAULT 0,
                    organization_id INTEGER
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS whisper_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT REFERENCES whisper_sessions(id),
                    message_type TEXT NOT NULL,
                    priority TEXT DEFAULT 'medium',
                    content TEXT NOT NULL,
                    context TEXT,
                    source TEXT DEFAULT 'ai',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    acknowledged_at TIMESTAMP
                )
            """))

        else:
            # PostgreSQL
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS whisper_sessions (
                    id VARCHAR(50) PRIMARY KEY,
                    call_id VARCHAR(100),
                    user_id INTEGER REFERENCES users(id),
                    contact_id INTEGER,
                    contact_name VARCHAR(255),
                    contact_type VARCHAR(50),
                    status VARCHAR(20) DEFAULT 'active',
                    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ended_at TIMESTAMP WITH TIME ZONE,
                    duration_seconds INTEGER,
                    whisper_count INTEGER DEFAULT 0,
                    ai_suggestions_count INTEGER DEFAULT 0,
                    organization_id INTEGER
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS whisper_messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(50) REFERENCES whisper_sessions(id),
                    message_type VARCHAR(50) NOT NULL,
                    priority VARCHAR(20) DEFAULT 'medium',
                    content TEXT NOT NULL,
                    context JSONB,
                    source VARCHAR(20) DEFAULT 'ai',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    acknowledged_at TIMESTAMP WITH TIME ZONE
                )
            """))

            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_whisper_sessions_user ON whisper_sessions(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_whisper_sessions_status ON whisper_sessions(status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_whisper_messages_session ON whisper_messages(session_id)"))

        # Create production_forecasts table for Production Predictor history
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS production_forecasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    forecast_date DATE NOT NULL,
                    period_days INTEGER NOT NULL,
                    predicted_units INTEGER,
                    predicted_volume REAL,
                    confidence REAL,
                    actual_units INTEGER,
                    actual_volume REAL,
                    model_version TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    organization_id INTEGER
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS production_forecasts (
                    id SERIAL PRIMARY KEY,
                    entity_type VARCHAR(20) NOT NULL,
                    entity_id INTEGER NOT NULL,
                    forecast_date DATE NOT NULL,
                    period_days INTEGER NOT NULL,
                    predicted_units INTEGER,
                    predicted_volume NUMERIC(15, 2),
                    confidence NUMERIC(5, 4),
                    actual_units INTEGER,
                    actual_volume NUMERIC(15, 2),
                    model_version VARCHAR(50),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    organization_id INTEGER
                )
            """))

            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_prod_forecasts_entity ON production_forecasts(entity_type, entity_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_prod_forecasts_date ON production_forecasts(forecast_date)"))

        conn.commit()
        logger.info("Deal alerts migration completed successfully")


if __name__ == "__main__":
    import os
    from sqlalchemy import create_engine

    logging.basicConfig(level=logging.INFO)

    database_url = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
    engine = create_engine(database_url)

    run_migration(engine)
    print("Migration completed!")
