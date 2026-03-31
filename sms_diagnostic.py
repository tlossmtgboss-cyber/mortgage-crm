#!/usr/bin/env python3
"""
SMS Diagnostic and Test Script for Perennia AI Mortgage CRM

This script diagnoses SMS configuration issues and provides detailed
setup instructions for fixing SMS functionality.
"""
import os
import sys
import subprocess
from typing import Dict, Any, List

def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "="*60)
    print(f" {title}")
    print("="*60)

def print_status(check: str, status: bool, message: str = ""):
    """Print a status line with check mark or X."""
    icon = "✅" if status else "❌"
    print(f"{icon} {check}: {message if message else ('OK' if status else 'FAILED')}")

def check_environment_variables() -> Dict[str, Any]:
    """Check all required SMS environment variables."""
    print_header("SMS Environment Variables Check")
    
    required_vars = {
        "TELNYX_API_KEY": "Telnyx API key for authentication",
        "TELNYX_PHONE_NUMBER": "Phone number for sending SMS (E.164 format)",
        "TELNYX_MESSAGING_PROFILE_ID": "Messaging profile ID from Telnyx portal"
    }
    
    optional_vars = {
        "TELNYX_CONNECTION_ID": "Connection ID for voice calls (optional)",
        "TELNYX_WEBHOOK_SECRET": "Webhook signature verification secret (optional)",
        "ENABLE_2FA_SMS": "Enable SMS-based 2FA (optional)"
    }
    
    issues = []
    all_vars = {}
    
    print("\nRequired Variables:")
    for var, desc in required_vars.items():
        value = os.getenv(var, "")
        is_set = bool(value)
        all_vars[var] = value
        print_status(f"{var:<25}", is_set, desc)
        if not is_set:
            issues.append(f"Missing required variable: {var}")
    
    print("\nOptional Variables:")
    for var, desc in optional_vars.items():
        value = os.getenv(var, "")
        is_set = bool(value)
        all_vars[var] = value
        status_msg = f"{desc} - {'SET' if is_set else 'NOT SET'}"
        print_status(f"{var:<25}", True, status_msg)
    
    return {
        "variables": all_vars,
        "issues": issues,
        "enabled": len(issues) == 0
    }

def check_file_structure() -> Dict[str, Any]:
    """Check if all SMS-related files exist."""
    print_header("SMS File Structure Check")
    
    base_path = "/Users/timothyloss/my-project/mortgage-crm/backend"
    
    required_files = [
        "integrations/sms_service.py",
        ".env.example",
        ".env"
    ]
    
    optional_files = [
        "integrations/sms_compliance_gate.py",
        "integrations/sms_rate_limiter.py",
        "integrations/sms_template_engine.py",
        "integrations/sms_delivery_tracker.py"
    ]
    
    missing_files = []
    
    print("\nRequired Files:")
    for file_path in required_files:
        full_path = os.path.join(base_path, file_path)
        exists = os.path.exists(full_path)
        print_status(f"{file_path:<40}", exists)
        if not exists:
            missing_files.append(file_path)
    
    print("\nOptional SMS Components:")
    for file_path in optional_files:
        full_path = os.path.join(base_path, file_path)
        exists = os.path.exists(full_path)
        status_msg = "Available" if exists else "Not installed"
        print_status(f"{file_path:<40}", True, status_msg)
    
    return {
        "missing_files": missing_files,
        "structure_ok": len(missing_files) == 0
    }

def check_imports() -> Dict[str, Any]:
    """Check if SMS service can be imported correctly."""
    print_header("SMS Import Check")
    
    import_checks = [
        ("Basic SMS Service", "from integrations.sms_service import SMSClient"),
        ("SMS Templates", "from integrations.sms_service import SMSTemplates"),
        ("SMS Configuration", "from integrations.sms_service import check_sms_configuration"),
        ("SMS Helper", "from integrations.sms_service import get_sms_client")
    ]
    
    issues = []
    
    for check_name, import_statement in import_checks:
        try:
            exec(import_statement)
            print_status(check_name, True, "Import successful")
        except ImportError as e:
            print_status(check_name, False, f"Import failed: {e}")
            issues.append(f"{check_name}: {e}")
        except Exception as e:
            print_status(check_name, False, f"Error: {e}")
            issues.append(f"{check_name}: {e}")
    
    return {
        "import_issues": issues,
        "imports_ok": len(issues) == 0
    }

def check_dependencies() -> Dict[str, Any]:
    """Check if required dependencies are installed."""
    print_header("SMS Dependencies Check")
    
    dependencies = [
        ("requests", "HTTP client for Telnyx API"),
        ("sqlalchemy", "Database ORM"),
        ("python-dotenv", "Environment variable loader")
    ]
    
    missing_deps = []
    
    for dep, desc in dependencies:
        try:
            __import__(dep)
            print_status(f"{dep:<15}", True, desc)
        except ImportError:
            print_status(f"{dep:<15}", False, f"{desc} - NOT INSTALLED")
            missing_deps.append(dep)
    
    return {
        "missing_dependencies": missing_deps,
        "dependencies_ok": len(missing_deps) == 0
    }

def provide_setup_instructions(env_check: Dict, file_check: Dict, import_check: Dict, dep_check: Dict):
    """Provide comprehensive setup instructions."""
    print_header("SMS Setup Instructions")
    
    has_issues = (env_check["issues"] or 
                 file_check["missing_files"] or 
                 import_check["import_issues"] or 
                 dep_check["missing_dependencies"])
    
    if not has_issues:
        print("🎉 SMS configuration appears to be complete!")
        print("Your SMS system should be working correctly.")
        return
    
    print("Follow these steps to fix SMS configuration:")
    
    # Step 1: Dependencies
    if dep_check["missing_dependencies"]:
        print("\n1️⃣ Install Missing Dependencies:")
        print("   cd /Users/timothyloss/my-project/mortgage-crm/backend")
        for dep in dep_check["missing_dependencies"]:
            print(f"   python3 -m pip install --user {dep}")
    
    # Step 2: Environment Variables
    if env_check["issues"]:
        print("\n2️⃣ Set Up Telnyx Account and Configure Environment:")
        print("   a) Sign up at: https://telnyx.com/sign-up")
        print("   b) Get API key from: https://portal.telnyx.com/#/app/api-keys")
        print("   c) Purchase a phone number in your Telnyx portal")
        print("   d) Create messaging profile at: https://portal.telnyx.com/#/app/messaging")
        print("   e) Edit your .env file and add:")
        print("      TELNYX_API_KEY=your_actual_api_key_here")
        print("      TELNYX_PHONE_NUMBER=+15551234567")
        print("      TELNYX_MESSAGING_PROFILE_ID=your_messaging_profile_id")
    
    # Step 3: File Issues
    if file_check["missing_files"]:
        print("\n3️⃣ Missing Files:")
        for file_path in file_check["missing_files"]:
            print(f"   ❌ {file_path} - needs to be created or restored")
    
    # Step 4: Import Issues
    if import_check["import_issues"]:
        print("\n4️⃣ Import Issues:")
        for issue in import_check["import_issues"]:
            print(f"   ❌ {issue}")
    
    # Step 5: Testing
    print("\n5️⃣ Test Configuration:")
    print("   After fixing the above, restart your backend server:")
    print("   cd /Users/timothyloss/my-project/mortgage-crm/backend")
    print("   python3 -m uvicorn main:app --reload")
    print("   Then test SMS from a lead profile in the CRM.")

def run_diagnostic():
    """Run complete SMS diagnostic."""
    print_header("SMS System Diagnostic Report")
    print("Checking SMS configuration for Perennia AI Mortgage CRM...")
    
    # Run all checks
    env_check = check_environment_variables()
    file_check = check_file_structure()
    import_check = check_imports()
    dep_check = check_dependencies()
    
    # Summary
    print_header("Summary")
    total_checks = 4
    passed_checks = sum([
        1 if env_check["enabled"] else 0,
        1 if file_check["structure_ok"] else 0,
        1 if import_check["imports_ok"] else 0,
        1 if dep_check["dependencies_ok"] else 0
    ])
    
    print(f"✅ Passed: {passed_checks}/{total_checks} check groups")
    
    if passed_checks == total_checks:
        print("🎉 SMS system is fully configured and ready to use!")
    else:
        print(f"⚠️  {total_checks - passed_checks} issue(s) need to be resolved")
    
    # Provide setup instructions
    provide_setup_instructions(env_check, file_check, import_check, dep_check)
    
    print("\n" + "="*60)
    print(" For additional help, see: SMS_SETUP_GUIDE.md")
    print("="*60)

if __name__ == "__main__":
    # Change to backend directory
    os.chdir("/Users/timothyloss/my-project/mortgage-crm/backend")
    
    # Add current directory to Python path
    sys.path.insert(0, ".")
    
    try:
        # Load environment variables
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("Warning: python-dotenv not available, using system environment only")
    
    run_diagnostic()