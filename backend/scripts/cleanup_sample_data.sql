-- Sample Data Cleanup SQL Script
-- Run this against your production database to remove all sample data
-- IMPORTANT: This will DELETE data permanently. Make sure you have a backup!

-- Admin email to preserve (change if needed)
-- This script preserves admin@perenniaai.com

BEGIN;

-- Step 1: Delete all tasks
DELETE FROM tasks;
DELETE FROM task_instances;
DELETE FROM purl_tasks;

-- Step 2: Delete team members and profiles
DELETE FROM team_members;
DELETE FROM team_member_profiles;

-- Step 3: Delete extracted data (reconciliation)
DELETE FROM extracted_data;

-- Step 4: Delete referral partners
DELETE FROM referral_partners;

-- Step 5: Get the admin user ID (to preserve)
-- First, verify the admin exists
SELECT id, email, full_name, role FROM users WHERE email = 'admin@perenniaai.com';

-- Step 6: Delete all users EXCEPT admin@perenniaai.com
-- Run this after confirming the admin user exists in Step 5
DELETE FROM users WHERE email != 'admin@perenniaai.com';

-- Step 7: Delete suspended and cancelled accounts
DELETE FROM tenant_accounts WHERE status IN ('suspended', 'canceled');

-- Step 8: Clean up account management data (optional - run if needed)
-- DELETE FROM subscription_events;
-- DELETE FROM account_subscriptions;
-- DELETE FROM account_invoices;
-- DELETE FROM cost_ledger_monthly;
-- DELETE FROM login_events;
-- DELETE FROM admin_audit_log;

COMMIT;

-- Verify remaining data
SELECT 'users' as table_name, COUNT(*) as count FROM users
UNION ALL
SELECT 'tasks', COUNT(*) FROM tasks
UNION ALL
SELECT 'team_members', COUNT(*) FROM team_members
UNION ALL
SELECT 'tenant_accounts', COUNT(*) FROM tenant_accounts;
