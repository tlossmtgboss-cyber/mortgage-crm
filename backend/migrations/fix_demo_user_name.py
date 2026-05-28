"""Fix Demo User name for tloss@cmgfi.com

Updates the full_name from 'Demo User' to 'Tim Loss' and backfills
any loans that were stamped with 'Demo User' as loan_officer_name.
"""
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")


def run():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        return

    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)

    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE users
            SET full_name = 'Tim Loss'
            WHERE email = 'tloss@cmgfi.com'
              AND (full_name IS NULL OR full_name = 'Demo User' OR full_name = '')
        """))
        print(f"Updated {result.rowcount} user(s)")

        row = conn.execute(text(
            "SELECT id FROM users WHERE email = 'tloss@cmgfi.com'"
        )).fetchone()

        if row:
            user_id = row[0]
            loan_result = conn.execute(text("""
                UPDATE loans
                SET loan_officer_name = 'Tim Loss'
                WHERE loan_officer_id = :uid
                  AND (loan_officer_name = 'Demo User' OR loan_officer_name IS NULL)
            """), {"uid": user_id})
            print(f"Updated {loan_result.rowcount} loan(s)")
        else:
            print("tloss@cmgfi.com user not found")

    print("Done")


if __name__ == "__main__":
    run()
