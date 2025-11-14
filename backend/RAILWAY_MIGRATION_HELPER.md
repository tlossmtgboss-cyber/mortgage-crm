# Railway Migration Helper

## Issue: Railway CLI Service Linkage

The Railway CLI is authenticated but cannot find services to link to in the current directory. This is a common issue when projects are set up through the Railway web interface.

## Solution: Run Migration with Direct DATABASE_URL

Follow these steps to complete the AI system setup:

### Option 1: Using Railway Dashboard (Recommended - 2 minutes)

1. **Get DATABASE_URL from Railway Dashboard:**
   - Go to: https://railway.app/dashboard
   - Select project: `mortgage-crm`
   - Click on your backend service
   - Go to "Variables" tab
   - Copy the `DATABASE_URL` value (starts with `postgresql://`)

2. **Run Migration:**
   ```bash
   cd /Users/timothyloss/my-project/mortgage-crm/backend
   export DATABASE_URL="<paste-your-database-url-here>"
   python3 run_ai_migration.py
   ```

3. **Initialize AI System:**
   ```bash
   python3 initialize_ai_system.py
   ```

### Option 2: Using Railway Web Terminal (Easiest - 5 minutes)

1. Go to: https://railway.app/dashboard
2. Select project: `mortgage-crm`
3. Click on your backend service
4. Click "Terminal" or "Shell" button
5. Run these commands directly in the Railway terminal:
   ```bash
   cd /app
   python3 run_ai_migration.py
   python3 initialize_ai_system.py
   ```

### Option 3: Fix Railway CLI Linkage (Advanced)

If you want to fix the Railway CLI for future use:

1. Check Railway project structure:
   ```bash
   railway list
   ```

2. Manually link service (Railway will prompt for selection):
   ```bash
   cd /Users/timothyloss/my-project/mortgage-crm/backend
   railway unlink
   railway link
   # Select: mortgage-crm project
   # Select: backend service (or whichever service runs your FastAPI app)
   ```

3. Verify linkage:
   ```bash
   railway status
   ```

4. Then run:
   ```bash
   railway run python3 run_ai_migration.py
   railway run python3 initialize_ai_system.py
   ```

## What These Scripts Do

### `run_ai_migration.py`
- Creates 20+ AI tables in PostgreSQL database
- Safe to run multiple times (uses `CREATE TABLE IF NOT EXISTS`)
- Creates:
  - Agent management tables
  - Tool registry
  - Execution tracking
  - Self-improvement infrastructure
  - Long-term memory & knowledge graph

### `initialize_ai_system.py`
- Registers 7 AI agents
- Registers 15+ tools
- Creates initial prompt versions
- Verifies setup

## Expected Output

After successful migration, you should see:
```
✅ Migration completed!
✅ Found 20 AI tables
```

After initialization:
```
✅ Successfully registered 7/7 agents
✅ Successfully registered 15/15 tools
✅ AI system is ready!
```

## Testing After Setup

```bash
# Test 1: List agents
curl https://mortgage-crm-production-7a9a.up.railway.app/api/ai/agents

# Test 2: Check system health
curl https://mortgage-crm-production-7a9a.up.railway.app/health
```

## Need Help?

If you encounter errors:
1. Check that DATABASE_URL is correctly set and points to PostgreSQL (not SQLite)
2. Verify the database is accessible
3. Check Railway logs for any connection issues

## Next Steps

Once migration and initialization complete successfully, the AI system will be fully operational and ready to:
- Automatically triage leads
- Monitor pipeline progress
- Classify documents
- Engage customers
- Analyze portfolio for opportunities
- And more...

See `COMPLETE_AI_SETUP.md` for full feature list and business impact.
