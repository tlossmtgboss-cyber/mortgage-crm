#!/bin/bash

echo "=========================================="
echo "Push Mortgage CRM to GitHub"
echo "=========================================="
echo ""

# Get GitHub username
echo "Enter your GitHub username:"
read GITHUB_USERNAME

echo ""
echo "📋 Setting up remote..."

# Add remote
git remote add origin https://github.com/$GITHUB_USERNAME/mortgage-crm.git

echo "✅ Remote added"
echo ""
echo "🚀 Pushing to GitHub..."
echo ""
echo "You'll be asked for authentication:"
echo "  Username: $GITHUB_USERNAME"
echo "  Password: Use your Personal Access Token (NOT your password)"
echo ""
echo "Don't have a token? Get one here:"
echo "👉 https://github.com/settings/tokens"
echo "   (Select scope: 'repo')"
echo ""

# Push to GitHub
git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ SUCCESS! Code pushed to GitHub!"
    echo "=========================================="
    echo ""
    echo "🌐 Your repository is now live at:"
    echo "👉 https://github.com/$GITHUB_USERNAME/mortgage-crm"
    echo ""
    echo "Next steps:"
    echo "1. Visit your repository URL above"
    echo "2. Star your own repo ⭐"
    echo "3. Share it with others!"
    echo ""
else
    echo ""
    echo "❌ Push failed. Common issues:"
    echo ""
    echo "1. Repository doesn't exist on GitHub"
    echo "   → Create it at: https://github.com/new"
    echo ""
    echo "2. Authentication failed"
    echo "   → Get a token: https://github.com/settings/tokens"
    echo ""
    echo "3. Remote already exists"
    echo "   → Run: git remote remove origin"
    echo "   → Then run this script again"
    echo ""
fi
