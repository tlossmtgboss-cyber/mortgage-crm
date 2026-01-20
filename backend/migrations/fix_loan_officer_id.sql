-- Fix loan_officer_id for imported loans
UPDATE loans SET loan_officer_id = 118 WHERE organization_id = 1;

-- Fix task assignments to match loan_officer_id for multi-tenancy
UPDATE ai_tasks
SET assigned_to_id = loans.loan_officer_id
FROM loans
WHERE ai_tasks.loan_id = loans.id
AND loans.loan_officer_id IS NOT NULL
AND (ai_tasks.assigned_to_id IS NULL OR ai_tasks.assigned_to_id != loans.loan_officer_id);
