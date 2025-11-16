#!/bin/bash
# Run AI Receptionist Dashboard migration SQL

echo "🚀 Creating AI Receptionist Dashboard tables..."
echo ""

psql "$DATABASE_URL" -f create_dashboard_tables.sql

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Migration completed successfully!"
else
    echo ""
    echo "❌ Migration failed"
    exit 1
fi
