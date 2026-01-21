# Vapi AI Voicemail Drop Setup Guide

## Overview
The voicemail drop feature uses Vapi AI to deliver natural, conversational voicemails using your AI receptionist's voice.

## Required Environment Variables

Add these to your Railway environment variables:

```bash
# Vapi API Credentials
VAPI_API_KEY=your_vapi_api_key_here
VAPI_ASSISTANT_ID=your_assistant_id_here

# Optional: Dedicated voicemail assistant (recommended)
VAPI_VOICEMAIL_ASSISTANT_ID=your_voicemail_assistant_id_here
```

## How to Get Your Vapi Credentials

### 1. Get Your API Key
1. Log in to [Vapi Dashboard](https://dashboard.vapi.ai)
2. Go to Account Settings
3. Copy your API Key

### 2. Get Your Assistant ID
1. In Vapi Dashboard, go to Assistants
2. Select your AI Receptionist assistant
3. Copy the Assistant ID from the URL or settings

### 3. (Optional) Create Dedicated Voicemail Assistant
For best results, create a separate assistant specifically for voicemail drops:

1. In Vapi Dashboard, click "New Assistant"
2. Configure:
   - **Name**: Voicemail Drop Assistant
   - **Voice**: Same as your main AI receptionist
   - **First Message**: `{{voicemail_message}}` (dynamic)
   - **End Call**: On voicemail detection
   - **Recording**: Disabled
3. Copy the new Assistant ID
4. Set `VAPI_VOICEMAIL_ASSISTANT_ID` in Railway

## Database Migration

The voicemail_drops table will be created automatically on first deployment.

If you need to create it manually:

```sql
CREATE TABLE voicemail_drops (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER REFERENCES leads(id),
    loan_id INTEGER REFERENCES loans(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    phone_number VARCHAR(20) NOT NULL,
    recipient_name VARCHAR(255),
    message_text TEXT NOT NULL,
    vapi_call_id VARCHAR(255),
    delivery_status VARCHAR(50) DEFAULT 'pending',
    delivered_at TIMESTAMP,
    call_duration INTEGER,
    call_cost DECIMAL(10,4),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_voicemail_lead ON voicemail_drops(lead_id);
CREATE INDEX idx_voicemail_loan ON voicemail_drops(loan_id);
CREATE INDEX idx_voicemail_user ON voicemail_drops(user_id);
CREATE INDEX idx_voicemail_vapi_call ON voicemail_drops(vapi_call_id);
CREATE INDEX idx_voicemail_created ON voicemail_drops(created_at);
```

## Testing

1. Set environment variables in Railway
2. Redeploy the application
3. In the CRM, navigate to any lead or loan with a phone number
4. Click "Voicemail Drop" button
5. Record your message
6. Click "Send Voicemail"
7. Check the voicemail_drops table for delivery status

## How It Works

1. User records or types a voicemail message
2. System calls Vapi API with:
   - Recipient phone number
   - Custom message
   - Voicemail detection enabled
3. Vapi AI makes outbound call
4. When voicemail is detected:
   - Waits for beep
   - Delivers message in natural AI voice
   - Ends call
5. Vapi sends webhook with delivery status
6. Database is updated with:
   - Delivery status (delivered/failed/no-answer)
   - Call duration
   - Call cost

## Delivery Status

- **pending**: Call initiated, waiting for completion
- **delivered**: Message successfully left on voicemail
- **no-answer**: No answer, no voicemail system
- **failed**: Call failed (busy, invalid number, etc.)
- **completed**: Call completed (may have been answered by human)

## Webhook Configuration

**Important**: Configure the webhook URL in your Vapi Assistant settings:

1. Go to Vapi Dashboard → Your Assistant → Settings
2. Set Server URL to:
```
https://app.perenniaai.com/api/v1/webhooks/vapi/voicemail-status
```
3. Enable Server Messages: `end-of-call-report`

The webhook will receive call completion data with:
- Call duration
- End reason
- Call cost
- Delivery confirmation

**Note**: Each voicemail drop will pass its ID as a query parameter, but the base webhook URL must be configured in your assistant settings.

## Cost Tracking

All voicemail drops are tracked in the database with:
- Call duration (seconds)
- Call cost (USD)
- Timestamp
- Recipient information

Query costs:
```sql
SELECT
    user_id,
    COUNT(*) as total_drops,
    SUM(call_duration) as total_seconds,
    SUM(call_cost) as total_cost,
    AVG(call_cost) as avg_cost_per_drop
FROM voicemail_drops
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY user_id;
```

## Troubleshooting

### "Vapi API key not configured"
- Check Railway environment variables
- Ensure `VAPI_API_KEY` is set
- Redeploy after adding env vars

### "Vapi assistant ID not configured"
- Set `VAPI_ASSISTANT_ID` or `VAPI_VOICEMAIL_ASSISTANT_ID`
- Use the Assistant ID from Vapi Dashboard
- Redeploy

### Voicemail not delivered
- Check voicemail_drops table for error_message
- Check Vapi Dashboard for call logs
- Verify phone number format (E.164)
- Check Vapi account balance

### Status stuck on "pending"
- Wait up to 60 seconds for webhook
- Check Railway logs for webhook errors
- Verify webhook URL is accessible
- Check Vapi Dashboard for call completion

## Best Practices

1. **Use Dedicated Assistant**: Create a separate Vapi assistant just for voicemail drops
2. **Keep Messages Short**: 30-60 seconds max for voicemail messages
3. **Test First**: Test with your own phone before using with customers
4. **Monitor Costs**: Track voicemail costs in the database
5. **Handle Failures**: Check delivery status and retry if needed

## Example Usage

From the UI:
1. Open lead/loan profile
2. Click "📞 Voicemail Drop"
3. Record: "Hi this is Sam from Tim Loss Team, your closing disclosures are ready"
4. Click "Send Voicemail"
5. AI calls and delivers: "Hi [Name], this is the AI assistant calling from Sam's office. Your closing disclosures are ready. Feel free to call us back at your convenience. Have a great day!"

## Support

- Vapi Documentation: https://docs.vapi.ai
- Vapi Dashboard: https://dashboard.vapi.ai
- CRM Issues: https://github.com/yourusername/mortgage-crm/issues
