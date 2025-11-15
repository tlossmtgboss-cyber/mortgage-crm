#!/bin/bash
# Switch to local database
# Usage: source backend/use_local_db.sh

export DATABASE_URL="sqlite:///./test_agentic_crm.db"
echo "✅ Switched to LOCAL database"
echo "Database: test_agentic_crm.db"
echo ""
echo "Safe for development and testing."
