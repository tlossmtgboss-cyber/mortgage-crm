#!/usr/bin/env python3
"""
Fix MUM clients schema to match the model expectations
"""

import os
import requests

API_BASE = "https://app.perenniaai.com"

_password = os.getenv("DEMO_USER_PASSWORD")
if not _password:
    raise ValueError("DEMO_USER_PASSWORD env var required")

# Login
response = requests.post(
    f"{API_BASE}/token",
    data={"username": "admin@perenniaai.com", "password": _password},
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

token = response.json()["access_token"]

# SQL to fix the schema
fix_schema_sql = """
-- Add missing columns that the model expects
ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS name VARCHAR(200);
ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS loan_number VARCHAR(100);
ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS original_close_date TIMESTAMP;
ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS days_since_funding INTEGER;
ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS original_rate DECIMAL(6, 4);
ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS current_rate DECIMAL(6, 4);
ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS loan_balance DECIMAL(12, 2);
ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS estimated_savings DECIMAL(10, 2);
ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS engagement_score INTEGER;
ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS last_contact TIMESTAMP;

-- Copy data from old columns to new ones
UPDATE mum_clients SET name = client_name WHERE name IS NULL;
UPDATE mum_clients SET loan_number = servicing_loan_number WHERE loan_number IS NULL;
UPDATE mum_clients SET original_close_date = closing_date WHERE original_close_date IS NULL;
UPDATE mum_clients SET original_rate = interest_rate WHERE original_rate IS NULL;
UPDATE mum_clients SET current_rate = interest_rate WHERE current_rate IS NULL;
UPDATE mum_clients SET loan_balance = current_loan_amount WHERE loan_balance IS NULL;
UPDATE mum_clients SET last_contact = last_contact_date WHERE last_contact IS NULL;
"""

print(fix_schema_sql)
print("\n" + "="*60)
print("This SQL needs to be run on the database to fix the schema mismatch")
