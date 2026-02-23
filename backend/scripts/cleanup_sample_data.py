#!/usr/bin/env python3
"""
One-time cleanup script to delete sample data for tloss@cmgfi.com
Run via: railway run python scripts/cleanup_sample_data.py
"""
import os
import sys
from sqlalchemy import create_engine, text

def main():
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return False
        
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)

    print("Connecting to database...")
    engine = create_engine(db_url)

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Delete sample loans by borrower name
            sample_names = ['Jeffrey Kim', 'Patricia Luna', 'David Okafor', 
                           'Rachel Green', 'William Chen', 'Sandra Yee']
            
            total_loans = 0
            for name in sample_names:
                # Delete related records first
                for table in ['loan_documents', 'loan_notes', 'loan_activities', 'loan_conditions']:
                    try:
                        conn.execute(text(f"""
                            DELETE FROM {table} 
                            WHERE loan_id IN (SELECT id FROM loans WHERE borrower_name = :name)
                        """), {"name": name})
                    except Exception:
                        pass

                # Delete the loans
                result = conn.execute(text("DELETE FROM loans WHERE borrower_name = :name"), {"name": name})
                total_loans += result.rowcount
                print(f"  Deleted loans for {name}: {result.rowcount}")
            
            print(f"Total loans deleted: {total_loans}")
            
            # Delete sample leads
            sample_first_names = ['Jeffrey', 'Patricia', 'David', 'Rachel', 'William', 'Sandra']
            sample_last_names = ['Kim', 'Luna', 'Okafor', 'Green', 'Chen', 'Yee']
            
            # Delete lead-related records first
            for table in ['lead_activities', 'lead_notes', 'lead_engagements']:
                try:
                    conn.execute(text(f"""
                        DELETE FROM {table} 
                        WHERE lead_id IN (
                            SELECT id FROM leads 
                            WHERE first_name = ANY(:first_names) 
                            AND last_name = ANY(:last_names)
                        )
                    """), {"first_names": sample_first_names, "last_names": sample_last_names})
                except Exception:
                    pass

            result = conn.execute(text("""
                DELETE FROM leads 
                WHERE first_name = ANY(:first_names) 
                AND last_name = ANY(:last_names)
            """), {"first_names": sample_first_names, "last_names": sample_last_names})
            print(f"Deleted {result.rowcount} sample leads")
            
            # Delete tasks related to sample data
            result = conn.execute(text("""
                DELETE FROM tasks 
                WHERE title LIKE '%%TEST-%%' 
                OR description LIKE '%%Jeffrey Kim%%'
                OR description LIKE '%%Sandra Yee%%'
            """))
            print(f"Deleted {result.rowcount} sample tasks")
            
            # Delete sample notifications
            try:
                result = conn.execute(text("""
                    DELETE FROM notifications 
                    WHERE message LIKE '%%Jeffrey Kim%%'
                    OR message LIKE '%%Sandra Yee%%'
                    OR title LIKE '%%TEST-%%'
                """))
                print(f"Deleted {result.rowcount} sample notifications")
            except Exception as e:
                print(f"Notifications: {e}")
            
            trans.commit()
            print("\n✅ SUCCESS: Sample data deleted!")
            return True
            
        except Exception as e:
            trans.rollback()
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
