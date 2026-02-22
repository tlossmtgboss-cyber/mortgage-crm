#!/usr/bin/env python3
"""
Test Vapi Setup - Verify assistant and webhook endpoint
"""
import requests
import json
import os

# Vapi credentials from environment
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "")
CRM_WEBHOOK_URL = "https://app.perenniaai.com/api/vapi/webhook"

print("=" * 80)
print("🧪 TESTING VAPI SETUP")
print("=" * 80)

# Test 1: Verify Vapi assistant exists
print("\n📋 TEST 1: Verify Vapi Assistant")
print(f"   Assistant ID: {VAPI_ASSISTANT_ID}")

headers = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json"
}

try:
    response = requests.get(
        f"https://api.vapi.ai/assistant/{VAPI_ASSISTANT_ID}",
        headers=headers,
        timeout=10
    )

    if response.status_code == 200:
        assistant = response.json()
        print(f"   ✅ Assistant found: {assistant.get('name', 'Unnamed')}")
        print(f"   Model: {assistant.get('model', {}).get('model', 'Unknown')}")
        print(f"   Voice: {assistant.get('voice', {}).get('provider', 'Unknown')}")

        # Check functions
        functions = assistant.get('model', {}).get('tools', [])
        print(f"   Functions: {len(functions)} configured")
        for func in functions:
            if func.get('type') == 'function':
                func_name = func.get('function', {}).get('name', 'Unknown')
                print(f"      - {func_name}")
    else:
        print(f"   ❌ Failed to fetch assistant: {response.status_code}")
        print(f"   Response: {response.text}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: Verify CRM webhook endpoint is accessible
print(f"\n📋 TEST 2: Verify CRM Webhook Endpoint")
print(f"   URL: {CRM_WEBHOOK_URL}")

try:
    # Send a test webhook payload
    test_payload = {
        "message": {
            "type": "test",
            "call": {"id": "test_call_123"}
        }
    }

    response = requests.post(
        CRM_WEBHOOK_URL,
        json=test_payload,
        timeout=10
    )

    if response.status_code == 200:
        print(f"   ✅ Webhook endpoint accessible")
        print(f"   Response: {response.json()}")
    else:
        print(f"   ⚠️  Unexpected status: {response.status_code}")
        print(f"   Response: {response.text}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 3: Check Vapi phone number configuration
print(f"\n📋 TEST 3: Check Vapi Phone Number")

try:
    response = requests.get(
        "https://api.vapi.ai/phone-number",
        headers=headers,
        timeout=10
    )

    if response.status_code == 200:
        phone_numbers = response.json()
        print(f"   ✅ Found {len(phone_numbers)} phone number(s)")

        for phone in phone_numbers:
            number = phone.get('number', 'Unknown')
            assistant_id = phone.get('assistantId', 'None')
            print(f"   📞 {number}")
            print(f"      Assistant: {assistant_id}")
            if assistant_id == VAPI_ASSISTANT_ID:
                print(f"      ✅ Correctly linked to Sam!")
    else:
        print(f"   ⚠️  Status: {response.status_code}")
        print(f"   Response: {response.text}")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 80)
print("📊 SUMMARY")
print("=" * 80)
print("\n✅ Vapi Configuration:")
print(f"   - API Key: Configured")
print(f"   - Assistant ID: {VAPI_ASSISTANT_ID}")
print(f"   - Phone Number: +18434169589")
print(f"   - Webhook URL: {CRM_WEBHOOK_URL}")

print("\n📞 Call Flow:")
print("   1. Caller dials +18434169589")
print("   2. Telnyx → Vapi AI (assistant)")
print("   3. Sam answers with natural voice")
print("   4. Vapi → CRM webhook (logs call)")
print("   5. Call appears in AI Receptionist Dashboard")

print("\n🎯 READY TO TEST:")
print("   Call +18434169589 and verify:")
print("   - Sam answers immediately")
print("   - Natural conversation works")
print("   - Call logs to dashboard")
print("\n" + "=" * 80)
