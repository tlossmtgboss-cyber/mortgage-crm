#!/usr/bin/env python3
"""Clear old guideline updates to make room for real scraped data"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from guideline_updates_models import GuidelineUpdate, UserUpdateView

def clear_guidelines():
    db = SessionLocal()

    try:
        # Delete all user views first (foreign key constraint)
        view_count = db.query(UserUpdateView).delete()
        print(f"Deleted {view_count} user update views")

        # Delete all guideline updates
        update_count = db.query(GuidelineUpdate).delete()
        print(f"Deleted {update_count} guideline updates")

        db.commit()
        print("✅ Database cleared successfully")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    print("Clearing all guideline updates from database...")
    clear_guidelines()
