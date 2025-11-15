# Production Database Connection Guide

## Overview
This guide covers all aspects of connecting to and working with your Railway PostgreSQL production database.

---

## ⚠️ DATABASE_URL Verification Needed

**Issue Detected:** The DATABASE_URL you provided appears to be malformed:
```
postgresql://postgres:RzXRIwJsZINuRwMQybDbZYqfFoHBaXRwd3svitchback.proxy.rlwy.net:38467/railway
```

**Problem:** Missing `@` symbol between password and hostname.

**Expected Format:**
```
postgresql://postgres:PASSWORD@HOSTNAME:PORT/DATABASE
```

**How to Get Correct URL:**
1. Go to Railway Dashboard: https://railway.app
2. Open project: "balanced-achievement"
3. Click on the **PostgreSQL** service (not the mortgage-crm service)
4. Go to **Variables** or **Connect** tab
5. Look for `DATABASE_PUBLIC_URL` or copy the connection string

The correct URL should look like:
```
postgresql://postgres:PASSWORD@something.proxy.rlwy.net:PORT/railway
```

---

## TASK 1: Test Production Database Connection

### Using Python (SQLAlchemy)

**Script:** `backend/test_production_db_connection.py`

```python
#!/usr/bin/env python3
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

# REPLACE WITH YOUR CORRECT DATABASE_URL
PROD_DB_URL = "postgresql://postgres:PASSWORD@HOST:PORT/railway"

engine = create_engine(PROD_DB_URL)

with engine.connect() as conn:
    result = conn.execute(text("SELECT version()"))
    print(f"✅ Connected! PostgreSQL version: {result.scalar()}")
```

**Run:**
```bash
source .venv/bin/activate
cd backend
python test_production_db_connection.py
```

### Using psql Command Line

```bash
psql "postgresql://postgres:PASSWORD@HOST:PORT/railway" -c "SELECT version();"
```

### Using Railway CLI

```bash
railway connect
# Then in the shell that opens:
psql $DATABASE_URL
```

---

## TASK 2: Run Mission Control Systems Check on Production DB

### Update Test Script for Production

Create `backend/test_mission_control_production.py`:

```python
#!/usr/bin/env python3
"""
Mission Control Systems Check - Production Database
"""
import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text, inspect

# Use production database
PROD_DB_URL = os.getenv("PROD_DATABASE_URL", "postgresql://postgres:PASSWORD@HOST:PORT/railway")

print("="*70)
print("MISSION CONTROL PRODUCTION SYSTEMS CHECK")
print("="*70)
print(f"Database: Production PostgreSQL (Railway)")
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

engine = create_engine(PROD_DB_URL)
inspector = inspect(engine)

# Check Mission Control tables
required_tables = [
    "ai_colleague_actions",
    "ai_colleague_learning_metrics",
    "ai_performance_daily",
    "ai_journey_insights",
    "ai_health_score"
]

print("Checking Mission Control Tables:")
for table in required_tables:
    if table in inspector.get_table_names():
        columns = inspector.get_columns(table)
        print(f"  ✅ {table} ({len(columns)} columns)")
    else:
        print(f"  ❌ {table} MISSING")

# Count data
print("\nChecking Data:")
with engine.connect() as conn:
    for table in required_tables:
        try:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"  {table}: {count} records")
        except Exception as e:
            print(f"  {table}: Error - {str(e)}")

# Test health score function
print("\nTesting Health Score Function:")
try:
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT * FROM calculate_ai_health_score(
                NOW() - INTERVAL '7 days',
                NOW()
            )
        """))
        health = result.fetchone()
        if health:
            print(f"  ✅ Overall Score: {health[0]:.2f}")
            print(f"  ✅ Autonomy Score: {health[1]:.2f}")
            print(f"  ✅ Total Actions: {health[6]}")
        else:
            print("  ⚠️ No data yet")
except Exception as e:
    print(f"  ❌ Error: {str(e)}")

print("\n" + "="*70)
print("SYSTEMS CHECK COMPLETE")
print("="*70)
```

**Run:**
```bash
export PROD_DATABASE_URL="your_correct_database_url_here"
source .venv/bin/activate
cd backend
python test_mission_control_production.py
```

---

## TASK 3: Query Production Data for Mission Control Metrics

### Create Query Script

`backend/query_mission_control_data.py`:

```python
#!/usr/bin/env python3
"""
Query Mission Control Production Data
"""
import os
from sqlalchemy import create_engine, text
from datetime import datetime
import json

PROD_DB_URL = os.getenv("PROD_DATABASE_URL")

engine = create_engine(PROD_DB_URL)

print("="*70)
print("MISSION CONTROL DATA QUERY")
print("="*70)
print()

with engine.connect() as conn:
    # Query 1: Recent Actions
    print("RECENT AI ACTIONS (Last 10):")
    print("-" * 70)
    result = conn.execute(text("""
        SELECT
            agent_name,
            action_type,
            outcome,
            confidence_score,
            created_at
        FROM ai_colleague_actions
        ORDER BY created_at DESC
        LIMIT 10
    """))

    for row in result:
        print(f"{row[0]:20} | {row[1]:25} | {row[2]:10} | {row[3]:.2f} | {row[4]}")

    print()

    # Query 2: Agent Performance Summary
    print("AGENT PERFORMANCE SUMMARY:")
    print("-" * 70)
    result = conn.execute(text("""
        SELECT
            agent_name,
            COUNT(*) as total_actions,
            COUNT(*) FILTER (WHERE outcome = 'success') as successful,
            AVG(confidence_score) as avg_confidence,
            AVG(impact_score) as avg_impact
        FROM ai_colleague_actions
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY agent_name
        ORDER BY total_actions DESC
    """))

    for row in result:
        success_rate = (row[2] / row[1] * 100) if row[1] > 0 else 0
        print(f"{row[0]:25} | {row[1]:5} actions | {success_rate:5.1f}% success | {row[3]:.2f} conf | {row[4]:.2f} impact")

    print()

    # Query 3: Daily Performance Trends
    print("DAILY PERFORMANCE TRENDS (Last 7 Days):")
    print("-" * 70)
    result = conn.execute(text("""
        SELECT
            DATE(created_at) as day,
            COUNT(*) as actions,
            COUNT(*) FILTER (WHERE autonomy_level = 'full') as autonomous,
            COUNT(*) FILTER (WHERE outcome = 'success') as successful
        FROM ai_colleague_actions
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY DATE(created_at)
        ORDER BY day DESC
    """))

    for row in result:
        auto_pct = (row[2] / row[1] * 100) if row[1] > 0 else 0
        success_pct = (row[3] / row[1] * 100) if row[1] > 0 else 0
        print(f"{row[0]} | {row[1]:4} actions | {auto_pct:5.1f}% autonomous | {success_pct:5.1f}% successful")

    print()

    # Query 4: Health Score Over Time
    print("HEALTH SCORE HISTORY:")
    print("-" * 70)
    result = conn.execute(text("""
        SELECT
            calculated_at,
            overall_score,
            autonomy_score,
            accuracy_score,
            total_actions
        FROM ai_health_score
        ORDER BY calculated_at DESC
        LIMIT 5
    """))

    for row in result:
        print(f"{row[0]} | Overall: {row[1]:5.1f} | Autonomy: {row[2]:5.1f} | Accuracy: {row[3]:5.1f} | Actions: {row[4]}")

    print()
    print("="*70)
```

**Run:**
```bash
export PROD_DATABASE_URL="your_database_url"
source .venv/bin/activate
cd backend
python query_mission_control_data.py
```

---

## TASK 4: Update Local .env with Production Database URL

### Backup Current .env

```bash
cp backend/.env backend/.env.backup
```

### Add Production Database Variable

Edit `backend/.env` and add:

```bash
# Production Database (Railway)
PROD_DATABASE_URL=postgresql://postgres:PASSWORD@HOST:PORT/railway

# Keep local for development
DATABASE_URL=sqlite:///./test_agentic_crm.db
```

### Create Environment Switcher

`backend/use_production_db.sh`:

```bash
#!/bin/bash
# Switch to production database
export DATABASE_URL=$PROD_DATABASE_URL
echo "✅ Switched to PRODUCTION database"
echo "URL: ${DATABASE_URL}"
```

`backend/use_local_db.sh`:

```bash
#!/bin/bash
# Switch to local database
export DATABASE_URL="sqlite:///./test_agentic_crm.db"
echo "✅ Switched to LOCAL database"
echo "URL: ${DATABASE_URL}"
```

**Usage:**
```bash
source backend/use_production_db.sh  # Switch to production
python backend/test_mission_control.py

source backend/use_local_db.sh  # Switch back to local
```

---

## TASK 5: Database Client Connection Instructions

### Option 1: TablePlus (Recommended - GUI)

**Download:** https://tableplus.com/

**Connection Settings:**
- **Type:** PostgreSQL
- **Name:** Railway Production CRM
- **Host:** `switchback.proxy.rlwy.net` (or your correct host)
- **Port:** `38467` (or your correct port)
- **User:** `postgres`
- **Password:** `RzXRIwJsZINuRwMQybbbZYqYFoHBaxRw` (or your correct password)
- **Database:** `railway`
- **SSL:** Enabled (prefer)

**Steps:**
1. Open TablePlus
2. Click "Create a new connection"
3. Select "PostgreSQL"
4. Enter the details above
5. Click "Test" to verify
6. Click "Connect"

### Option 2: pgAdmin (GUI)

**Download:** https://www.pgadmin.org/

**Connection Steps:**
1. Right-click "Servers" → "Register" → "Server"
2. **General Tab:**
   - Name: Railway Production CRM
3. **Connection Tab:**
   - Host: `switchback.proxy.rlwy.net`
   - Port: `38467`
   - Database: `railway`
   - Username: `postgres`
   - Password: `RzXRIwJsZINuRwMQybbbZYqYFoHBaxRw`
4. **SSL Tab:**
   - SSL mode: Prefer
5. Click "Save"

### Option 3: psql (Command Line)

**Install psql:**
```bash
# macOS
brew install postgresql

# Ubuntu/Debian
sudo apt-get install postgresql-client
```

**Connect:**
```bash
psql "postgresql://postgres:PASSWORD@HOST:PORT/railway"

# Or with environment variable:
export PROD_DATABASE_URL="postgresql://postgres:PASSWORD@HOST:PORT/railway"
psql $PROD_DATABASE_URL
```

**Common psql Commands:**
```sql
\l                  -- List databases
\dt                 -- List tables
\d table_name       -- Describe table
\q                  -- Quit

-- Query examples:
SELECT COUNT(*) FROM ai_colleague_actions;
SELECT * FROM ai_colleague_actions LIMIT 10;
```

### Option 4: DBeaver (Free, Cross-Platform)

**Download:** https://dbeaver.io/

**Connection Steps:**
1. Click "New Database Connection"
2. Select "PostgreSQL"
3. Enter connection details
4. Test connection
5. Connect

### Option 5: DataGrip (JetBrains - Paid)

**Download:** https://www.jetbrains.com/datagrip/

**Connection Steps:**
1. Click "+" → "Data Source" → "PostgreSQL"
2. Enter connection details
3. Download drivers if prompted
4. Test connection
5. Apply

---

## TASK 6: Run Specific Diagnostic Queries

### Query Collection

Create `backend/diagnostic_queries.sql`:

```sql
-- ============================================================================
-- MISSION CONTROL DIAGNOSTIC QUERIES
-- ============================================================================

-- Query 1: Table Sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
    AND tablename LIKE 'ai_%'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Query 2: Index Usage
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
    AND tablename LIKE 'ai_%'
ORDER BY idx_scan DESC;

-- Query 3: Recent Actions Detail
SELECT
    action_id,
    agent_name,
    action_type,
    autonomy_level,
    confidence_score,
    status,
    outcome,
    impact_score,
    reasoning,
    created_at,
    completed_at
FROM ai_colleague_actions
ORDER BY created_at DESC
LIMIT 20;

-- Query 4: Agent Performance Matrix
SELECT
    agent_name,
    COUNT(*) as total_actions,
    COUNT(*) FILTER (WHERE autonomy_level = 'full') as autonomous_count,
    ROUND(COUNT(*) FILTER (WHERE autonomy_level = 'full')::NUMERIC / COUNT(*) * 100, 2) as autonomy_rate,
    COUNT(*) FILTER (WHERE outcome = 'success') as success_count,
    ROUND(COUNT(*) FILTER (WHERE outcome = 'success')::NUMERIC / COUNT(*) * 100, 2) as success_rate,
    ROUND(AVG(confidence_score)::NUMERIC, 3) as avg_confidence,
    ROUND(AVG(impact_score)::NUMERIC, 3) as avg_impact
FROM ai_colleague_actions
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY agent_name
ORDER BY total_actions DESC;

-- Query 5: Hourly Activity Pattern
SELECT
    DATE_TRUNC('hour', created_at) as hour,
    COUNT(*) as actions,
    COUNT(*) FILTER (WHERE outcome = 'success') as successful,
    AVG(confidence_score) as avg_confidence
FROM ai_colleague_actions
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE_TRUNC('hour', created_at)
ORDER BY hour DESC
LIMIT 168; -- 7 days * 24 hours

-- Query 6: Failed Actions Analysis
SELECT
    agent_name,
    action_type,
    COUNT(*) as failure_count,
    AVG(confidence_score) as avg_confidence_when_failed,
    MAX(created_at) as last_failure
FROM ai_colleague_actions
WHERE outcome = 'failure'
    AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY agent_name, action_type
ORDER BY failure_count DESC;

-- Query 7: Learning Metrics Trends
SELECT
    metric_type,
    metric_name,
    COUNT(*) as measurement_count,
    AVG(metric_value) as avg_value,
    AVG(improvement_percentage) as avg_improvement,
    MAX(measured_at) as last_measured
FROM ai_colleague_learning_metrics
WHERE measured_at >= NOW() - INTERVAL '30 days'
GROUP BY metric_type, metric_name
ORDER BY avg_improvement DESC;

-- Query 8: Daily Rollup Summary
SELECT
    date,
    agent_name,
    total_actions,
    autonomous_actions,
    success_rate,
    avg_confidence_score,
    avg_impact_score
FROM ai_performance_daily
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY date DESC, agent_name;

-- Query 9: Active Insights
SELECT
    insight_id,
    insight_type,
    pattern_description,
    pattern_confidence,
    recommended_action,
    expected_impact,
    priority,
    discovered_at
FROM ai_journey_insights
WHERE status = 'active'
    AND (expires_at IS NULL OR expires_at > NOW())
ORDER BY priority DESC, pattern_confidence DESC;

-- Query 10: Health Score Trend
SELECT
    calculated_at,
    overall_score,
    autonomy_score,
    accuracy_score,
    efficiency_score,
    learning_score,
    impact_score,
    total_actions,
    score_trend
FROM ai_health_score
ORDER BY calculated_at DESC
LIMIT 30;

-- Query 11: Check for Data Issues
SELECT
    'Orphaned Learning Metrics' as issue,
    COUNT(*) as count
FROM ai_colleague_learning_metrics lm
LEFT JOIN ai_colleague_actions a ON lm.action_id = a.action_id
WHERE a.action_id IS NULL

UNION ALL

SELECT
    'Actions Without Completion Time' as issue,
    COUNT(*) as count
FROM ai_colleague_actions
WHERE status = 'completed' AND completed_at IS NULL

UNION ALL

SELECT
    'Negative Confidence Scores' as issue,
    COUNT(*) as count
FROM ai_colleague_actions
WHERE confidence_score < 0 OR confidence_score > 1;

-- Query 12: Top Performing Actions
SELECT
    agent_name,
    action_type,
    AVG(confidence_score) as avg_confidence,
    AVG(impact_score) as avg_impact,
    COUNT(*) as count
FROM ai_colleague_actions
WHERE outcome = 'success'
    AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY agent_name, action_type
HAVING COUNT(*) >= 5
ORDER BY AVG(impact_score) DESC, AVG(confidence_score) DESC
LIMIT 20;
```

### Run Queries Using psql

```bash
psql $PROD_DATABASE_URL -f backend/diagnostic_queries.sql > diagnostic_results.txt
cat diagnostic_results.txt
```

### Run Queries Using Python

```python
#!/usr/bin/env python3
import os
from sqlalchemy import create_engine, text

PROD_DB_URL = os.getenv("PROD_DATABASE_URL")
engine = create_engine(PROD_DB_URL)

# Read SQL file
with open('backend/diagnostic_queries.sql', 'r') as f:
    queries = f.read().split(';')

with engine.connect() as conn:
    for i, query in enumerate(queries, 1):
        query = query.strip()
        if query and not query.startswith('--'):
            print(f"\n{'='*70}")
            print(f"QUERY {i}")
            print(f"{'='*70}\n")
            try:
                result = conn.execute(text(query))
                for row in result:
                    print(row)
            except Exception as e:
                print(f"Error: {e}")
```

---

## Quick Reference

### Environment Variables
```bash
# Local Development
DATABASE_URL=sqlite:///./test_agentic_crm.db

# Production (Railway)
PROD_DATABASE_URL=postgresql://postgres:PASSWORD@HOST:PORT/railway
```

### Connection String Format
```
postgresql://USERNAME:PASSWORD@HOSTNAME:PORT/DATABASE
```

### Common Operations
```bash
# Test connection
psql $PROD_DATABASE_URL -c "SELECT version();"

# List tables
psql $PROD_DATABASE_URL -c "\dt"

# Count Mission Control actions
psql $PROD_DATABASE_URL -c "SELECT COUNT(*) FROM ai_colleague_actions;"

# Run diagnostic queries
psql $PROD_DATABASE_URL -f backend/diagnostic_queries.sql
```

---

## Troubleshooting

### Connection Refused
- Check if Railway PostgreSQL service is running
- Verify the port number is correct
- Check firewall settings

### Authentication Failed
- Verify password is correct
- Check for special characters that need URL encoding
- Try resetting the database password in Railway dashboard

### Host Not Found
- Verify the hostname is correct
- Check your internet connection
- Try using the Railway CLI: `railway connect`

### SSL Required
- Add `?sslmode=require` to connection string
- Or use: `postgresql://user:pass@host:port/db?sslmode=require`

---

## Security Best Practices

1. **Never commit database URLs to git**
   - Add `.env` to `.gitignore`
   - Use environment variables

2. **Use read-only credentials for queries**
   - Create a separate read-only user for analytics

3. **Rotate passwords regularly**
   - Update in Railway dashboard
   - Update in local `.env`

4. **Use SSL/TLS for connections**
   - Always use `sslmode=require` for production

5. **Limit connection pooling**
   - Don't create too many simultaneous connections

---

## Next Steps

1. ✅ Verify the correct DATABASE_URL from Railway dashboard
2. ✅ Test connection using psql or Python script
3. ✅ Run Mission Control systems check on production
4. ✅ Query production data to verify Mission Control is working
5. ✅ Set up your preferred database client
6. ✅ Run diagnostic queries to check system health

---

*Last Updated: November 15, 2025*
