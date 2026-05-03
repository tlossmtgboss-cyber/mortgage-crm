# Aria Inline Scheduling — Design Spec

When Aria can't answer a borrower's question, she schedules a call with the loan officer directly from the chat — no page navigation, no separate widget. The borrower picks a time from inline slot chips, and everything else (email, calendar invite, reminders) happens automatically.

## Trigger Conditions

Aria offers to schedule when:

1. **AI escalation** — the guidelines agent returns `escalation_reason` (confidence = "escalate"). Aria's response includes the explanation + slot chips.
2. **Explicit request** — borrower clicks the "Connect me with my loan officer" suggestion chip or types something like "I want to talk to my LO". Aria skips the AI answer step and goes straight to scheduling.

## Conversation Flow

```
Borrower: "how much can i afford?"
    ↓
Aria: "Great question! Affordability depends on your specific income, 
       debts, and the rate you qualify for — your loan officer can run 
       those numbers for you. Let me get you on a quick call with 
       Timothy Loss."
    ↓
Aria: [slot chips: Mon 5/5 · 9:30a | Mon 5/5 · 10:00a | Tue 5/6 · 2:00p | ...]
    ↓
Borrower: [clicks Mon 5/5 · 10:00a]
    ↓
Aria: "✓ You're booked! Call with Timothy Loss — Monday, May 5 · 10:00 AM EDT
       Your question 'how much can I afford?' has been shared so Timothy 
       can prepare. Confirmation email sent · Calendar invite delivered."
    ↓
Aria: "In the meantime, is there anything else I can help with?"
```

## Backend Changes

### 1. Extend `AIQAService.ask()` response

When `escalation_recommended` is true, the service also calls `CalendarService.get_available_slots()` and includes the slots in the response.

**File:** `backend/services/pos/ai_qa_service.py`

New fields in the return dict:
```python
{
    # ... existing fields ...
    "scheduling": {
        "available": True,
        "loan_officer_name": "Timothy Loss",
        "loan_officer_user_id": 42,
        "slots": [
            {"start": "2026-05-05T09:30:00-04:00", "end": "2026-05-05T09:45:00-04:00"},
            {"start": "2026-05-05T10:00:00-04:00", "end": "2026-05-05T10:15:00-04:00"},
            ...
        ],
        "duration_minutes": 15,
        "timezone": "America/New_York",
        "meeting_type": "checkin"
    }
}
```

When CalendarService can't resolve an LO or no slots are available:
```python
{
    "scheduling": {
        "available": False,
        "reason": "no_slots" | "no_lo_assigned"
    }
}
```

Slot fetch uses the existing `CalendarService.get_available_slots()` with a 14-day window and 15-minute duration (quick call, not full consultation). Limit to the first 8 slots to keep the chat compact.

### 2. New booking endpoint

**File:** `backend/routes/pos/ai_qa.py`

```
POST /api/v1/pos/ai-qa/book
```

Request body:
```json
{
    "application_id": "uuid",
    "slot_start": "2026-05-05T10:00:00-04:00",
    "slot_end": "2026-05-05T10:15:00-04:00",
    "borrower_question": "how much can I afford?",
    "timezone": "America/New_York"
}
```

This endpoint:
1. Resolves the LO via `CalendarService.resolve_loan_officer()`
2. Calls `CalendarService.book()` with:
   - `meeting_type="checkin"` (15 min)
   - `notes` = the borrower's question text
   - `attendee_name/email` from the POS application's personal section
3. Persists an Aria message confirming the booking (role='aria', with booking details)
4. Publishes a `POS_APPOINTMENT_BOOKED` event
5. Returns booking confirmation

Response:
```json
{
    "appointment_id": 123,
    "loan_officer_name": "Timothy Loss",
    "scheduled_start": "2026-05-05T10:00:00-04:00",
    "scheduled_end": "2026-05-05T10:15:00-04:00",
    "timezone": "America/New_York",
    "email_sent": true,
    "calendar_event_created": true,
    "ics_link": "https://...",
    "aria_message_id": 456
}
```

### 3. "Connect me" intent detection

When the borrower types a connect/schedule request (or clicks the suggestion chip), the guidelines agent should recognize this as a scheduling intent rather than a question to answer. The agent returns:
```python
{
    "content": "I'll get you on a call with your loan officer right now.",
    "escalation_reason": "borrower_requested_lo_contact",
    "sources": [],
    "follow_ups": []
}
```

This triggers the same slot-fetch path as a normal escalation.

## Frontend Changes

### 1. New types

**File:** `frontend/src/features/pos/types.ts`

```typescript
interface SchedulingData {
    available: boolean;
    loan_officer_name?: string;
    loan_officer_user_id?: number;
    slots?: Array<{ start: string; end: string }>;
    duration_minutes?: number;
    timezone?: string;
    meeting_type?: MeetingType;
    reason?: 'no_slots' | 'no_lo_assigned';
}

// Extend AskResponse
interface AskResponse {
    // ... existing fields ...
    scheduling?: SchedulingData | null;
}

interface AriaBookingRequest {
    application_id: string;
    slot_start: string;
    slot_end: string;
    borrower_question: string;
    timezone: string;
}

interface AriaBookingResponse {
    appointment_id: number;
    loan_officer_name: string;
    scheduled_start: string;
    scheduled_end: string;
    timezone: string;
    email_sent: boolean;
    calendar_event_created: boolean;
    ics_link: string | null;
    aria_message_id: number;
}
```

### 2. API client method

**File:** `frontend/src/features/pos/api/client.ts`

```typescript
posApi.bookFromChat(body: AriaBookingRequest): Promise<AriaBookingResponse>
// POST /api/v1/pos/ai-qa/book
```

### 3. Chat hook updates

**File:** `frontend/src/features/pos/hooks/useAriaChat.ts`

New state:
- `bookingInProgress: boolean`
- Last escalation question tracked so it can be passed to booking

New method:
- `bookSlot(slot: { start: string; end: string }): Promise<void>` — calls `posApi.bookFromChat()`, adds confirmation message to the chat

### 4. AriaPanel rendering

**File:** `frontend/src/features/pos/components/AriaPanel.tsx`

When a message has `scheduling?.available === true`:
- Render slot chips below the message text using `.aria-slot-chips` container
- Each chip shows day + time (e.g., "Mon 5/5 · 9:30a")
- On click: chip gets selected state, booking request fires
- After booking: chips replaced by confirmation card
- If `scheduling.available === false`: render "No times available right now — reach out to {LO name} directly"

"+ N more times" chip at the end if there are more than 5 slots, expanding to show all on click.

### 5. CSS additions

**File:** `frontend/src/features/pos/pos.css`

New classes:
- `.aria-slot-chips` — flex-wrap container for time chips
- `.aria-slot-chip` — individual time button (white bg, border, rounded)
- `.aria-slot-chip.is-selected` — selected state (green border + bg)
- `.aria-slot-chip.is-booked` — post-booking state (checkmark)
- `.aria-booking-card` — the confirmation card shown after booking
- `.aria-booking-card__detail` — individual detail line in the card

## What Happens For Each Party

### Loan Officer / Production Assistant
- Appointment appears on their Smart Calendar
- Email notification with subject: "POS Booking: [Borrower Name] — [Question]"
- `Appointment.attendee_notes` contains the borrower's question
- `Appointment.ai_booking_context` includes `{"source": "aria_chat_escalation", "question": "...", "confidence": "escalate"}`
- Appointment linked to the borrower's loan via `Appointment.loan_id`

### Borrower
- Confirmation email with ICS calendar file (sent by existing scheduler infrastructure)
- Calendar invite delivered
- Automatic reminders at 24h and 2h before the call (existing reminder tasks)
- Confirmation card visible in the Aria chat history
- Can continue chatting with Aria about other questions

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| LO has no booking link | Aria says "I couldn't find available times — please reach out to {name} directly at {email}" |
| No slots in next 14 days | Same fallback message |
| Slot taken between display and click | Show error "That time was just taken — here are updated times" + refresh slots |
| Borrower already has a pending appointment | Aria mentions the existing appointment and asks if they want another one |
| CalendarService throws | Aria falls back to text-only escalation (current behavior) — scheduling is best-effort |
| Multiple escalations in one chat | Each gets its own set of slot chips |

## Not In Scope

- Video call booking from chat (phone only for quick escalation calls)
- Rescheduling from within the chat (borrower can cancel from email/calendar)
- PA routing (always routes to the LO assigned to the loan)
- Custom meeting duration selection from chat (hardcoded to 15-min checkin)
