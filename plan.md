# Plan: Complete Test Account with Demo Data

## Goal
Expand the test account seed script to populate **every area** a loan officer sees in the CRM, and add an API endpoint so it can run on the production Railway deployment.

## Current Coverage (seed_test_account.py)
- User account + organization
- 13 Leads (various stages)
- 10 Loans (various pipeline stages)
- 8 MUM Clients
- 8 Referral Partners
- 15 Tasks
- 6 Reconciliation events

## Missing Areas for Complete LO Demo
1. **Activities** - Communication history (calls, emails, meetings)
2. **Calendar Events** - Upcoming appointments
3. **Documents** - Sample documents on loans
4. **Notifications** - System notifications
5. **SMS Messages** - SMS conversation history
6. **Email Messages** - Email thread history
7. **Stage History** - Lead/loan progression history
8. **Goals** - User goals and key results
9. **Call Logs** - Recent call records

## Implementation Steps

### 1. Expand seed_test_account.py with new data generators
Add functions:
- `create_test_activities()` - 20+ activity records across leads/loans
- `create_test_calendar_events()` - 8-10 upcoming appointments
- `create_test_documents()` - Documents attached to pipeline loans
- `create_test_notifications()` - Recent notifications
- `create_test_communications()` - SMS and email records
- `create_test_stage_history()` - Historical stage changes
- `create_test_goals()` - User goals with key results
- `create_test_call_logs()` - Call records

### 2. Add protected API endpoint
Create `/api/admin/seed-test-account` route:
- Protected by admin authentication
- Calls the seed function
- Returns summary of created records

### 3. Make seeding idempotent
Ensure running multiple times doesn't create duplicates (already partially done).

## Files to Modify
1. `backend/seed_test_account.py` - Expand with new data generators
2. `backend/auto_import_routes.py` (or new file) - Add admin seed endpoint

## Test Credentials (unchanged)
- Email: `testuser@perenniaai.com`
- Password: `TestAccount2026!`
