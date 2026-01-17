-- ===================================================================
-- COMPREHENSIVE SAMPLE DATA REMOVAL SCRIPT
-- ===================================================================
-- This script removes ALL sample data from the CRM database
-- IMPORTANT: Replace 'YOUR_ADMIN_EMAIL_HERE' with your actual admin email
-- before running this script!
-- ===================================================================

BEGIN;

-- Step 1: Identify your admin account
-- CRITICAL: Update this email to YOUR admin email address
DO $$
DECLARE
    v_admin_email TEXT := 'YOUR_ADMIN_EMAIL_HERE';  -- CHANGE THIS!
    v_admin_user_id UUID;
    v_admin_tenant_id UUID;
BEGIN
    -- Get admin user and tenant IDs
    SELECT id, tenant_account_id INTO v_admin_user_id, v_admin_tenant_id
    FROM users 
    WHERE email = v_admin_email;
    
    IF v_admin_user_id IS NULL THEN
        RAISE EXCEPTION 'Admin user not found with email: %', v_admin_email;
    END IF;
    
    RAISE NOTICE 'Found admin user: % (ID: %)', v_admin_email, v_admin_user_id;
    RAISE NOTICE 'Admin tenant ID: %', v_admin_tenant_id;
    
    -- Store in temp table for reference
    CREATE TEMP TABLE admin_info AS
    SELECT v_admin_user_id as user_id, v_admin_tenant_id as tenant_id;
END $$;

-- Step 2: Delete all tasks (except admin's)
DELETE FROM tasks
WHERE assigned_to NOT IN (SELECT user_id FROM admin_info)
   OR created_by NOT IN (SELECT user_id FROM admin_info);

RAISE NOTICE 'Deleted sample tasks';

-- Step 3: Delete all team members (keep only admin)
DELETE FROM user_assigned_roles
WHERE user_id NOT IN (SELECT user_id FROM admin_info);

DELETE FROM user_active_role
WHERE user_id NOT IN (SELECT user_id FROM admin_info);

DELETE FROM users
WHERE id NOT IN (SELECT user_id FROM admin_info);

RAISE NOTICE 'Deleted sample team members';

-- Step 4: Delete all tenant accounts (except admin's)
DELETE FROM account_subscriptions
WHERE account_id NOT IN (SELECT tenant_id FROM admin_info);

DELETE FROM tenant_accounts
WHERE id NOT IN (SELECT tenant_id FROM admin_info);

RAISE NOTICE 'Deleted sample tenant accounts';

-- Step 5: Delete all invitations (both subscriber and user invitations)
DELETE FROM subscriber_invitations
WHERE invited_by NOT IN (SELECT user_id FROM admin_info)
   OR email NOT IN (SELECT user_id FROM admin_info);

DELETE FROM user_invitations
WHERE invited_by NOT IN (SELECT user_id FROM admin_info);

RAISE NOTICE 'Deleted sample invitations';

-- Step 6: Delete all leads and related data
DELETE FROM leads
WHERE owner_id NOT IN (SELECT user_id FROM admin_info)
   OR created_by NOT IN (SELECT user_id FROM admin_info);

RAISE NOTICE 'Deleted sample leads';

-- Step 7: Delete all loans and related data
DELETE FROM loans
WHERE loan_officer_id NOT IN (SELECT user_id FROM admin_info)
   OR processor_id NOT IN (SELECT user_id FROM admin_info);

RAISE NOTICE 'Deleted sample loans';

-- Step 8: Clean up audit logs (keep only admin's actions)
DELETE FROM admin_audit_log
WHERE actor_admin_id NOT IN (SELECT user_id FROM admin_info);

RAISE NOTICE 'Cleaned audit logs';

-- Step 9: Reset sequences if needed
-- (Add any sequence resets here if your tables use them)

-- Final verification
DO $$
DECLARE
    v_user_count INT;
    v_tenant_count INT;
    v_task_count INT;
BEGIN
    SELECT COUNT(*) INTO v_user_count FROM users;
    SELECT COUNT(*) INTO v_tenant_count FROM tenant_accounts;
    SELECT COUNT(*) INTO v_task_count FROM tasks;
    
    RAISE NOTICE '===================================';
    RAISE NOTICE 'CLEANUP COMPLETE!';
    RAISE NOTICE 'Remaining users: %', v_user_count;
    RAISE NOTICE 'Remaining tenants: %', v_tenant_count;
    RAISE NOTICE 'Remaining tasks: %', v_task_count;
    RAISE NOTICE '===================================';
END $$;

COMMIT;

-- ===================================================================
-- INSTRUCTIONS FOR RUNNING THIS SCRIPT:
-- ===================================================================
-- 1. Replace 'YOUR_ADMIN_EMAIL_HERE' on line 13 with your email
-- 2. In Railway, go to your PostgreSQL database
-- 3. Click "Query" or "Data" tab
-- 4. Paste this entire script
-- 5. Run it
-- 6. Verify the output shows only 1 user, 1 tenant remaining
-- ===================================================================
