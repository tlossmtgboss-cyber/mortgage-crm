#!/bin/bash

echo "========================================================================"
echo "Configuring SMTP for Daily Priorities Email"
echo "========================================================================"

# Check if Railway CLI is available
if ! command -v railway &> /dev/null; then
    echo "Error: Railway CLI not found"
    exit 1
fi

# Check authentication
echo "Checking Railway authentication..."
railway whoami || { echo "Error: Not logged into Railway"; exit 1; }

echo ""
echo "Current project:"
railway status

echo ""
echo "========================================================================"
echo "Adding SMTP Configuration to Railway"
echo "========================================================================"

# Prompt for app password
echo ""
echo "Please enter your Gmail App Password (16 characters with spaces):"
echo "Get it from: https://myaccount.google.com/apppasswords"
echo ""
read -s -p "App Password: " APP_PASSWORD
echo ""

if [ -z "$APP_PASSWORD" ]; then
    echo "Error: App password cannot be empty"
    exit 1
fi

# Remove spaces from app password
APP_PASSWORD_CLEAN=$(echo "$APP_PASSWORD" | tr -d ' ')

echo ""
echo "Setting SMTP variables..."

# Set environment variables
railway variables set SMTP_HOST="smtp.gmail.com" \
    SMTP_PORT="587" \
    SMTP_USER="tlossmtgboss@gmail.com" \
    SMTP_PASSWORD="$APP_PASSWORD_CLEAN" \
    FROM_EMAIL="tlossmtgboss@gmail.com" \
    FROM_NAME="Pipeline 360 CRM"

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ SMTP configuration added successfully!"
    echo ""
    echo "The service will automatically redeploy with new variables."
    echo "Wait about 2-3 minutes for deployment to complete."
    echo ""
    echo "========================================================================"
    echo "Testing Email (after deployment)"
    echo "========================================================================"
    echo ""
    echo "Run this command to test:"
    echo ""
    echo "python3 test_email_priorities.py"
    echo ""
else
    echo ""
    echo "✗ Error setting variables"
    exit 1
fi
