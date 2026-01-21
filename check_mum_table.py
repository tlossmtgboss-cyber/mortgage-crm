#!/usr/bin/env python3
"""Check what columns exist in mum_clients table"""

import requests

API_BASE = "https://app.perenniaai.com"

# Login
response = requests.post(
    f"{API_BASE}/token",
    data={"username": "admin@perenniaai.com", "password": "demo123"},
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

token = response.json()["access_token"]

# Create a test script to check table structure
test_script = """
import psycopg2
import os

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

# Check if mum_clients table exists
cur.execute(\"\"\"
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'mum_clients'
    ORDER BY ordinal_position
\"\"\")

print("MUM Clients table columns:")
for row in cur.fetchall():
    print(f"  - {row[0]}: {row[1]}")

cur.close()
conn.close()
"""

print(test_script)
print("\n" + "="*60)
print("Please run this via: railway run python -c '<paste script above>'")
