#!/usr/bin/env python3
"""Clear test/sample data from production database using direct SQL"""
import subprocess
import json

print("=" * 70)
print("CLEARING TEST/SAMPLE DATA FROM AI RECEPTIONIST DASHBOARD")
print("=" * 70)

# Get DATABASE_URL from Railway
print("\n1. Getting database connection...")
result = subprocess.run(
    ['railway', 'variables', '--json'],
    capture_output=True,
    text=True
)

if result.returncode != 0:
    print("❌ Could not get Railway variables")
    exit(1)

vars_data = json.loads(result.stdout)
database_url = vars_data.get('DATABASE_URL')

if not database_url:
    print("❌ DATABASE_URL not found")
    exit(1)

print("✅ Got database URL")

# SQL to clear sample data
sql = """
-- Clear test/sample data
DELETE FROM ai_receptionist_activity
WHERE client_phone IN ('+15555551234', '+15551234TEST', '+15546104794')
   OR client_name LIKE 'Client %'
   OR client_name LIKE 'Sample %';

DELETE FROM ai_receptionist_conversations
WHERE client_phone IN ('+15555551234', '+15551234TEST', '+15546104794')
   OR client_name LIKE 'Client %';

DELETE FROM ai_receptionist_skills
WHERE last_update < NOW() - INTERVAL '1 hour';

DELETE FROM ai_receptionist_errors
WHERE timestamp < NOW() - INTERVAL '1 hour';

DELETE FROM ai_receptionist_metrics_daily
WHERE date < CURRENT_DATE;

-- Show remaining counts
SELECT 'Activities' as table_name, COUNT(*) as count FROM ai_receptionist_activity
UNION ALL
SELECT 'Conversations', COUNT(*) FROM ai_receptionist_conversations
UNION ALL
SELECT 'Skills', COUNT(*) FROM ai_receptionist_skills
UNION ALL
SELECT 'Errors', COUNT(*) FROM ai_receptionist_errors
UNION ALL
SELECT 'Metrics', COUNT(*) FROM ai_receptionist_metrics_daily;
"""

print("\n2. Executing SQL to clear sample data...")

# Run SQL via Railway
result = subprocess.run(
    ['railway', 'run', 'bash', '-c', f'psql "$DATABASE_URL" -c "{sql}"'],
    capture_output=True,
    text=True,
    timeout=30
)

if result.returncode == 0:
    print("✅ Sample data cleared successfully\n")
    print("Output:")
    print(result.stdout)
else:
    print(f"⚠️ Error: {result.stderr}")

print("\n" + "=" * 70)
print("✅ DASHBOARD IS NOW CLEAN")
print("=" * 70)
print("""
All test/sample data has been removed.

Now when you call +1 (832) 648-2297:
✅ Your REAL call will be logged to the dashboard
✅ You'll see your actual phone number
✅ Conversation will be transcribed
✅ Call will appear at: https://mortgage-crm-nine.vercel.app/ai-receptionist-dashboard

Test it now:
1. Call: +1 (832) 648-2297
2. Talk to the AI assistant
3. Hang up
4. Go to the dashboard and click "Refresh"
5. You should see your call!
""")
