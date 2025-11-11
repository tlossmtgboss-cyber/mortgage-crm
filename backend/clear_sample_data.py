#!/usr/bin/env python3
"""
Clear all sample/test data from the database.
This will remove:
- All loans (which will clear the "team members" list)
- All leads (except those you want to keep)
- All tasks
- All referral partners (sample ones)
- All MUM clients

Keeps: Your user account and company settings
"""
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import Base, User, Lead, Loan, AITask, ReferralPartner, MUMClient, Branch

# Database connection
DATABASE_URL = "sqlite:///./mortgage_crm.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def clear_sample_data():
    """Clear all sample data while keeping user accounts"""
    db = SessionLocal()
    try:
        print("🗑️  Clearing sample data...\n")

        # Count before deletion
        loans_count = db.query(Loan).count()
        leads_count = db.query(Lead).count()
        tasks_count = db.query(AITask).count()
        partners_count = db.query(ReferralPartner).count()
        mum_count = db.query(MUMClient).count()

        print(f"Found:")
        print(f"  - {loans_count} loans")
        print(f"  - {leads_count} leads")
        print(f"  - {tasks_count} tasks")
        print(f"  - {partners_count} referral partners")
        print(f"  - {mum_count} MUM clients")
        print()

        # Ask for confirmation
        response = input("⚠️  Are you sure you want to delete ALL this data? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Cancelled. No data was deleted.")
            return

        print("\n🗑️  Deleting data...")

        # Delete in order (tasks first since they reference loans)
        deleted_tasks = db.query(AITask).delete()
        print(f"  ✅ Deleted {deleted_tasks} tasks")

        deleted_loans = db.query(Loan).delete()
        print(f"  ✅ Deleted {deleted_loans} loans")

        deleted_leads = db.query(Lead).delete()
        print(f"  ✅ Deleted {deleted_leads} leads")

        deleted_partners = db.query(ReferralPartner).delete()
        print(f"  ✅ Deleted {deleted_partners} referral partners")

        deleted_mum = db.query(MUMClient).delete()
        print(f"  ✅ Deleted {deleted_mum} MUM clients")

        # Commit the changes
        db.commit()

        print("\n✅ Sample data cleared successfully!")
        print("\n📝 What's left:")
        users_count = db.query(User).count()
        branches_count = db.query(Branch).count()
        print(f"  - {users_count} user(s) (your account)")
        print(f"  - {branches_count} branch(es)")
        print("\n🎉 Your CRM is now clean and ready for real data!")
        print("\n💡 The 'Team Members' list will now be empty.")
        print("   Team members will appear as you add loans with real processors, underwriters, etc.")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    clear_sample_data()
