#!/usr/bin/env python3
"""
Microsoft Graph Webhook Subscription Manager
=============================================
Register, list, renew, and delete Graph webhook subscriptions.
Supports all subscription kinds: calendar, email, teams_chats, call_records.

Usage:
    python scripts/register_graph_webhook.py list
    python scripts/register_graph_webhook.py create --kind call_records
    python scripts/register_graph_webhook.py create --kind email --user-email user@org.com
    python scripts/register_graph_webhook.py renew -s <subscription-id>
    python scripts/register_graph_webhook.py delete -s <subscription-id>
    python scripts/register_graph_webhook.py setup-calls
    python scripts/register_graph_webhook.py test-lightbox --api-token <jwt>

Environment Variables:
    MS_TENANT_ID        - Azure AD tenant ID (or MICROSOFT_TENANT_ID)
    MS_CLIENT_ID        - Azure App client ID (or MICROSOFT_CLIENT_ID)
    MS_CLIENT_SECRET    - Azure App client secret (or MICROSOFT_CLIENT_SECRET)
    MS_WEBHOOK_CLIENT_STATE - HMAC secret for Graph notification verification
    MS_WEBHOOK_BASE_URL - Webhook base URL (default: https://api.perenniaai.com/api/v1/microsoft/webhooks)
    TEAMS_WEBHOOK_SECRET - Secret for direct Teams call webhook (Power Automate path)
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

API_BASE = os.getenv("API_BASE_URL", "https://api.perenniaai.com")

SUBSCRIPTION_KINDS = {
    "calendar": {
        "resource": "/me/events",
        "change_type": "created,updated,deleted",
        "max_minutes": 4230,
        "permission": "Calendars.Read (delegated)",
        "flow": "delegated",
    },
    "email": {
        "resource": "/me/messages",
        "change_type": "created,updated",
        "max_minutes": 4230,
        "permission": "Mail.Read (delegated)",
        "flow": "delegated",
    },
    "teams_chats": {
        "resource": "/me/chats/getAllMessages",
        "change_type": "created",
        "max_minutes": 4230,
        "permission": "Chat.Read (delegated)",
        "flow": "delegated",
    },
    "call_records": {
        "resource": "/communications/callRecords",
        "change_type": "created",
        "max_minutes": 4230,
        "permission": "CallRecords.Read.All (application)",
        "flow": "application",
    },
}


def _env(name: str, *fallbacks: str) -> str:
    for key in (name, *fallbacks):
        val = os.getenv(key, "").strip()
        if val:
            return val
    return ""


def get_config():
    return {
        "tenant_id": _env("MS_TENANT_ID", "MICROSOFT_TENANT_ID"),
        "client_id": _env("MS_CLIENT_ID", "MICROSOFT_CLIENT_ID"),
        "client_secret": _env("MS_CLIENT_SECRET", "MICROSOFT_CLIENT_SECRET"),
        "webhook_base_url": _env("MS_WEBHOOK_BASE_URL") or "https://api.perenniaai.com/api/v1/microsoft/webhooks",
        "webhook_client_state": _env("MS_WEBHOOK_CLIENT_STATE"),
        "teams_webhook_secret": _env("TEAMS_WEBHOOK_SECRET"),
    }


def get_app_token(cfg: dict) -> str | None:
    if not all([cfg["tenant_id"], cfg["client_id"], cfg["client_secret"]]):
        print("ERROR: Missing credentials. Set MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET")
        return None

    resp = requests.post(
        GRAPH_TOKEN_URL.format(tenant=cfg["tenant_id"]),
        data={
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if resp.status_code == 200:
        return resp.json()["access_token"]

    print(f"ERROR: Token request failed ({resp.status_code}): {resp.text}")
    return None


def _graph_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _client_state_for(account_id: int, kind: str, secret: str) -> str:
    raw = f"{account_id}:{kind}:{secret}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Commands ─────────────────────────────────────────────────────────────

def cmd_list(token: str):
    print("\n=== Existing Graph Subscriptions ===")
    resp = requests.get(f"{GRAPH_BASE}/subscriptions", headers=_graph_headers(token))

    if resp.status_code != 200:
        print(f"  ERROR ({resp.status_code}): {resp.text}")
        return []

    subs = resp.json().get("value", [])
    if not subs:
        print("  (none)")
        return subs

    for s in subs:
        expires = s.get("expirationDateTime", "?")
        print(f"  {s['id']}")
        print(f"    resource:  {s.get('resource')}")
        print(f"    changeType: {s.get('changeType')}")
        print(f"    notifyUrl: {s.get('notificationUrl')}")
        print(f"    expires:   {expires}")
        print()

    return subs


def cmd_create(token: str, cfg: dict, kind: str, user_email: str | None = None):
    if kind not in SUBSCRIPTION_KINDS:
        print(f"ERROR: Unknown kind '{kind}'. Choose from: {', '.join(SUBSCRIPTION_KINDS)}")
        return None

    spec = SUBSCRIPTION_KINDS[kind]
    notification_url = f"{cfg['webhook_base_url']}/{kind}"
    expiration = datetime.now(timezone.utc) + timedelta(minutes=spec["max_minutes"])

    resource = spec["resource"]
    if user_email and spec["flow"] == "delegated":
        resource = resource.replace("/me/", f"/users/{user_email}/")

    client_state = cfg["webhook_client_state"] or ""

    payload = {
        "changeType": spec["change_type"],
        "notificationUrl": notification_url,
        "resource": resource,
        "expirationDateTime": expiration.isoformat().replace("+00:00", "Z"),
        "clientState": client_state,
        "latestSupportedTlsVersion": "v1_2",
    }

    print(f"\n=== Creating '{kind}' Subscription ===")
    print(f"  resource:    {resource}")
    print(f"  changeType:  {spec['change_type']}")
    print(f"  notifyUrl:   {notification_url}")
    print(f"  expires:     {expiration.isoformat()}")
    print(f"  permission:  {spec['permission']}")
    print(f"  flow:        {spec['flow']}")

    resp = requests.post(
        f"{GRAPH_BASE}/subscriptions",
        headers=_graph_headers(token),
        json=payload,
    )

    if resp.status_code == 201:
        sub = resp.json()
        print(f"\n  OK — subscription created")
        print(f"  id: {sub['id']}")
        print(f"  expires: {sub.get('expirationDateTime')}")
        return sub

    print(f"\n  FAILED ({resp.status_code})")
    error = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    code = error.get("error", {}).get("code", "")
    msg = error.get("error", {}).get("message", resp.text)
    print(f"  code: {code}")
    print(f"  message: {msg}")

    if "Authorization_RequestDenied" in code or "Forbidden" in msg:
        print(f"\n  FIX: Grant '{spec['permission']}' in Azure Portal:")
        print(f"    portal.azure.com > App Registrations > your app > API Permissions")
        print(f"    Add Permission > Microsoft Graph > Application > {spec['permission'].split(' ')[0]}")
        print(f"    Then click 'Grant admin consent'")

    if "InvalidRequest" in code and "notificationUrl" in msg.lower():
        print(f"\n  FIX: Your webhook URL must be publicly reachable and respond to")
        print(f"  Graph's validation handshake (GET with validationToken query param).")
        print(f"  Make sure the backend is deployed and the route is registered.")

    return None


def cmd_renew(token: str, subscription_id: str):
    expiration = datetime.now(timezone.utc) + timedelta(days=2, hours=23)

    print(f"\n=== Renewing Subscription ===")
    print(f"  id: {subscription_id}")

    resp = requests.patch(
        f"{GRAPH_BASE}/subscriptions/{subscription_id}",
        headers=_graph_headers(token),
        json={"expirationDateTime": expiration.isoformat().replace("+00:00", "Z")},
    )

    if resp.status_code == 200:
        print(f"  OK — expires {resp.json().get('expirationDateTime')}")
        return resp.json()

    print(f"  FAILED ({resp.status_code}): {resp.text}")
    return None


def cmd_delete(token: str, subscription_id: str):
    print(f"\n=== Deleting Subscription ===")
    print(f"  id: {subscription_id}")

    resp = requests.delete(
        f"{GRAPH_BASE}/subscriptions/{subscription_id}",
        headers=_graph_headers(token),
    )

    if resp.status_code == 204:
        print("  OK — deleted")
        return True

    print(f"  FAILED ({resp.status_code}): {resp.text}")
    return False


def cmd_check_permissions(token: str):
    print("\n=== Checking Application Permissions ===")

    test_resources = {
        "CallRecords.Read.All": "/communications/callRecords?$top=1",
        "User.Read.All": "/users?$top=1",
    }

    for perm, endpoint in test_resources.items():
        resp = requests.get(f"{GRAPH_BASE}{endpoint}", headers=_graph_headers(token))
        status = "granted" if resp.status_code == 200 else f"MISSING ({resp.status_code})"
        print(f"  {perm}: {status}")


def cmd_setup_calls(token: str, cfg: dict):
    print("=" * 60)
    print("Teams Call Record Subscription Setup")
    print("=" * 60)

    # Step 1: Check permissions
    cmd_check_permissions(token)

    # Step 2: Check for existing call_records subscription
    print("\n--- Checking existing subscriptions ---")
    subs = cmd_list(token)
    call_subs = [s for s in subs if "callRecords" in s.get("resource", "")]

    if call_subs:
        print(f"  Found {len(call_subs)} existing callRecords subscription(s)")
        for s in call_subs:
            print(f"    {s['id']} — expires {s.get('expirationDateTime')}")
        print("\n  To replace, delete the old one first:")
        print(f"    python scripts/register_graph_webhook.py delete -s {call_subs[0]['id']}")
        renew = input("\n  Renew existing subscription? [y/N]: ").strip().lower()
        if renew == "y":
            cmd_renew(token, call_subs[0]["id"])
            return
        return

    # Step 3: Create call_records subscription
    print("\n--- Creating callRecords subscription ---")
    sub = cmd_create(token, cfg, "call_records")

    if sub:
        print("\n--- Setup Complete ---")
        print(f"  Graph subscription ID: {sub['id']}")
        print(f"  Webhook URL: {cfg['webhook_base_url']}/call_records")
        print(f"  Expires: {sub.get('expirationDateTime')}")
        print()
        print("  IMPORTANT: This subscription expires in ~2.9 days.")
        print("  The backend auto-renews via the scheduled renewal task,")
        print("  but you need to also save it to the DB. Hit this endpoint:")
        print()
        print("  Next steps:")
        print("    1. Set TEAMS_WEBHOOK_SECRET on Railway (for Power Automate path)")
        print("    2. Test with: python scripts/register_graph_webhook.py test-lightbox --api-token <jwt>")
        print("    3. For real-time ring detection, set up Power Automate flow")
    else:
        print("\n  Setup incomplete — fix the errors above and re-run.")


def cmd_test_lightbox(api_token: str):
    print("\n=== Testing Inbound Call Lightbox ===")
    print(f"  Target: {API_BASE}/api/v1/teams/calls/simulate")

    resp = requests.post(
        f"{API_BASE}/api/v1/teams/calls/simulate",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        json={
            "phone": "+15551234567",
            "name": "Test Caller — Setup Script",
        },
    )

    if resp.status_code == 200:
        data = resp.json()
        print(f"  OK — notification sent")
        print(f"  payload: {json.dumps(data.get('payload', {}), indent=2)}")
        print()
        print("  If the lightbox didn't appear in the browser:")
        print("    1. Make sure you're logged in at app.perenniaai.com")
        print("    2. Open browser DevTools > Console — check for WebSocket errors")
        print("    3. Check Network tab for ws://... connection to /ws/calls/inbound")
    else:
        print(f"  FAILED ({resp.status_code}): {resp.text}")

        if resp.status_code == 401:
            print("\n  FIX: The --api-token must be a valid JWT from the CRM.")
            print("    Get it from browser DevTools > Application > Local Storage > token")

        if resp.status_code == 404:
            print("\n  FIX: The /simulate endpoint isn't deployed yet.")
            print("    Make sure the latest commit is deployed to Railway.")


def cmd_test_webhook(cfg: dict):
    print("\n=== Testing Webhook Endpoint ===")
    url = f"{cfg['webhook_base_url']}/call_records"

    print(f"  Testing validation handshake: {url}?validationToken=test123")
    resp = requests.post(f"{url}?validationToken=test123")

    if resp.status_code == 200 and resp.text == "test123":
        print("  OK — validation handshake works")
    else:
        print(f"  FAILED ({resp.status_code}): {resp.text}")
        print("  The webhook endpoint must echo validationToken as text/plain")


def main():
    parser = argparse.ArgumentParser(
        description="Manage Microsoft Graph webhook subscriptions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full Teams call setup (interactive)
  python scripts/register_graph_webhook.py setup-calls

  # Register call_records subscription
  python scripts/register_graph_webhook.py create --kind call_records

  # Register email subscription for a specific user
  python scripts/register_graph_webhook.py create --kind email --user-email john@company.com

  # List all subscriptions
  python scripts/register_graph_webhook.py list

  # Test the lightbox end-to-end
  python scripts/register_graph_webhook.py test-lightbox --api-token eyJhbG...

  # Test webhook endpoint responds to Graph validation
  python scripts/register_graph_webhook.py test-webhook
""",
    )
    parser.add_argument(
        "action",
        choices=["list", "create", "renew", "delete", "setup-calls", "check-permissions", "test-lightbox", "test-webhook"],
        help="Action to perform",
    )
    parser.add_argument("--kind", "-k", choices=list(SUBSCRIPTION_KINDS.keys()), help="Subscription kind")
    parser.add_argument("--subscription-id", "-s", help="Subscription ID (for renew/delete)")
    parser.add_argument("--user-email", "-u", help="User email (for delegated subscriptions)")
    parser.add_argument("--api-token", "-t", help="CRM JWT token (for test-lightbox)")

    args = parser.parse_args()

    cfg = get_config()

    print("=" * 60)
    print("Microsoft Graph Webhook Manager")
    print("=" * 60)

    # Actions that don't need a Graph token
    if args.action == "test-lightbox":
        if not args.api_token:
            print("ERROR: --api-token required. Get it from browser Local Storage > 'token'")
            sys.exit(1)
        cmd_test_lightbox(args.api_token)
        print("\n" + "=" * 60)
        return

    if args.action == "test-webhook":
        cmd_test_webhook(cfg)
        print("\n" + "=" * 60)
        return

    # All other actions need a Graph token
    token = get_app_token(cfg)
    if not token:
        sys.exit(1)
    print("  App token acquired")

    if args.action == "list":
        cmd_list(token)

    elif args.action == "create":
        if not args.kind:
            print("ERROR: --kind required. Choose from: " + ", ".join(SUBSCRIPTION_KINDS))
            sys.exit(1)
        existing = cmd_list(token)
        notify_url = f"{cfg['webhook_base_url']}/{args.kind}"
        for s in existing:
            if s.get("notificationUrl") == notify_url:
                print(f"\n  Subscription already exists for {notify_url}")
                print(f"  Use 'renew -s {s['id']}' or 'delete -s {s['id']}' first")
                return
        cmd_create(token, cfg, args.kind, args.user_email)

    elif args.action == "renew":
        if not args.subscription_id:
            print("ERROR: --subscription-id required")
            sys.exit(1)
        cmd_renew(token, args.subscription_id)

    elif args.action == "delete":
        if not args.subscription_id:
            print("ERROR: --subscription-id required")
            sys.exit(1)
        cmd_delete(token, args.subscription_id)

    elif args.action == "setup-calls":
        cmd_setup_calls(token, cfg)

    elif args.action == "check-permissions":
        cmd_check_permissions(token)

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
