"""
Clear all dummy/sample tasks from the CRM
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def clear_tasks():
    """Delete all tasks from the database"""
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()

        # Import Task model
        from main import Task

        # Get count of tasks before deletion
        task_count = db.query(Task).count()
        print(f"Found {task_count} tasks in the database")

        if task_count == 0:
            print("No tasks to delete")
            db.close()
            return

        # List tasks before deletion
        tasks = db.query(Task).all()
        print("\nTasks to be deleted:")
        for task in tasks:
            print(f"  - {task.title} (ID: {task.id}, Priority: {task.priority})")

        # Confirm deletion
        print(f"\nDeleting all {task_count} tasks...")

        # Delete all tasks
        deleted = db.query(Task).delete()
        db.commit()

        print(f"✅ Successfully deleted {deleted} tasks")

        # Verify deletion
        remaining = db.query(Task).count()
        print(f"Remaining tasks: {remaining}")

        db.close()
        return True

    except Exception as e:
        print(f"❌ Error clearing tasks: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("CLEARING DUMMY TASKS FROM CRM")
    print("=" * 60)
    clear_tasks()
    print("\n✅ Done!")
