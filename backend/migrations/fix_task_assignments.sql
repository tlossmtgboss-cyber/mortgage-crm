-- Fix task assignments to match loan_officer_id
-- This ensures multi-tenancy by reassigning tasks to the correct user

-- Update tasks that are associated with loans to use the loan's loan_officer_id
UPDATE ai_tasks
SET assigned_to_id = loans.loan_officer_id
FROM loans
WHERE ai_tasks.loan_id = loans.id
AND loans.loan_officer_id IS NOT NULL
AND (ai_tasks.assigned_to_id IS NULL OR ai_tasks.assigned_to_id != loans.loan_officer_id);
