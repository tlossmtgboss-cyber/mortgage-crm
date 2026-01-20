# Step-by-Step Migration Execution Guide

## Step 1: Get Authentication Token

```bash
# Get your auth token
curl -X POST "https://api.perenniaai.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=YOUR_EMAIL&password=YOUR_PASSWORD"
```

This will return:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Copy the `access_token` value.

## Step 2: Run Migration

```bash
# Replace YOUR_TOKEN with the token from Step 1
curl -X POST "https://api.perenniaai.com/api/v1/migrations/add-ai-receptionist-dashboard-tables" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

**Expected Success Response:**
```json
{
  "success": true,
  "message": "Successfully created AI Receptionist Dashboard tables (6 tables, 13 indices)",
  "tables_created": [
    "ai_receptionist_activity",
    "ai_receptionist_metrics_daily",
    "ai_receptionist_skills",
    "ai_receptionist_errors",
    "ai_receptionist_system_health",
    "ai_receptionist_conversations"
  ],
  "already_exists": false
}
```

## Step 3: Verify Tables Exist (Railway Dashboard)

Go to Railway dashboard → Database → Query Editor and run:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name LIKE 'ai_receptionist%'
ORDER BY table_name;
```

**Expected Result:**
```
ai_receptionist_activity
ai_receptionist_conversations
ai_receptionist_errors
ai_receptionist_metrics_daily
ai_receptionist_skills
ai_receptionist_system_health
```

## Step 4: Seed Sample Data

```bash
# Get production DATABASE_URL from Railway
# Go to: Railway Dashboard → Variables → DATABASE_URL

# On your local machine:
cd backend
source ../.venv/bin/activate
export DATABASE_URL="postgresql://user:pass@host:port/db"  # From Railway
python seed_ai_receptionist_dashboard.py
```

**Expected Output:**
```
AI RECEPTIONIST DASHBOARD - DATA SEEDING SCRIPT
================================================================

📊 Seeding activity feed (7 days)...
✅ Created 734 activity feed items

📈 Seeding daily metrics (14 days)...
✅ Created 14 daily metric records

🎯 Seeding AI skills...
✅ Created 12 skill records

🚨 Seeding error logs...
✅ Created 10 error records

💚 Seeding system health...
✅ Created 11 system health records

💬 Seeding conversations...
✅ Created 3 conversation records

================================================================
✅ SEEDING COMPLETE!
================================================================

Total Records: 784
```

## Step 5: Test All Endpoints

```bash
# Use your auth token from Step 1

# Test 1: Activity Feed (should return 200 with data)
curl -X GET "https://api.perenniaai.com/api/v1/ai-receptionist/dashboard/activity/feed?limit=5" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Test 2: Realtime Metrics (should return 200 with metrics)
curl -X GET "https://api.perenniaai.com/api/v1/ai-receptionist/dashboard/metrics/realtime" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Test 3: Skills (should return 200 with skills array)
curl -X GET "https://api.perenniaai.com/api/v1/ai-receptionist/dashboard/skills" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Test 4: ROI (should return 200 with ROI calculations)
curl -X GET "https://api.perenniaai.com/api/v1/ai-receptionist/dashboard/roi" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Test 5: Errors (should return 200 with errors array)
curl -X GET "https://api.perenniaai.com/api/v1/ai-receptionist/dashboard/errors" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Test 6: System Health (should return 200 with health data)
curl -X GET "https://api.perenniaai.com/api/v1/ai-receptionist/dashboard/system-health" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

All should return HTTP 200 with JSON data.

## Step 6: Verify Row Counts

In Railway Query Editor:

```sql
SELECT 'activities' as table_name, COUNT(*) as row_count FROM ai_receptionist_activity
UNION ALL
SELECT 'daily_metrics', COUNT(*) FROM ai_receptionist_metrics_daily
UNION ALL
SELECT 'skills', COUNT(*) FROM ai_receptionist_skills
UNION ALL
SELECT 'errors', COUNT(*) FROM ai_receptionist_errors
UNION ALL
SELECT 'system_health', COUNT(*) FROM ai_receptionist_system_health
UNION ALL
SELECT 'conversations', COUNT(*) FROM ai_receptionist_conversations;
```

**Expected Counts:**
```
activities      | ~700+
daily_metrics   | 14
skills          | 12
errors          | 10
system_health   | 11
conversations   | 3
```

---

## What to Send Me After Completion

1. Screenshot of migration success response
2. Screenshot of table list query results
3. Screenshot of row count query results
4. Output from each curl command (all 6 endpoints)

Then I'll proceed with Phase 2: Integration with AI receptionist.
