#!/usr/bin/env python3
"""
Migration script to add missing 'Company Admin' role to onboarding_roles table.

This script fixes the registration issue where users cannot create companies
because the 'Company Admin' role is missing from the database.

Usage:
    python fix_company_admin_role.py
"""

import os
import sys
import psycopg2
from datetime import datetime

def get_database_url():
    """Get database URL from environment variable."""
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("Please set DATABASE_URL to your PostgreSQL connection string")
        print("Example: export DATABASE_URL='postgresql://user:pass@host:port/dbname'")
        sys.exit(1)
    return db_url

def check_role_exists(cursor, role_name):
    """Check if a role already exists in the database."""
    cursor.execute(
        "SELECT COUNT(*) FROM onboarding_roles WHERE name = %s",
        (role_name,)
    )
    count = cursor.fetchone()[0]
    return count > 0

def add_company_admin_role(cursor):
    """Add the Company Admin role to the database."""
    role_name = 'Company Admin'
    
    if check_role_exists(cursor, role_name):
        print(f"✓ Role '{role_name}' already exists in the database")
        return False
    
    print(f"Adding '{role_name}' role to database...")
    
    cursor.execute("""
        INSERT INTO onboarding_roles (name, description, is_active, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        role_name,
        'Company administrator with access to manage their organization',
        True,
        datetime.now(),
        datetime.now()
    ))
    
    print(f"✓ Successfully added '{role_name}' role")
    return True

def main():
    """Main migration function."""
    print("=" * 70)
    print("Company Admin Role Migration Script")
    print("=" * 70)
    print()
    
    # Get database connection string
    db_url = get_database_url()
    
    try:
        # Connect to database
        print("Connecting to database...")
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        print("✓ Connected successfully\n")
        
        # Add the Company Admin role
        role_added = add_company_admin_role(cursor)
        
        if role_added:
            # Commit the transaction
            conn.commit()
            print("\n✓ Migration completed successfully!")
            print("\nThe registration issue should now be fixed.")
            print("Users can now create companies and be assigned the Company Admin role.")
        else:
            print("\nNo changes were made to the database.")
        
    except psycopg2.Error as e:
        print(f"\n✗ Database error: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            print("\nDatabase connection closed.")
    
    print("=" * 70)

if __name__ == "__main__":
    main()
