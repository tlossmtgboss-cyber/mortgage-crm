# Aria Inline Scheduling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When Aria can't answer a borrower's question, she fetches the LO's calendar and presents available time slots as inline chips in the chat. The borrower picks a time, Aria books it, and everyone gets notified.

**Architecture:** Backend extends the `/ask` response with an optional `scheduling` block when escalation fires. A new `/book` endpoint handles chat-initiated bookings. Frontend renders slot chips inline in Aria messages and handles the booking flow without leaving the chat.

**Tech Stack:** FastAPI + Pydantic (backend), React + TypeScript (frontend), existing CalendarService/SchedulerBridge for slot fetching and booking.

---

### Task 1: Backend — Add scheduling schemas

**Files:**
- Modify: `backend/schemas/pos/ai_qa.py`

- [ ] **Step 1: Add SchedulingSlot and SchedulingData schemas**

Add after the `Source` class (line 33):

```python
class SchedulingSlot(BaseModel):
    """A single available time slot for inline scheduling."""
    start: str = Field(..., description="ISO 8601 datetime")
    end: str = Field(..., description="ISO 8601 datetime")


class SchedulingData(BaseModel):
    """Calendar data attached to an escalation response."""
    available: bool
    loan_officer_name: str | None = None
    loan_officer_user_id: int | None = None
    slots: list[SchedulingSlot] = Field(default_factory=list)
    duration_minutes: int = 15
    timezone: str = "America/New_York"
    meeting_type: str = "checkin"
    reason: str | None = None
```

- [ ] **Step 2: Add scheduling field to AskResponse**

Add to `AskResponse` after `escalation_reason` (line 77):

```python
    scheduling: SchedulingData | None = None
```

- [ ] **Step 3: Add AriaBookingRequest and AriaBookingResponse schemas**

Add at the end of the file:

```python
class AriaBookingRequest(BaseModel):
    """Body for POST /api/v1/pos/ai-qa/book."""
    application_id: UUID
    slot_start: str = Field(..., description="ISO 8601 datetime")
    slot_end: str = Field(..., description="ISO 8601 datetime")
    borrower_question: str = Field(..., max_length=2000)
    timezone: str = Field(default="America/New_York", max_length=64)


class AriaBookingResponse(BaseModel):
    """Response for a chat-initiated booking."""
    appointment_id: int
    loan_officer_name: str
    scheduled_start: str
    scheduled_end: str
    timezone: str
    meeting_type: str
    email_sent: bool = False
    calendar_event_created: bool = False
    ics_link: str | None = None
    aria_message_id: int
```

- [ ] **Step 4: Commit**

```bash
git add backend/schemas/pos/ai_qa.py
git commit -m "feat(pos): add scheduling schemas for Aria inline booking"
```

---

### Task 2: Backend — Extend AIQAService to fetch slots on escalation

**Files:**
- Modify: `backend/services/pos/ai_qa_service.py`

- [ ] **Step 1: Add CalendarService import and slot-fetch helper**

Add imports at the top (after line 30):

```python
from datetime import datetime, timedelta, timezone

from .calendar_service import CalendarService, NoLoanOfficerAssignedError
```

Add a new method to `AIQAService` after `_score_confidence` (after line 303):

```python
    async def _fetch_scheduling_data(
        self,
        session: Session,
        application: POSApplication,
    ) -> dict[str, Any]:
        """Fetch available slots for inline scheduling on escalation."""
        cal = CalendarService()
        try:
            lo = cal.resolve_loan_officer(session, application)
        except NoLoanOfficerAssignedError:
            return {"available": False, "reason": "no_lo_assigned"}

        now = datetime.now(timezone.utc)
        tz_str = "America/New_York"
        try:
            result = await cal.get_available_slots(
                session,
                application=application,
                start_date=now,
                end_date=now + timedelta(days=14),
                duration_minutes=15,
                timezone_str=tz_str,
            )
        except Exception as exc:
            logger.warning("Failed to fetch slots for inline scheduling: %s", exc)
            return {"available": False, "reason": "slot_fetch_failed"}

        all_slots = []
        for date_slots in result.get("slots_by_date", {}).values():
            for s in date_slots:
                if s.get("is_available", True):
                    all_slots.append({"start": s["start"], "end": s["end"]})
        all_slots.sort(key=lambda s: s["start"])
        all_slots = all_slots[:8]

        if not all_slots:
            return {
                "available": False,
                "reason": "no_slots",
                "loan_officer_name": result.get("loan_officer_name"),
            }

        return {
            "available": True,
            "loan_officer_name": result.get("loan_officer_name"),
            "loan_officer_user_id": result.get("loan_officer_user_id"),
            "slots": all_slots,
            "duration_minutes": 15,
            "timezone": tz_str,
            "meeting_type": "checkin",
        }
```

- [ ] **Step 2: Call slot fetch in ask() when escalation fires**

In the `ask()` method, after the line `escalate = confidence == AIQAConfidence.ESCALATE` (line 92), add:

```python
        # 4b. If escalating, fetch available slots for inline scheduling.
        scheduling = None
        if escalate:
            try:
                scheduling = await self._fetch_scheduling_data(session, application)
            except Exception as exc:
                logger.warning("Inline scheduling fetch failed: %s", exc)
```

Then add `"scheduling": scheduling,` to the return dict (after `"escalation_reason"`):

```python
            "escalation_reason": agent_response.get("escalation_reason"),
            "scheduling": scheduling,
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/pos/ai_qa_service.py
git commit -m "feat(pos): fetch calendar slots on Aria escalation"
```

---

### Task 3: Backend — Wire scheduling into the /ask route response

**Files:**
- Modify: `backend/routes/pos/ai_qa.py`

- [ ] **Step 1: Import the new schemas**

Update the import from `schemas.pos.ai_qa` (line 22-28) to include:

```python
from schemas.pos.ai_qa import (
    AskRequest,
    AskResponse,
    QAHistoryResponse,
    QAMessageResponse,
    SchedulingData,
    SchedulingSlot,
    Source,
)
```

- [ ] **Step 2: Pass scheduling data through in ask_aria()**

In the `ask_aria` function, update the `AskResponse(...)` construction (lines 94-105). After `escalation_reason`, add:

```python
        scheduling=SchedulingData(**result["scheduling"]) if result.get("scheduling") else None,
```

The full return becomes:

```python
    return AskResponse(
        message_id=result["message_id"],
        application_id=result["application_id"],
        content=result["content"],
        sources=[Source(**s) if isinstance(s, dict) else s for s in result.get("sources") or []],
        follow_ups=result.get("follow_ups") or [],
        latency_ms=result["latency_ms"],
        confidence=result["confidence"],
        escalation_recommended=result["escalation_recommended"],
        escalation_reason=result.get("escalation_reason"),
        scheduling=SchedulingData(**result["scheduling"]) if result.get("scheduling") else None,
        created_at=result["created_at"],
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/routes/pos/ai_qa.py
git commit -m "feat(pos): wire scheduling data into /ask response"
```

---

### Task 4: Backend — Add /book endpoint for chat-initiated bookings

**Files:**
- Modify: `backend/routes/pos/ai_qa.py`
- Modify: `backend/services/pos/ai_qa_service.py`

- [ ] **Step 1: Add book_from_chat method to AIQAService**

Add to `AIQAService` after the `get_history` method:

```python
    async def book_from_chat(
        self,
        session: Session,
        *,
        application: POSApplication,
        slot_start: str,
        slot_end: str,
        borrower_question: str,
        timezone_str: str,
        ctx: AuditContext,
    ) -> dict[str, Any]:
        """Book an appointment from the Aria chat, embedding the question."""
        from datetime import datetime as dt

        cal = CalendarService()
        lo = cal.resolve_loan_officer(session, application)

        # Resolve borrower name/email from the personal section.
        personal = next(
            (s.data for s in application.sections if s.section_key == "personal"),
            {},
        ) or {}
        attendee_name = " ".join(
            filter(None, [personal.get("first_name"), personal.get("last_name")])
        ) or "Borrower"
        attendee_email = personal.get("email") or ""

        notes = f"Borrower's question: {borrower_question}"

        booking = await cal.book(
            session,
            application=application,
            meeting_type="checkin",
            slot_start=dt.fromisoformat(slot_start),
            slot_end=dt.fromisoformat(slot_end),
            timezone_str=timezone_str,
            attendee_name=attendee_name,
            attendee_email=attendee_email,
            attendee_phone=personal.get("phone"),
            notes=notes,
            ctx=ctx,
        )

        # Resolve LO name for the response.
        lo_name_parts = [
            getattr(lo, "first_name", None) or "",
            getattr(lo, "last_name", None) or "",
        ]
        lo_name = " ".join(p for p in lo_name_parts if p).strip() or f"User #{lo.id}"

        # Persist an Aria confirmation message in the chat history.
        aria_msg = POSAIQAMessage(
            application_id=application.id,
            role="aria",
            content=(
                f"You're booked! Your call with **{lo_name}** is confirmed.\n\n"
                f"Your question \"{borrower_question}\" has been shared so "
                f"{lo_name.split()[0]} can prepare."
            ),
            sources=[],
            follow_ups=["What documents do I still owe?", "When will I close?"],
            confidence=AIQAConfidence.HIGH,
        )
        session.add(aria_msg)
        session.flush()

        return {
            "appointment_id": booking.appointment_id,
            "loan_officer_name": lo_name,
            "scheduled_start": booking.scheduled_start.isoformat(),
            "scheduled_end": booking.scheduled_end.isoformat(),
            "timezone": timezone_str,
            "meeting_type": "checkin",
            "email_sent": booking.email_sent,
            "calendar_event_created": booking.calendar_event_created,
            "ics_link": booking.ics_link,
            "aria_message_id": aria_msg.id,
        }
```

- [ ] **Step 2: Add the /book route handler**

Add to `backend/routes/pos/ai_qa.py` after the `ask_aria` function, before the History section. Import `AriaBookingRequest` and `AriaBookingResponse` in the imports block:

```python
from schemas.pos.ai_qa import (
    AriaBookingRequest,
    AriaBookingResponse,
    AskRequest,
    AskResponse,
    QAHistoryResponse,
    QAMessageResponse,
    SchedulingData,
    Source,
)
```

Then add the route:

```python
@router.post(
    "/book",
    response_model=AriaBookingResponse,
    summary="Book an appointment from the Aria chat (embeds borrower's question)",
)
async def book_from_chat(
    body: AriaBookingRequest,
    purl_ctx: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db),
    ctx: AuditContext = Depends(build_audit_context),
    service: AIQAService = Depends(get_ai_qa_service),
) -> AriaBookingResponse:
    """Book a call with the LO, embedding the borrower's question in the notes."""
    from ._helpers import resolve_application_direct

    application = resolve_application_direct(
        body.application_id,
        purl_ctx=purl_ctx,
        db=db,
    )

    result = await service.book_from_chat(
        db,
        application=application,
        slot_start=body.slot_start,
        slot_end=body.slot_end,
        borrower_question=body.borrower_question,
        timezone_str=body.timezone,
        ctx=ctx,
    )
    db.commit()

    return AriaBookingResponse(**result)
```

- [ ] **Step 3: Commit**

```bash
git add backend/routes/pos/ai_qa.py backend/services/pos/ai_qa_service.py
git commit -m "feat(pos): add /book endpoint for Aria chat-initiated scheduling"
```

---

### Task 5: Frontend — Add scheduling types and API method

**Files:**
- Modify: `frontend/src/features/pos/types.ts`
- Modify: `frontend/src/features/pos/api/client.ts`

- [ ] **Step 1: Add scheduling types**

Add to `frontend/src/features/pos/types.ts` after the `AskResponse` interface:

```typescript
export interface SchedulingSlot {
  start: string;
  end: string;
}

export interface SchedulingData {
  available: boolean;
  loan_officer_name?: string;
  loan_officer_user_id?: number;
  slots?: SchedulingSlot[];
  duration_minutes?: number;
  timezone?: string;
  meeting_type?: MeetingType;
  reason?: string;
}

export interface AriaBookingRequest {
  application_id: string;
  slot_start: string;
  slot_end: string;
  borrower_question: string;
  timezone: string;
}

export interface AriaBookingResponse {
  appointment_id: number;
  loan_officer_name: string;
  scheduled_start: string;
  scheduled_end: string;
  timezone: string;
  meeting_type: string;
  email_sent: boolean;
  calendar_event_created: boolean;
  ics_link: string | null;
  aria_message_id: number;
}
```

Add `scheduling` to the existing `AskResponse` interface:

```typescript
export interface AskResponse {
  // ... existing fields ...
  scheduling?: SchedulingData | null;
}
```

- [ ] **Step 2: Add bookFromChat API method**

In `frontend/src/features/pos/api/client.ts`, add after the existing `ask` method:

```typescript
  bookFromChat: (body: AriaBookingRequest) =>
    request<AriaBookingResponse>('/api/v1/pos/ai-qa/book', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/pos/types.ts frontend/src/features/pos/api/client.ts
git commit -m "feat(pos): add scheduling types and API method for Aria chat booking"
```

---

### Task 6: Frontend — Extend useAriaChat hook with scheduling state

**Files:**
- Modify: `frontend/src/features/pos/hooks/useAriaChat.ts`

- [ ] **Step 1: Add scheduling fields to UIMessage**

Update the `UIMessage` interface (line 18-27):

```typescript
export interface UIMessage {
  id?: number;
  role: 'borrower' | 'aria';
  content: string;
  sources?: Source[];
  followUps?: string[];
  confidence?: Confidence | string;
  createdAt?: string;
  isOptimistic?: boolean;
  scheduling?: SchedulingData | null;
  bookingConfirmation?: AriaBookingResponse | null;
}
```

Add imports:

```typescript
import type {
  AskResponse,
  AriaBookingResponse,
  Confidence,
  QAMessageResponse,
  SchedulingData,
  SchedulingSlot,
  Source,
} from '../types';
```

- [ ] **Step 2: Add bookSlot method and pass scheduling through**

In the `ask` callback (line 96-113), add `scheduling` to the Aria message:

```typescript
          {
            id: result.message_id,
            role: 'aria',
            content: result.content,
            sources: result.sources,
            followUps: result.follow_ups,
            confidence: result.confidence,
            createdAt: result.created_at,
            scheduling: result.scheduling ?? null,
          },
```

Add a `bookSlot` callback after the `ask` callback:

```typescript
  const bookSlot = useCallback(
    async (slot: SchedulingSlot, question: string) => {
      if (!applicationId) return;
      setThinking(true);
      setError(null);
      try {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York';
        const result = await posApi.bookFromChat({
          application_id: applicationId,
          slot_start: slot.start,
          slot_end: slot.end,
          borrower_question: question,
          timezone: tz,
        });

        // Add the borrower's time selection as a message.
        const timeLabel = new Date(slot.start).toLocaleString(undefined, {
          weekday: 'long',
          month: 'long',
          day: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
          timeZone: tz,
        });

        setMessages(prev => [
          // Clear scheduling from the original Aria message (slot chips go away).
          ...prev.map(m =>
            m.scheduling ? { ...m, scheduling: null } : m,
          ),
          { role: 'borrower', content: `📅 ${timeLabel}` },
          {
            id: result.aria_message_id,
            role: 'aria',
            content: `You're booked! Your call with **${result.loan_officer_name}** is confirmed.\n\nYour question has been shared so ${result.loan_officer_name.split(' ')[0]} can prepare.`,
            followUps: ['What documents do I still owe?', 'When will I close?'],
            bookingConfirmation: result,
          },
        ]);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Booking failed');
      } finally {
        setThinking(false);
      }
    },
    [applicationId],
  );
```

Update the return block to include `bookSlot`:

```typescript
  return {
    messages,
    thinking,
    loading,
    error,
    ask,
    bookSlot,
  };
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/pos/hooks/useAriaChat.ts
git commit -m "feat(pos): add scheduling state and bookSlot to useAriaChat"
```

---

### Task 7: Frontend — Render slot chips and booking card in AriaPanel

**Files:**
- Modify: `frontend/src/features/pos/components/AriaPanel.tsx`

- [ ] **Step 1: Update hook import and track last question**

Update the hook usage (line 26) to include `bookSlot`:

```typescript
  const { messages, thinking, ask, bookSlot, error } = useAriaChat(applicationId, currentStep);
```

Add state to track the last borrower question (after `draft` state, line 27):

```typescript
  const [lastQuestion, setLastQuestion] = useState('');
```

In the `submit` function (line 67-72), track the question:

```typescript
  const submit = (text: string) => {
    if (!text.trim() || thinking) return;
    setLastQuestion(text.trim());
    ask(text);
    setDraft('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
  };
```

- [ ] **Step 2: Add SlotChips component**

Add before the icon components (before `const CloseIcon`, line 308):

```typescript
const SlotChips: React.FC<{
  scheduling: SchedulingData;
  onBook: (slot: SchedulingSlot) => void;
  disabled?: boolean;
}> = ({ scheduling, onBook, disabled }) => {
  const [expanded, setExpanded] = useState(false);

  if (!scheduling.available || !scheduling.slots?.length) {
    return (
      <div className="aria-slot-empty">
        No times available right now — please reach out to{' '}
        {scheduling.loan_officer_name ?? 'your loan officer'} directly.
      </div>
    );
  }

  const visible = expanded ? scheduling.slots : scheduling.slots.slice(0, 5);
  const remaining = scheduling.slots.length - 5;
  const tz = scheduling.timezone || 'America/New_York';

  return (
    <div className="aria-slot-section">
      <div className="aria-slot-label">
        Pick a time with {scheduling.loan_officer_name ?? 'your loan officer'}:
      </div>
      <div className="aria-slot-chips">
        {visible.map((slot, i) => (
          <button
            key={i}
            type="button"
            className="aria-slot-chip"
            onClick={() => onBook(slot)}
            disabled={disabled}
          >
            {formatSlotLabel(slot.start, tz)}
          </button>
        ))}
        {!expanded && remaining > 0 && (
          <button
            type="button"
            className="aria-slot-chip aria-slot-chip--more"
            onClick={() => setExpanded(true)}
          >
            + {remaining} more
          </button>
        )}
      </div>
    </div>
  );
};

function formatSlotLabel(iso: string, tz: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString(undefined, { weekday: 'short', timeZone: tz });
  const date = d.toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', timeZone: tz });
  const time = d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', timeZone: tz });
  return `${day} ${date} · ${time}`;
}
```

Add the import for `SchedulingData` and `SchedulingSlot` at the top:

```typescript
import type { SchedulingData, SchedulingSlot, Source } from '../types';
```

Also import `useState` since `SlotChips` uses it (it's already imported at line 8).

- [ ] **Step 3: Add BookingCard component**

Add after `SlotChips`:

```typescript
const BookingCard: React.FC<{ booking: AriaBookingResponse }> = ({ booking }) => (
  <div className="aria-booking-card">
    <div className="aria-booking-card__header">
      <span className="aria-booking-card__check">✓</span>
      <strong>Call with {booking.loan_officer_name}</strong>
    </div>
    <div className="aria-booking-card__detail">
      {new Date(booking.scheduled_start).toLocaleString(undefined, {
        weekday: 'long',
        month: 'long',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        timeZone: booking.timezone,
        timeZoneName: 'short',
      })}
    </div>
    <div className="aria-booking-card__detail">📞 15-minute phone call</div>
    <div className="aria-booking-card__meta">
      {booking.email_sent && '✉️ Confirmation email sent'}
      {booking.email_sent && booking.calendar_event_created && ' · '}
      {booking.calendar_event_created && '📅 Calendar invite delivered'}
    </div>
  </div>
);
```

Add the `AriaBookingResponse` import:

```typescript
import type { AriaBookingResponse, SchedulingData, SchedulingSlot, Source } from '../types';
```

- [ ] **Step 4: Wire SlotChips and BookingCard into Message component**

Update the `Message` component (lines 198-222). Replace the existing Aria branch with:

```typescript
  return (
    <div className="aria-msg-row aria-msg-row--aria">
      <div className="aria-msg-seal" aria-hidden>A</div>
      <div className="aria-msg-bubble">
        <AriaContent content={message.content} />
        {message.sources && message.sources.length > 0 && (
          <div className="aria-sources">
            <div className="aria-sources__label">Sources</div>
            {message.sources.map((s, i) => (
              <SourceChip key={i} source={s} />
            ))}
          </div>
        )}
        {message.scheduling && (
          <SlotChips
            scheduling={message.scheduling}
            onBook={slot => bookSlot(slot, lastQuestion)}
            disabled={thinking}
          />
        )}
        {message.bookingConfirmation && (
          <BookingCard booking={message.bookingConfirmation} />
        )}
      </div>
    </div>
  );
```

The `Message` component needs access to `bookSlot`, `lastQuestion`, and `thinking`. The simplest approach: convert `Message` from a standalone component to an inline render function, or pass these as props. Use props:

Update the Message component signature:

```typescript
const Message: React.FC<{
  message: UIMessage;
  onBookSlot?: (slot: SchedulingSlot, question: string) => void;
  lastQuestion?: string;
  disabled?: boolean;
}> = ({ message, onBookSlot, lastQuestion, disabled }) => {
```

Then in `SlotChips`:
```typescript
        {message.scheduling && onBookSlot && (
          <SlotChips
            scheduling={message.scheduling}
            onBook={slot => onBookSlot(slot, lastQuestion || '')}
            disabled={disabled}
          />
        )}
```

And update the message rendering in the main component body (line 124-126):

```typescript
          {messages.map((m, i) => (
            <Message
              key={m.id ?? `optimistic-${i}`}
              message={m}
              onBookSlot={bookSlot}
              lastQuestion={lastQuestion}
              disabled={thinking}
            />
          ))}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/pos/components/AriaPanel.tsx
git commit -m "feat(pos): render inline slot chips and booking card in Aria chat"
```

---

### Task 8: Frontend — Add CSS for slot chips and booking card

**Files:**
- Modify: `frontend/src/features/pos/pos.css`

- [ ] **Step 1: Add slot chip and booking card styles**

Add after the `.aria-panel__disclaimer` block (before `/* ---------- Smart Calendar ---------- */`):

```css
/* ---------- Aria Scheduling Chips ---------- */

.aria-slot-section {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--bt-border);
}

.aria-slot-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--bt-text-secondary);
  margin-bottom: 8px;
}

.aria-slot-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.aria-slot-chip {
  background: var(--bt-bg-surface);
  border: 1.5px solid var(--bt-border);
  border-radius: 8px;
  padding: 7px 12px;
  font-family: var(--bt-font-body);
  font-size: 12px;
  color: var(--bt-text-primary);
  cursor: pointer;
  transition: all 0.15s;
}
.aria-slot-chip:hover:not(:disabled) {
  border-color: var(--bt-primary);
  background: var(--bt-primary-tint);
  color: var(--bt-primary);
}
.aria-slot-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.aria-slot-chip--more {
  color: var(--bt-text-muted);
  border-style: dashed;
}
.aria-slot-chip--more:hover:not(:disabled) {
  color: var(--bt-text-secondary);
  border-color: var(--bt-border-strong);
  background: var(--bt-bg-elevated);
}

.aria-slot-empty {
  margin-top: 10px;
  font-size: 12px;
  color: var(--bt-text-muted);
  font-style: italic;
}

/* Booking confirmation card */
.aria-booking-card {
  margin-top: 12px;
  background: var(--bt-bg-surface);
  border: 1px solid var(--bt-border);
  border-radius: 8px;
  padding: 12px 14px;
}

.aria-booking-card__header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 13px;
}

.aria-booking-card__check {
  color: var(--bt-success);
  font-size: 15px;
}

.aria-booking-card__detail {
  font-size: 12px;
  color: var(--bt-text-secondary);
  margin-bottom: 2px;
}

.aria-booking-card__meta {
  margin-top: 8px;
  font-size: 11px;
  color: var(--bt-text-muted);
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/pos/pos.css
git commit -m "feat(pos): add CSS for Aria inline scheduling chips and booking card"
```

---

### Task 9: Integration test — full flow

**Files:**
- Modify: `frontend/src/features/pos/components/AriaPanel.tsx` (if needed)
- No new test file (manual verification in browser)

- [ ] **Step 1: Verify TypeScript compiles**

Run:
```bash
cd frontend && npx tsc --noEmit --skipLibCheck
```
Expected: no errors in `features/pos/` files.

- [ ] **Step 2: Test the flow in the browser**

1. Open the POS app at `app.perenniaai.com/pos`
2. Open Aria chat panel
3. Ask a question Aria can't answer (e.g., "how much can I afford?")
4. Verify: Aria response includes inline slot chips
5. Click a time slot
6. Verify: booking confirmation card appears in chat
7. Verify: LO receives calendar appointment with the question in notes

- [ ] **Step 3: Push to production**

```bash
git push origin main
```

---

### Task 10: Add "Connect me with my loan officer" as a scheduling trigger

**Files:**
- Modify: `frontend/src/features/pos/hooks/useAriaChat.ts`

- [ ] **Step 1: Detect scheduling intent in the hook**

The suggestion chip "Connect me with my loan officer" is already shown by the seed greeting (line 162 of useAriaChat.ts). When the borrower clicks it (or types similar text), the guidelines agent on the backend returns an escalation. No frontend changes needed for this path — it flows through the normal escalation → scheduling pipeline.

Verify the seed greeting includes the suggestion:

```typescript
    followUps: [
      'How are my numbers looking?',
      'Can I use gift funds?',
      "What's left to do?",
      'Connect me with my loan officer',
    ],
```

Update line 160 to replace `'Will I need PMI?'` with `'Connect me with my loan officer'`.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/pos/hooks/useAriaChat.ts
git commit -m "feat(pos): add 'Connect me with my loan officer' to Aria seed suggestions"
```
