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
# Try python3 first, fall back to python
if command -v python3 &> /dev/null; then
    python3 -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
else
    python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
fi
