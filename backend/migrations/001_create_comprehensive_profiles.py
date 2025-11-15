"""
Migration 001: Create Comprehensive Profile Tables
Creates all 4 profile types + EmailInteraction + tracking tables

Run with: python backend/migrations/001_create_comprehensive_profiles.py
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database import Base

# Import all models to ensure they're registered with Base
from models.lead_profile import LeadProfile
from models.active_loan_profile import ActiveLoanProfile
from models.mum_client_profile import MUMClientProfile
from models.team_member_profile import TeamMemberProfile
from models.email_interaction import EmailInteraction
from models.field_update_history import FieldUpdateHistory
from models.data_conflict import DataConflict


def run_migration():
    """
    Create all comprehensive profile tables
    """

    print("=" * 70)
    print("MIGRATION 001: Creating Comprehensive Profile Tables")
    print("=" * 70)

    # Get database URL
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
    # Fix postgres:// to postgresql:// for SQLAlchemy
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    print(f"\nConnecting to database...")
    print(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'local'}")

    # Create engine
    engine = create_engine(DATABASE_URL)

    try:
        # Create all tables
        print("\n📊 Creating tables...")
        Base.metadata.create_all(bind=engine)

        print("\n✅ Successfully created the following tables:")
        print("  ✓ lead_profiles (52 fields)")
        print("  ✓ active_loan_profiles (53 fields)")
        print("  ✓ mum_client_profiles (22 fields)")
        print("  ✓ team_member_profiles (29 fields)")
        print("  ✓ email_interactions")
        print("  ✓ field_update_history")
        print("  ✓ data_conflicts")

        # Verify tables were created
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        result = session.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN (
                'lead_profiles',
                'active_loan_profiles',
                'mum_client_profiles',
                'team_member_profiles',
                'email_interactions',
                'field_update_history',
                'data_conflicts'
            )
            ORDER BY table_name
        """))

        tables = [row[0] for row in result]

        print(f"\n📋 Verified {len(tables)} tables in database:")
        for table in tables:
            print(f"  • {table}")

        session.close()

        print("\n" + "=" * 70)
        print("✅ MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 70)

        print("\n💡 Next steps:")
        print("  1. Update .env with ANTHROPIC_API_KEY")
        print("  2. Set AI_PROVIDER=claude in .env")
        print("  3. Test email parsing with: python backend/test_claude_parser.py")

        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def rollback_migration():
    """
    Drop all tables created by this migration
    WARNING: This will delete all data!
    """

    print("=" * 70)
    print("ROLLBACK MIGRATION 001")
    print("=" * 70)

    response = input("\n⚠️  WARNING: This will DELETE ALL DATA in these tables. Continue? (yes/no): ")

    if response.lower() != 'yes':
        print("Rollback cancelled.")
        return

    DATABASE_URL = get_db_url()
    engine = create_engine(DATABASE_URL)

    try:
        print("\n🗑️  Dropping tables...")

        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS data_conflicts CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS field_update_history CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS email_interactions CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS mum_client_profiles CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS active_loan_profiles CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS team_member_profiles CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS lead_profiles CASCADE"))
            conn.commit()

        print("\n✅ All tables dropped successfully")

    except Exception as e:
        print(f"\n❌ Rollback failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Migration 001: Create comprehensive profile tables')
    parser.add_argument('--rollback', action='store_true', help='Rollback this migration (deletes all data!)')

    args = parser.parse_args()

    if args.rollback:
        rollback_migration()
    else:
        success = run_migration()
        sys.exit(0 if success else 1)
