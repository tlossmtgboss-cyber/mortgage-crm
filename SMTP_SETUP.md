# SMTP Email Configuration Setup

To enable the daily priorities email functionality, you need to add SMTP configuration to your `.env` file.

## Required Environment Variables

Add these to your `.env` file:

```bash
# Email Configuration
SMTP_HOST=smtp.gmail.com          # Your SMTP server
SMTP_PORT=587                      # Usually 587 for TLS
SMTP_USER=your-email@gmail.com    # Your email address
SMTP_PASSWORD=your-app-password    # Your email password or app password
FROM_EMAIL=your-email@gmail.com    # From address
FROM_NAME=Perennia AI CRM         # Sender name
```

## Option 1: Gmail Setup

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate an App Password**:
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and your device
   - Copy the 16-character password
3. **Add to .env**:
   ```bash
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASSWORD=xxxx xxxx xxxx xxxx  # Your app password
   FROM_EMAIL=your-email@gmail.com
   FROM_NAME=Perennia AI CRM
   ```

## Option 2: Microsoft 365/Outlook Setup

```bash
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=your-email@company.com
SMTP_PASSWORD=your-password
FROM_EMAIL=your-email@company.com
FROM_NAME=Perennia AI CRM
```

## Option 3: SendGrid (Recommended for Production)

```bash
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
FROM_EMAIL=noreply@yourdomain.com
FROM_NAME=Perennia AI CRM
```

## Testing

After configuration, test the email functionality:

```bash
python3 test_email_priorities.py
```

Or use the API directly:

```bash
curl -X POST "https://api.perenniaai.com/api/v1/ai/send-daily-priorities-email" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email_address": "tloss@cmgfi.com"}'
```

## Deployment

For Railway/production deployment, add the environment variables to your Railway project:

1. Go to Railway dashboard
2. Select your project
3. Go to Variables tab
4. Add all SMTP_* variables
5. Redeploy

## Email Features

The daily priorities email includes:
- ✅ All pending tasks (regardless of due date)
- ✅ Priority scoring and urgency labels
- ✅ Overdue tasks highlighted in red
- ✅ Loans requiring attention
- ✅ Clean HTML formatting
- ✅ Plain text fallback
- ✅ Mobile-responsive design
