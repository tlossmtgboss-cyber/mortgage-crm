#!/usr/bin/env python3
"""
Verify Twilio Setup on Backend
Tests that Twilio credentials are properly configured
"""
import requests
import sys
import time

BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

print("="*60)
print("🔍 VERIFYING TWILIO SETUP")
print("="*60)
print(f"\nBackend URL: {BACKEND_URL}")
print("\n⏳ Waiting for backend to fully restart (30 seconds)...")
print("   Railway takes time to apply new environment variables...")

# Wait for backend to restart
for i in range(30, 0, -5):
    print(f"   ⏰ {i} seconds remaining...")
    time.sleep(5)

print("\n✅ Wait complete! Now checking backend status...\n")

# Test 1: Backend Health
print("📊 TEST 1: Backend Health Check")
print("-" * 60)
try:
    response = requests.get(f"{BACKEND_URL}/docs", timeout=10)
    if response.status_code == 200:
        print("✅ Backend is online and responding")
        print(f"   Status: {response.status_code}")
    else:
        print(f"⚠️  Backend returned status: {response.status_code}")
        print("   This might be normal - backend may be restarting")
except Exception as e:
    print(f"❌ Cannot reach backend: {e}")
    print("   Wait a bit longer and try again")
    sys.exit(1)

# Test 2: Check Railway Logs Hint
print("\n📊 TEST 2: How to Check Twilio Status")
print("-" * 60)
print("To verify Twilio is initialized, check your Railway logs:")
print("\n1. Go to: https://railway.app/dashboard")
print("2. Click your 'mortgage-crm' project")
print("3. Click your 'backend' service")
print("4. Click 'Deployments' tab")
print("5. Click the latest deployment (top one)")
print("6. Look for this message in logs:")
print("   ✅ 'Twilio SMS initialized successfully'")
print("\nOR if not configured:")
print("   ⚠️  'Twilio SMS credentials not configured'")

# Test 3: Frontend Test Page
print("\n📊 TEST 3: Frontend Integration Test Page")
print("-" * 60)
print("Best way to verify: Use the test page in your CRM!")
print("\n1. Go to: https://mortgage-crm-git-main-tim-loss-projects.vercel.app/verizon-test")
print("2. Log in to your CRM")
print("3. Look at the 'Integration Status' section")
print("4. Find the 'Twilio SMS API' card")
print("5. Status should show: ✅ 'Active' (green badge)")
print("\nIf it shows 'Not Configured':")
print("   - Wait another 30 seconds")
print("   - Refresh the page (Ctrl+R or Cmd+R)")
print("   - Check Railway logs for errors")

# Summary
print("\n" + "="*60)
print("📋 VERIFICATION CHECKLIST")
print("="*60)
print("\n✓ To verify your setup is working, check these:")
print("\n1. [ ] Backend has finished restarting (check Railway)")
print("2. [ ] Railway logs show 'Twilio SMS initialized successfully'")
print("3. [ ] Test page shows Twilio as 'Active' ✅")
print("4. [ ] No errors in Railway deployment logs")

print("\n" + "="*60)
print("🎯 NEXT STEPS")
print("="*60)
print("\n1. Open: https://mortgage-crm-git-main-tim-loss-projects.vercel.app/verizon-test")
print("2. Log in to your CRM")
print("3. Check if Twilio status is 'Active' ✅")
print("\nIf Active:")
print("   🎉 SUCCESS! Twilio is configured!")
print("   You can now use advanced SMS features")
print("\nIf Not Active:")
print("   1. Wait 1-2 more minutes")
print("   2. Check Railway deployment logs")
print("   3. Verify variable names are correct:")
print("      - TWILIO_ACCOUNT_SID")
print("      - TWILIO_AUTH_TOKEN")
print("      - TWILIO_PHONE_NUMBER")
print("   4. Check phone number format: +15551234567 (no spaces)")

print("\n" + "="*60)
print("💡 TROUBLESHOOTING TIPS")
print("="*60)
print("\nCommon Issues:")
print("\n❌ Twilio still shows 'Not Configured':")
print("   → Wait longer (deployment can take 1-2 minutes)")
print("   → Hard refresh: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)")
print("   → Check Railway logs for error messages")
print("\n❌ Variables not taking effect:")
print("   → Make sure you clicked 'Deploy' or 'Restart' in Railway")
print("   → Variables should show in Railway Variables tab")
print("   → Phone number must be: +15551234567 format")
print("\n❌ Backend deployment failed:")
print("   → Check Railway logs for red error messages")
print("   → Verify no typos in variable names")
print("   → Check Account SID starts with 'AC'")

print("\n✨ You're almost there! Check the test page now!")
print("\n")
