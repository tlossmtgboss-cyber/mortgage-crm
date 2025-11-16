#!/bin/bash
# Run permission requests migration on Railway

echo "Running permission requests migration on Railway..."
railway run python backend/run_permission_requests_migration.py

if [ $? -eq 0 ]; then
    echo "✅ Migration completed successfully!"
else
    echo "❌ Migration failed. Please check the logs."
    exit 1
fi
