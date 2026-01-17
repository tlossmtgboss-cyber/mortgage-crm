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
echo "🔐 Demo Login: admin@perenniaai.com / demo123"
echo ""

# Start uvicorn server (Railway provides PORT environment variable)
# Run migrations first, then start the server
python run_migrations.py || echo "Warning: Migration had issues, continuing anyway..."
python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
