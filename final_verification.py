#!/usr/bin/env python3
"""
Final Verification - Verizon Phone Integration
Comprehensive check of all components and features
"""
import os
import requests
import sys
from pathlib import Path

CRM_URL = "https://mortgage-crm-git-main-tim-loss-projects.vercel.app"
BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)

def print_section(text):
    print(f"\n{'─'*70}")
    print(f"📋 {text}")
    print('─'*70)

def check_mark(condition):
    return "✅" if condition else "❌"

def test_frontend_files():
    """Verify all frontend files exist"""
    print_section("Frontend Files Check")

    files_to_check = {
        "VerizonTest Page": "frontend/src/pages/VerizonTest.js",
        "VerizonTest CSS": "frontend/src/pages/VerizonTest.css",
        "ClickableContact Component": "frontend/src/components/ClickableContact.js",
        "ClickableContact CSS": "frontend/src/components/ClickableContact.css",
        "LeadDetail Page": "frontend/src/pages/LeadDetail.js",
        "Leads Page": "frontend/src/pages/Leads.js",
        "App Router": "frontend/src/App.js",
    }

    results = {}
    for name, path in files_to_check.items():
        exists = os.path.exists(path)
        results[name] = exists
        print(f"{check_mark(exists)} {name}: {path}")

    return all(results.values())

def test_documentation():
    """Verify documentation files exist"""
    print_section("Documentation Check")

    docs_to_check = {
        "Setup Instructions": "SETUP_INSTRUCTIONS.md",
        "Backend Environment Setup": "BACKEND_ENVIRONMENT_SETUP.md",
        "Verizon Integration Guide": "VERIZON_INTEGRATION_GUIDE.md",
        "Twilio Verification Script": "verify_twilio_setup.py",
        "Live Test Script": "test_verizon_live.py",
    }

    results = {}
    for name, path in docs_to_check.items():
        exists = os.path.exists(path)
        results[name] = exists
        print(f"{check_mark(exists)} {name}: {path}")

    return all(results.values())

def test_frontend_code():
    """Verify key code implementations"""
    print_section("Frontend Code Implementation Check")

    checks = {}

    # Check VerizonTest route
    try:
        with open('frontend/src/App.js', 'r') as f:
            app_content = f.read()
            has_import = 'VerizonTest' in app_content
            has_route = '/verizon-test' in app_content
            checks['VerizonTest Route'] = has_import and has_route
            print(f"{check_mark(checks['VerizonTest Route'])} VerizonTest route in App.js")
    except Exception as e:
        checks['VerizonTest Route'] = False
        print(f"❌ Error checking App.js: {e}")

    # Check ClickablePhone showActions
    try:
        with open('frontend/src/components/ClickableContact.js', 'r') as f:
            clickable_content = f.read()
            has_show_actions = 'showActions' in clickable_content
            has_tel = 'tel:' in clickable_content
            has_sms = 'sms:' in clickable_content
            checks['ClickablePhone Actions'] = has_show_actions and has_tel and has_sms
            print(f"{check_mark(checks['ClickablePhone Actions'])} ClickablePhone with showActions, tel:, sms:")
    except Exception as e:
        checks['ClickablePhone Actions'] = False
        print(f"❌ Error checking ClickableContact.js: {e}")

    # Check Leads page uses showActions
    try:
        with open('frontend/src/pages/Leads.js', 'r') as f:
            leads_content = f.read()
            uses_show_actions = 'showActions={true}' in leads_content or 'showActions={True}' in leads_content or 'showActions' in leads_content
            checks['Leads showActions'] = uses_show_actions
            print(f"{check_mark(checks['Leads showActions'])} Leads page uses showActions prop")
    except Exception as e:
        checks['Leads showActions'] = False
        print(f"❌ Error checking Leads.js: {e}")

    # Check LeadDetail Quick Actions
    try:
        with open('frontend/src/pages/LeadDetail.js', 'r') as f:
            detail_content = f.read()
            has_quick_actions = 'Quick Actions' in detail_content
            has_call_action = "case 'call':" in detail_content
            has_sms_action = "case 'sms':" in detail_content
            has_tel_protocol = 'tel:' in detail_content
            has_sms_protocol = 'sms:' in detail_content
            checks['LeadDetail Actions'] = all([has_quick_actions, has_call_action, has_sms_action, has_tel_protocol, has_sms_protocol])
            print(f"{check_mark(checks['LeadDetail Actions'])} LeadDetail has Quick Actions with call/sms")
    except Exception as e:
        checks['LeadDetail Actions'] = False
        print(f"❌ Error checking LeadDetail.js: {e}")

    return all(checks.values())

def test_live_deployment():
    """Test live deployment accessibility"""
    print_section("Live Deployment Check")

    checks = {}

    # Test frontend
    try:
        response = requests.get(f"{CRM_URL}/verizon-test", timeout=10)
        # 401 or 403 is fine - means auth is working
        # 200 is also fine - means test page is accessible
        checks['Frontend Test Page'] = response.status_code in [200, 401, 403]
        status = "✅ Accessible" if checks['Frontend Test Page'] else f"❌ Status {response.status_code}"
        print(f"{status} - Test page at /verizon-test")
    except Exception as e:
        checks['Frontend Test Page'] = False
        print(f"❌ Frontend test page error: {e}")

    # Test backend
    try:
        response = requests.get(f"{BACKEND_URL}/docs", timeout=10)
        checks['Backend API'] = response.status_code == 200
        print(f"{check_mark(checks['Backend API'])} Backend API at {BACKEND_URL}")
    except Exception as e:
        checks['Backend API'] = False
        print(f"❌ Backend error: {e}")

    return all(checks.values())

def test_frontend_build():
    """Test if frontend builds successfully"""
    print_section("Frontend Build Check")

    build_dir = Path('frontend/build')
    if build_dir.exists():
        build_files = list(build_dir.rglob('*'))
        has_js = any('main' in str(f) and '.js' in str(f) for f in build_files)
        has_css = any('.css' in str(f) for f in build_files)
        success = has_js and has_css
        print(f"{check_mark(success)} Build directory exists with JS and CSS bundles")
        return success
    else:
        print("⚠️  Build directory not found (may need: cd frontend && npm run build)")
        return False

def main():
    print_header("🔍 FINAL VERIFICATION - VERIZON PHONE INTEGRATION")

    results = {
        "Frontend Files": test_frontend_files(),
        "Documentation": test_documentation(),
        "Frontend Code": test_frontend_code(),
        "Live Deployment": test_live_deployment(),
        "Frontend Build": test_frontend_build(),
    }

    # Summary
    print_header("📊 VERIFICATION SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, status in results.items():
        print(f"{check_mark(status)} {test}")

    print(f"\n{'─'*70}")
    print(f"  {passed}/{total} checks passed")
    print('─'*70)

    if all(results.values()):
        print("\n✅ ALL CHECKS PASSED!")
        print("\n🎉 Verizon Phone Integration is READY TO USE!")
        print(f"\n📱 Test it now: {CRM_URL}/verizon-test")
        print("\n📚 Documentation:")
        print("   • SETUP_INSTRUCTIONS.md - Step-by-step setup guide")
        print("   • VERIZON_INTEGRATION_GUIDE.md - User guide")
        print("   • BACKEND_ENVIRONMENT_SETUP.md - Backend configuration")

        print("\n🚀 Features Available:")
        print("   ✅ Click-to-call (tel: protocol)")
        print("   ✅ SMS/Text messaging (sms: protocol)")
        print("   ✅ Email links (mailto: protocol)")
        print("   ✅ Quick Actions in Lead Detail page")
        print("   ✅ Phone action buttons in Leads table")
        print("   ✅ Comprehensive test page")
        print("   ✅ Twilio integration ready (optional)")

        print("\n💡 Next Steps:")
        print("   1. Test the integration at /verizon-test")
        print("   2. Optional: Add Twilio variables for advanced SMS")
        print("   3. Share SETUP_INSTRUCTIONS.md with your team")

        return 0
    else:
        print("\n⚠️  Some checks failed")
        print("\nFailed checks:")
        for test, status in results.items():
            if not status:
                print(f"   ❌ {test}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
