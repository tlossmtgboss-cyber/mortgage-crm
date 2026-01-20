# Slybroadcast Ringless Voicemail Setup Guide

## Overview
This system uses Slybroadcast for true ringless voicemail drops - messages are delivered directly to voicemail without ringing the recipient's phone. The voicemail is generated using OpenAI's Text-to-Speech API for natural, conversational delivery.

## Required Environment Variables

Add these to your Railway environment variables:

```bash
# Slybroadcast Credentials
SLYBROADCAST_EMAIL=your_email@example.com
SLYBROADCAST_PASSWORD=your_password

# Slybroadcast Caller ID (the number that appears in voicemail)
SLYBROADCAST_CALLER_ID=8438345251  # Your business phone number (10 digits, no +1)

# OpenAI API Key (for Text-to-Speech)
OPENAI_API_KEY=your_openai_api_key_here

# API URL (for hosting audio files)
API_URL=https://api.perenniaai.com
```

## How to Get Your Slybroadcast Credentials

### 1. Login Information
1. Log in to your Slybroadcast account at https://www.slybroadcast.com
2. Use your account email and password as the credentials

### 2. Caller ID Setup
- Your caller ID must be a valid 10-digit US phone number
- This is the number that will appear in the recipient's voicemail inbox
- Recommend using your business main line (e.g., 8438345251)

### 3. OpenAI API Key
1. Go to https://platform.openai.com/api-keys
2. Create a new API key for TTS (Text-to-Speech)
3. The system uses the `tts-1` model with the "nova" voice

## How It Works

1. **User records/types a message** in the CRM interface
2. **System generates natural speech** using OpenAI TTS API
   - Uses "nova" voice (natural, friendly female voice)
   - Slightly slowed for clarity (0.95 speed)
3. **Audio file is saved** to static directory and made accessible via URL
4. **Slybroadcast API is called** with:
   - Recipient phone number
   - Generated audio URL
   - Caller ID
   - Immediate delivery time
5. **Voicemail is delivered directly** to recipient's voicemail box without ringing
6. **System tracks delivery** via session ID in the database

## Features

### Ringless Delivery
- Phone does NOT ring when voicemail is dropped
- Message appears directly in voicemail inbox
- Recipient sees a missed call notification with your caller ID

### Natural Voice
- Uses OpenAI's "nova" voice for natural, conversational delivery
- Message is formatted with:
  - Personal greeting with recipient name
  - Your name/office
  - Custom message
  - Professional closing

### Mobile-Only Delivery
- Configured to deliver only to mobile phones
- Landlines are skipped automatically

## Database Tracking

All voicemail drops are tracked in the `voicemail_drops` table with:
- Session ID (Slybroadcast campaign ID)
- Delivery status (pending, sent, delivered, failed)
- Phone number and recipient name
- Message text
- Timestamps

## Delivery Status

- **pending**: Voicemail drop initiated, awaiting Slybroadcast response
- **sent**: Successfully sent to Slybroadcast (session ID received)
- **delivered**: Confirmed delivery to voicemail box (via webhook)
- **failed**: Delivery failed (error message captured)

## Checking Delivery Status

### Via Slybroadcast Dashboard
1. Log in to https://www.slybroadcast.com
2. Go to "Campaign Reports"
3. Find your campaign by session ID
4. View detailed delivery results

### Via API (Future Enhancement)
You can poll Slybroadcast API for status using:
```bash
c_option=campaign_result
c_session_id=[session_id]
```

## Cost Tracking

Slybroadcast charges per successful delivery (typically 2 credits per voicemail).

Track costs via Slybroadcast dashboard:
- View campaign reports
- Check credit usage
- Download billing reports

## Testing

1. Set environment variables in Railway
2. Redeploy the application
3. In the CRM, navigate to any lead/loan with a phone number
4. Click "📞 Voicemail Drop" button
5. Record your message (or it will be transcribed from voice)
6. Click "Send Voicemail"
7. **Your phone should NOT ring** - check voicemail directly after 1-2 minutes

## Troubleshooting

### "Slybroadcast credentials not configured"
- Check Railway environment variables
- Ensure `SLYBROADCAST_EMAIL` and `SLYBROADCAST_PASSWORD` are set
- Redeploy after adding env vars

### "OpenAI API key not configured for TTS"
- Set `OPENAI_API_KEY` in Railway environment variables
- Ensure you have credits in your OpenAI account
- Redeploy

### Voicemail not delivered
- Check Slybroadcast dashboard for campaign status
- Verify phone number is mobile (landlines may be skipped)
- Check Slybroadcast account credit balance
- Review error_message in voicemail_drops table

### Audio file not accessible
- Check static directory exists: `/app/static` or `backend/static`
- Verify API_URL is set correctly
- Check Railway logs for file save errors

### Phone is ringing instead of going to voicemail
- Verify `provider` is set to `"slybroadcast"` (not `"vapi"`)
- Check logs to confirm "Using Slybroadcast for ringless voicemail" message
- If using Vapi accidentally, it will ring the phone normally

## API Usage

### Drop Voicemail Endpoint

```bash
POST /api/v1/voice/drop-voicemail
Authorization: Bearer <token>
Content-Type: application/json

{
  "to_number": "8438344997",
  "message": "Your closing disclosures are ready for review.",
  "recipient_name": "John Smith",
  "lead_id": 123,  // optional
  "loan_id": 456,  // optional
  "provider": "slybroadcast"  // default, use "vapi" to fallback
}
```

### Response

```json
{
  "success": true,
  "voicemail_id": 7,
  "session_id": "12345678",
  "provider": "slybroadcast",
  "message": "Ringless voicemail sent successfully via slybroadcast"
}
```

## Message Format

Messages are automatically formatted as:

```
Hi [Recipient Name], this is the AI assistant calling from [Your Name]'s office.
[Your Custom Message]
Feel free to call us back at your convenience. Have a great day!
```

Example:
```
Hi John Smith, this is the AI assistant calling from Tim Loss's office.
Your closing disclosures are ready for review.
Feel free to call us back at your convenience. Have a great day!
```

## Best Practices

1. **Keep messages short**: 30-60 seconds max
2. **Test with your own phone** before using with clients
3. **Use personal greetings**: Include recipient's name when available
4. **Clear call-to-action**: Tell them what you need them to do
5. **Professional closer**: End with "call us back" or similar
6. **Monitor credits**: Check Slybroadcast balance regularly
7. **Verify numbers**: Ensure phone numbers are mobile for best delivery

## Compliance & Legal

⚠️ **Important Legal Notice**:
- Ringless voicemail is regulated by TCPA (Telephone Consumer Protection Act)
- Only send to contacts who have provided consent
- Include opt-out mechanisms if required in your jurisdiction
- Check state-specific regulations (some states have additional restrictions)
- Keep records of consent for compliance

## Support

- Slybroadcast Support: https://www.slybroadcast.com/support.php
- Slybroadcast Documentation: https://www.slybroadcast.com/documentation.php
- OpenAI TTS Documentation: https://platform.openai.com/docs/guides/text-to-speech
- CRM Issues: Contact your development team

## Fallback to Vapi

If Slybroadcast is unavailable, the system can fallback to Vapi for voicemail drops:

```json
{
  "provider": "vapi"
}
```

⚠️ **Note**: Vapi will **ring the phone normally** - it's not ringless. Only use this for testing or when ringless is not available.
