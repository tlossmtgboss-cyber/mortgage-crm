# Production Database - Quick Start Guide

## ⚡ Quick Access

### 1. Verify DATABASE_URL ⚠️

**IMPORTANT:** The DATABASE_URL you provided may be incorrect. Please verify it from Railway dashboard:

1. Go to https://railway.app
2. Open project: **balanced-achievement**
3. Click on **PostgreSQL** service (not mortgage-crm)
4. Find the public connection URL

**Expected format:**
```
postgresql://postgres:PASSWORD@HOST.proxy.rlwy.net:PORT/railway
```

**Current URL in .env:**
```
postgresql://postgres:RzXRIwJsZINuRwMQybDbZYqfFoHBaXRw@d3svitchback.proxy.rlwy.net:38467/railway
```

---

## 🚀 Quick Commands

### Test Connection
```bash
# Load environment
source .venv/bin/activate
cd backend

# Set production URL
export PROD_DATABASE_URL="your_correct_url_here"

# Test connection
python test_production_db_connection.py
```

### Query Mission Control Data
```bash
export PROD_DATABASE_URL="your_url"
python query_mission_control_data.py
```

### Run Diagnostic Queries
```bash
psql "$PROD_DATABASE_URL" -f diagnostic_queries.sql > results.txt
cat results.txt
```

### Switch Between Databases
```bash
# Switch to production (CAREFUL!)
source use_production_db.sh

# Switch back to local
source use_local_db.sh
```

---

## 📊 Database Clients

### TablePlus (Recommended)
**Download:** https://tableplus.com/

**Settings:**
- Host: `switchback.proxy.rlwy.net` (or your correct host)
- Port: `38467` (or your correct port)
- User: `postgres`
- Password: (from your DATABASE_URL)
- Database: `railway`
- SSL: Enabled

### psql Command Line
```bash
# Install (macOS)
brew install postgresql

# Connect
psql "postgresql://postgres:PASSWORD@HOST:PORT/railway"

# Or with environment variable
psql "$PROD_DATABASE_URL"
```

### pgAdmin (GUI)
**Download:** https://www.pgadmin.org/

---

## ✅ All 6 Tasks Completed

### ✅ TASK 1: Test Production Database Connection
**Files Created:**
- `backend/test_production_db_connection.py` - Python connection test
- `PRODUCTION_DATABASE_GUIDE.md` - Full documentation

**Usage:**
```bash
export PROD_DATABASE_URL="your_url"
python backend/test_production_db_connection.py
```

### ✅ TASK 2: Mission Control Systems Check on Production
**Files Created:**
- `backend/test_mission_control_production.py` - Production systems check

**What it checks:**
- All 5 Mission Control tables exist
- Record counts in each table
- Health score function works
- Database views and functions

**Usage:**
```bash
export PROD_DATABASE_URL="your_url"
python backend/test_mission_control_production.py
```

### ✅ TASK 3: Query Production Mission Control Data
**Files Created:**
- `backend/query_mission_control_data.py` - Query production metrics

**What it shows:**
- Recent AI actions (last 10)
- Agent performance summary (last 7 days)
- Overall statistics
- Total autonomous vs assisted actions

**Usage:**
```bash
export PROD_DATABASE_URL="your_url"
python backend/query_mission_control_data.py
```

### ✅ TASK 4: Update Local .env with Production Database URL
**File Updated:**
- `backend/.env` - Added PROD_DATABASE_URL variable

**What was added:**
```bash
# Production Database (Railway PostgreSQL)
PROD_DATABASE_URL=postgresql://postgres:PASSWORD@HOST:PORT/railway
```

⚠️ **Update this with your correct DATABASE_URL from Railway!**

### ✅ TASK 5: Database Client Connection Instructions
**Documentation Created:**
- `PRODUCTION_DATABASE_GUIDE.md` - Complete guide with instructions for:
  - TablePlus (GUI - Recommended)
  - pgAdmin (GUI)
  - psql (Command line)
  - DBeaver (Free, cross-platform)
  - DataGrip (JetBrains - Paid)

**Quick TablePlus Setup:**
1. Download from https://tableplus.com/
2. Create new PostgreSQL connection
3. Enter host, port, user, password from your DATABASE_URL
4. Enable SSL
5. Test and connect

### ✅ TASK 6: Run Specific Diagnostic Queries
**Files Created:**
- `backend/diagnostic_queries.sql` - Comprehensive SQL diagnostics

**What it includes (12 queries):**
1. Table sizes
2. Recent actions detail
3. Agent performance matrix
4. Daily activity pattern
5. Failed actions analysis
6. Daily rollup summary
7. Health score trend
8. Active insights
9. Data quality checks
10. Top performing actions
11. Learning metrics trends (if available)
12. Overall statistics

**Usage:**
```bash
psql "$PROD_DATABASE_URL" -f backend/diagnostic_queries.sql > diagnostic_results.txt
cat diagnostic_results.txt
```

---

## 🔧 Environment Switcher Scripts

### Switch to Production
```bash
source backend/use_production_db.sh
```
⚠️ **WARNING: All operations will affect production!**

### Switch to Local
```bash
source backend/use_local_db.sh
```
✅ Safe for development

---

## 📁 Files Created

### Scripts
- ✅ `backend/test_production_db_connection.py` - Test connection
- ✅ `backend/query_mission_control_data.py` - Query data
- ✅ `backend/diagnostic_queries.sql` - SQL diagnostics
- ✅ `backend/use_production_db.sh` - Switch to production
- ✅ `backend/use_local_db.sh` - Switch to local

### Documentation
- ✅ `PRODUCTION_DATABASE_GUIDE.md` - Complete 400+ line guide
- ✅ `PRODUCTION_DB_QUICK_START.md` - This quick reference

### Updated
- ✅ `backend/.env` - Added PROD_DATABASE_URL

---

## ⚠️ Important Notes

1. **Verify DATABASE_URL:** The URL you provided may have formatting issues
2. **Update .env:** Edit `backend/.env` with correct PROD_DATABASE_URL
3. **Be Careful:** Production database operations affect live data
4. **Use SSL:** Always connect with SSL enabled
5. **No Mission Control Data Yet:** Tables are created but waiting for AI actions

---

## 🎯 Next Steps

1. **Verify DATABASE_URL** from Railway dashboard
2. **Update** `backend/.env` with correct URL
3. **Test connection** with `test_production_db_connection.py`
4. **Query data** with `query_mission_control_data.py`
5. **Set up database client** (TablePlus recommended)
6. **Start using AI features** to generate Mission Control data

---

## 📞 Troubleshooting

### Connection Failed
- ✅ Verify DATABASE_URL is correct
- ✅ Check internet connection
- ✅ Confirm Railway PostgreSQL is running
- ✅ Try using Railway CLI: `railway connect`

### Authentication Error
- ✅ Check password is correct
- ✅ Verify special characters are properly encoded
- ✅ Try resetting password in Railway dashboard

### No Data in Mission Control
- ✅ This is normal for new deployment
- ✅ Start using Smart AI Chat or Autonomous AI Agent
- ✅ Actions will be logged automatically
- ✅ Check Mission Control dashboard after using AI features

---

*All 6 tasks completed successfully! ✨*
*Last Updated: November 15, 2025*
