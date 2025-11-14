"""
Enable Email Auto-Delete Feature
Simple script to enable auto-delete in production
"""
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def enable_auto_delete():
    """Enable auto-delete for Microsoft OAuth token"""
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Import models after engine is created
        from main import MicrosoftOAuthToken

        db = SessionLocal()

        oauth = db.query(MicrosoftOAuthToken).first()

        if oauth:
            oauth.auto_delete_imported_emails = True
            db.commit()
            print('✅ Auto-delete enabled!')
            print(f'Email: {oauth.email_address}')
            print(f'Sync enabled: {oauth.sync_enabled}')
            print(f'Auto-delete: {oauth.auto_delete_imported_emails}')
            db.close()
            return True
        else:
            print('❌ No OAuth token found - you need to connect Microsoft 365 first')
            db.close()
            return False

    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = enable_auto_delete()
    sys.exit(0 if success else 1)
