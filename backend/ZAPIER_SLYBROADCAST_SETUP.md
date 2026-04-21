# Zapier + Slybroadcast Integration (Interim Solution)

## Overview
This guide shows you how to set up ringless voicemail using Zapier as a bridge between your CRM and Slybroadcast. This is an **interim solution** while waiting for Slybroadcast to enable direct API access.

**Why use Zapier?**
- Zapier has a pre-built Slybroadcast integration
- Works with standard Slybroadcast accounts (no API access required)
- Quick to set up (15 minutes)
- Can be used immediately while waiting for API access

## Prerequisites

1. **Slybroadcast Account** (you already have this)
   - Email: tloss@cmgfi.com
   - Password: [SET VIA ENVIRONMENT VARIABLE]
   - Caller ID: 843-834-5251

2. **Zapier Account**
   - Sign up at https://zapier.com (free plan works)
   - You'll need a paid plan for unlimited voicemails ($20/month+)

3. **OpenAI API Key** (for text-to-speech)
   - You already have this configured

## Step-by-Step Setup

### Part 1: Create Zapier Webhook Trigger

1. **Log in to Zapier**: https://zapier.com

2. **Create New Zap**:
   - Click "Create Zap"
   - Name it: "CRM Ringless Voicemail"

3. **Set up Trigger**:
   - **Trigger App**: Search for "Webhooks by Zapier"
   - **Trigger Event**: "Catch Hook"
   - Click "Continue"

4. **Get Webhook URL**:
   - Zapier will show you a webhook URL like:
     ```
     https://hooks.zapier.com/hooks/catch/123456/abcdef/
     ```
   - **COPY THIS URL** - you'll need it for Railway

5. **Test the Trigger**:
   - Leave this tab open for now
   - We'll test it after setting up Railway

### Part 2: Set up Slybroadcast Action

1. **Add Action Step**:
   - Click "+ Add Step"
   - Choose "Action/Search"

2. **Choose Slybroadcast**:
   - **Action App**: Search for "Slybroadcast"
   - **Action Event**: "Send Ringless Voicemail" or "Send Voice Broadcast"
   - Click "Continue"

3. **Connect Slybroadcast Account**:
   - Click "Sign in to Slybroadcast"
   - Enter your credentials:
     - Email: tloss@cmgfi.com
     - Password: [SET VIA ENVIRONMENT VARIABLE]
   - Click "Yes, Continue"

4. **Configure the Action**:
   - **Phone Number**: Click in field, select "Phone Number" from webhook data
   - **Caller ID**: 8438345251
   - **Message**: Click in field, select "Message" from webhook data
   - **Delivery Time**: "Now" or leave blank for immediate
   - **Audio URL**: (We'll handle this with OpenAI TTS - see Part 3)

5. **Test the Action**:
   - Click "Test & Continue"
   - If successful, you'll see a confirmation

6. **Turn On Zap**:
   - Click "Publish Zap" or toggle to ON
   - Your Zap is now active!

### Part 3: Add OpenAI Text-to-Speech (Optional but Recommended)

For natural voice, add OpenAI TTS before Slybroadcast:

1. **Insert Step Between Webhook and Slybroadcast**:
   - Click "+" between Webhook and Slybroadcast
   - Search for "Code by Zapier"
   - Choose "Run Python"

2. **Configure Python Code**:
   ```python
   import requests
   import json

   # Get OpenAI API key from environment
   openai_key = "YOUR_OPENAI_KEY_HERE"

   # Get message from webhook
   message = input_data['message']

   # Generate TTS audio
   response = requests.post(
       "https://api.openai.com/v1/audio/speech",
       headers={
           "Authorization": f"Bearer {openai_key}",
           "Content-Type": "application/json"
       },
       json={
           "model": "tts-1",
           "voice": "nova",
           "input": message,
           "speed": 0.95
       }
   )

   # Save audio to temp URL (or return base64)
   # For now, we'll use text-to-speech feature in Slybroadcast

   return {"message": message}
   ```

3. **OR Simpler: Use Slybroadcast's Built-in TTS**:
   - In Slybroadcast action, there should be a "Text Message" field
   - Map the "message" from webhook directly
   - Slybroadcast will convert text to speech automatically

### Part 4: Configure Railway Environment

1. **Add Zapier Webhook URL to Railway**:
   ```bash
   railway variables --service mortgage-crm --set "ZAPIER_VOICEMAIL_WEBHOOK_URL=https://hooks.zapier.com/hooks/catch/YOUR_URL_HERE"
   ```

2. **Redeploy** (automatic after setting variable)

### Part 5: Update Frontend to Use Zapier

The frontend already supports multiple providers. Just make sure requests use:
```json
{
  "provider": "zapier"
}
```

Or set Zapier as the default in the backend code.

## Testing

### Test 1: Manual Zapier Test

1. In Zapier, go to your Zap
2. Click "Test" on the webhook trigger
3. Send this test data:
   ```json
   {
     "phone_number": "8438344997",
     "message": "This is a test ringless voicemail from Zapier integration",
     "recipient_name": "Tim",
     "caller_id": "8438345251"
   }
   ```
4. Check your phone - voicemail should appear without ringing!

### Test 2: CRM Integration Test

Run this command:
```bash
cd /Users/timothyloss/my-project/mortgage-crm/backend
./test_zapier_voicemail.sh
```

Or manually:
```bash
curl -X POST "https://app.perenniaai.com/api/v1/voice/drop-voicemail" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to_number": "8438344997",
    "message": "Testing Zapier ringless voicemail integration",
    "recipient_name": "Tim",
    "provider": "zapier"
  }'
```

## How It Works

```
CRM Frontend
    ↓
CRM Backend API
    ↓
Zapier Webhook
    ↓
[OpenAI TTS - Optional]
    ↓
Slybroadcast
    ↓
Ringless Voicemail Delivered ✅
```

## Troubleshooting

### "Zapier webhook URL not configured"
- Make sure you added `ZAPIER_VOICEMAIL_WEBHOOK_URL` to Railway
- Redeploy after adding the variable

### Zapier Zap not triggering
- Check that Zap is turned ON
- View Zap history in Zapier dashboard
- Make sure webhook URL is correct in Railway

### Voicemail not delivered
- Check Zapier task history for errors
- Verify Slybroadcast account is connected in Zapier
- Check Slybroadcast credit balance

### Phone is ringing
- Verify you're using Slybroadcast action (not Twilio or other)
- Slybroadcast should be in "ringless" mode
- Check Slybroadcast settings in Zapier

## Costs

### Zapier
- **Free Plan**: 100 tasks/month (good for testing)
- **Starter Plan**: $20/month for 750 tasks
- **Professional**: $50/month for 2,000 tasks

### Slybroadcast
- Typically 2-3 credits per voicemail
- Credits purchased in bulk from Slybroadcast

### OpenAI TTS (if using)
- ~$0.015 per 1,000 characters
- Very cheap (pennies per voicemail)

## Migrating to Direct API

Once Slybroadcast enables API access:

1. Simply change provider from "zapier" to "slybroadcast"
2. No code changes needed - already integrated!
3. Can keep Zapier as backup if needed

## Next Steps

1. ✅ Set up Zapier account
2. ✅ Create Webhook → Slybroadcast Zap
3. ✅ Get webhook URL
4. ✅ Add to Railway environment
5. ✅ Test with your phone
6. ✅ Use in CRM!

## Support

- **Zapier Help**: https://zapier.com/help
- **Slybroadcast in Zapier**: https://zapier.com/apps/slybroadcast/integrations
- **CRM Issues**: Contact development team
