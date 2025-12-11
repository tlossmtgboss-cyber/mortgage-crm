#!/usr/bin/env python3
"""Upgrade demo user to admin role for testing"""

from sqlalchemy import create_engine, text
import os

def upgrade_demo_user():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not set")
        return

    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Check current role
        result = conn.execute(text("""
            SELECT email, role, full_name
            FROM users
            WHERE email = 'admin@perenniaai.com'
        """))
        user = result.fetchone()

        if user:
            print(f"📋 Current user: {user[2]} ({user[0]})")
            print(f"📋 Current role: {user[1]}")

            if user[1] in ['admin', 'management']:
                print(f"✅ User already has {user[1]} role!")
            else:
                # Update to admin
                conn.execute(text("""
                    UPDATE users
                    SET role = 'admin'
                    WHERE email = 'admin@perenniaai.com'
                """))
                conn.commit()
                print("✅ User upgraded to 'admin' role!")

                # Verify
                result = conn.execute(text("""
                    SELECT role FROM users WHERE email = 'admin@perenniaai.com'
                """))
                new_role = result.fetchone()[0]
                print(f"✅ Verified new role: {new_role}")
        else:
            print("❌ Demo user not found!")

if __name__ == '__main__':
    upgrade_demo_user()
