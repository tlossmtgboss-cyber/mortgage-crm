#!/usr/bin/env python3
"""
Script to create a master admin user for the Mortgage CRM system.
This script creates a user directly in the database with hashed password.
"""

import bcrypt
import sqlite3
import os
from pathlib import Path

# Master Admin Credentials
ADMIN_EMAIL = "admin@mortgagecrm.com"
ADMIN_PASSWORD = "MasterAdmin@2025!Secure"
ADMIN_FULL_NAME = "Master Administrator"

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_admin_user():
    """Create master admin user in the database."""
    
    # Find the database file
    db_path = Path(__file__).parent / "crm.db"
    
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        print("Please ensure the application has been initialized first.")
        return
    
    # Hash the password
    hashed_password = hash_password(ADMIN_PASSWORD)
    
    try:
        # Connect to the database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if user already exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            print(f"User with email {ADMIN_EMAIL} already exists.")
            print("If you need to reset the password, please delete the existing user first.")
        else:
            # Insert the new admin user
            cursor.execute(
                "INSERT INTO users (email, hashed_password, full_name) VALUES (?, ?, ?)",
                (ADMIN_EMAIL, hashed_password, ADMIN_FULL_NAME)
            )
            conn.commit()
            print("\n" + "="*60)
            print("Master Admin User Created Successfully!")
            print("="*60)
            print(f"Username (Email): {ADMIN_EMAIL}")
            print(f"Password: {ADMIN_PASSWORD}")
            print("="*60)
            print("\nIMPORTANT: Save these credentials in a secure location.")
            print("You can use these credentials to log in to the Mortgage CRM frontend.")
            print("="*60 + "\n")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    create_admin_user()
