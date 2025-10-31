# Master Admin User Credentials

This document contains the master administrator credentials for the Mortgage CRM system.

## Login Credentials

**Username (Email):** `admin@mortgagecrm.com`  
**Password:** `MasterAdmin@2025!Secure`  
**Full Name:** Master Administrator

---

## How to Use These Credentials

### Option 1: Using the Setup Script (Recommended)

1. Ensure your database is initialized (run the application at least once)
2. Run the admin user creation script:
   ```bash
   python create_admin_user.py
   ```
3. The script will create the master admin user in the database
4. You can now log in to the frontend using the credentials above

### Option 2: Using the API Registration Endpoint

If you prefer to create the user via the API:

```bash
curl -X POST "http://localhost:8000/api/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@mortgagecrm.com",
    "password": "MasterAdmin@2025!Secure",
    "full_name": "Master Administrator"
  }'
```

---

## Logging In to the Frontend

1. Navigate to the Mortgage CRM frontend application
2. Go to the login page
3. Enter:
   - **Username/Email:** `admin@mortgagecrm.com`
   - **Password:** `MasterAdmin@2025!Secure`
4. Click "Login" or "Sign In"

---

## Security Notes

⚠️ **IMPORTANT SECURITY REMINDERS:**

- These credentials are for initial setup and administrative access
- **Change the password immediately** after first login if the system provides that capability
- Store these credentials securely (use a password manager)
- Do not commit this file to version control in production environments
- Consider adding `ADMIN_CREDENTIALS.md` to `.gitignore` for production deployments
- The password uses a strong format with:
  - Uppercase letters
  - Lowercase letters
  - Numbers
  - Special characters
  - Length of 26 characters

---

## Troubleshooting

### "User already exists" Error

If you run the `create_admin_user.py` script and get a "user already exists" message:
- The admin user has already been created
- Try logging in with the credentials above
- If you need to reset the password, you'll need to manually delete the user from the database first

### Cannot Log In

1. Verify the user was created successfully:
   ```bash
   python -c "import sqlite3; conn = sqlite3.connect('crm.db'); cursor = conn.cursor(); cursor.execute('SELECT email, full_name FROM users WHERE email=\"admin@mortgagecrm.com\"'); print(cursor.fetchone()); conn.close()"
   ```

2. Check that you're using the correct credentials (copy-paste to avoid typos)

3. Ensure the frontend is configured to connect to the correct backend API endpoint

---

## Additional Admin Users

To create additional admin users, you can:

1. Use the API registration endpoint with different email addresses
2. Modify the `create_admin_user.py` script with new credentials
3. Use the frontend registration functionality (if available)

---

**Document Created:** October 28, 2025  
**Last Updated:** October 28, 2025
