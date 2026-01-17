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
# Find the correct Python executable
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "ERROR: No Python found! Trying /usr/bin/python3..."
    PYTHON="/usr/bin/python3"
fi
echo "Using Python: $PYTHON"
$PYTHON run_migrations.py || echo "Warning: Migration had issues, continuing anyway..."
$PYTHON -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
