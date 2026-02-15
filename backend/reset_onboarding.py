"""
Reset Onboarding Wizard for Demo User
"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL')

def reset_onboarding():
    """Reset onboarding for admin@perenniaai.com"""
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get demo user
        user_query = text("SELECT id, email FROM users WHERE email = 'admin@perenniaai.com'")
        result = session.execute(user_query).fetchone()

        if not result:
            print("❌ Demo user not found")
            return

        user_id = result[0]
        print(f"✅ Found demo user (ID: {user_id})")

        # Reset onboarding_completed flag in users table
        update_user = text("""
            UPDATE users
            SET onboarding_completed = FALSE
            WHERE id = :user_id
        """)
        session.execute(update_user, {"user_id": user_id})
        print("✅ Reset onboarding_completed flag in users table")

        # Delete onboarding progress
        delete_progress = text("""
            DELETE FROM onboarding_progress
            WHERE user_id = :user_id
        """)
        session.execute(delete_progress, {"user_id": user_id})
        print("✅ Deleted onboarding_progress records")

        session.commit()
        print("\n🎉 Onboarding wizard reset successfully!")
        print("   The demo user will see the onboarding wizard on next login.")

    except Exception as e:
        session.rollback()
        print(f"❌ Error resetting onboarding: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    print("🔄 Resetting onboarding wizard for demo user...\n")
    reset_onboarding()
