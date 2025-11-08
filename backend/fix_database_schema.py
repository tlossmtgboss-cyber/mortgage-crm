#!/usr/bin/env python3
"""
Database Schema Fix Script
Adds missing columns to existing tables
"""
import os
from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    logger.error("DATABASE_URL not set!")
    exit(1)

logger.info(f"Connecting to database...")
engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        # Check if email_verified column exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users' AND column_name='email_verified'
        """))

        if result.fetchone() is None:
            logger.info("Adding email_verified column to users table...")
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE
            """))
            conn.commit()
            logger.info("✅ email_verified column added successfully!")
        else:
            logger.info("✅ email_verified column already exists")

        # Verify the column was added
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users' AND column_name='email_verified'
        """))

        if result.fetchone():
            logger.info("✅ Database schema is correct!")
        else:
            logger.error("❌ Failed to add column")
            exit(1)

except Exception as e:
    logger.error(f"❌ Error fixing database: {e}")
    exit(1)

logger.info("✅ Database schema fix complete!")
