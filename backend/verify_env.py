#!/usr/bin/env python3
"""
Environment Variables Verification Script
Checks all required environment variables for the Mortgage CRM backend
"""
import os
import sys
from typing import Dict, List, Tuple

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def check_env_var(name: str, required: bool = True, description: str = "") -> Tuple[bool, str]:
    """Check if an environment variable is set"""
    value = os.getenv(name)

    if value:
        # Mask sensitive values
        if any(keyword in name.lower() for keyword in ['secret', 'key', 'token', 'password']):
            display_value = f"{value[:8]}..." if len(value) > 8 else "***"
        else:
            display_value = value if len(value) < 50 else f"{value[:47]}..."

        return True, display_value
    elif required:
        return False, "MISSING (REQUIRED)"
    else:
        return False, "Not set (optional)"


def main():
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}")
    print("🔍 MORTGAGE CRM - Environment Variables Verification")
    print(f"{'='*70}{Colors.ENDC}\n")

    # Define all environment variables
    env_vars: Dict[str, Tuple[bool, str]] = {
        # Core Configuration
        "DATABASE_URL": (True, "PostgreSQL database connection string"),
        "SECRET_KEY": (True, "JWT token secret key (generate with: openssl rand -hex 32)"),
        "ENVIRONMENT": (False, "Environment: development, staging, or production"),

        # AI Integration
        "OPENAI_API_KEY": (True, "OpenAI API key for AI Assistant features"),

        # Microsoft Graph API (Teams, Email, Calendar)
        "MICROSOFT_CLIENT_ID": (False, "Azure AD App Client ID"),
        "MICROSOFT_CLIENT_SECRET": (False, "Azure AD App Client Secret"),
        "MICROSOFT_TENANT_ID": (False, "Azure AD Tenant ID"),
        "MICROSOFT_REDIRECT_URI": (False, "OAuth callback URL"),
        "MICROSOFT_FROM_EMAIL": (False, "Email address for sending emails"),

        # Twilio SMS
        "TWILIO_ACCOUNT_SID": (False, "Twilio Account SID"),
        "TWILIO_AUTH_TOKEN": (False, "Twilio Auth Token"),
        "TWILIO_PHONE_NUMBER": (False, "Twilio phone number for SMS"),

        # Stripe Payment Processing
        "STRIPE_SECRET_KEY": (False, "Stripe secret key"),
        "STRIPE_PUBLISHABLE_KEY": (False, "Stripe publishable key"),
        "STRIPE_WEBHOOK_SECRET": (False, "Stripe webhook signing secret"),

        # Optional Settings
        "ACCESS_TOKEN_EXPIRE_MINUTES": (False, "JWT token expiration (default: 30)"),
        "WEBHOOK_BASE_URL": (False, "Base URL for webhooks"),
        "ALLOWED_ORIGINS": (False, "CORS allowed origins (comma-separated)"),
        "LOG_LEVEL": (False, "Logging level (INFO, DEBUG, WARNING, ERROR)"),
    }

    results = []
    required_missing = []
    optional_missing = []

    # Check each variable
    for var_name, (required, description) in env_vars.items():
        is_set, value = check_env_var(var_name, required, description)

        status_symbol = f"{Colors.GREEN}✓{Colors.ENDC}" if is_set else (
            f"{Colors.RED}✗{Colors.ENDC}" if required else f"{Colors.YELLOW}⚠{Colors.ENDC}"
        )

        results.append({
            'name': var_name,
            'required': required,
            'is_set': is_set,
            'value': value,
            'description': description,
            'symbol': status_symbol
        })

        if not is_set:
            if required:
                required_missing.append((var_name, description))
            else:
                optional_missing.append((var_name, description))

    # Print results
    print(f"{Colors.BOLD}📋 REQUIRED VARIABLES:{Colors.ENDC}\n")
    for result in [r for r in results if r['required']]:
        print(f"{result['symbol']} {Colors.BOLD}{result['name']}{Colors.ENDC}")
        print(f"   {result['description']}")
        print(f"   Value: {result['value']}\n")

    print(f"\n{Colors.BOLD}📋 OPTIONAL VARIABLES (Integrations):{Colors.ENDC}\n")
    for result in [r for r in results if not r['required']]:
        print(f"{result['symbol']} {Colors.BOLD}{result['name']}{Colors.ENDC}")
        print(f"   {result['description']}")
        print(f"   Value: {result['value']}\n")

    # Print summary
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}")
    print("📊 SUMMARY")
    print(f"{'='*70}{Colors.ENDC}\n")

    total_required = sum(1 for r in results if r['required'])
    required_set = sum(1 for r in results if r['required'] and r['is_set'])
    total_optional = sum(1 for r in results if not r['required'])
    optional_set = sum(1 for r in results if not r['required'] and r['is_set'])

    print(f"Required Variables: {required_set}/{total_required} configured")
    print(f"Optional Variables: {optional_set}/{total_optional} configured")

    # Print missing required variables
    if required_missing:
        print(f"\n{Colors.RED}{Colors.BOLD}⚠️  CRITICAL: Missing Required Variables:{Colors.ENDC}")
        for var_name, description in required_missing:
            print(f"{Colors.RED}   • {var_name}{Colors.ENDC}: {description}")
        print(f"\n{Colors.RED}The application may not start without these variables!{Colors.ENDC}")

    # Print missing optional variables
    if optional_missing:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}ℹ️  Info: Missing Optional Variables (Features Disabled):{Colors.ENDC}")
        for var_name, description in optional_missing:
            print(f"{Colors.YELLOW}   • {var_name}{Colors.ENDC}: {description}")

    # Special checks
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}")
    print("🔧 CONFIGURATION CHECKS")
    print(f"{'='*70}{Colors.ENDC}\n")

    # Check DATABASE_URL format
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
            print(f"{Colors.GREEN}✓{Colors.ENDC} DATABASE_URL format is valid")
            if db_url.startswith("postgres://"):
                print(f"{Colors.YELLOW}  Note: Will be auto-converted to postgresql://{Colors.ENDC}")
        else:
            print(f"{Colors.RED}✗{Colors.ENDC} DATABASE_URL format may be invalid")
            print(f"  Expected: postgresql://user:password@host:port/database")

    # Check SECRET_KEY strength
    secret_key = os.getenv("SECRET_KEY", "")
    if secret_key:
        if len(secret_key) >= 32:
            print(f"{Colors.GREEN}✓{Colors.ENDC} SECRET_KEY length is adequate ({len(secret_key)} characters)")
        else:
            print(f"{Colors.YELLOW}⚠{Colors.ENDC} SECRET_KEY is short ({len(secret_key)} characters)")
            print(f"  Recommended: At least 32 characters")
            print(f"  Generate with: openssl rand -hex 32")

    # Check if we're in production
    environment = os.getenv("ENVIRONMENT", "development").lower()
    print(f"\n{Colors.BOLD}Environment:{Colors.ENDC} {environment}")

    if environment == "production":
        if not required_missing:
            print(f"{Colors.GREEN}✓ Ready for production deployment{Colors.ENDC}")
        else:
            print(f"{Colors.RED}✗ NOT ready for production (missing required variables){Colors.ENDC}")

    # Print setup instructions
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}")
    print("📝 SETUP INSTRUCTIONS")
    print(f"{'='*70}{Colors.ENDC}\n")

    if required_missing or optional_missing:
        print("To fix missing variables:\n")

        print(f"{Colors.BOLD}For Local Development:{Colors.ENDC}")
        print("1. Create a .env file in the backend directory")
        print("2. Copy from .env.example: cp .env.example .env")
        print("3. Fill in the values in .env\n")

        print(f"{Colors.BOLD}For Railway Deployment:{Colors.ENDC}")
        print("1. Go to https://railway.app/dashboard")
        print("2. Select your mortgage-crm project → backend service")
        print("3. Click 'Variables' tab")
        print("4. Add missing variables:\n")

        if required_missing:
            print("   Required:")
            for var_name, description in required_missing:
                print(f"   • {var_name}")
                if var_name == "SECRET_KEY":
                    print(f"     Run: openssl rand -hex 32")
                elif var_name == "DATABASE_URL":
                    print(f"     Use: ${{Postgres.DATABASE_URL}}")

        print(f"\n   Optional (for integrations):")
        for var_name, description in optional_missing[:3]:  # Show first 3
            print(f"   • {var_name}")
        if len(optional_missing) > 3:
            print(f"   ... and {len(optional_missing) - 3} more")
    else:
        print(f"{Colors.GREEN}✓ All variables are configured!{Colors.ENDC}")

    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.ENDC}\n")

    # Exit code
    if required_missing:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    # Load .env file if it exists
    try:
        from dotenv import load_dotenv
        if os.path.exists(".env"):
            load_dotenv()
            print(f"{Colors.GREEN}✓ Loaded .env file{Colors.ENDC}\n")
        elif os.path.exists("backend/.env"):
            load_dotenv("backend/.env")
            print(f"{Colors.GREEN}✓ Loaded backend/.env file{Colors.ENDC}\n")
        else:
            print(f"{Colors.YELLOW}⚠ No .env file found (checking system environment){Colors.ENDC}\n")
    except ImportError:
        print(f"{Colors.YELLOW}⚠ python-dotenv not installed (checking system environment only){Colors.ENDC}\n")

    main()
