"""
Set test company logo for users
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# Test logo - CMG Financial logo
TEST_LOGO_URL = "https://www.cmgfi.com/hubfs/CMGFinancial_logo_2-Color.png"

def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return False

    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Find users with email containing 'tim' or 'loss' or 'admin'
        result = conn.execute(text("""
            SELECT id, email, full_name, company_logo_url
            FROM users
            WHERE email ILIKE '%tim%' OR email ILIKE '%loss%' OR email ILIKE '%admin%'
            LIMIT 10
        """))
        users = result.fetchall()

        print(f"Found {len(users)} matching users:")
        for u in users:
            print(f"  ID: {u[0]}, Email: {u[1]}, Name: {u[2]}, Logo: {u[3]}")

        # Update all matching users with the test logo
        result = conn.execute(text("""
            UPDATE users
            SET company_logo_url = :logo_url
            WHERE email ILIKE '%tim%' OR email ILIKE '%loss%' OR email ILIKE '%admin%'
            RETURNING id, email
        """), {"logo_url": TEST_LOGO_URL})

        updated = result.fetchall()
        conn.commit()

        print(f"\nUpdated {len(updated)} users with logo: {TEST_LOGO_URL}")
        for u in updated:
            print(f"  Updated: {u[1]} (ID: {u[0]})")

        return True

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
