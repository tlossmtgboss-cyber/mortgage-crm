#!/usr/bin/env python3
"""Check production database structure"""
import os
import psycopg2
from psycopg2 import sql

# This will use the Railway DATABASE_URL when run via 'railway run'
DATABASE_URL = os.environ.get('DATABASE_URL')

def check_users_table():
    """Check users table structure"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print("=" * 80)
    print("USERS TABLE STRUCTURE")
    print("=" * 80)

    # Check if users table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'users'
        );
    """)
    exists = cur.fetchone()[0]

    if not exists:
        print("❌ Users table does NOT exist!")
        return

    # Get column information
    cur.execute("""
        SELECT
            column_name,
            data_type,
            character_maximum_length,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_name = 'users'
        ORDER BY ordinal_position;
    """)

    columns = cur.fetchall()

    print(f"\n✅ Users table exists with {len(columns)} columns:\n")
    print(f"{'Column':<25} {'Type':<20} {'Nullable':<10} {'Default':<30}")
    print("-" * 85)

    for col in columns:
        col_name = col[0]
        data_type = col[1]
        if col[2]:  # character_maximum_length
            data_type += f"({col[2]})"
        nullable = col[3]
        default = col[4] or ''
        print(f"{col_name:<25} {data_type:<20} {nullable:<10} {default:<30}")

    # Check for required columns
    print("\n" + "=" * 80)
    print("REQUIRED COLUMNS FOR CALL ROUTING")
    print("=" * 80)

    required_columns = ['id', 'name', 'phone', 'email', 'role']
    column_names = [col[0] for col in columns]

    for req_col in required_columns:
        if req_col in column_names:
            print(f"✅ {req_col}")
        else:
            print(f"❌ {req_col} - MISSING!")

    # Get sample user data (first 5 users)
    print("\n" + "=" * 80)
    print("SAMPLE USER DATA (first 5 users)")
    print("=" * 80)

    cur.execute("""
        SELECT id, name, phone, email, role
        FROM users
        LIMIT 5;
    """)

    users = cur.fetchall()

    if users:
        print(f"\n{'ID':<5} {'Name':<25} {'Phone':<20} {'Email':<30} {'Role':<15}")
        print("-" * 95)
        for user in users:
            user_id = str(user[0])
            name = user[1] or 'NULL'
            phone = user[2] or 'NULL'
            email = user[3] or 'NULL'
            role = user[4] or 'NULL'
            print(f"{user_id:<5} {name:<25} {phone:<20} {email:<30} {role:<15}")
    else:
        print("\n❌ No users found in database!")

    cur.close()
    conn.close()

if __name__ == '__main__':
    try:
        check_users_table()
    except Exception as e:
        print(f"❌ Error: {e}")
