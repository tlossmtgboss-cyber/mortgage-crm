#!/usr/bin/env python3
"""Test if WebSocket endpoint is accessible from outside"""
import asyncio
import websockets

async def test_websocket():
    url = "wss://api.perenniaai.com/api/v1/voice/ws/voice-stream"

    print("=" * 70)
    print("TESTING WEBSOCKET ENDPOINT")
    print("=" * 70)
    print(f"\nURL: {url}")
    print("Attempting to connect...")

    try:
        async with websockets.connect(url, timeout=10) as ws:
            print("✅ WebSocket connected successfully!")
            print("Endpoint is accessible from outside.")

            # Try to send a test message
            test_msg = '{"event": "ping"}'
            await ws.send(test_msg)
            print(f"Sent test message: {test_msg}")

            # Wait for response
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=3)
                print(f"Received response: {response[:100]}...")
            except asyncio.TimeoutError:
                print("No response received (timeout)")

    except websockets.exceptions.InvalidStatusCode as e:
        print(f"❌ WebSocket connection failed!")
        print(f"Status Code: {e.status_code}")
        if e.status_code == 404:
            print("Issue: Endpoint not found (404)")
        elif e.status_code == 403:
            print("Issue: Access denied (403)")
        elif e.status_code == 502:
            print("Issue: Bad Gateway - Railway may not support WebSockets")
    except asyncio.TimeoutError:
        print("❌ Connection timeout")
        print("Issue: WebSocket endpoint not responding")
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"Type: {type(e).__name__}")

asyncio.run(test_websocket())

print("\n" + "=" * 70)
print("DIAGNOSIS")
print("=" * 70)
print("""
If connection FAILED:
- Railway may not support WebSocket connections on your plan
- OR WebSocket endpoint is not properly configured
- This is why calls hang up immediately

SOLUTION:
We need to use a different approach that doesn't require WebSockets.
Option 1: Use Twilio's <Say> with OpenAI text-to-speech
Option 2: Use Twilio's <Gather> for speech recognition
Option 3: Use a third-party service that handles the WebSocket (like Vapi.ai)

Let me know and I'll implement the working solution.
""")
