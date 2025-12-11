#!/bin/bash

echo "🌱 Seeding Default Voicemail Templates"
echo "======================================"
echo ""

# Get authentication token
echo "📝 Authenticating..."
TOKEN_RESPONSE=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  exit 1
fi

echo "✅ Authenticated"
echo ""

# Create templates
echo "📝 Creating default templates..."
echo ""

# Template 1: Closing Disclosure Ready
echo "1. Closing Disclosure Ready..."
curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/templates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Closing Disclosure Ready",
    "category": "closing",
    "message_text": "Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. I wanted to let you know that your closing disclosures are ready for review. They have been sent to your email. Please review and sign them at your earliest convenience. If you have any questions, feel free to call me back. Thanks!",
    "variables": ["contact_name", "loan_officer"]
  }' | jq -r '.success' > /dev/null
echo "   ✅ Closing Disclosure Ready"

# Template 2: Document Request
echo "2. Document Request..."
curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/templates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Document Request",
    "category": "follow_up",
    "message_text": "Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. We need a few additional documents to move your loan application forward. I have sent you an email with the complete list. Please upload them to your secure portal when you get a chance. If you need any help, just give me a call. Thank you!",
    "variables": ["contact_name", "loan_officer"]
  }' | jq -r '.success' > /dev/null
echo "   ✅ Document Request"

# Template 3: Rate Lock Expiration
echo "3. Rate Lock Expiration..."
curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/templates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Rate Lock Expiration",
    "category": "urgent",
    "message_text": "Hi {{contact_name}}, this is {{loan_officer}}. I wanted to give you a heads up that your rate lock expires soon. We need to take action to secure your current rate. Please call me back as soon as possible so we can discuss your options. Thanks!",
    "variables": ["contact_name", "loan_officer"]
  }' | jq -r '.success' > /dev/null
echo "   ✅ Rate Lock Expiration"

# Template 4: Application Status Update
echo "4. Application Status Update..."
curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/templates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Application Status Update",
    "category": "status_update",
    "message_text": "Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. I wanted to give you a quick update on your loan application. Everything is moving along smoothly. I will keep you posted on any developments. If you have questions, feel free to reach out. Have a great day!",
    "variables": ["contact_name", "loan_officer"]
  }' | jq -r '.success' > /dev/null
echo "   ✅ Application Status Update"

# Template 5: Appointment Reminder
echo "5. Appointment Reminder..."
curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/templates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Appointment Reminder",
    "category": "scheduling",
    "message_text": "Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. Just a friendly reminder about our appointment tomorrow. I am looking forward to speaking with you. If you need to reschedule, just give me a call. See you soon!",
    "variables": ["contact_name", "loan_officer"]
  }' | jq -r '.success' > /dev/null
echo "   ✅ Appointment Reminder"

echo ""
echo "======================================"
echo "✅ All 5 default templates created!"
echo ""

# Verify
echo "📋 Verifying templates..."
TEMPLATES_RESPONSE=$(curl -s "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/templates" \
  -H "Authorization: Bearer $TOKEN")

TEMPLATE_COUNT=$(echo "$TEMPLATES_RESPONSE" | jq -r '.templates | length')
echo "   Templates in database: $TEMPLATE_COUNT"
echo ""

if [ "$TEMPLATE_COUNT" -ge "5" ]; then
  echo "✅ Template seeding successful!"
  echo ""
  echo "Available templates:"
  echo "$TEMPLATES_RESPONSE" | jq -r '.templates[] | "  📝 \(.name) [\(.category)]"'
else
  echo "⚠️  Expected 5 templates, found $TEMPLATE_COUNT"
fi

echo ""
echo "======================================"
