# User Cleanup Script

This directory contains administrative scripts for managing the CRM system.

## cleanup_users.py

Deletes all users except those with `@cmgfi.com` email addresses.

### Usage

**Dry run (see what would be deleted without actually deleting):**
```bash
cd backend
export DATABASE_URL="your-database-url"
python scripts/cleanup_users.py --dry-run
```

**Actual deletion (requires confirmation):**
```bash
cd backend
export DATABASE_URL="your-database-url"
python scripts/cleanup_users.py
```

### What it does

1. Connects to the database
2. Finds all users without `@cmgfi.com` email addresses
3. Displays a list of users to be deleted
4. Shows count of users to keep vs. delete
5. Asks for confirmation (you must type `DELETE`)
6. Deletes the users
7. Shows remaining `@cmgfi.com` users

### Safety Features

- **Dry run mode**: Test without making changes
- **Confirmation required**: Must type `DELETE` to proceed
- **Clear reporting**: Shows exactly what will be deleted before proceeding
- **Database transactions**: Uses proper rollback on errors

### Example Output

```
============================================================
🧹 User Cleanup Script
============================================================

This script will DELETE all users except @cmgfi.com emails

🔍 Finding users to remove...
------------------------------------------------------------

📋 Found 15 users to delete:

   • ID:  123 | demo@example.com                       | John Demo                      | Created: 2025-01-10 10:30:00
   • ID:  124 | test@test.com                          | Test User                      | Created: 2025-01-11 14:20:00
   ...

------------------------------------------------------------

✅ Users to KEEP (@cmgfi.com): 5
❌ Users to DELETE (non-@cmgfi.com): 15

⚠️  WARNING: This action cannot be undone!

Type 'DELETE' to confirm deletion: DELETE

🗑️  Deleting users...
   ✓ Deleted: demo@example.com (ID: 123)
   ✓ Deleted: test@test.com (ID: 124)
   ...

✅ Successfully deleted 15 users
✅ Remaining @cmgfi.com users: 5

📋 Remaining users:
   ✓ ID:    1 | tloss@cmgfi.com                        | Tim Loss
   ✓ ID:    2 | jsmith@cmgfi.com                       | John Smith
   ...

✅ Cleanup completed successfully!
```

### Database URL

Set your database URL as an environment variable:

**Local:**
```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/mortgage_crm"
```

**Railway Production:**
```bash
export DATABASE_URL="postgresql://postgres:password@containers-us-west-123.railway.app:5432/railway"
```

**Or get from Railway CLI:**
```bash
railway variables
# Copy the DATABASE_URL value
export DATABASE_URL="<value-from-railway>"
```

### Safety Recommendations

1. **Always run with `--dry-run` first** to preview what will be deleted
2. **Backup your database** before running the script
3. **Verify the users to keep** by checking the remaining users list
4. **Run during off-hours** to avoid disrupting active users

### Troubleshooting

**Error: "DATABASE_URL environment variable not set"**
```bash
# Set the environment variable
export DATABASE_URL="your-database-url"
```

**Error: "Email already registered" when creating new users**
- The cleanup script doesn't affect user creation
- Check if the email already exists in the database

**Script cancelled by user**
- Press Ctrl+C to cancel at any time
- No changes will be made if you cancel during confirmation
