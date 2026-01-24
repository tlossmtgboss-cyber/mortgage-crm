#!/usr/bin/env python3
"""
Start script for Railway deployment.
Handles PORT environment variable properly and runs migrations first.
"""

import os
import subprocess
import sys

def main():
    # Run migrations first
    print("=" * 50, flush=True)
    print("START.PY: Running migrations...", flush=True)
    result = subprocess.run([sys.executable, "run_migrations.py"], check=False)
    if result.returncode != 0:
        print("START.PY: Warning: Migration had issues, continuing anyway...", flush=True)

    # Run multi-tenant organization_id migration
    print("=" * 50, flush=True)
    print("START.PY: Running multi-tenant migration...", flush=True)
    try:
        from migrations.add_multi_tenant_organization_id import run_migration
        success = run_migration()
        if success:
            print("START.PY: Multi-tenant migration completed successfully!", flush=True)
        else:
            print("START.PY: Multi-tenant migration completed with warnings", flush=True)
    except Exception as e:
        print(f"START.PY: Multi-tenant migration error: {e}", flush=True)

    # Get port from environment or default to 8080
    port = os.environ.get("PORT", "8080")
    print(f"START.PY: PORT env var = {os.environ.get('PORT', 'NOT SET')}", flush=True)
    print(f"START.PY: Starting uvicorn on port {port}...", flush=True)
    print("=" * 50, flush=True)

    # Start uvicorn
    os.execvp("uvicorn", [
        "uvicorn",
        "main:app",
        "--host", "0.0.0.0",
        "--port", port
    ])

if __name__ == "__main__":
    main()
