#!/usr/bin/env python3
"""
API Key Rotation Helper

This script helps you rotate compromised API keys by:
1. Listing all keys that need rotation
2. Providing links to each service's key management page
3. Generating new secure values where applicable
4. Creating a new .env file with placeholders

IMPORTANT: API keys in your .env file were exposed. You MUST:
1. Rotate ALL keys listed below
2. Update them in Railway environment variables (not .env for production)
3. Never commit .env files with real credentials

Run: python scripts/rotate_api_keys.py
"""

import secrets
import os
from datetime import datetime

# Keys that need rotation and their management URLs
KEYS_TO_ROTATE = [
    {
        "name": "SECRET_KEY",
        "description": "JWT signing key - generate new one",
        "url": None,
        "can_generate": True,
        "generate_func": lambda: secrets.token_hex(32),
    },
    {
        "name": "DATA_ENCRYPTION_KEY",
        "description": "Field-level encryption key (Fernet) - generate new one",
        "url": None,
        "can_generate": True,
        "generate_func": lambda: __import__('cryptography.fernet', fromlist=['Fernet']).Fernet.generate_key().decode(),
    },
    {
        "name": "OPENAI_API_KEY",
        "description": "OpenAI API key",
        "url": "https://platform.openai.com/api-keys",
        "can_generate": False,
    },
    {
        "name": "ANTHROPIC_API_KEY",
        "description": "Anthropic Claude API key",
        "url": "https://console.anthropic.com/settings/keys",
        "can_generate": False,
    },
    {
        "name": "MICROSOFT_CLIENT_SECRET",
        "description": "Microsoft OAuth client secret",
        "url": "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
        "can_generate": False,
    },
    {
        "name": "SENDGRID_API_KEY",
        "description": "SendGrid email API key",
        "url": "https://app.sendgrid.com/settings/api_keys",
        "can_generate": False,
    },
    {
        "name": "TELNYX_API_KEY",
        "description": "Telnyx API key",
        "url": "https://portal.telnyx.com/#/app/api-keys",
        "can_generate": False,
    },
    {
        "name": "TELNYX_API_KEY_V2",
        "description": "Telnyx API key (v2)",
        "url": "https://portal.telnyx.com/#/app/api-keys",
        "can_generate": False,
    },
    {
        "name": "CALENDLY_CLIENT_SECRET",
        "description": "Calendly OAuth client secret",
        "url": "https://developer.calendly.com/",
        "can_generate": False,
    },
    {
        "name": "RECALLAI_WEBHOOK_SECRET",
        "description": "Recall.ai webhook signing secret",
        "url": "https://app.recall.ai/",
        "can_generate": False,
    },
    {
        "name": "FACEBOOK_APP_SECRET",
        "description": "Facebook app secret",
        "url": "https://developers.facebook.com/apps/",
        "can_generate": False,
    },
    {
        "name": "GOOGLE_PLACES_API_KEY",
        "description": "Google Places API key",
        "url": "https://console.cloud.google.com/apis/credentials",
        "can_generate": False,
    },
    {
        "name": "SALESFORCE_CLIENT_SECRET",
        "description": "Salesforce OAuth client secret",
        "url": "https://login.salesforce.com/",
        "can_generate": False,
    },
    {
        "name": "RETELL_API_KEY",
        "description": "Retell AI API key",
        "url": "https://app.retellai.com/",
        "can_generate": False,
    },
    {
        "name": "TELNYX_API_KEY",
        "description": "Telnyx API key",
        "url": "https://portal.telnyx.com/#/app/api-keys",
        "can_generate": False,
    },
]


def print_header():
    print("=" * 70)
    print("🔐 API KEY ROTATION HELPER")
    print("=" * 70)
    print(f"\n⚠️  Your API keys were exposed. You MUST rotate them immediately.\n")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


def print_key_info():
    print("=" * 70)
    print("KEYS TO ROTATE")
    print("=" * 70)

    for i, key in enumerate(KEYS_TO_ROTATE, 1):
        print(f"\n{i}. {key['name']}")
        print(f"   Description: {key['description']}")
        if key['url']:
            print(f"   Rotate at: {key['url']}")
        if key.get('can_generate'):
            print(f"   ✅ Can auto-generate (see below)")


def generate_new_values():
    print("\n" + "=" * 70)
    print("AUTO-GENERATED NEW VALUES")
    print("=" * 70)
    print("\nCopy these to Railway environment variables:\n")

    generated = {}
    for key in KEYS_TO_ROTATE:
        if key.get('can_generate') and key.get('generate_func'):
            try:
                value = key['generate_func']()
                generated[key['name']] = value
                print(f"{key['name']}={value}")
            except Exception as e:
                print(f"# Could not generate {key['name']}: {e}")

    return generated


def print_railway_instructions():
    print("\n" + "=" * 70)
    print("RAILWAY DEPLOYMENT INSTRUCTIONS")
    print("=" * 70)
    print("""
1. Go to Railway Dashboard: https://railway.app/dashboard

2. Select your project and service

3. Go to "Variables" tab

4. Update these environment variables with new values:
   - SECRET_KEY (use generated value above)
   - DATA_ENCRYPTION_KEY (use generated value above)
   - OPENAI_API_KEY (get from OpenAI dashboard)
   - ANTHROPIC_API_KEY (get from Anthropic console)
   - SENDGRID_API_KEY (get from SendGrid)
   - TELNYX_API_KEY (get from Telnyx portal)
   - All other keys listed above

5. Add Redis URL:
   - Click "New" → "Database" → "Redis"
   - Or use existing Redis service
   - Copy the REDIS_URL to your variables

6. Redeploy your service after updating variables
""")


def print_redis_setup():
    print("\n" + "=" * 70)
    print("REDIS SETUP FOR TOKEN BLACKLIST")
    print("=" * 70)
    print("""
For token blacklist to work, you need Redis:

Option 1: Railway Redis (Recommended)
  1. In Railway dashboard, click "New" → "Database" → "Redis"
  2. Railway auto-creates REDIS_URL variable
  3. Your app will auto-detect it

Option 2: External Redis
  Add to Railway variables:
  REDIS_URL=redis://username:password@host:port

For local development, add to .env:
  REDIS_URL=redis://localhost:6379

Without Redis, token blacklist runs in memory-only mode
(tokens invalidated on server restart).
""")


def create_env_template():
    """Create a safe .env template without secrets."""
    template = '''# Environment Variables Template
# DO NOT COMMIT REAL VALUES - Use Railway/AWS Secrets Manager

# =============================================================================
# SECURITY (Required)
# =============================================================================
SECRET_KEY=<GENERATE_NEW_VALUE>
DATA_ENCRYPTION_KEY=<GENERATE_NEW_VALUE>

# =============================================================================
# DATABASE
# =============================================================================
DATABASE_URL=sqlite:///./mortgage_crm.db
# Production: Set PROD_DATABASE_URL in Railway

# =============================================================================
# REDIS (Required for token blacklist)
# =============================================================================
REDIS_URL=redis://localhost:6379

# =============================================================================
# AI SERVICES
# =============================================================================
OPENAI_API_KEY=<GET_FROM_OPENAI_DASHBOARD>
ANTHROPIC_API_KEY=<GET_FROM_ANTHROPIC_CONSOLE>
AI_PROVIDER=claude

# =============================================================================
# EMAIL (SendGrid)
# =============================================================================
SENDGRID_API_KEY=<GET_FROM_SENDGRID>
FROM_EMAIL=admin@yourdomain.com
FROM_NAME=Your Company

# =============================================================================
# SMS (Telnyx)
# =============================================================================
TELNYX_API_KEY=<GET_FROM_TELNYX_PORTAL>
TELNYX_PHONE_NUMBER=+1234567890

# =============================================================================
# OAUTH
# =============================================================================
MICROSOFT_CLIENT_ID=<YOUR_CLIENT_ID>
MICROSOFT_CLIENT_SECRET=<GET_FROM_AZURE>
MICROSOFT_TENANT_ID=<YOUR_TENANT_ID>

SALESFORCE_CLIENT_ID=<YOUR_CLIENT_ID>
SALESFORCE_CLIENT_SECRET=<GET_FROM_SALESFORCE>

# =============================================================================
# OTHER SERVICES
# =============================================================================
GOOGLE_PLACES_API_KEY=<GET_FROM_GOOGLE_CONSOLE>
CALENDLY_CLIENT_ID=<YOUR_CLIENT_ID>
CALENDLY_CLIENT_SECRET=<GET_FROM_CALENDLY>

# =============================================================================
# ENVIRONMENT
# =============================================================================
ENVIRONMENT=development
'''

    template_path = os.path.join(os.path.dirname(__file__), '..', '.env.template')
    with open(template_path, 'w') as f:
        f.write(template)
    print(f"\n✅ Created .env.template at {template_path}")
    print("   Use this as a reference for required variables.")


def main():
    print_header()
    print_key_info()
    generated = generate_new_values()
    print_railway_instructions()
    print_redis_setup()
    create_env_template()

    print("\n" + "=" * 70)
    print("✅ NEXT STEPS")
    print("=" * 70)
    print("""
1. [ ] Copy generated SECRET_KEY and DATA_ENCRYPTION_KEY above
2. [ ] Log into each service and rotate/regenerate API keys
3. [ ] Update ALL keys in Railway environment variables
4. [ ] Add Redis to Railway (or set REDIS_URL)
5. [ ] Redeploy your Railway service
6. [ ] Test that all integrations still work
7. [ ] Delete any backups of old .env files
""")


if __name__ == "__main__":
    main()
