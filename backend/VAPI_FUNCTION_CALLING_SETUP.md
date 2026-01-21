# Vapi Function Calling Setup Guide

This guide will help you configure your Vapi assistant (Sam) to update the CRM in real-time during phone calls.

## What's Been Implemented

5 new API endpoints that Sam can call during conversations:

1. **get_lead_info** - Lookup caller information by phone number
2. **update_lead_status** - Update lead stage and add notes
3. **create_task** - Create follow-up tasks for the team
4. **schedule_appointment** - Schedule meetings/callbacks
5. **get_available_time_slots** - Show available appointment times

## Step 1: Update System Prompt

1. Go to https://dashboard.vapi.ai
2. Navigate to your assistant: **120e239e-4d19-4e43-ad92-1f8b07d08c8c**
3. Click on the assistant to edit
4. Find the **System Prompt** section
5. Replace the current prompt with the content from `backend/vapi_system_prompt.txt`

The new prompt instructs Sam to:
- Check for existing leads at the start of each call
- Update lead records with information gathered
- Create tasks when callers request callbacks
- Schedule appointments
- Provide personalized service to existing customers

## Step 2: Add Server URL for Functions

In the Vapi assistant configuration:

1. Scroll to the **Server** section
2. Set **Server URL** to:
   ```
   https://app.perenniaai.com/api/vapi/functions
   ```
3. Set **Server URL Request Method** to `POST`

## Step 3: Configure Functions

In the **Functions** section of your assistant, add these 5 functions:

### Function 1: Get Lead Info
```json
{
  "name": "get_lead_info",
  "description": "Get information about a lead by their phone number. Use this to personalize the conversation with existing customers.",
  "parameters": {
    "type": "object",
    "properties": {
      "phone_number": {
        "type": "string",
        "description": "The caller's phone number"
      }
    },
    "required": ["phone_number"]
  },
  "url": "https://app.perenniaai.com/api/vapi/functions/get-lead-info",
  "method": "POST"
}
```

### Function 2: Update Lead Status
```json
{
  "name": "update_lead_status",
  "description": "Update a lead's status or add notes after gathering information. Use this when the conversation progresses the lead to a new stage or when important information is shared.",
  "parameters": {
    "type": "object",
    "properties": {
      "phone_number": {
        "type": "string",
        "description": "The caller's phone number"
      },
      "stage": {
        "type": "string",
        "enum": ["New", "Attempted Contact", "Prospect", "Application Started", "Application Complete", "Pre-Approved"],
        "description": "The new stage for the lead"
      },
      "notes": {
        "type": "string",
        "description": "Notes to add to the lead record"
      }
    },
    "required": ["phone_number"]
  },
  "url": "https://app.perenniaai.com/api/vapi/functions/update-lead-status",
  "method": "POST"
}
```

### Function 3: Create Task
```json
{
  "name": "create_task",
  "description": "Create a follow-up task for the team. Use this when the caller requests a callback, needs documentation, or any action item is identified.",
  "parameters": {
    "type": "object",
    "properties": {
      "phone_number": {
        "type": "string",
        "description": "The caller's phone number"
      },
      "title": {
        "type": "string",
        "description": "Brief title for the task"
      },
      "description": {
        "type": "string",
        "description": "Detailed description of what needs to be done"
      },
      "priority": {
        "type": "string",
        "enum": ["low", "medium", "high"],
        "description": "Task priority level"
      },
      "due_date": {
        "type": "string",
        "description": "ISO format datetime string for when the task is due"
      }
    },
    "required": ["phone_number", "title"]
  },
  "url": "https://app.perenniaai.com/api/vapi/functions/create-task",
  "method": "POST"
}
```

### Function 4: Schedule Appointment
```json
{
  "name": "schedule_appointment",
  "description": "Schedule an appointment or meeting with the caller. Use this when they want to meet with a loan officer or schedule a callback at a specific time.",
  "parameters": {
    "type": "object",
    "properties": {
      "phone_number": {
        "type": "string",
        "description": "The caller's phone number"
      },
      "type": {
        "type": "string",
        "enum": ["Meeting", "Call", "Email"],
        "description": "Type of appointment"
      },
      "appointment_time": {
        "type": "string",
        "description": "ISO format datetime string for the appointment"
      },
      "notes": {
        "type": "string",
        "description": "Additional notes about the appointment"
      }
    },
    "required": ["phone_number"]
  },
  "url": "https://app.perenniaai.com/api/vapi/functions/schedule-appointment",
  "method": "POST"
}
```

### Function 5: Get Available Time Slots
```json
{
  "name": "get_available_time_slots",
  "description": "Get available appointment time slots for a specific date. Use this to help customers schedule appointments.",
  "parameters": {
    "type": "object",
    "properties": {
      "date": {
        "type": "string",
        "description": "ISO format date string (YYYY-MM-DD)"
      }
    }
  },
  "url": "https://app.perenniaai.com/api/vapi/functions/available-time-slots",
  "method": "GET"
}
```

## Step 4: Save and Publish

1. Click **Save** to save your assistant configuration
2. Click **Publish** to make the changes live

## Testing the Functions

Make a test call to: **(832) 648-2297**

Try these scenarios:

### Test 1: Existing Customer Recognition
1. Call from a phone number that's already in the CRM
2. Sam should recognize you and greet you by name

### Test 2: Schedule a Callback
Say: "Can someone call me back tomorrow at 2 PM?"
- Sam should create a task for the team
- Check the Tasks page in the CRM to verify

### Test 3: Schedule an Appointment
Say: "I'd like to schedule a meeting with a loan officer"
- Sam should offer available time slots
- After you choose, check Activities and Tasks in the CRM

### Test 4: Update Lead Information
Say: "I'm interested in a conventional loan for a $500,000 home in Austin"
- Sam should update your lead record with these details
- Check the lead's notes in the CRM

## Monitoring Function Calls

To see function calling in action:

1. Go to https://dashboard.vapi.ai
2. Navigate to **Calls** after making a test call
3. Click on your call to see the transcript
4. Look for function calls in the **Events** section
5. You should see when Sam called functions and the responses

## Troubleshooting

**Functions not being called?**
- Verify the Server URL is set correctly
- Check that all 5 functions are configured
- Make sure the system prompt was updated
- Ensure the assistant is published

**Function calls failing?**
- Check Railway logs for errors
- Verify the endpoints are accessible
- Test endpoints directly with curl:
  ```bash
  curl -X POST https://app.perenniaai.com/api/vapi/functions/get-lead-info \
    -H "Content-Type: application/json" \
    -d '{"phone_number": "+18434169589"}'
  ```

**Sam not recognizing existing leads?**
- Make sure you have leads with phone numbers in your CRM
- Phone number matching works with or without formatting
- Check that the phone number in the CRM matches the caller ID

## What Happens During a Call

1. **Call starts** → Sam greets the caller
2. **First action** → Calls `get_lead_info` to check for existing customer
3. **If found** → Personalizes greeting with their name and information
4. **During conversation** → Calls functions as needed:
   - Caller requests callback → `create_task`
   - Caller wants appointment → `schedule_appointment`
   - Important info shared → `update_lead_status`
5. **End of call** → Webhook saves full transcript and analysis

## Benefits

With function calling enabled:

- Real-time CRM updates during calls
- No manual data entry needed
- Immediate task creation for follow-ups
- Personalized service for returning customers
- Automatic appointment scheduling
- Complete audit trail of all interactions

## Next Steps

After testing, consider:
- Training your team on how to review AI-scheduled appointments
- Setting up notifications for high-priority tasks created by Sam
- Reviewing call transcripts to improve Sam's prompts
- Adding more functions for specific workflows
