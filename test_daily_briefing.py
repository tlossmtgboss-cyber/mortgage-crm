#!/usr/bin/env python3
"""Test daily briefing through AI interface"""

import requests
import json

API_URL = "https://api.perenniaai.com/api/v1/ai/process-command"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZW1vQGV4YW1wbGUuY29tIiwiZXhwIjoxNzY0MDE2OTcxfQ.DvKjpG2FOrpR_g8XHZ1ETk7bEFKRaABHW0D25csrdxA"

print("="* 80)
print("Testing Daily Briefing Query")
print("="* 80)

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "message": "Daily Briefing - Get my top 3 priorities for today"
}

print("\nSending request...")
response = requests.post(API_URL, json=payload, headers=headers, timeout=30)

print(f"Status Code: {response.status_code}\n")

try:
    data = response.json()
    print(json.dumps(data, indent=2))

    # Check if we got data back
    if response.status_code == 200:
        print("\n" + "="*80)
        print("✓ SUCCESS: Query executed")
        print("="*80)

        # Show data summary
        if 'data' in data:
            tasks = data['data'].get('tasks', [])
            loans = data['data'].get('follow_ups', [])
            print(f"\nTasks found: {len(tasks)}")
            print(f"Follow-ups found: {len(loans)}")

            if tasks:
                print("\n Sample tasks:")
                for i, task in enumerate(tasks[:5], 1):
                    print(f"  {i}. {task.get('title', 'N/A')}")
        else:
            print("\nNo data field in response")
    else:
        print(f"\n✗ FAILED: {data.get('detail', 'Unknown error')}")

except Exception as e:
    print(f"Error: {e}")
    print(f"Raw response: {response.text[:500]}")
