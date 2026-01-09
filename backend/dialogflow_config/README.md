# Dialogflow CX Lead Qualification Widget Setup

This directory contains configuration files for setting up a Dialogflow CX agent for the mortgage lead qualification widget.

## Overview

The lead qualification flow captures:
1. **Loan Purpose** - Purchase, refinance, or cash-out
2. **Experience** - First-time buyer status
3. **Location** - Target city/state
4. **Timeline** - When they want to close
5. **Price/Amount** - Target purchase price or loan amount
6. **Credit Tier** - Self-reported credit range
7. **Contact Info** - Name, phone, email, preferred contact method

## Files

- `entity_types.json` - Custom entity definitions for loan purposes, timelines, credit tiers, etc.
- `intents.json` - Intent definitions with training phrases and parameters
- `flows.json` - Conversation flow routing and page definitions

## Setup Instructions

### 1. Create Dialogflow CX Agent

1. Go to [Dialogflow CX Console](https://dialogflow.cloud.google.com/cx)
2. Create a new agent:
   - Name: `Mortgage Lead Qualification`
   - Default Language: English
   - Time Zone: Your timezone
   - Location: us-central1 (recommended)

### 2. Import Entity Types

1. Go to **Manage** > **Entity Types**
2. For each entity in `entity_types.json`:
   - Click **Create**
   - Enter the display name
   - Add entities with synonyms
   - Enable **Fuzzy matching** for better recognition

Key entities to create:
- `loan_purpose` - purchase, refinance, cash_out
- `timeline` - immediate, 1_3_months, 3_6_months, etc.
- `credit_tier` - excellent_740+, good_700_739, etc.
- `first_time_buyer` - true, false
- `contact_preference` - sms, email, call
- `property_type` - single_family, condo, etc.
- `us_state` - All US states with abbreviations

### 3. Create Intents

1. Go to **Manage** > **Intents**
2. Create each intent from `intents.json`:
   - `start_qualification`
   - `capture_loan_purpose`
   - `capture_experience`
   - `capture_location`
   - `capture_timeline`
   - `capture_price`
   - `capture_credit`
   - `capture_contact`
   - `request_human_handoff`
   - `default_fallback` (mark as fallback intent)

3. For each intent:
   - Add training phrases from the JSON
   - Map parameters to entity types
   - Enable webhook for all intents

### 4. Configure Webhook

1. Go to **Manage** > **Webhooks**
2. Click **Create**
3. Configure:
   ```
   Display name: mortgage-webhook
   Webhook URL: https://YOUR_RAILWAY_DOMAIN/api/v1/dialogflow/webhook
   Timeout: 10 seconds
   ```

### 5. Build Flows

1. Go to **Build** > **Start Page**
2. Create pages for each qualification step:
   - Capture Loan Purpose
   - Capture Experience
   - Capture Location
   - Capture Timeline
   - Capture Price
   - Capture Credit
   - Capture Contact
   - Qualification Complete
   - Human Handoff

3. Configure routes between pages based on `flows.json`

4. Set fulfillment tags for webhook calls:
   - `start_qualification`
   - `capture_loan_purpose`
   - `capture_experience`
   - `capture_location`
   - `capture_timeline`
   - `capture_price`
   - `capture_credit`
   - `capture_contact`
   - `qualification_complete`

### 6. Test the Agent

1. Use the **Test Agent** panel in Dialogflow CX
2. Try conversations like:
   ```
   User: I want to buy a home
   Agent: Great! Is this your first home, or have you purchased before?
   User: First time
   Agent: What area are you looking to buy in?
   User: Austin, Texas
   ...
   ```

## FastAPI Endpoints

The webhook connects to these FastAPI endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/dialogflow/webhook` | POST | Main Dialogflow fulfillment |
| `/api/v1/dialogflow/health` | GET | Health check |
| `/api/v1/widget/chat` | POST | Direct widget chat (non-Dialogflow) |
| `/api/v1/widget/create-lead` | POST | Create lead from session |
| `/api/v1/widget/generate-summary` | POST | Generate LO summary |
| `/api/v1/widget/notify-lo` | POST | Send LO notification |

## Database Migration

Run the migration to create the `widget_sessions` table:

```bash
cd backend
python -m migrations.add_widget_sessions_table
```

## Environment Variables

Ensure these are set:

```env
# Required
DATABASE_URL=postgresql://...
OPENAI_API_KEY=sk-...  # For AI summary generation

# Optional
APP_BASE_URL=https://app.yourcompany.com  # For lead URLs in notifications
```

## Widget Integration

To embed the widget on your site:

### Option 1: Dialogflow Messenger (Recommended)
```html
<script src="https://www.gstatic.com/dialogflow-console/fast/messenger/bootstrap.js?v=1"></script>
<df-messenger
  intent="WELCOME"
  chat-title="Mortgage Assistant"
  agent-id="YOUR_AGENT_ID"
  language-code="en"
></df-messenger>
```

### Option 2: Custom Widget (Direct API)
```javascript
// Initialize session
const sessionId = crypto.randomUUID();

// Send message
const response = await fetch('/api/v1/widget/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    session_id: sessionId,
    message: userMessage,
    page_url: window.location.href
  })
});

const data = await response.json();
// Display data.response to user
```

## Lead Flow

```
┌─────────────────┐
│  Site Visitor   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Widget Opens   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Qualification  │ ◄── 7 questions
│     Dialog      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ widget_sessions │
│    (database)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Create Lead    │ → lead_profiles table
└────────┬────────┘
         │
         ├──► Assign LO
         │
         ├──► Create Tasks (purl_tasks)
         │
         ├──► Generate AI Summary
         │
         └──► Notify LO (in-app, SMS, email)
```

## Troubleshooting

### Webhook not responding
1. Check `/api/v1/dialogflow/health` returns 200
2. Verify DATABASE_URL is set
3. Check Railway logs for errors

### Entities not matching
1. Ensure entity synonyms cover common variations
2. Enable fuzzy matching in Dialogflow
3. Add more training phrases to intents

### Lead not created
1. Check `widget_sessions` table for session data
2. Verify required fields (email, phone) were captured
3. Check logs for database errors

## Support

For issues:
- Check debug endpoint: `/api/v1/debug/dialogflow-webhook-status`
- Review Railway logs
- Test webhook with Dialogflow's built-in test panel
