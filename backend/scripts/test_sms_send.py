#!/usr/bin/env python3
"""
Diagnostic: test SMS through the full application code path.
Simulates what the backend does when the frontend calls POST /api/v1/sms/send.
"""
import os
import sys
import re

# Ensure backend is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TO_PHONE = "(843) 834-4997"  # Raw format from frontend
MESSAGE = "Perennia AI SMS test — please ignore. Reply STOP to opt out."

print("=" * 60)
print("STEP 1: Phone Normalization (_to_e164)")
print("=" * 60)

from integrations.sms_service import _to_e164

normalized = _to_e164(TO_PHONE)
print(f"  Input:      '{TO_PHONE}'")
print(f"  Normalized: '{normalized}'")
if not normalized:
    print("  ❌ FAILED — would be rejected as invalid phone")
    sys.exit(1)
print("  ✅ OK")

print(f"\n{'=' * 60}")
print("STEP 2: Telnyx Credentials")
print("=" * 60)

api_key = os.getenv("TELNYX_API_KEY", "")
from_number = os.getenv("TELNYX_PHONE_NUMBER", "")
profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

print(f"  API key set: {bool(api_key)} (len={len(api_key)})")
print(f"  From:        {from_number}")
print(f"  Profile:     {profile_id}")

if not api_key or not from_number:
    print("  ❌ Missing credentials")
    sys.exit(1)
print("  ✅ OK")

print(f"\n{'=' * 60}")
print("STEP 3: Compliance Gate (standalone, no DB)")
print("=" * 60)

from integrations.sms_compliance_gate import _normalize_phone, _is_quiet_hours, _scan_message_content

gate_phone = _normalize_phone(TO_PHONE)
print(f"  Gate normalizes to: {gate_phone}")

content_issue = _scan_message_content(MESSAGE)
print(f"  Content scan: {'❌ ' + content_issue if content_issue else '✅ clean'}")

quiet = _is_quiet_hours("America/New_York")
print(f"  Quiet hours (ET): {'❌ YES — would block' if quiet else '✅ NO'}")

print(f"\n{'=' * 60}")
print("STEP 4: Direct Telnyx API Send")
print("=" * 60)

import requests

payload = {
    "from": from_number.strip(),
    "to": normalized,
    "text": MESSAGE,
    "messaging_profile_id": profile_id.strip(),
}
print(f"  Sending to {normalized} from {from_number}...")

try:
    response = requests.post(
        "https://api.telnyx.com/v2/messages",
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )
    print(f"  HTTP {response.status_code}")

    if response.status_code in (200, 201, 202):
        data = response.json()
        msg_id = data.get("data", {}).get("id")
        print(f"  ✅ SMS SENT — Message ID: {msg_id}")
    else:
        print(f"  ❌ Telnyx error: {response.text[:300]}")
except Exception as e:
    print(f"  ❌ Request failed: {e}")
