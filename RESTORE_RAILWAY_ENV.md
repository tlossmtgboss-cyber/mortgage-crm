# 🚨 Restore Railway Environment Variables

All required environment variables for the backend to run properly.

## Critical Variables (App Won't Start Without These)

### Database
```bash
DATABASE_URL=postgresql://postgres:password@host:port/railway
```
**Note:** Railway auto-provides this if you have PostgreSQL service linked

### Security
```bash
SECRET_KEY=your-secret-key-here-min-32-chars
JWT_SECRET_KEY=your-jwt-secret-key-here-min-32-chars
```

### CORS (Frontend URL)
```bash
FRONTEND_URL=https://mortgage-crm-production-7a9a.up.railway.app
```

## Microsoft 365 Integration

```bash
MICROSOFT_CLIENT_ID=185b7101-9435-44da-87ab-b7582c4e4607
MICROSOFT_CLIENT_SECRET=your-microsoft-client-secret
MICROSOFT_TENANT_ID=common
MICROSOFT_REDIRECT_URI=https://mortgage-crm-production-7a9a.up.railway.app/api/v1/email/oauth/callback
```

## Twilio SMS (Optional - but needed if configured)

```bash
TWILIO_ACCOUNT_SID=your-twilio-account-sid
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_PHONE_NUMBER=+15551234567
```

## Calendly Integration (Optional)

```bash
CALENDLY_API_KEY=your-calendly-api-key
```

## OpenAI/Anthropic (Optional - for AI features)

```bash
OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
```

---

## Quick Restore via Railway Dashboard

1. Go to https://railway.app/project/YOUR_PROJECT_ID
2. Click on your **backend service**
3. Go to **Variables** tab
4. Click **+ New Variable** for each one above
5. Click **Deploy** after adding all variables

---

## Restore via Railway CLI

```bash
# Set critical variables first
railway variables set SECRET_KEY="$(openssl rand -base64 32)"
railway variables set JWT_SECRET_KEY="$(openssl rand -base64 32)"
railway variables set FRONTEND_URL="https://mortgage-crm-production-7a9a.up.railway.app"

# Microsoft 365
railway variables set MICROSOFT_CLIENT_ID="185b7101-9435-44da-87ab-b7582c4e4607"
railway variables set MICROSOFT_CLIENT_SECRET="YOUR_SECRET_HERE"
railway variables set MICROSOFT_TENANT_ID="common"
railway variables set MICROSOFT_REDIRECT_URI="https://mortgage-crm-production-7a9a.up.railway.app/api/v1/email/oauth/callback"

# Database (if not auto-linked)
railway variables set DATABASE_URL="postgresql://..."

# Redeploy
railway up
```

---

## Minimum Required to Start

At minimum, you need these 3 variables to start the app:

1. **DATABASE_URL** (usually auto-provided by Railway PostgreSQL service)
2. **SECRET_KEY** (for session encryption)
3. **JWT_SECRET_KEY** (for authentication tokens)

Example:
```bash
SECRET_KEY=abcdef1234567890abcdef1234567890
JWT_SECRET_KEY=1234567890abcdef1234567890abcdef
DATABASE_URL=postgresql://postgres:password@containers-us-west-1.railway.app:5432/railway
```

---

## Check Current Variables

```bash
railway variables
```

This will list all current environment variables set in Railway.

---

## What Happens Without These Variables?

| Missing Variable | Result |
|------------------|--------|
| DATABASE_URL | App crashes immediately - can't connect to database |
| SECRET_KEY | App crashes - can't encrypt sessions |
| JWT_SECRET_KEY | Authentication fails - users can't login |
| FRONTEND_URL | CORS errors - frontend can't call backend API |
| MICROSOFT_CLIENT_ID | OAuth fails - can't connect Microsoft 365 |
| MICROSOFT_CLIENT_SECRET | OAuth fails - can't exchange auth code for token |

---

## Generate New Secret Keys

```bash
# Generate SECRET_KEY
openssl rand -base64 32

# Generate JWT_SECRET_KEY
openssl rand -base64 32
```

Copy the output and use as the variable values.

---

## After Restoring Variables

1. Railway will automatically redeploy
2. Wait 1-2 minutes for deployment
3. Check health: https://mortgage-crm-production-7a9a.up.railway.app/health
4. Should return: `{"status": "healthy"}`

---

## If You Had Previous Values

If you remember the previous SECRET_KEY and JWT_SECRET_KEY values, **use those exact same values**.

Changing these will:
- Invalidate all existing user sessions
- Require all users to log in again
- Break existing Microsoft 365 OAuth connections (will need to reconnect)

---

## Need Help?

If you're not sure what the previous values were, let me know and I can help you:
1. Generate new secure keys
2. Guide you through re-establishing OAuth connections
3. Help reset user sessions
