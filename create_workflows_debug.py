#!/usr/bin/env python3
"""Debug script to check API responses"""

import requests
import json

API_BASE = "https://app.perenniaai.com"

# Login
response = requests.post(
    f"{API_BASE}/token",
    data={"username": "admin@perenniaai.com", "password": "demo123"},
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

token = response.json()["access_token"]
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# Try creating a responsibility for user ID 58 (Sarah Johnson)
print("Testing responsibility creation for user 58...")
payload = {
    "title": "Test Responsibility",
    "description": "Test description",
    "key_activities": ["Activity 1", "Activity 2"]
}

response = requests.post(
    f"{API_BASE}/api/v1/users/58/responsibilities",
    headers=headers,
    json=payload
)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
print()

# Try creating a goal
print("Testing goal creation for user 58...")
payload = {
    "title": "Test Task",
    "description": "Test description",
    "category": "daily_tasks",
    "target_date": "2024-12-01T00:00:00",
    "status": "active"
}

response = requests.post(
    f"{API_BASE}/api/v1/users/58/goals",
    headers=headers,
    json=payload
)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
print()

# Get team members to see what we created
print("Fetching team members...")
response = requests.get(
    f"{API_BASE}/api/v1/team/members",
    headers=headers
)

if response.status_code == 200:
    members = response.json()
    print(f"Total members: {len(members)}")
    for member in members[-10:]:  # Show last 10
        print(f"  - {member.get('first_name')} {member.get('last_name')}: ID={member.get('id')}, Role={member.get('role')}")
