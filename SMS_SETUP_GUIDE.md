# SMS Setup Guide for Perennia AI Mortgage CRM

## Overview

The SMS functionality in your Mortgage CRM is powered by Telnyx, a reliable enterprise communications platform. This guide will help you set up SMS messaging for lead communication, document requests, and workflow automation.

## Current Status

❌ **SMS is currently disabled** due to missing Telnyx configuration.

## Quick Setup Checklist

- [ ] Create Telnyx account
- [ ] Get API key
- [ ] Purchase phone number
- [ ] Create messaging profile
- [ ] Update environment variables
- [ ] Test SMS functionality

## Step 1: Create Telnyx Account

1. Go to [Telnyx Sign-up](https://telnyx.com/sign-up)
2. Create your account
3. Verify your email address
4. Add billing information

## Step 2: Get API Key

1. Navigate to [Telnyx API Keys](https://portal.telnyx.com/#/app/api-keys)
2. Click "Create API Key"
3. Give it a name (e.g., "Mortgage CRM")
4. Copy the generated API key (keep it secure!)

## Step 3: Purchase Phone Number

1. Go to [Phone Numbers](https://portal.telnyx.com/#/app/phone-numbers)
2. Click "Buy Numbers"
3. Search for numbers in your area code
4. Purchase a number (cost ~$1-5/month)
5. Note down the phone number in E.164 format (e.g., +15551234567)

## Step 4: Create Messaging Profile

1. Navigate to [Messaging](https://portal.telnyx.com/#/app/messaging)
2. Click "Create Profile"
3. Give it a name (e.g., "Mortgage CRM SMS")
4. Assign your purchased phone number to this profile
5. Copy the Messaging Profile ID

## Step 5: Configure Webhooks (Optional but Recommended)

1. In your messaging profile settings
2. Set webhook URL to: `https://your-domain.com/api/v1/webhooks/telnyx/sms`
3. Enable "message.received" events
4. Copy the webhook secret

## Step 6: Update Environment Variables

Edit your `backend/.env` file and add:

```bash
# TELNYX SMS & TELEPHONY
TELNYX_API_KEY=your_actual_api_key_here
TELNYX_PHONE_NUMBER=+15551234567
TELNYX_MESSAGING_PROFILE_ID=your_messaging_profile_id
TELNYX_CONNECTION_ID=your_connection_id_if_using_voice
TELNYX_WEBHOOK_SECRET=your_webhook_secret_if_configured
ENABLE_2FA_SMS=false
```

## Step 7: Test SMS Functionality

After configuration, test SMS by:

1. Restart your backend server
2. Go to a lead profile in the CRM
3. Try sending an SMS message
4. Check the logs for any errors

## Features Enabled After Setup

✅ **Manual SMS sending** from lead profiles
✅ **Automated workflow SMS** for follow-ups
✅ **Document request SMS** notifications
✅ **Appointment reminder SMS** messages
✅ **Two-factor authentication** SMS (optional)
✅ **SMS conversation tracking** in lead history

## Troubleshooting

### Common Issues

**Error: "SMS service not configured"**
- Check that all environment variables are set
- Restart the backend server after making changes

**Error: "SMS delivery failed"**
- Verify your API key is correct
- Check that your phone number is in E.164 format
- Ensure your messaging profile is active

**Error: "Rate limit exceeded"**
- Telnyx has built-in rate limiting
- The CRM also has compliance rate limiting
- Wait a few minutes and try again

### Checking Configuration

Run this command to check your SMS setup:

```bash
cd backend
python3 -c "
import os
print('SMS Configuration:')
print(f'API Key: {\"SET\" if os.getenv(\"TELNYX_API_KEY\") else \"NOT SET\"}')
print(f'Phone: {os.getenv(\"TELNYX_PHONE_NUMBER\", \"NOT SET\")}')
print(f'Profile: {\"SET\" if os.getenv(\"TELNYX_MESSAGING_PROFILE_ID\") else \"NOT SET\"}')
"
```

### Log Analysis

Check backend logs for SMS-related issues:

```bash
grep -i "sms\|telnyx" logs/app.log
```

## Cost Estimates

- **Setup**: Free (account creation)
- **Phone Number**: $1-5/month
- **SMS Messages**: $0.004-0.01 per message
- **API Usage**: Included with messaging

## Security Best Practices

1. **Never commit** API keys to version control
2. **Use environment variables** for all credentials
3. **Enable webhook signatures** for incoming messages
4. **Monitor usage** for unexpected spikes
5. **Implement rate limiting** in your application

## TCPA Compliance

The CRM includes built-in TCPA compliance features:

- ✅ Opt-in tracking per lead
- ✅ Quiet hours enforcement
- ✅ DNC list checking
- ✅ STOP keyword handling
- ✅ Consent logging

## Support

If you need help:

1. **Telnyx Support**: [support.telnyx.com](https://support.telnyx.com)
2. **Documentation**: [developers.telnyx.com](https://developers.telnyx.com)
3. **CRM Logs**: Check `backend/logs/` for error details

## Next Steps After Setup

1. Configure SMS templates for common messages
2. Set up automated workflows with SMS notifications
3. Train your team on SMS best practices
4. Monitor SMS analytics in the CRM dashboard
5. Consider adding voice calling features

---

**Need Help?** Contact your development team with any questions about SMS configuration or troubleshooting.