#!/usr/bin/env python3
import requests

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

print("🏆 Testing Performance Coach Endpoint\n")

# Get token
print("1. Getting authentication token...")
try:
    response = requests.post(
        f"{API_BASE_URL}/token",
        data={"username": "demo@example.com", "password": "demo123"}
    )
    print(f"   Response status: {response.status_code}")
    print(f"   Response: {response.json()}")
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print(f"   ✓ Token obtained")
except Exception as e:
    print(f"   ❌ Error: {e}")
    print(f"   Response text: {response.text if 'response' in locals() else 'No response'}")
    exit(1)

# Test Coach endpoint
print("\n2. Testing Coach endpoint...")
try:
    response = requests.post(
        f"{API_BASE_URL}/api/v1/coach",
        headers=headers,
        json={"mode": "daily_briefing"}
    )
    print(f"   Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"\n   ✅ SUCCESS! Coach is working!")
        print(f"   Mode: {data.get('mode')}")
        print(f"   Response preview: {data.get('response', '')[:100]}...")
    elif response.status_code == 503:
        print(f"\n   ❌ Service Unavailable (503)")
        print(f"   Response: {response.json()}")
        print(f"\n   💡 This means OpenAI API key is not configured on the server")
    else:
        print(f"\n   ❌ Failed with status {response.status_code}")
        print(f"   Response: {response.text[:500]}")

except Exception as e:
    print(f"   ❌ Error: {e}")
