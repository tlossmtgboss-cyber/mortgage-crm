#!/bin/bash
# Switch to production database
# Usage: source backend/use_production_db.sh

if [ -z "$PROD_DATABASE_URL" ]; then
    echo "❌ Error: PROD_DATABASE_URL not set in environment"
    echo "Please set it in backend/.env or export it:"
    echo "  export PROD_DATABASE_URL='postgresql://postgres:PASSWORD@HOST:PORT/railway'"
    return 1
fi

export DATABASE_URL=$PROD_DATABASE_URL
echo "✅ Switched to PRODUCTION database"
echo "Host: $(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\):.*/\1/p')"
echo ""
echo "⚠️  WARNING: You are now connected to PRODUCTION!"
echo "All database operations will affect the live system."
