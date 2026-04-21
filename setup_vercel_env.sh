#!/bin/bash

# Setup Vercel Environment Variables for Microsoft 365 Integration
# This script adds REACT_APP_MICROSOFT_CLIENT_ID to your Vercel project
# SECURITY: Set MICROSOFT_CLIENT_ID env var before running this script.

if [ -z "$MICROSOFT_CLIENT_ID" ]; then
    echo "ERROR: MICROSOFT_CLIENT_ID env var is not set. Export it before running this script."
    exit 1
fi

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

vercel env add REACT_APP_MICROSOFT_CLIENT_ID production <<< "$MICROSOFT_CLIENT_ID"
vercel env add REACT_APP_MICROSOFT_CLIENT_ID preview <<< "$MICROSOFT_CLIENT_ID"
vercel env add REACT_APP_MICROSOFT_CLIENT_ID development <<< "$MICROSOFT_CLIENT_ID"

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
echo "1. Go to https://app.perenniaai.com/settings"
echo "2. Click Integrations → Outlook Email"
echo "3. Complete OAuth flow"
echo "4. Test sync in Reconciliation Center"
