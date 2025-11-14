#!/usr/bin/env python3
"""
Trigger AI migration remotely via HTTP endpoint.
This script creates a temporary admin endpoint to run migrations.
"""
import subprocess
import sys
import time

print("=" * 70)
print("🚀 TRIGGERING AI MIGRATION VIA HTTP API")
print("=" * 70)
print()

# Step 1: Add migration endpoint to main.py
print("Step 1: Adding migration endpoint to main.py...")

migration_endpoint_code = '''

# ============================================================================
# TEMPORARY MIGRATION ENDPOINT (Remove after migration completes)
# ============================================================================
@app.post("/admin/run-ai-migration")
async def run_ai_migration_endpoint(secret: str):
    """
    Temporary endpoint to run AI migration remotely.
    Usage: POST /admin/run-ai-migration with body: {"secret": "migrate-ai-2024"}
    """
    import subprocess

    # Simple security check
    if secret != "migrate-ai-2024":
        raise HTTPException(status_code=403, detail="Invalid secret")

    try:
        # Run migration script
        result = subprocess.run(
            ["python3", "run_ai_migration.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app"
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Migration timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/admin/initialize-ai-system")
async def initialize_ai_system_endpoint(secret: str):
    """
    Temporary endpoint to initialize AI system remotely.
    Usage: POST /admin/initialize-ai-system with body: {"secret": "migrate-ai-2024"}
    """
    import subprocess

    # Simple security check
    if secret != "migrate-ai-2024":
        raise HTTPException(status_code=403, detail="Invalid secret")

    try:
        # Run initialization script
        result = subprocess.run(
            ["python3", "initialize_ai_system.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app"
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Initialization timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
'''

# Read current main.py
with open('/Users/timothyloss/my-project/mortgage-crm/backend/main.py', 'r') as f:
    main_content = f.read()

# Check if endpoint already exists
if '/admin/run-ai-migration' in main_content:
    print("✅ Migration endpoint already exists in main.py")
else:
    # Add endpoint before the final lines
    main_content = main_content + migration_endpoint_code

    with open('/Users/timothyloss/my-project/mortgage-crm/backend/main.py', 'w') as f:
        f.write(main_content)

    print("✅ Added migration endpoint to main.py")

print()
print("Step 2: Committing and pushing changes...")

# Git commit and push
subprocess.run(['git', 'add', 'main.py'], check=True, cwd='/Users/timothyloss/my-project/mortgage-crm/backend')
subprocess.run([
    'git', 'commit', '-m',
    'Add temporary admin endpoints for remote migration\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n\nCo-Authored-By: Claude <noreply@anthropic.com>'
], cwd='/Users/timothyloss/my-project/mortgage-crm/backend')
subprocess.run(['git', 'push'], check=True, cwd='/Users/timothyloss/my-project/mortgage-crm/backend')

print("✅ Changes pushed to Railway")
print()
print("Step 3: Waiting for Railway deployment (60 seconds)...")

time.sleep(60)

print()
print("Step 4: Triggering migration via HTTP...")

# Trigger migration
result = subprocess.run([
    'curl', '-s', '-X', 'POST',
    'https://mortgage-crm-production-7a9a.up.railway.app/admin/run-ai-migration',
    '-H', 'Content-Type: application/json',
    '-d', '{"secret": "migrate-ai-2024"}'
], capture_output=True, text=True)

print("Migration Response:")
print(result.stdout)
print()

if '"success": true' in result.stdout:
    print("✅ Migration completed successfully!")
    print()
    print("Step 5: Initializing AI system...")

    result = subprocess.run([
        'curl', '-s', '-X', 'POST',
        'https://mortgage-crm-production-7a9a.up.railway.app/admin/initialize-ai-system',
        '-H', 'Content-Type: application/json',
        '-d', '{"secret": "migrate-ai-2024"}'
    ], capture_output=True, text=True)

    print("Initialization Response:")
    print(result.stdout)
    print()

    if '"success": true' in result.stdout:
        print("=" * 70)
        print("🎉 AI SYSTEM SETUP COMPLETE!")
        print("=" * 70)
        sys.exit(0)
    else:
        print("❌ Initialization failed")
        sys.exit(1)
else:
    print("❌ Migration failed")
    sys.exit(1)
