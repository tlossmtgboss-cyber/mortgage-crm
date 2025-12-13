"""
Debug script for PURL token verification
"""
import os
import sys
import hashlib

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Token to verify
TEST_TOKEN = "purl_live_5383b8e412db4dedb9e99f18be1d5e4a53ee9e5c7b97f55e4b7a2d7f3c8e1a2b"
WORKSPACE_SLUG = "tokenverify-test-islso4m9"

def main():
    # Get database URL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return

    print(f"Connecting to database...")
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # 1. Token format validation
        print("\n=== TOKEN FORMAT VALIDATION ===")
        print(f"Token length: {len(TEST_TOKEN)}")
        print(f"Expected length: {10 + 64} = 74 (purl_live_ + 64 hex)")
        print(f"Starts with purl_live_: {TEST_TOKEN.startswith('purl_live_')}")
        print(f"Format valid: {len(TEST_TOKEN) == 74 and TEST_TOKEN.startswith('purl_live_')}")

        # 2. Hash the token
        print("\n=== TOKEN HASH ===")
        token_hash = hashlib.sha256(TEST_TOKEN.encode()).hexdigest()
        print(f"Computed hash: {token_hash}")

        # 3. Check workspace exists
        print("\n=== WORKSPACE CHECK ===")
        workspace = db.execute(text("""
            SELECT id, slug, organization_id, status
            FROM purl_workspaces
            WHERE slug = :slug
        """), {"slug": WORKSPACE_SLUG}).fetchone()

        if workspace:
            print(f"Workspace found: ID={workspace[0]}, slug={workspace[1]}, org={workspace[2]}, status={workspace[3]}")
        else:
            print("ERROR: Workspace not found!")
            return

        # 4. Check tokens for this workspace
        print("\n=== TOKENS FOR WORKSPACE ===")
        tokens = db.execute(text("""
            SELECT id, token_hash, token_prefix, scope, status, expires_at, created_at
            FROM purl_access_tokens
            WHERE workspace_id = :workspace_id
        """), {"workspace_id": workspace[0]}).fetchall()

        if not tokens:
            print("ERROR: No tokens found for workspace!")
        else:
            for t in tokens:
                print(f"Token ID={t[0]}")
                print(f"  Stored hash: {t[1]}")
                print(f"  Prefix: {t[2]}")
                print(f"  Scope: {t[3]}")
                print(f"  Status: {t[4]}")
                print(f"  Expires: {t[5]}")
                print(f"  Created: {t[6]}")
                print(f"  Hash matches: {t[1] == token_hash}")
                print()

        # 5. Direct query by hash
        print("\n=== DIRECT HASH LOOKUP ===")
        token_record = db.execute(text("""
            SELECT id, workspace_id, scope, status, expires_at
            FROM purl_access_tokens
            WHERE token_hash = :hash
        """), {"hash": token_hash}).fetchone()

        if token_record:
            print(f"Token found by hash!")
            print(f"  ID: {token_record[0]}")
            print(f"  Workspace ID: {token_record[1]}")
            print(f"  Scope: {token_record[2]}")
            print(f"  Status: {token_record[3]}")
            print(f"  Expires: {token_record[4]}")
        else:
            print("ERROR: Token not found by hash!")
            print("The token stored in the database does not match the computed hash.")
            print("This means the token returned by the API was different from what was stored.")

    finally:
        db.close()

if __name__ == "__main__":
    main()
