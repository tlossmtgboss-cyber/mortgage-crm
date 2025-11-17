#!/usr/bin/env python3
"""Check production database structure"""
import sys
from sqlalchemy import inspect, text
from database import engine

def check_users_table():
    """Check users table structure"""

    print("=" * 80)
    print("USERS TABLE STRUCTURE")
    print("=" * 80)

    inspector = inspect(engine)

    # Check if users table exists
    tables = inspector.get_table_names()

    if 'users' not in tables:
        print("\n❌ Users table does NOT exist!")
        print(f"\nAvailable tables: {', '.join(tables)}")
        return

    # Get column information
    columns = inspector.get_columns('users')

    print(f"\n✅ Users table exists with {len(columns)} columns:\n")
    print(f"{'Column':<25} {'Type':<25} {'Nullable':<10}")
    print("-" * 60)

    for col in columns:
        col_name = col['name']
        col_type = str(col['type'])
        nullable = 'YES' if col['nullable'] else 'NO'
        print(f"{col_name:<25} {col_type:<25} {nullable:<10}")

    # Check for required columns
    print("\n" + "=" * 80)
    print("REQUIRED COLUMNS FOR CALL ROUTING")
    print("=" * 80)

    required_columns = ['id', 'name', 'phone', 'email', 'role']
    column_names = [col['name'] for col in columns]

    all_present = True
    for req_col in required_columns:
        if req_col in column_names:
            print(f"✅ {req_col}")
        else:
            print(f"❌ {req_col} - MISSING!")
            all_present = False

    if not all_present:
        print("\n⚠️  WARNING: Missing required columns for call routing!")
        return

    # Get sample user data (first 5 users)
    print("\n" + "=" * 80)
    print("SAMPLE USER DATA (first 5 users)")
    print("=" * 80)

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, name, phone, email, role
            FROM users
            LIMIT 5
        """))

        users = result.fetchall()

        if users:
            print(f"\n{'ID':<5} {'Name':<25} {'Phone':<20} {'Email':<35} {'Role':<15}")
            print("-" * 100)
            for user in users:
                user_id = str(user[0])[:5]
                name = (user[1] or 'NULL')[:24]
                phone = (user[2] or 'NULL')[:19]
                email = (user[3] or 'NULL')[:34]
                role = (user[4] or 'NULL')[:14]
                print(f"{user_id:<5} {name:<25} {phone:<20} {email:<35} {role:<15}")
        else:
            print("\n❌ No users found in database!")

    print("\n" + "=" * 80)

if __name__ == '__main__':
    try:
        check_users_table()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
