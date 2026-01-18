"""
Clean up partially created Tim Loss account to allow fresh signup.
"""
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Delete partial Tim Loss account data."""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        return False

    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)

    with engine.begin() as conn:
        email = 'tloss@cmghomeloans.com'

        # Get user info
        user = conn.execute(text("""
            SELECT id, tenant_account_id FROM users WHERE email = :email
        """), {'email': email}).fetchone()

        if not user:
            print(f"No user found with email {email}")
            return {'deleted': False, 'reason': 'no_user'}

        user_id = user[0]
        tenant_id = user[1]

        print(f"Found user: id={user_id}, tenant_id={tenant_id}")

        # Clear foreign key references
        conn.execute(text("""
            UPDATE leads SET owner_id = NULL WHERE owner_id = :user_id
        """), {'user_id': user_id})
        print("Cleared leads.owner_id references")

        conn.execute(text("""
            UPDATE loans SET loan_officer_id = NULL WHERE loan_officer_id = :user_id
        """), {'user_id': user_id})
        print("Cleared loans.loan_officer_id references")

        # Delete user roles
        conn.execute(text("""
            DELETE FROM user_assigned_roles WHERE user_id = :user_id
        """), {'user_id': user_id})
        print("Deleted user_assigned_roles")

        conn.execute(text("""
            DELETE FROM user_active_role WHERE user_id = :user_id
        """), {'user_id': user_id})
        print("Deleted user_active_role")

        # Delete onboarding profiles
        conn.execute(text("""
            DELETE FROM onboarding_user_profiles WHERE user_id = :user_id
        """), {'user_id': user_id})
        print("Deleted onboarding_user_profiles")

        # Delete tenant BEFORE user (tenant.owner_user_id references user)
        if tenant_id:
            conn.execute(text("""
                DELETE FROM tenant_accounts WHERE id = :tenant_id
            """), {'tenant_id': str(tenant_id)})
            print(f"Deleted tenant {tenant_id}")

        # Delete user (after tenant is deleted)
        conn.execute(text("""
            DELETE FROM users WHERE id = :user_id
        """), {'user_id': user_id})
        print(f"Deleted user {user_id}")

        # Reset invitation status
        conn.execute(text("""
            UPDATE subscriber_invitations
            SET status = 'pending', accepted_at = NULL, accepted_by_user_id = NULL
            WHERE email = :email AND status = 'accepted'
        """), {'email': email})
        print("Reset invitation status to pending")

        print("\n✅ Cleanup complete! Tim Loss can now sign up fresh.")
        return {'deleted': True, 'user_id': user_id, 'tenant_id': str(tenant_id) if tenant_id else None}


if __name__ == "__main__":
    run_migration()
