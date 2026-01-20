-- Check task assignments
SELECT assigned_to_id, COUNT(*) as count
FROM ai_tasks
GROUP BY assigned_to_id;
