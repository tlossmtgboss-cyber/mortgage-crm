#!/bin/bash

echo "=========================================="
echo "Agentic AI Mortgage CRM - Quick Start"
echo "=========================================="
echo ""

# Navigate to backend directory
cd backend

# Start the FastAPI application
echo "=========================================="
echo "✅ Starting CRM Backend Server..."
echo "=========================================="
echo ""
echo "📍 API: http://0.0.0.0:${PORT:-8000}"
echo "📚 Docs: http://0.0.0.0:${PORT:-8000}/docs"
echo "🔐 Demo Login: demo@example.com / demo123"
echo ""

# Start uvicorn server (Railway provides PORT environment variable)
python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
>>>>>>> d774359 (✨ Add comprehensive profile fields, AI Assistant page, and Railway deployment updates)
