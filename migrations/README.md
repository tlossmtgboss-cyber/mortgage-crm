# Database Migrations

This folder contains database migration scripts for the Mortgage CRM application.

## Available Migrations

### fix_company_admin_role.py

Fixes the registration issue caused by missing 'Company Admin' role in the `onboarding_roles` table.

**Problem:** Users were unable to complete company registration because the system tried to assign a 'Company Admin' role that didn't exist in the database.

**Solution:** This script adds the missing role with proper configuration.

#### How to Run

1. **Set the DATABASE_URL environment variable:**

   ```bash
   export DATABASE_URL="postgresql://username:password@host:port/database"
   ```

   Or on Railway, the DATABASE_URL is automatically available from the Postgres service.

2. **Install required dependencies:**

   ```bash
   pip install psycopg2-binary
   ```

3. **Run the migration script:**

   ```bash
   python migrations/fix_company_admin_role.py
   ```

4. **Expected output:**

   ```
   ======================================================================
   Company Admin Role Migration Script
   ======================================================================

   Connecting to database...
   ✓ Connected successfully

   Adding 'Company Admin' role to database...
   ✓ Successfully added 'Company Admin' role

   ✓ Migration completed successfully!

   The registration issue should now be fixed.
   Users can now create companies and be assigned the Company Admin role.

   Database connection closed.
   ======================================================================
   ```

#### Running on Railway

To run this script on your Railway deployment:

1. SSH into your Railway service or use Railway CLI
2. The DATABASE_URL is already set in the environment
3. Run: `python migrations/fix_company_admin_role.py`

Alternatively, you can run it locally if you have access to the production database credentials.

## SQL Migrations

### add_user_roles_tables.sql

Creates the onboarding_roles and user_assigned_roles tables.

### add_user_integrations_table.sql

Creates tables for user OAuth integrations.

---

**Note:** Always backup your database before running migrations in production.
