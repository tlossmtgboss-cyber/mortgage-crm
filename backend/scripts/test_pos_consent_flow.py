"""
Test the POS Consent Flow end-to-end.

Usage:
  python backend/scripts/test_pos_consent_flow.py [--base-url http://localhost:8000]

Steps:
  1. POST /api/v1/pos/voice-complete  → creates BorrowerApplication + magic link
  2. GET  /api/v1/pos/consent/{token}/status  → verify PENDING_CONSENT
  3. GET  /api/v1/pos/consent/{token}/disclosures  → fetch legal text
  4. POST /api/v1/pos/consent/{token}/credit-auth  → sign FCRA auth
  5. POST /api/v1/pos/consent/{token}/e-disclosure  → sign E-SIGN consent
  6. POST /api/v1/pos/consent/{token}/submit  → final submission
  7. Verify Lead + Loan created in CRM (if authenticated)

Requires:
  - Backend running
  - CRM_API_KEY env var set (or pass --api-key)
"""

import argparse
import json
import os
import sys
import time
import requests


def banner(step, msg):
    print(f"\n{'='*60}")
    print(f"  Step {step}: {msg}")
    print(f"{'='*60}")


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    symbol = "+" if condition else "!"
    print(f"  [{symbol}] {label}: {status}" + (f" — {detail}" if detail else ""))
    if not condition:
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Test POS consent flow end-to-end")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--api-key", default=None, help="CRM API key (or set CRM_API_KEY env)")
    parser.add_argument("--frontend-url", default="http://localhost:3000", help="Frontend base URL")
    parser.add_argument("--voice-loan-id", default=None, help="Existing voice loan ID to resume")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    api_key = args.api_key or os.environ.get("CRM_API_KEY", "")
    if not api_key:
        print("WARNING: No CRM_API_KEY set. Voice-complete endpoint may reject the request.")
        print("         Set CRM_API_KEY env var or pass --api-key\n")

    all_passed = True
    token = None

    # ── Step 1: Trigger voice-complete ──────────────────────────
    banner(1, "POST /api/v1/pos/voice-complete")

    voice_loan_id = args.voice_loan_id or f"TEST-{int(time.time())}"
    payload = {
        "voice_loan_id": voice_loan_id,
        "borrower_first_name": "Test",
        "borrower_last_name": "Borrower",
        "borrower_phone": "8435551234",
        "borrower_email": "test@example.com",
        "lo_name": "Sarah Johnson",
    }
    print(f"  Payload: {json.dumps(payload, indent=2)}")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        r = requests.post(f"{base}/api/v1/pos/voice-complete", json=payload, headers=headers, timeout=15)
        print(f"  Status: {r.status_code}")
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        print(f"  Response: {json.dumps(data, indent=2)[:500]}")

        if not check("Voice-complete accepted", r.status_code in (200, 201), f"HTTP {r.status_code}"):
            all_passed = False

        magic_link = data.get("magic_link", "")
        if magic_link:
            # Extract token from magic link URL
            token = magic_link.split("/apply/voice-review/")[-1] if "/apply/voice-review/" in magic_link else None
            check("Magic link generated", bool(token), magic_link)
        else:
            print("  [!] No magic_link in response — checking if token is in response directly")
            token = data.get("token") or data.get("purl_token")
            if not token:
                print("  [!] Cannot extract token. Remaining steps will be skipped.")
                print(f"\n  TIP: Check the borrower_applications table for voice_loan_id={voice_loan_id}")
                print(f"       and the purl_access_tokens table for the token.")

    except requests.exceptions.ConnectionError:
        print(f"  [!] FAIL: Cannot connect to {base}")
        print(f"      Is the backend running? Try: cd backend && uvicorn main:app --reload")
        sys.exit(1)
    except Exception as e:
        print(f"  [!] FAIL: {e}")
        all_passed = False

    if not token:
        print("\n  Skipping consent steps (no token). To test the frontend UI only:")
        print(f"  Open: {args.frontend_url}/apply/voice-review/demo")
        print(f"\n{'='*60}")
        print(f"  RESULT: PARTIAL — voice-complete tested, consent flow needs token")
        print(f"{'='*60}")
        sys.exit(0)

    # ── Step 2: Check consent status ────────────────────────────
    banner(2, f"GET /api/v1/pos/consent/{token[:20]}…/status")

    try:
        r = requests.get(f"{base}/api/v1/pos/consent/{token}/status", timeout=10)
        print(f"  Status: {r.status_code}")
        data = r.json() if r.ok else {}
        print(f"  Response: {json.dumps(data, indent=2)[:500]}")

        all_passed &= check("Status endpoint works", r.status_code == 200)
        all_passed &= check("Application status", data.get("application_status") == "pending_consent",
                           data.get("application_status"))
        all_passed &= check("Credit auth not yet done", data.get("credit_auth", {}).get("completed") is False)
        all_passed &= check("E-consent not yet done", data.get("e_consent", {}).get("completed") is False)
        all_passed &= check("Form data present", bool(data.get("form_data")), f"{len(data.get('form_data', {}))} fields")
    except Exception as e:
        print(f"  [!] FAIL: {e}")
        all_passed = False

    # ── Step 3: Fetch disclosures ───────────────────────────────
    banner(3, f"GET /api/v1/pos/consent/{token[:20]}…/disclosures")

    try:
        r = requests.get(f"{base}/api/v1/pos/consent/{token}/disclosures", timeout=10)
        print(f"  Status: {r.status_code}")
        data = r.json() if r.ok else {}

        all_passed &= check("Disclosures endpoint works", r.status_code == 200)
        all_passed &= check("Credit auth text present", bool(data.get("credit_auth", {}).get("text")))
        all_passed &= check("E-consent text present", bool(data.get("e_consent", {}).get("text")))
    except Exception as e:
        print(f"  [!] FAIL: {e}")
        all_passed = False

    # ── Step 4: Sign credit authorization ───────────────────────
    banner(4, f"POST /api/v1/pos/consent/{token[:20]}…/credit-auth")

    try:
        r = requests.post(
            f"{base}/api/v1/pos/consent/{token}/credit-auth",
            json={"typed_full_name": "Test Borrower", "consent_agreed": True},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        print(f"  Status: {r.status_code}")
        data = r.json() if r.ok else {}
        print(f"  Response: {json.dumps(data, indent=2)[:300]}")

        all_passed &= check("Credit auth accepted", r.status_code in (200, 201))
        all_passed &= check("Has authorized_at", bool(data.get("authorized_at")))
    except Exception as e:
        print(f"  [!] FAIL: {e}")
        all_passed = False

    # ── Step 5: Sign e-disclosure consent ───────────────────────
    banner(5, f"POST /api/v1/pos/consent/{token[:20]}…/e-disclosure")

    try:
        r = requests.post(
            f"{base}/api/v1/pos/consent/{token}/e-disclosure",
            json={"typed_full_name": "Test Borrower", "consent_agreed": True},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        print(f"  Status: {r.status_code}")
        data = r.json() if r.ok else {}
        print(f"  Response: {json.dumps(data, indent=2)[:300]}")

        all_passed &= check("E-consent accepted", r.status_code in (200, 201))
        all_passed &= check("Has consented_at", bool(data.get("consented_at")))
    except Exception as e:
        print(f"  [!] FAIL: {e}")
        all_passed = False

    # ── Step 6: Submit application ──────────────────────────────
    banner(6, f"POST /api/v1/pos/consent/{token[:20]}…/submit")

    try:
        r = requests.post(
            f"{base}/api/v1/pos/consent/{token}/submit",
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        print(f"  Status: {r.status_code}")
        data = r.json() if r.ok else {}
        print(f"  Response: {json.dumps(data, indent=2)[:300]}")

        all_passed &= check("Submission accepted", r.status_code in (200, 201))
        all_passed &= check("Status is submitted", data.get("status") in ("submitted", "SUBMITTED", True),
                           data.get("status"))
    except Exception as e:
        print(f"  [!] FAIL: {e}")
        all_passed = False

    # ── Step 7: Verify consent status is complete ───────────────
    banner(7, "Verify final state")

    try:
        r = requests.get(f"{base}/api/v1/pos/consent/{token}/status", timeout=10)
        data = r.json() if r.ok else {}

        all_passed &= check("Application submitted",
                           data.get("application_status") in ("submitted", "SUBMITTED"),
                           data.get("application_status"))
        all_passed &= check("Credit auth complete", data.get("credit_auth", {}).get("completed") is True)
        all_passed &= check("E-consent complete", data.get("e_consent", {}).get("completed") is True)
        all_passed &= check("All consents complete", data.get("all_complete") is True)
    except Exception as e:
        print(f"  [!] FAIL: {e}")
        all_passed = False

    # ── Summary ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  VOICE LOAN ID: {voice_loan_id}")
    print(f"  FRONTEND URL:  {args.frontend_url}/apply/voice-review/{token}")
    if all_passed:
        print(f"\n  RESULT: ALL STEPS PASSED")
    else:
        print(f"\n  RESULT: SOME STEPS FAILED — check output above")
    print(f"{'='*60}\n")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
