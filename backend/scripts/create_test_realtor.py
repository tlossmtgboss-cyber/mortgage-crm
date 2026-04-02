"""
Create a test realtor account in production.
Run with: python scripts/create_test_realtor.py
"""
import os
import sys
import secrets
from datetime import datetime, timedelta, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    print("Set it with: export DATABASE_URL='postgresql://...'")
    sys.exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"Connecting to database...")
engine = create_engine(DATABASE_URL)

# Test realtor data
TEST_REALTOR = {
    "email": "test.realtor@perenniaai.com",
    "phone": "555-TEST-001",
    "first_name": "Test",
    "last_name": "Realtor",
    "brokerage_name": "Perennia Test Realty",
    "license_number": "TEST12345",
    "license_state": "CA",
}

def create_test_realtor():
    """Create test realtor account."""
    with engine.connect() as conn:
        # Check if realtor already exists
        existing = conn.execute(text("""
            SELECT id, email FROM realtor_portal_users
            WHERE email = :email
        """), {"email": TEST_REALTOR["email"]}).fetchone()

        if existing:
            print(f"Test realtor already exists: ID={existing[0]}, Email={existing[1]}")
            realtor_id = existing[0]
        else:
            # Get first organization
            org = conn.execute(text("""
                SELECT id FROM organizations LIMIT 1
            """)).fetchone()

            if not org:
                print("No organizations found. Creating default organization...")
                conn.execute(text("""
                    INSERT INTO organizations (name, created_at)
                    VALUES ('Perennia AI', NOW())
                """))
                conn.commit()
                org = conn.execute(text("SELECT id FROM organizations LIMIT 1")).fetchone()

            org_id = org[0]
            print(f"Using organization ID: {org_id}")

            # Get first LO user
            lo = conn.execute(text("""
                SELECT id, full_name FROM users WHERE role IN ('loan_officer', 'admin', 'sales') LIMIT 1
            """)).fetchone()

            lo_id = lo[0] if lo else None
            print(f"Primary LO: {lo[1] if lo else 'None'}")

            # Create realtor
            result = conn.execute(text("""
                INSERT INTO realtor_portal_users (
                    organization_id, email, phone, first_name, last_name,
                    brokerage_name, license_number, license_state,
                    primary_lo_id, is_active, created_at
                ) VALUES (
                    :org_id, :email, :phone, :first_name, :last_name,
                    :brokerage_name, :license_number, :license_state,
                    :lo_id, TRUE, NOW()
                ) RETURNING id
            """), {
                "org_id": org_id,
                "lo_id": lo_id,
                **TEST_REALTOR
            })

            realtor_id = result.fetchone()[0]
            conn.commit()
            print(f"Created test realtor: ID={realtor_id}")

        # Create a session token
        token = f"test-prod-{secrets.token_urlsafe(32)}"
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        # Check for existing session
        existing_session = conn.execute(text("""
            SELECT token FROM realtor_portal_sessions
            WHERE realtor_id = :realtor_id AND expires_at > NOW()
            LIMIT 1
        """), {"realtor_id": realtor_id}).fetchone()

        if existing_session:
            token = existing_session[0]
            print(f"Using existing session token")
        else:
            conn.execute(text("""
                INSERT INTO realtor_portal_sessions (
                    realtor_id, token, expires_at, ip_address, user_agent, created_at
                ) VALUES (
                    :realtor_id, :token, :expires_at, '127.0.0.1', 'Test Script', NOW()
                )
            """), {
                "realtor_id": realtor_id,
                "token": token,
                "expires_at": expires_at
            })
            conn.commit()
            print(f"Created session token (expires: {expires_at})")

        # Associate with some loans
        loans = conn.execute(text("""
            SELECT id, borrower_name FROM loans
            WHERE id NOT IN (SELECT loan_id FROM realtor_loan_associations WHERE realtor_id = :realtor_id)
            ORDER BY id DESC LIMIT 3
        """), {"realtor_id": realtor_id}).fetchall()

        for loan in loans:
            conn.execute(text("""
                INSERT INTO realtor_loan_associations (
                    realtor_id, loan_id, role, access_granted_at, granted_by_user_id
                ) VALUES (
                    :realtor_id, :loan_id, 'buyer_agent', NOW(), NULL
                )
            """), {"realtor_id": realtor_id, "loan_id": loan[0]})
            print(f"  Associated with loan: {loan[0]} - {loan[1]}")

        if loans:
            conn.commit()

        print("\n" + "="*60)
        print("TEST REALTOR ACCOUNT CREATED")
        print("="*60)
        print(f"Email:    {TEST_REALTOR['email']}")
        print(f"Name:     {TEST_REALTOR['first_name']} {TEST_REALTOR['last_name']}")
        print(f"Realtor ID: {realtor_id}")
        print(f"\nSession Token (use for API calls):")
        print(f"  {token}")
        print(f"\nTest the portal:")
        print(f"  curl 'https://app.perenniaai.com/api/v1/realtor-portal/me?token={token}'")
        print(f"  curl 'https://app.perenniaai.com/api/v1/realtor-portal/loans?token={token}'")
        print("="*60)

        return realtor_id, token


if __name__ == "__main__":
    create_test_realtor()
