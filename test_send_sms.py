#!/usr/bin/env python3
"""Test sending SMS through the CRM API"""
import requests

BASE_URL = "http://localhost:8000"

# Step 1: Login
print("Logging in...")
login_response = requests.post(
    f"{BASE_URL}/token",
    data={"username": "demo@example.com", "password": "demo123"}
)

if login_response.status_code != 200:
    print(f"Login failed: {login_response.text}")
    exit(1)

token = login_response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("✅ Logged in successfully\n")

# Step 2: Check SMS status
print("Checking SMS service status...")
status_response = requests.get(f"{BASE_URL}/api/v1/sms/status", headers=headers)
print(f"SMS Status: {status_response.json()}")
print()

if not status_response.json().get("enabled"):
    print("❌ SMS service is not enabled!")
    exit(1)

# Step 3: Get SMS templates
print("Available SMS templates:")
templates_response = requests.get(f"{BASE_URL}/api/v1/sms/templates", headers=headers)
templates = templates_response.json().get("templates", [])
for i, template in enumerate(templates, 1):
    print(f"{i}. {template['name']}")
print()

# Step 4: Send test SMS
print("="*60)
print("SEND TEST SMS")
print("="*60)
print("Enter a phone number to send a test SMS to:")
print("Format: +1234567890 (include + and country code)")
phone = input("Phone number: ").strip()

if not phone:
    print("No phone number provided. Exiting.")
    exit(0)

if not phone.startswith('+'):
    phone = f"+1{phone}"

print(f"\nSending SMS to {phone}...")

sms_data = {
    "to_number": phone,
    "message": "Hello! This is a test message from your Mortgage CRM. Your Twilio integration is working perfectly! 🎉",
    "template": "test"
}

send_response = requests.post(
    f"{BASE_URL}/api/v1/sms/send",
    json=sms_data,
    headers=headers
)

if send_response.status_code == 201:
    result = send_response.json()
    print("✅ SMS sent successfully!")
    print(f"   Message ID: {result['id']}")
    print(f"   Status: {result['status']}")
    print(f"   Twilio SID: {result.get('twilio_sid', 'N/A')}")
    print(f"   From: {result['from_number']}")
    print(f"   To: {result['to_number']}")
else:
    print(f"❌ Failed to send SMS")
    print(f"   Status: {send_response.status_code}")
    print(f"   Error: {send_response.text}")

print("\n" + "="*60)
print("Test completed!")
