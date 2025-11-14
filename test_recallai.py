#!/usr/bin/env python3
"""
Test script for Recall.ai integration
"""
import requests
import json

# Recall.ai credentials
API_KEY = "2710d1a040a03295045e0ad6bb2535997da8acd0"
WEBHOOK_SECRET = "whsec_suIiYYXb7fgjFjOtVWT0spOfalxNKtldS/MI13wAGV3thi5JbpPjpCUYU2Y0BcxN"

def test_api_connection():
    """Test if the API key is valid by making a simple request"""
    print("Testing Recall.ai API connection...")

    headers = {
        "Authorization": f"Token {API_KEY}",
        "Content-Type": "application/json"
    }

    # Try to list bots (this should return empty list or existing bots)
    try:
        response = requests.get(
            "https://us-west-2.recall.ai/api/v1/bot/",
            headers=headers
        )

        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        if response.status_code == 200:
            print("✅ API connection successful!")
            return True
        else:
            print("❌ API connection failed!")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def save_credentials_to_env():
    """Save credentials to .env file for backend use"""
    print("\nSaving credentials to backend .env file...")

    env_content = f"""
# Recall.ai Configuration
RECALLAI_WEBHOOK_SECRET={WEBHOOK_SECRET}
"""

    try:
        # Append to existing .env file
        with open('/Users/timothyloss/my-project/mortgage-crm/backend/.env', 'a') as f:
            f.write(env_content)
        print("✅ Credentials saved to backend/.env")
    except Exception as e:
        print(f"⚠️  Could not save to .env: {e}")
        print(f"Please manually add this to backend/.env:")
        print(env_content)

if __name__ == "__main__":
    print("=" * 60)
    print("Recall.ai Integration Test")
    print("=" * 60)

    # Test API connection
    api_works = test_api_connection()

    if api_works:
        # Save credentials
        save_credentials_to_env()

        print("\n" + "=" * 60)
        print("Next Steps:")
        print("=" * 60)
        print("1. Go to Settings → Integrations in the frontend")
        print("2. Click 'Connect Recall.ai'")
        print(f"3. Paste the API key: {API_KEY}")
        print("4. Configure webhook URL in Recall.ai dashboard:")
        print("   https://mortgage-crm-production-7a9a.up.railway.app/api/v1/recallai/webhook")
        print(f"5. Use webhook secret: {WEBHOOK_SECRET}")
        print("\nTo test:")
        print("1. Open any lead profile")
        print("2. Click 'Start Recording'")
        print("3. Paste a Zoom/Teams/Meet URL")
        print("4. The bot will join and transcript will appear in Conversation Log")
        print("=" * 60)
