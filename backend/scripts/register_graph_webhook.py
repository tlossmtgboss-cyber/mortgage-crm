#!/usr/bin/env python3
"""
Microsoft Graph Webhook Registration Script
============================================
This script registers a webhook subscription with Microsoft Graph API
to receive real-time email notifications.

Usage:
    python scripts/register_graph_webhook.py

Environment Variables Required:
    MICROSOFT_CLIENT_ID - Azure App client ID
    MICROSOFT_CLIENT_SECRET - Azure App client secret
    MICROSOFT_TENANT_ID - Azure AD tenant ID
    GRAPH_WEBHOOK_URL - Public URL for webhook endpoint (e.g., https://yourdomain.com/api/webhooks/graph)
    GRAPH_WEBHOOK_SECRET - Secret for webhook validation (uses WEBHOOK_SECRET as fallback)

The subscription will monitor the inbox for new emails and send notifications
to the configured webhook URL.
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_access_token():
    """Get an access token from Microsoft Graph API."""
    tenant_id = os.getenv("MICROSOFT_TENANT_ID")
    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")

    if not all([tenant_id, client_id, client_secret]):
        print("ERROR: Missing Microsoft Graph credentials")
        print("  Required: MICROSOFT_TENANT_ID, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET")
        return None

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    response = requests.post(
        token_url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        print(f"ERROR: Failed to get access token: {response.text}")
        return None


def list_subscriptions(access_token):
    """List existing webhook subscriptions."""
    print("\n=== Existing Subscriptions ===")

    response = requests.get(
        "https://graph.microsoft.com/v1.0/subscriptions",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )

    if response.status_code == 200:
        subscriptions = response.json().get("value", [])
        if subscriptions:
            for sub in subscriptions:
                print(f"  ID: {sub.get('id')}")
                print(f"  Resource: {sub.get('resource')}")
                print(f"  Expires: {sub.get('expirationDateTime')}")
                print(f"  URL: {sub.get('notificationUrl')}")
                print()
        else:
            print("  No existing subscriptions found")
        return subscriptions
    else:
        print(f"  ERROR: Failed to list subscriptions: {response.text}")
        return []


def create_subscription(access_token, user_email=None):
    """Create a new webhook subscription for email notifications."""
    webhook_url = os.getenv("GRAPH_WEBHOOK_URL")
    webhook_secret = os.getenv("GRAPH_WEBHOOK_SECRET", os.getenv("WEBHOOK_SECRET"))

    if not webhook_url:
        print("ERROR: GRAPH_WEBHOOK_URL not configured")
        print("  Set the public URL for your webhook endpoint")
        print("  Example: https://your-app.railway.app/api/webhooks/graph")
        return None

    # Subscription expires in 3 days (max for mail is 4230 minutes = ~2.9 days)
    expiration = (datetime.now(timezone.utc) + timedelta(days=2, hours=23)).isoformat() + "Z"

    # Resource path - either for specific user or /me
    if user_email:
        resource = f"users/{user_email}/mailFolders/inbox/messages"
    else:
        resource = "me/mailFolders/inbox/messages"

    subscription_data = {
        "changeType": "created",
        "notificationUrl": webhook_url,
        "resource": resource,
        "expirationDateTime": expiration,
        "clientState": webhook_secret or "",
    }

    print(f"\n=== Creating Subscription ===")
    print(f"  Resource: {resource}")
    print(f"  Notification URL: {webhook_url}")
    print(f"  Expires: {expiration}")

    response = requests.post(
        "https://graph.microsoft.com/v1.0/subscriptions",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=subscription_data,
    )

    if response.status_code == 201:
        subscription = response.json()
        print(f"\n✓ Subscription created successfully!")
        print(f"  Subscription ID: {subscription.get('id')}")
        print(f"  Resource: {subscription.get('resource')}")
        print(f"  Expires: {subscription.get('expirationDateTime')}")
        return subscription
    else:
        print(f"\n✗ Failed to create subscription")
        print(f"  Status: {response.status_code}")
        print(f"  Error: {response.text}")
        return None


def renew_subscription(access_token, subscription_id):
    """Renew an existing subscription."""
    # Extend by 3 days
    expiration = (datetime.now(timezone.utc) + timedelta(days=2, hours=23)).isoformat() + "Z"

    print(f"\n=== Renewing Subscription ===")
    print(f"  Subscription ID: {subscription_id}")
    print(f"  New Expiration: {expiration}")

    response = requests.patch(
        f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"expirationDateTime": expiration},
    )

    if response.status_code == 200:
        subscription = response.json()
        print(f"\n✓ Subscription renewed successfully!")
        print(f"  New Expiration: {subscription.get('expirationDateTime')}")
        return subscription
    else:
        print(f"\n✗ Failed to renew subscription")
        print(f"  Status: {response.status_code}")
        print(f"  Error: {response.text}")
        return None


def delete_subscription(access_token, subscription_id):
    """Delete a subscription."""
    print(f"\n=== Deleting Subscription ===")
    print(f"  Subscription ID: {subscription_id}")

    response = requests.delete(
        f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )

    if response.status_code == 204:
        print(f"\n✓ Subscription deleted successfully!")
        return True
    else:
        print(f"\n✗ Failed to delete subscription")
        print(f"  Status: {response.status_code}")
        print(f"  Error: {response.text}")
        return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage Microsoft Graph webhook subscriptions")
    parser.add_argument("action", choices=["list", "create", "renew", "delete"],
                        help="Action to perform")
    parser.add_argument("--subscription-id", "-s", help="Subscription ID for renew/delete")
    parser.add_argument("--user-email", "-u", help="User email to monitor (optional)")

    args = parser.parse_args()

    print("=" * 60)
    print("Microsoft Graph Webhook Subscription Manager")
    print("=" * 60)

    # Get access token
    access_token = get_access_token()
    if not access_token:
        sys.exit(1)

    print("✓ Access token obtained")

    # Perform action
    if args.action == "list":
        list_subscriptions(access_token)

    elif args.action == "create":
        # First check existing subscriptions
        existing = list_subscriptions(access_token)

        # Check if we already have a subscription for this resource
        webhook_url = os.getenv("GRAPH_WEBHOOK_URL")
        for sub in existing:
            if sub.get("notificationUrl") == webhook_url:
                print(f"\n⚠ Subscription already exists for this URL")
                print(f"  Use 'renew' to extend it, or 'delete' to remove it")
                return

        create_subscription(access_token, args.user_email)

    elif args.action == "renew":
        if not args.subscription_id:
            print("ERROR: --subscription-id required for renew")
            sys.exit(1)
        renew_subscription(access_token, args.subscription_id)

    elif args.action == "delete":
        if not args.subscription_id:
            print("ERROR: --subscription-id required for delete")
            sys.exit(1)
        delete_subscription(access_token, args.subscription_id)

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
