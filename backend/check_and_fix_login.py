#!/usr/bin/env python
"""Check and fix login for tloss@cmgfi.com"""
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import bcrypt as _bcrypt

load_dotenv()

# Password hashing


class _BcryptCompat:
    """Drop-in replacement providing .hash() over raw bcrypt."""
    def hash(self, password: str) -> str:
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

pwd_context = _BcryptCompat()

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("❌ DATABASE_URL not set")
    sys.exit(1)

print("="*80)
print("CHECKING LOGIN FOR tloss@cmgfi.com")
print("="*80)

engine = create_engine(database_url)

with engine.connect() as conn:
    # Check if user exists
    result = conn.execute(text("""
        SELECT id, email, username, hashed_password, is_active, is_admin
        FROM users
        WHERE email = 'tloss@cmgfi.com' OR username = 'tloss@cmgfi.com'
        LIMIT 1
    """))

    user = result.fetchone()

    if not user:
        print("\n❌ USER NOT FOUND")
        print("\nThe account tloss@cmgfi.com does not exist in the database.")
        print("\nOptions:")
        print("1. Create the account via the registration page")
        print("2. Or let me know if you want to create it via script")
        sys.exit(1)

    user_id, email, username, hashed_password, is_active, is_admin = user

    print(f"\n✅ USER FOUND")
    print(f"   ID: {user_id}")
    print(f"   Email: {email}")
    print(f"   Username: {username}")
    print(f"   Active: {is_active}")
    print(f"   Admin: {is_admin}")
    print(f"   Has password: {'Yes' if hashed_password else 'No'}")

    if not is_active:
        print(f"\n⚠️  ACCOUNT IS INACTIVE")
        print(f"   Activating account...")
        conn.execute(text("""
            UPDATE users
            SET is_active = true
            WHERE id = :user_id
        """), {"user_id": user_id})
        conn.commit()
        print(f"   ✅ Account activated!")

    # Offer to reset password
    print(f"\n💡 Would you like to reset the password?")
    print(f"   Current script will set password to: 'NewPassword123!'")
    print(f"   Run with --reset flag to change password")

    if "--reset" in sys.argv:
        new_password = os.environ.get("NEW_PASSWORD", "NewPassword123!")
        new_hash = pwd_context.hash(new_password)

        conn.execute(text("""
            UPDATE users
            SET hashed_password = :new_hash
            WHERE id = :user_id
        """), {"user_id": user_id, "new_hash": new_hash})
        conn.commit()

        print(f"\n✅ PASSWORD RESET!")
        print(f"   Email: {email}")
        print(f"   New Password: {new_password}")
        print(f"\n   You can now log in and change your password in Settings")
    else:
        print(f"\n   To reset password, run: python check_and_fix_login.py --reset")

print(f"\n{'='*80}")
print("DONE")
print("="*80)
