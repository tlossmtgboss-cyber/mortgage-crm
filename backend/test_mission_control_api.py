import requests
import json
import os

API_BASE = "https://app.perenniaai.com"

# SECURITY: Password must be provided via environment variable
USERNAME = os.environ.get("MISSION_CONTROL_USERNAME", "")
PASSWORD = os.environ.get("MISSION_CONTROL_PASSWORD", "")

if not USERNAME or not PASSWORD:
    print("❌ Error: Set MISSION_CONTROL_USERNAME and MISSION_CONTROL_PASSWORD environment variables")
    print("Usage: MISSION_CONTROL_USERNAME='user@example.com' MISSION_CONTROL_PASSWORD='...' python test_mission_control_api.py")
    exit(1)

# Try to get token
print("🔐 Getting authentication token...")
try:
    response = requests.post(
        f"{API_BASE}/token",
        data={"username": USERNAME, "password": PASSWORD}
    )
    
    if response.status_code == 200:
        token = response.json().get("access_token")
        print(f"✅ Token obtained: {token[:20]}...")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test Mission Control endpoints
        print("\n📊 Testing Mission Control endpoints...")
        
        endpoints = [
            "/api/v1/ai/mission-control/health?days=7",
            "/api/v1/ai/mission-control/actions?limit=5",
            "/api/v1/ai/mission-control/metrics?days=7"
        ]
        
        for endpoint in endpoints:
            print(f"\nTesting: {endpoint}")
            r = requests.get(f"{API_BASE}{endpoint}", headers=headers)
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"Response: {json.dumps(data, indent=2)[:200]}...")
            else:
                print(f"Error: {r.text[:200]}")
    else:
        print(f"❌ Authentication failed: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"❌ Error: {e}")
