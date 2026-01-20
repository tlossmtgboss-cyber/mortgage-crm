#!/usr/bin/env python3
"""Test Smart AI Assistant"""
import requests
import json

API_URL = "https://api.perenniaai.com"

# Get auth token
print("Getting auth token...")
token_response = requests.post(
    f"{API_URL}/token",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={"username": "admin@perenniaai.com", "password": "demo123"}
)
token = token_response.json()["access_token"]
print(f"✅ Got token\n")

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# Test Smart AI Chat
print("=" * 70)
print("TEST: Smart AI Assistant")
print("=" * 70)

print("\n1. Testing /api/v1/ai/smart-chat endpoint...")
test_message = "What can you help me with?"

response = requests.post(
    f"{API_URL}/api/v1/ai/smart-chat",
    headers=headers,
    json={
        "message": test_message,
        "include_context": True
    }
)

print(f"   Status Code: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print(f"   ✅ SUCCESS")
    print(f"\n   User: {test_message}")
    print(f"   AI: {data.get('response', 'No response')[:200]}")
    if data.get('context_used'):
        print(f"   Context Used: {data.get('context_count', 0)} items")
elif response.status_code == 500:
    print(f"   ❌ ERROR 500 - Internal Server Error")
    try:
        error_data = response.json()
        print(f"   Error: {error_data.get('detail', 'Unknown error')}")
    except:
        print(f"   Error: {response.text[:200]}")
elif response.status_code == 404:
    print(f"   ❌ ERROR 404 - Endpoint not found")
else:
    print(f"   ❌ ERROR {response.status_code}")
    print(f"   Response: {response.text[:200]}")

# Test memory stats
print("\n2. Testing /api/v1/ai/memory-stats endpoint...")
memory_response = requests.get(
    f"{API_URL}/api/v1/ai/memory-stats",
    headers=headers
)

print(f"   Status Code: {memory_response.status_code}")
if memory_response.status_code == 200:
    print(f"   ✅ Memory stats loaded")
    memory_data = memory_response.json()
    print(f"   Total conversations: {memory_data.get('total_conversations', 0)}")
else:
    print(f"   ❌ Failed to load memory stats")

print("\n" + "=" * 70)
print("DIAGNOSIS")
print("=" * 70)

if response.status_code == 200:
    print("✅ Smart AI Assistant is WORKING")
    print("\nThe Smart AI Chat feature is functional and responding")
else:
    print("❌ Smart AI Assistant is NOT WORKING")
    print(f"\nError: HTTP {response.status_code}")
    print("Possible issues:")
    print("  1. OpenAI API key not configured")
    print("  2. Backend AI service error")
    print("  3. Database connection issue")
    print("  4. Missing environment variables")
