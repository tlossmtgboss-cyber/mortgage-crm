import requests
import json

# Test Smart AI Chat endpoint
API_BASE = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get token first
print("🔐 Getting authentication token...")
auth_response = requests.post(
    f"{API_BASE}/token",
    data={"username": "demo@example.com", "password": "demo"}
)

if auth_response.status_code == 200:
    token = auth_response.json().get("access_token")
    print(f"✅ Token obtained")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test Smart AI Chat
    print("\n📨 Testing Smart AI Chat...")
    chat_response = requests.post(
        f"{API_BASE}/api/v1/ai/smart-chat",
        headers=headers,
        json={
            "message": "What is this lead about?",
            "lead_id": 1,
            "include_context": True
        }
    )
    
    print(f"Status: {chat_response.status_code}")
    print(f"Response: {json.dumps(chat_response.json(), indent=2)[:500]}")
    
else:
    print(f"❌ Auth failed: {auth_response.status_code}")
    print(f"Response: {auth_response.text}")
