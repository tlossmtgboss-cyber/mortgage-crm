#!/usr/bin/env python
"""Reset password for tloss@cmgfi.com"""
import os
from sqlalchemy import create_engine, text
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("ERROR: DATABASE_URL not set")
    exit(1)

email = "tloss@cmgfi.com"
new_password = os.environ.get("NEW_PASSWORD")
if not new_password:
    print("ERROR: Set NEW_PASSWORD environment variable")
    exit(1)
new_hash = pwd_context.hash(new_password)

engine = create_engine(database_url)

with engine.connect() as conn:
    # Check if user exists
    result = conn.execute(text(
        "SELECT id, email FROM users WHERE LOWER(email) = LOWER(:email)"
    ), {"email": email})
    user = result.fetchone()

    if not user:
        print(f"ERROR: User {email} not found")
        exit(1)

    # Update password
    conn.execute(text(
        "UPDATE users SET hashed_password = :hash WHERE LOWER(email) = LOWER(:email)"
    ), {"hash": new_hash, "email": email})
    conn.commit()

    print(f"SUCCESS: Password updated for {email}")
