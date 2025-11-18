#!/bin/bash

# Voice OS Quick Setup Script
echo "🚀 Voice OS Quick Setup"
echo "======================="
echo ""

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: Run this from the voice_os directory"
    echo "   cd /Users/timothyloss/my-project/mortgage-crm/backend/voice_os"
    exit 1
fi

echo "📁 Current directory: $(pwd)"
echo ""

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Please install Node.js 18+ first."
    exit 1
fi

echo "✅ Node.js version: $(node --version)"
echo ""

# Install dependencies
echo "📦 Installing dependencies..."
npm install
if [ $? -ne 0 ]; then
    echo "❌ npm install failed"
    exit 1
fi
echo "✅ Dependencies installed"
echo ""

# Setup environment
if [ ! -f ".env" ]; then
    echo "📝 Creating .env from template..."
    cp .env.example .env
    echo "✅ .env created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and add your API keys:"
    echo "   - TWILIO_ACCOUNT_SID"
    echo "   - TWILIO_AUTH_TOKEN"
    echo "   - DEEPGRAM_API_KEY"
    echo "   - ELEVENLABS_API_KEY"
    echo "   - OPENAI_API_KEY"
    echo "   - CRM_API_URL"
    echo "   - CRM_API_KEY"
    echo ""
else
    echo "✅ .env already exists"
    echo ""
fi

# Check for tool executor
if [ ! -f "src/tools/executor.ts" ] || [ ! -s "src/tools/executor.ts" ]; then
    echo "⚠️  Tool executor not found or empty"
    echo "   You need to copy the tool-executor.ts content from your Voice OS spec"
    echo "   to: src/tools/executor.ts"
    echo ""
fi

# Build TypeScript
echo "🔨 Building TypeScript..."
npm run build
if [ $? -ne 0 ]; then
    echo "❌ Build failed - check TypeScript errors above"
    exit 1
fi
echo "✅ Build successful"
echo ""

# Check for PostgreSQL
if command -v psql &> /dev/null; then
    echo "✅ PostgreSQL found: $(psql --version)"
    echo ""
    echo "📊 To run database migration:"
    echo "   psql pipeline360 < ../migrations/001_voice_os_schema.sql"
    echo ""
else
    echo "⚠️  PostgreSQL not found in PATH"
    echo "   Install PostgreSQL or run database migration manually"
    echo ""
fi

# Check for Redis
if command -v redis-cli &> /dev/null; then
    echo "✅ Redis found"
    # Test connection
    if redis-cli ping &> /dev/null; then
        echo "✅ Redis is running"
    else
        echo "⚠️  Redis not running. Start with: redis-server"
    fi
    echo ""
else
    echo "⚠️  Redis not found. Install with:"
    echo "   brew install redis  # macOS"
    echo "   Or use Docker: docker run -d -p 6379:6379 redis:7-alpine"
    echo ""
fi

# Final status
echo "🎯 Setup Status:"
echo "   ✅ Dependencies installed"
echo "   ✅ TypeScript built"
echo "   ✅ Environment template created"
echo ""
echo "📋 Next Steps:"
echo "   1. Edit .env with your API keys"
echo "   2. Copy tool executor from your spec to src/tools/executor.ts"
echo "   3. Run database migration"
echo "   4. Start Redis if not running"
echo "   5. Run: npm run dev"
echo ""
echo "🚀 Ready to deploy!"
