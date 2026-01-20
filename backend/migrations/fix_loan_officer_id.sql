-- Fix loan_officer_id for imported loans
UPDATE loans SET loan_officer_id = 118 WHERE organization_id = 1;
