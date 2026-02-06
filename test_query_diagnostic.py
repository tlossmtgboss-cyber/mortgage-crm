#!/usr/bin/env python3
"""Diagnostic script to check what data exists for the daily priorities query"""

import os
import requests
import json

API_URL = os.environ.get("API_URL", "https://app.perenniaai.com/api/v1/ai/orchestrator-chat")
TOKEN = os.environ.get("AUTH_TOKEN", "")

print("="*80)
print("DIAGNOSTIC: Checking data in database")
print("="*80)

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Test 1: Check if any loans exist
print("\n1. Checking loans...")
payload = {
    "message": "How many loans do I have total? List them all.",
    "session_id": "diagnostic-test-1"
}

try:
    response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Response: {data.get('response', 'No response')[:500]}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text[:500])
except Exception as e:
    print(f"❌ Exception: {e}")

# Test 2: Check for tasks
print("\n2. Checking tasks...")
payload = {
    "message": "How many tasks do I have? Show me all my tasks.",
    "session_id": "diagnostic-test-2"
}

try:
    response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Response: {data.get('response', 'No response')[:500]}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text[:500])
except Exception as e:
    print(f"❌ Exception: {e}")

# Test 3: Specifically test daily priorities
print("\n3. Testing daily priorities query...")
payload = {
    "message": "Show me my daily priorities",
    "session_id": "diagnostic-test-3"
}

try:
    response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Response: {data.get('response', 'No response')[:500]}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text[:500])
except Exception as e:
    print(f"❌ Exception: {e}")

print("\n" + "="*80)
