"""Migration: Hash existing plaintext API keys and add key_hash/key_prefix columns.

Adds key_hash and key_prefix columns to the api_keys table, migrates existing
plaintext keys to SHA-256 hashes, and clears the plaintext key column.

Run standalone:  python migrations/hash_api_keys.py
Or call:         from migrations.hash_api_keys import run_migration; run_migration(engine)
"""
import os
import sys
import logging
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(engine=None):
    from sqlalchemy import text

    if engine is None:
        from db import engine as _engine
        engine = _engine

    with engine.connect() as conn:
        # Add columns if they don't exist
        conn.execute(text(
            "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS key_hash VARCHAR(64)"
        ))
        conn.execute(text(
            "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS key_prefix VARCHAR(12)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys (key_hash) WHERE key_hash IS NOT NULL"
        ))

        # Make the key column nullable (it was NOT NULL before)
        conn.execute(text(
            "ALTER TABLE api_keys ALTER COLUMN key DROP NOT NULL"
        ))

        # Drop the unique constraint on key column if it exists, since migrated rows will have key=NULL
        # PostgreSQL names auto-generated unique constraints as <table>_<col>_key
        conn.execute(text("""
            DO $$
            BEGIN
                ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS api_keys_key_key;
            EXCEPTION WHEN undefined_object THEN
                NULL;
            END $$;
        """))

        conn.commit()
        logger.info("Schema changes applied: key_hash, key_prefix columns added; key column now nullable.")

        # Migrate existing plaintext keys
        rows = conn.execute(text(
            "SELECT id, key FROM api_keys WHERE key IS NOT NULL AND key_hash IS NULL"
        )).fetchall()

        migrated = 0
        for row in rows:
            key_id, raw_key = row
            if raw_key:
                h = hashlib.sha256(raw_key.encode()).hexdigest()
                prefix = raw_key[:8]
                conn.execute(
                    text("UPDATE api_keys SET key_hash = :h, key_prefix = :p, key = NULL WHERE id = :id"),
                    {"h": h, "p": prefix, "id": key_id}
                )
                migrated += 1
                logger.info(f"Migrated API key {key_id} (prefix: {prefix}...)")

        conn.commit()
        logger.info(f"API key hash migration complete. {migrated} keys migrated out of {len(rows)} found.")


if __name__ == "__main__":
    run_migration()
