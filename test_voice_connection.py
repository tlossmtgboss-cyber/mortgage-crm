#!/usr/bin/env python3
"""Test if voice AI can actually connect to OpenAI Realtime API"""
import asyncio
import websockets
import json
import os
import subprocess

print("=" * 70)
print("TESTING OPENAI REALTIME API CONNECTION")
print("=" * 70)

# Get OpenAI API key from Railway
print("\n1. Getting OpenAI API key...")
result = subprocess.run(
    ['railway', 'variables', '--json'],
    capture_output=True,
    text=True
)
vars_data = json.loads(result.stdout)
openai_key = vars_data.get('OPENAI_API_KEY')

if not openai_key:
    print("❌ No OpenAI API key found")
    exit(1)

print(f"   ✅ Got API key: ...{openai_key[-10:]}")

async def test_openai_realtime():
    """Test WebSocket connection to OpenAI Realtime API"""
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"

    headers = {
        "Authorization": f"Bearer {openai_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    print("\n2. Connecting to OpenAI Realtime API...")
    print(f"   URL: {url}")

    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            print("   ✅ WebSocket connected!")

            # Send session update
            print("\n3. Configuring session...")
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": "You are Sam, a friendly AI receptionist.",
                    "voice": "alloy",
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16"
                }
            }))
            print("   ✅ Session configured")

            # Wait for response
            print("\n4. Waiting for confirmation...")
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(response)
            print(f"   ✅ Got response: {data.get('type')}")

            print("\n" + "=" * 70)
            print("✅ SUCCESS - OpenAI Realtime API is working!")
            print("=" * 70)
            print("""
The AI can connect to OpenAI successfully.

If calls still aren't working, the issue is likely:
1. WebSocket endpoint on Railway not accessible from Twilio
2. Railway blocking WebSocket connections
3. OpenAI API key not accessible from WebSocket handler

Let me check the Railway deployment...
""")

    except websockets.exceptions.InvalidStatusCode as e:
        print(f"\n   ❌ Connection failed: {e}")
        print(f"   Status: {e.status_code}")
        if e.status_code == 401:
            print("   Issue: Invalid API key or authentication failed")
        elif e.status_code == 403:
            print("   Issue: Access denied - check API key permissions")
    except asyncio.TimeoutError:
        print("\n   ❌ Timeout - OpenAI didn't respond")
    except Exception as e:
        print(f"\n   ❌ Error: {e}")

# Run the test
asyncio.run(test_openai_realtime())
