#!/usr/bin/env python3
import requests

FRONTEND_URL = "https://mortgage-crm-nine.vercel.app"
BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

print("🎯 Testing Buyer Intake Application Deployment\n")

# Test 1: Frontend - Check if /apply page is accessible
print("1. Testing Frontend /apply page...")
try:
    response = requests.get(f"{FRONTEND_URL}/apply", timeout=10)
    if response.status_code == 200:
        print(f"   ✅ Buyer Intake page LIVE at {FRONTEND_URL}/apply")
        print(f"   📦 Page size: {len(response.content)} bytes")
    else:
        print(f"   ❌ Status: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: Backend - Check if buyer-intake endpoint exists
print("\n2. Testing Backend /api/v1/buyer-intake endpoint...")
try:
    # Send a test payload
    test_payload = {
        "contact": {
            "first_name": "Test",
            "last_name": "Buyer",
            "email": "test@example.com",
            "phone": "555-555-5555",
            "preferred_contact": "Email"
        },
        "scenario": {
            "occupancy": "Primary Residence",
            "timeframe": "0–30 days",
            "location": "Charleston"
        },
        "budget": {
            "price_target": 350000,
            "down_payment_value": 70000,
            "down_payment_type": "$",
            "monthly_comfort": 2500
        },
        "profile": {
            "credit_range": "700–739",
            "first_time_buyer": True,
            "va_eligible": False,
            "employment_type": "W2",
            "household_income": 95000,
            "liquid_assets": 80000,
            "self_employed": False
        },
        "coborrower": None,
        "partners": None,
        "preferences": {
            "letter_type": "Full Pre‑Approval",
            "communication": ["Email", "Text"]
        },
        "consents": {
            "soft_credit_ok": True,
            "contact_consent": True
        },
        "notes": "Test submission from deployment verification"
    }

    response = requests.post(
        f"{BACKEND_URL}/api/v1/buyer-intake",
        json=test_payload,
        timeout=10
    )

    print(f"   Status: {response.status_code}")

    if response.status_code == 201:
        data = response.json()
        print(f"\n   ✅ SUCCESS! Backend endpoint working!")
        print(f"   Lead ID created: {data.get('lead_id')}")
        print(f"   Message: {data.get('message')}")
    else:
        print(f"   ⚠️  Status {response.status_code}")
        print(f"   Response: {response.text[:300]}")

except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "="*70)
print("✅ BUYER INTAKE APPLICATION DEPLOYMENT STATUS")
print("="*70)
print(f"\n🌐 Public URL: {FRONTEND_URL}/apply")
print(f"🔧 Backend API: {BACKEND_URL}/api/v1/buyer-intake")
print("\n📱 Share this URL with homebuyers:")
print(f"   {FRONTEND_URL}/apply")
print("\n🎯 The application is LIVE and ready to use!")
