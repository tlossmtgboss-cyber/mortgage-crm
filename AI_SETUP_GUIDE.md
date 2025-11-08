# Agentic AI Setup Guide

## Overview
This guide explains how to set up and enhance the agentic AI capabilities in your Mortgage CRM.

## Current Implementation Status

### ✅ Already Working
- **AI Chat Assistant**: Context-aware conversations with GPT-4o-mini
- **Lead/Loan Context**: AI has access to lead and loan data
- **Conversation History**: Maintains context across conversations
- **Task Suggestions**: AI can suggest task completions
- **Frontend Integration**: AI Assistant component in UI

### ✅ NEW - Agentic Features NOW IMPLEMENTED!
The AI can now autonomously execute actions using function calling:
- **create_task**: Creates tasks automatically
- **update_lead_stage**: Moves leads through pipeline
- **add_activity**: Logs notes and activities
- **get_lead_details**: Retrieves lead information
- **get_high_priority_leads**: Analyzes priorities
- **search_leads**: Searches your CRM data

### ❌ Not Yet Configured

#### 1. OpenAI API Key (CRITICAL - DO THIS FIRST)
**Status**: Not set in production
**Impact**: AI features return 503 errors without this

**How to Fix**:
```bash
# Step 1: Get API key from OpenAI
Visit: https://platform.openai.com/api-keys
Create a new secret key

# Step 2: Add to Railway
1. Go to Railway dashboard: https://railway.app
2. Select your backend service
3. Click "Variables" tab
4. Add variable:
   Name: OPENAI_API_KEY
   Value: sk-proj-your-key-here
5. Click "Redeploy" or service will auto-redeploy

# Step 3: Verify
Check backend logs for: "✅ OpenAI client initialized"
```

**Cost**: ~$0.50-2.00 per 1000 conversations (gpt-4o-mini is very affordable)

---

## Agentic AI Capabilities

### What "Agentic AI" Means
An agentic AI can:
1. **Take autonomous actions** (not just respond to questions)
2. **Execute functions** (create tasks, update leads, send emails)
3. **Make decisions** based on context
4. **Trigger workflows** without human intervention

### Current Capabilities vs. Full Agentic

| Feature | Current | Full Agentic |
|---------|---------|--------------|
| Answer questions | ✅ Yes | ✅ Yes |
| Suggest actions | ✅ Yes | ✅ Yes |
| **Execute actions** | ❌ No | ✅ Yes |
| **Create tasks** | ❌ Manual | ✅ Automatic |
| **Update leads** | ❌ Manual | ✅ Automatic |
| **Send emails** | ❌ Manual | ✅ Automatic |
| **Schedule meetings** | ❌ Manual | ✅ Automatic |

---

## Implementation Roadmap

### Phase 1: Basic AI (CURRENT)
- [x] Chat interface
- [x] Context awareness
- [ ] Set OpenAI API key ⚠️ **DO THIS NOW**

### Phase 2: Enhanced AI (NEXT)
Implement function calling to allow AI to take actions:

**Functions to Add**:
1. `create_task(title, description, due_date, lead_id)`
2. `update_lead_stage(lead_id, new_stage, reason)`
3. `send_email(lead_id, subject, body)`
4. `schedule_meeting(lead_id, date, duration)`
5. `add_note(lead_id, note)`
6. `create_activity(lead_id, type, description)`

**Example Implementation**:
```python
# Backend: Add function calling
tools = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new task for a lead",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "lead_id": {"type": "integer"},
                    "due_date": {"type": "string"}
                },
                "required": ["title", "lead_id"]
            }
        }
    }
]

response = openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    tools=tools,
    tool_choice="auto"
)

# Execute function if AI calls it
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        if tool_call.function.name == "create_task":
            args = json.loads(tool_call.function.arguments)
            # Actually create the task in database
            create_task_in_db(args)
```

### Phase 3: Autonomous Workflows
- Scheduled AI checks (daily lead reviews)
- Automatic lead scoring updates
- Proactive task creation
- Smart follow-up reminders
- Predictive analytics

### Phase 4: Advanced Features
- Voice integration (speech-to-text)
- Email parsing and auto-response
- Document analysis
- Market data integration
- Competitive analysis

---

## Quick Start (Get AI Working Now)

### Step 1: Set API Key
```bash
# In Railway dashboard:
OPENAI_API_KEY=sk-proj-your-actual-key-here
```

### Step 2: Test the Chat
```bash
# Open your CRM
# Click AI Assistant button (right side)
# Type: "What should I do with my high-priority leads?"
# Should get response (not 503 error)
```

### Step 3: Test Context Awareness
```bash
# Navigate to a lead detail page
# Open AI Assistant
# Ask: "What's the status of this lead?"
# AI should know the lead context
```

---

## Enabling Agentic Features (Requires Code Changes)

To make the AI truly "agentic" (able to take actions), you need to:

1. **Add OpenAI Function Calling**
   - Define available functions
   - Parse function calls from AI
   - Execute functions in backend

2. **Add Permission System**
   - Allow AI to create tasks (safe)
   - Require approval for emails (safety)
   - Log all AI actions (audit trail)

3. **Add Workflow Triggers**
   - Cron jobs for scheduled AI reviews
   - Webhooks for real-time AI responses
   - Event-driven AI actions

4. **Add Safety Controls**
   - Action limits (max 10 emails/day)
   - Human-in-the-loop for important decisions
   - Rollback capabilities
   - Audit logging

---

## Cost Estimates

### OpenAI Pricing (gpt-4o-mini)
- Input: $0.150 per 1M tokens
- Output: $0.600 per 1M tokens

**Typical Usage**:
- 100 conversations/day = ~$0.50/day = $15/month
- 500 conversations/day = ~$2.50/day = $75/month
- 1000 conversations/day = ~$5.00/day = $150/month

**Function calling adds minimal cost** (~10-20% increase)

---

## Security Considerations

1. **API Key Security**
   - ✅ Store in environment variables (Railway)
   - ❌ Never commit to code
   - ✅ Rotate every 90 days

2. **Action Permissions**
   - Only allow AI to act on user's own data
   - Require approval for:
     - Sending emails
     - Deleting records
     - Financial transactions

3. **Rate Limiting**
   - Limit AI requests per user
   - Implement exponential backoff
   - Monitor costs

---

## Monitoring & Debugging

### Check if AI is Working
```bash
# View backend logs in Railway
# Look for:
# ✅ "OpenAI client initialized"
# ✅ "AI chat completed for user..."
# ❌ "OpenAI API key not configured" = Key missing
# ❌ "OpenAI API error" = Check key or quota
```

### Common Issues

**503 Error**:
- Cause: OPENAI_API_KEY not set
- Fix: Add key to Railway variables

**500 Error**:
- Cause: Invalid API key or quota exceeded
- Fix: Check OpenAI dashboard for usage/billing

**No Response**:
- Cause: Network/timeout
- Fix: Check Railway logs

---

## Next Steps

### Immediate (Do Today):
1. ✅ Set OPENAI_API_KEY in Railway
2. ✅ Test AI chat in production
3. ✅ Monitor costs in OpenAI dashboard

### Short Term (This Week):
1. Implement function calling for task creation
2. Add AI action logging
3. Test agentic task automation

### Long Term (This Month):
1. Add email automation with AI
2. Implement scheduled AI reviews
3. Add predictive lead scoring
4. Build AI-powered insights dashboard

---

## Support Resources

- **OpenAI Documentation**: https://platform.openai.com/docs
- **Function Calling Guide**: https://platform.openai.com/docs/guides/function-calling
- **Pricing**: https://openai.com/pricing
- **Railway Docs**: https://docs.railway.app

---

## Want Me to Implement Agentic Features?

I can add full agentic capabilities with function calling. This would enable:
- Automatic task creation
- Smart email composition
- Proactive lead updates
- Autonomous workflow triggers

Just let me know and I'll implement the function calling framework!
