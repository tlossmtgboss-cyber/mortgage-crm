"""
Send invitation to Tim Loss at CMG Home Loans.
One-time migration to create subscriber invitation.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Create invitation for Tim Loss."""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        return None

    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=14)

    with engine.begin() as conn:
        # Check if email already has pending invitation
        existing = conn.execute(text("""
            SELECT token, status FROM subscriber_invitations
            WHERE email = :email AND status = 'pending'
            ORDER BY created_at DESC LIMIT 1
        """), {'email': 'tloss@cmghomeloans.com'}).fetchone()

        if existing:
            print(f"Existing pending invitation found!")
            print(f"Token: {existing[0]}")
            print(f"Signup URL: https://www.perenniaai.com/signup?invite={existing[0]}")
            return {
                'token': existing[0],
                'existing': True
            }

        # Create new invitation
        conn.execute(text("""
            INSERT INTO subscriber_invitations (
                token, email, company_name, contact_name, plan, seats,
                promo_code, status, expires_at, created_at, updated_at
            ) VALUES (
                :token, :email, :company_name, :contact_name, 'professional', 10,
                'TIMLOSS2024', 'pending', :expires_at, NOW(), NOW()
            )
        """), {
            'token': token,
            'email': 'tloss@cmghomeloans.com',
            'company_name': 'CMG Home Loans',
            'contact_name': 'Tim Loss',
            'expires_at': expires_at
        })

        print("=" * 60)
        print("INVITATION CREATED SUCCESSFULLY")
        print("=" * 60)
        print(f"Recipient: Tim Loss <tloss@cmghomeloans.com>")
        print(f"Company: CMG Home Loans")
        print(f"Plan: Professional (10 seats)")
        print(f"Promo Code: TIMLOSS2024")
        print(f"Expires: {expires_at.strftime('%Y-%m-%d')}")
        print("")
        print("SIGNUP URL:")
        print(f"https://www.perenniaai.com/signup?invite={token}&promo=TIMLOSS2024")
        print("=" * 60)

        return {
            'token': token,
            'email': 'tloss@cmghomeloans.com',
            'signup_url': f"https://www.perenniaai.com/signup?invite={token}&promo=TIMLOSS2024",
            'existing': False
        }


if __name__ == "__main__":
    run_migration()
