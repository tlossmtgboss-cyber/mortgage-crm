#!/usr/bin/env python3
"""
Setup Recall.ai integration - Store API key in database
"""
import sys
import os

# Add backend to path
sys.path.insert(0, '/Users/timothyloss/my-project/mortgage-crm/backend')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import RecallAIConnection, User
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/Users/timothyloss/my-project/mortgage-crm/backend/.env')

# Recall.ai credentials
API_KEY = "2710d1a040a03295045e0ad6bb2535997da8acd0"

def setup_recallai():
    """Store Recall.ai API key for the first user"""
    print("Setting up Recall.ai integration...")

    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in .env file")
        return False

    # Create database connection
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get the first user (assuming demo user)
        user = db.query(User).first()

        if not user:
            print("❌ No users found in database")
            return False

        print(f"✅ Found user: {user.email}")

        # Check if Recall.ai connection already exists
        existing = db.query(RecallAIConnection).filter(
            RecallAIConnection.user_id == user.id
        ).first()

        if existing:
            # Update existing connection
            existing.api_key = API_KEY
            existing.updated_at = datetime.now(timezone.utc)
            print("✅ Updated existing Recall.ai connection")
        else:
            # Create new connection
            connection = RecallAIConnection(
                user_id=user.id,
                api_key=API_KEY,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(connection)
            print("✅ Created new Recall.ai connection")

        db.commit()
        print(f"\n✅ Recall.ai API key stored for user: {user.email}")
        print("\nIntegration is ready to use!")
        print("\nNext steps:")
        print("1. Configure webhook in Recall.ai dashboard:")
        print("   URL: https://mortgage-crm-production-7a9a.up.railway.app/api/v1/recallai/webhook")
        print("   Secret: whsec_suIiYYXb7fgjFjOtVWT0spOfalxNKtldS/MI13wAGV3thi5JbpPjpCUYU2Y0BcxN")
        print("\n2. Test the integration:")
        print("   - Open any lead profile in the frontend")
        print("   - Click 'Start Recording' button")
        print("   - Paste a meeting URL (Zoom/Teams/Meet)")
        print("   - The bot will join and save transcript to Conversation Log")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Recall.ai Setup Script")
    print("=" * 60)
    success = setup_recallai()
    print("=" * 60)

    sys.exit(0 if success else 1)
