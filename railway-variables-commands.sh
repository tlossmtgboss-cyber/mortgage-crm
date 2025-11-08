#!/bin/bash
# Railway Environment Variables Setup
# Run these commands to add all variables at once

echo "Adding Railway environment variables..."
echo ""

# Make sure you're logged in first
railway login

# Link to your project (if not already linked)
railway link

# Add all environment variables
echo "Adding SECRET_KEY..."
railway variables set SECRET_KEY=d29e43b5059126da6dda9a061609a329c827a638eb43947cff69f115f4fbdd0a

echo "Adding DATABASE_URL..."
railway variables set DATABASE_URL="postgresql://postgres:RzXRIwJsZINuRwMQybbbZYqYFoHBaxRw@postgres.railway.internal:5432/railway"

echo "Adding OPENAI_API_KEY..."
railway variables set OPENAI_API_KEY=""

echo "Adding ENVIRONMENT..."
railway variables set ENVIRONMENT=production

echo ""
echo "✅ All variables added!"
echo ""
echo "Checking variables..."
railway variables

echo ""
echo "Deployment should start automatically."
echo "Check status with: railway status"
echo "View logs with: railway logs"
