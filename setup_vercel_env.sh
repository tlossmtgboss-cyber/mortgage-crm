#!/bin/bash

# Setup Vercel Environment Variables for Microsoft 365 Integration
# This script adds REACT_APP_MICROSOFT_CLIENT_ID to your Vercel project

echo "🔧 Setting up Vercel environment variable for Microsoft 365..."
echo ""

# Check if vercel CLI is installed
if ! command -v vercel &> /dev/null; then
    echo "❌ Vercel CLI not found. Installing..."
    npm install -g vercel
fi

# Navigate to frontend directory
cd "$(dirname "$0")/frontend" || exit 1

echo "📁 Current directory: $(pwd)"
echo ""

# Check if logged in
if ! vercel whoami &> /dev/null; then
    echo "🔐 Please log in to Vercel..."
    vercel login
    echo ""
fi

# Link to project if not already linked
if [ ! -d ".vercel" ]; then
    echo "🔗 Linking to Vercel project..."
    vercel link
    echo ""
fi

# Set environment variable for all environments
echo "⚙️  Adding REACT_APP_MICROSOFT_CLIENT_ID to Vercel..."
echo ""

vercel env add REACT_APP_MICROSOFT_CLIENT_ID production <<< "185b7101-9435-44da-87ab-b7582c4e4607"
vercel env add REACT_APP_MICROSOFT_CLIENT_ID preview <<< "185b7101-9435-44da-87ab-b7582c4e4607"
vercel env add REACT_APP_MICROSOFT_CLIENT_ID development <<< "185b7101-9435-44da-87ab-b7582c4e4607"

echo ""
echo "✅ Environment variable added!"
echo ""
echo "🚀 Now redeploying to apply changes..."
echo ""

# Trigger redeploy
vercel --prod

echo ""
echo "✨ Done! Your Microsoft 365 OAuth should now work."
echo ""
echo "Next steps:"
echo "1. Go to https://mortgage-crm-production-7a9a.up.railway.app/settings"
echo "2. Click Integrations → Outlook Email"
echo "3. Complete OAuth flow"
echo "4. Test sync in Reconciliation Center"
