#!/usr/bin/env python3
"""
Connect Recall.ai via API endpoint
"""
import requests
import json

# Configuration
BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"
# Use the demo token from earlier tests
AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZW1vQGV4YW1wbGUuY29tIiwiZXhwIjoxNzYyNzM4NDI0fQ.tVE9h1OpPxWF0ELj2-nwFkS1UiT5ILrctE7SRZ6wd5I"
API_KEY = "2710d1a040a03295045e0ad6bb2535997da8acd0"

def connect_recallai():
    """Connect Recall.ai using the API endpoint"""
    print("Connecting Recall.ai via API...")

    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "api_key": API_KEY
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/v1/recallai/connect",
            headers=headers,
            json=payload
        )

        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        if response.status_code == 200:
            print("\n✅ Recall.ai connected successfully!")
            return True
        else:
            print(f"\n❌ Failed to connect Recall.ai")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def check_status():
    """Check Recall.ai connection status"""
    print("\nChecking Recall.ai status...")

    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }

    try:
        response = requests.get(
            f"{BACKEND_URL}/api/v1/recallai/status",
            headers=headers
        )

        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        if response.status_code == 200:
            print("\n✅ Status check successful!")
            return True
        else:
            print(f"\n❌ Status check failed")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 70)
    print("Recall.ai API Connection Script")
    print("=" * 70)

    # Connect Recall.ai
    connected = connect_recallai()

    if connected:
        # Check status
        check_status()

        print("\n" + "=" * 70)
        print("Setup Complete!")
        print("=" * 70)
        print("\nRecall.ai is now connected to your CRM.")
        print("\nTo configure webhooks in Recall.ai dashboard:")
        print("1. Go to https://app.recall.ai/settings/webhooks")
        print("2. Add webhook URL:")
        print(f"   {BACKEND_URL}/api/v1/recallai/webhook")
        print("3. Use webhook secret:")
        print("   whsec_suIiYYXb7fgjFjOtVWT0spOfalxNKtldS/MI13wAGV3thi5JbpPjpCUYU2Y0BcxN")
        print("\n" + "=" * 70)
        print("Testing Instructions:")
        print("=" * 70)
        print("1. Open the frontend: http://localhost:3000")
        print("2. Navigate to any lead profile")
        print("3. Click the 'Start Recording' button")
        print("4. Paste a meeting URL (e.g., Zoom link)")
        print("5. The bot will join the meeting")
        print("6. After the meeting ends, the transcript will appear in Conversation Log")
        print("=" * 70)

    else:
        print("\n⚠️  Connection failed. You can manually connect in the UI:")
        print("1. Go to Settings → Integrations")
        print("2. Click 'Connect Recall.ai'")
        print(f"3. Paste API key: {API_KEY}")
