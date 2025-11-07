#!/bin/bash

echo "=========================================="
echo "Agentic AI Mortgage CRM - Quick Start"
echo "=========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "🔧 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📚 Installing Python dependencies..."
cd backend
pip install -q -r requirements.txt

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "🔧 Creating .env file..."
    cp .env.example .env
fi

# Start the server
echo ""
echo "=========================================="
echo "✅ Starting CRM Backend Server..."
echo "=========================================="
echo ""
echo "📍 API: http://localhost:8000"
echo "📚 Docs: http://localhost:8000/docs"
echo "🔐 Demo Login: demo@example.com / demo123"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

python -m uvicorn main:app --host 0.0.0.0 --port 8000
