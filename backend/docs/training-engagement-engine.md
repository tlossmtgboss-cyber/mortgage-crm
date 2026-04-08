# Perennia AI -- Omnichannel Engagement Engine Training Guide

## What Is the Engagement Engine?

The Engagement Engine is the AI-powered brain that automatically contacts, qualifies, and nurtures your leads across every communication channel -- voice calls, SMS, email, and ringless voicemail -- so you never miss a lead and never let one go cold.

At the center is **Aria**, your AI assistant. When a new lead arrives, Aria initiates first contact within 60 seconds. She qualifies borrowers by asking the right questions, books appointments on your calendar, and transfers hot leads to you live with a full briefing. Between those conversations, Aria runs intelligent drip campaigns that adapt based on how each borrower responds.

You do not need to manually chase leads, remember to follow up, or worry about compliance. The engine handles all of that. Your job is to close loans -- Aria handles everything that gets borrowers to your desk.


---


## How Leads Enter the System

Leads flow into Perennia from multiple sources:

- **Web forms** on your microsite or landing pages
- **Encompass imports** via the LOS integration sync
- **Salesforce sync** for organizations using Salesforce as a lead aggregator
- **Follow Up Boss (FUB) webhooks** from partner real estate agents
- **Manual entry** by you or your team in the Perennia dashboard

### Speed-to-Lead: The 60-Second Window

The moment a new lead is created, the engagement engine fires a `new_lead` trigger. If the lead has a phone number and it is within TCPA calling hours (8 AM to 9 PM in the borrower's local time), Aria places an AI voice call within 60 seconds.

If a call cannot be placed -- quiet hours, no phone number on file, or the number is on the Do Not Call list -- the engine automatically falls back to SMS, then email. The borrower always gets contacted on the fastest available channel.


---


## Channel 1: AI Voice Calls

### How It Works

Aria places outbound calls using Vapi AI with the Deepgram asteria voice. The call sounds natural and conversational, not robotic.

### What Aria Says

Each call opens with a personalized greeting built from the lead's data. If Aria already has context from prior SMS messages, emails, or previous calls, she references that context: "Hi Jane, I saw you were looking into purchase options for the Charleston area."

### Qualifying Questions

Aria asks one question at a time and adapts based on answers:

- **Loan purpose**: Purchase, refinance, cash-out, HELOC
- **Timeline**: How soon are you looking to move forward?
- **Price range / loan amount**: What price range are you targeting?
- **Credit range**: Excellent (740+), Good (680-739), Fair (620-679), or Below 620
- **Employment**: W-2 employed, self-employed, retired

### Call Outcomes

After qualification, one of four things happens:

1. **Live transfer** -- Borrower is ready now. Aria places the borrower on a brief hold, dials you, plays a whisper briefing with the borrower's details, then bridges both of you into a conference call.
2. **Appointment booked** -- Borrower wants to talk but not right this second. Aria books a time on your calendar.
3. **Nurture sequence** -- Borrower is interested but not ready. Aria enrolls them in a drip campaign matched to their loan type and timeline.
4. **Disqualification / Turn-down** -- A deal breaker was identified (e.g., credit below 580, timeline over 12 months). Aria provides alternatives (credit repair referral, long-term nurture) rather than dead-ending the conversation.

### TCPA Compliance

- No calls before 8 AM or after 9 PM in the borrower's local time zone
- Timezone is determined from the borrower's area code (comprehensive US area code mapping)
- DNC registry is checked before every single dial
- Call recording disclosure plays at the start: "This call may be recorded for quality purposes"


---


## Channel 2: AI SMS (Two-Way)

### How It Works

Aria sends and receives text messages via Telnyx from your organization's dedicated phone number. Messages are composed by Claude AI -- they are not canned templates. Aria adapts her tone, references prior conversations on any channel, and never repeats herself.

### Qualification Flow

When a borrower replies to an SMS, Aria conducts a natural text-based qualification:

- Asks one question at a time
- Remembers answers across messages (stored in the conversation's context data)
- Merges qualification data with information gathered on calls or emails

For example, if a borrower already told Aria their credit range on a phone call, SMS will not ask again.

### Deal Breaker Integration

If the SMS qualification flow reveals a blocker (credit below minimum, unrealistic timeline, property type not eligible), the system bridges to the Deal Breaker Service. This generates an ECOA-compliant response that provides alternatives -- a credit repair referral, a long-term nurture path, or an alternative loan program -- rather than a dead-end rejection.

Credit ranges from SMS ("excellent", "740+", "fair", "below 620") are automatically mapped to numeric midpoints for deal breaker evaluation.

### STOP Handling

Full A2P 10DLC compliance is built in:

- **STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT** -- Immediately opts the borrower out. All sequences halt. An auto-reply confirms: "You have been unsubscribed and will no longer receive messages from us. Reply START to re-subscribe."
- **HELP, INFO** -- Replies with company contact information and opt-out instructions.
- **START, YES, UNSTOP** -- Re-subscribes the borrower and confirms.

Every opt-out action is logged in the SMS consent table with a full audit trail.

### Cross-Channel Awareness

SMS messages know what happened on other channels. Example messages Aria might send:

- "Hi Jane, I tried calling earlier -- feel free to text me here if that's easier."
- "Just following up on the email we sent about your refinance options."
- "I see you spoke with your loan officer yesterday about refinancing -- any questions I can answer?"


---


## Channel 3: AI Email

### Sent from YOUR Email Address

Emails are sent from your actual Outlook address via Microsoft Graph -- not from a generic system email. Borrowers see your name and your reply-to address, building trust from the first touchpoint.

### AI-Composed Content

Claude composes hyper-personalized emails using the full lead context: name, loan type, pipeline stage, prior conversations, and current market conditions. This is not mail merge -- each email is individually written.

### Tracking

Every email includes an open-tracking pixel and click tracking. When a borrower opens your email, the engagement engine detects it and can escalate to an SMS follow-up within 5 minutes while the borrower is actively thinking about their mortgage.

### Common Email Templates

The AI draws from template categories but customizes the actual content:

- **Pre-approval intro** -- First email after a new lead inquiry
- **Rate environment** -- Current rate context and what it means for the borrower
- **Market update** -- Local market conditions and inventory
- **Appointment reminder** -- Confirmation and prep instructions
- **Post-close referral** -- Thank you and referral request after funding
- **Document reminder** -- Friendly nudge when documents are needed
- **Educational content** -- Closing costs, credit improvement, break-even analysis

### Trigger Events

Emails are dispatched automatically in response to engagement triggers:

- Rate drops that affect the borrower's scenario
- Stale leads that need re-engagement
- Post-call follow-up with a summary
- Document requests when the loan is in processing
- Appointment confirmations and no-show follow-ups


---


## Channel 4: Voicemail Drops

### Ringless Voicemail (RVM)

When Aria's outbound call detects an answering machine -- or when a call goes unanswered -- the system automatically triggers a ringless voicemail drop via Slybroadcast. The pre-recorded message appears in the borrower's voicemail inbox without their phone ever ringing.

### How It Works

1. Outbound call attempt goes to voicemail or no-answer
2. Telnyx AMD (Answering Machine Detection) identifies the machine result
3. Slybroadcast delivers the voicemail to the borrower's inbox
4. 15 minutes later, an automated SMS follow-up is sent: "Hi [Name], we left you a voicemail about your mortgage options. Reply here if you'd like to chat!"

### Compliance

- TCPA quiet hours enforced (8 AM - 9 PM borrower local time)
- Consent verified before every drop
- DNC freshness check is blocking -- stale DNC data prevents the drop entirely
- Audio must be at least 5 seconds long (Slybroadcast requirement)

### Circuit Breaker Protection

If Slybroadcast experiences outages (5 consecutive failures), a circuit breaker opens and the system falls back to SMS-only follow-up for 60 seconds before retrying.


---


## Channel 5: Live Transfer

### When It Triggers

Live transfer activates when Aria qualifies a borrower on a call and the borrower is ready to proceed immediately. This is the highest-value outcome of any AI call.

### The Transfer Flow

1. **Hold** -- The borrower is placed on a brief hold with hold music
2. **Dial LO** -- The system dials your phone number via Telnyx Call Control
3. **Whisper briefing** -- When you answer, you hear a text-to-speech briefing before the borrower is connected:

   > "Incoming transfer. Borrower: Jane Smith. Purchase loan. Amount: $450,000. Credit: 740. Property: Single Family."

   The whisper includes cross-channel context: prior SMS messages, voicemail drops, and the current call summary from the voice context builder.

4. **Bridge** -- After the whisper plays, both call legs (borrower and LO) are joined into a Telnyx conference. The borrower is taken off hold and the conversation begins.
5. **If you are unavailable** -- The transfer records a failure reason ("LO did not answer"), and the system creates a high-priority callback task on your dashboard plus an SMS notification.

### Tenant Isolation

The system verifies that the target loan officer belongs to the same organization as the requesting user before allowing any transfer. Cross-organization transfers are blocked.

### Transfer Statuses

Each transfer progresses through tracked stages: `initiated` -> `lo_ringing` -> `lo_answered` -> `whisper_playing` -> `bridged` -> `completed`. If any stage fails, the failure reason is recorded for review.

### LO Availability

The LO Availability system tracks your real-time status:

- **Available** -- Ready to receive transfers
- **Busy / On Call** -- Currently engaged, transfers will queue
- **DND** -- Do Not Disturb, no transfers
- **Offline / Away** -- Not available

You can set your status manually or configure weekly availability schedules with specific time slots per day. The system uses a 30-second TTL cache for fast availability lookups during transfers.


---


## Drip Campaigns (12-Month Sequences)

### Overview

When a lead is not ready to proceed immediately, the engagement engine enrolls them in an automated drip campaign. These are 12-month sequences with three distinct phases that gradually decrease in frequency.

### Phase 1: Hot Lead (Days 1-7) -- Daily Contact

The first week is high-frequency engagement while the lead is fresh:

- **Day 0**: Immediate intro SMS + voicemail follow-up if the call went to VM
- **Day 1**: Pre-approval intro email
- **Day 2**: Check-in SMS
- **Day 3**: Rate environment email
- **Day 5**: Pre-approval CTA SMS
- **Day 7**: Market update email

### Phase 2: Warm Nurture (Days 8-90) -- Weekly Contact

The cadence drops to weekly as the lead enters the consideration phase:

- Biweekly check-in texts and educational emails
- Content varies: closing costs education, credit improvement tips, market updates, success stories
- Refinance leads get rate-focused content instead of purchase content

### Phase 3: Long Nurture (Days 91-365) -- Monthly Touchpoints

For leads on a longer timeline, monthly contact keeps you top-of-mind:

- Quarterly market reviews
- Monthly check-in texts: "Hi Jane, hope all is well! Let me know if your home buying plans have changed."
- Rate watch alerts
- Anniversary re-engagement at the 1-year mark

### Adaptive Behavior

Drip campaigns are not static. The behavioral trigger engine monitors lead engagement and adjusts:

- **Email opened** -- Escalate from monthly to weekly frequency
- **Link clicked** -- Escalate from weekly to daily for 3 days
- **SMS replied** -- Pause the drip entirely, route to live AI conversation
- **No engagement for 14 days** -- Reduce frequency to avoid fatigue
- **No engagement for 30 days** -- Drop to minimal monthly contact
- **Email bounced** -- Switch primary channel from email to SMS

### Exit Conditions

A lead exits the drip sequence when any of the following occur:

- Lead responds to any message -- drip pauses, routes to live conversation
- Appointment is booked -- switches to appointment prep sequence
- Application is submitted -- switches to loan lifecycle sequence
- STOP received -- permanently exits all sequences (compliance requirement)
- Loan funded -- switches to post-close referral sequence

### Sequence Types

Four pre-built sequences are available:

- **purchase_12_month** -- For purchase leads, emphasizes home search and pre-approval
- **refinance_12_month** -- For refinance leads, emphasizes rate savings and break-even analysis
- **post_close** -- Post-funding referral nurture
- **reengagement** -- For stale leads being brought back into the pipeline

All drip steps are timezone-aware. Messages are scheduled for 10 AM in the borrower's local time, not UTC.


---


## The Brain: Engagement Orchestrator

### What It Does

The Engagement Orchestrator is the master decision engine that coordinates all channels. Every engagement action in Perennia flows through it. It decides WHAT to send, WHEN to send it, and on WHICH CHANNEL, then dispatches to the appropriate service.

### 15 Trigger Events

| Trigger | What Fires It |
|---------|---------------|
| `new_lead` | A new lead is created in the system |
| `no_answer` | An outbound call was not answered |
| `voicemail_dropped` | A voicemail was successfully delivered |
| `sms_no_response_24h` | An SMS was sent but no reply within 24 hours |
| `email_opened` | The borrower opened a tracked email |
| `call_completed` | An AI or manual call was completed |
| `appointment_set` | A consultation was booked |
| `appointment_missed` | The borrower did not show for their appointment |
| `rate_drop` | Interest rates dropped significantly |
| `document_needed` | A document is required to advance the loan |
| `stale_7d` | No engagement activity for 7 days |
| `stale_30d` | No engagement activity for 30 days |
| `qualification_complete` | Borrower has answered all qualifying questions |
| `deal_breaker_found` | A disqualifying factor was identified |
| `loan_funded` | The loan has closed and funded |

### Channel Selection Logic

The orchestrator chooses a channel based on multiple factors:

1. **Time of day** (borrower's local time):
   - Morning (8 AM - 12 PM): Call preferred, then SMS, then email
   - Afternoon (12 PM - 5 PM): Call preferred, then SMS, then email
   - Evening (5 PM - 9 PM): SMS preferred, then email (no calls)
   - Quiet hours (9 PM - 8 AM): No outbound contact

2. **Lead's stated preference**: If the lead indicated they prefer text or email, that channel moves to the front

3. **Pipeline stage**: New leads favor calls for immediacy; nurture-stage leads favor email and SMS to avoid call fatigue

4. **Channel availability**: No phone number? Skip call and SMS. No email? Skip email. DNC flag? Skip call.

5. **Consent status**: TCPA requires prior express consent for automated calls and SMS. The engine checks `call_consent` and `sms_consent` flags before dispatching.

6. **Recent engagement patterns**: If a call was already made today, the engine deprioritizes another call unless it is a new lead or rate drop trigger.

### Fatigue Prevention

The engine enforces strict contact limits to avoid overwhelming borrowers:

- **Maximum 5 contacts per day** per lead (configurable per-org)
- **Maximum 15 contacts per week** per lead (configurable per-org)
- **30-minute same-channel deduplication**: If the drip campaign already sent an SMS, the orchestrator will not send another SMS within 30 minutes
- **60-second trigger deduplication**: If the exact same trigger fires twice within 60 seconds (e.g., a webhook retry), only the first one is processed

When a daily or weekly limit is reached, the engagement is deferred to the next morning rather than dropped entirely.

### Sequence Scheduling

After every engagement action, the orchestrator determines what should happen next:

- `new_lead` call completed -> if no answer, trigger `no_answer` immediately
- `no_answer` -> voicemail drop, then schedule `sms_no_response_24h` in 24 hours
- `voicemail_dropped` -> SMS follow-up in 15 minutes
- `sms_no_response_24h` -> email, then schedule `stale_7d` in 7 days
- `stale_7d` -> re-engagement nudge, then schedule `stale_30d` in 23 more days
- `stale_30d` -> hand off to long-term drip campaign (orchestrator done)

Terminal triggers (`qualification_complete`, `deal_breaker_found`, `loan_funded`) do not schedule follow-ups.


---


## Cross-Channel Intelligence

### Unified Context

Every AI interaction -- whether it happens on a call, via SMS, or through email -- has access to what happened on every other channel. This is powered by the voice context builder and engagement event history.

When Aria calls a borrower, she knows:
- What SMS messages were exchanged and when
- Whether a voicemail was dropped and if the borrower listened
- Whether the borrower opened recent emails
- What qualifying information was already gathered on any channel

### Qualification Data Merging

Qualification answers are accumulated across channels:

- If the borrower said "740 credit" on a call, SMS will not ask their credit range again
- If the borrower texted "looking to buy in 3 months", the next call will reference that timeline
- Deal breaker evaluation pulls from the merged context, not just the current channel

### Engagement Scoring

Every interaction contributes to the lead's engagement score:

| Action | Score Impact |
|--------|-------------|
| SMS reply received | +5 |
| Email opened | +2 |
| Call answered | +10 |
| Appointment booked | +20 |

Higher engagement scores influence channel selection (more engaged leads may get calls; less engaged leads get lower-friction SMS/email).

### Channel Preference Detection

Over time, the system observes which channels a borrower responds to most frequently and weights future outreach toward those channels.


---


## Compliance Built In

Every engagement action passes through a multi-layer compliance check before it is dispatched. This is not optional -- the system enforces these rules automatically.

### TCPA (Telephone Consumer Protection Act)

- **Quiet hours**: No calls or SMS before 8 AM or after 9 PM in the borrower's local time zone
- **Prior express consent**: Required for automated calls and SMS. The engine checks `call_consent` and `sms_consent` flags before every dispatch
- **Recording disclosure**: Every outbound call opens with "This call may be recorded for quality purposes"

### ECOA (Equal Credit Opportunity Act)

- Aria never asks about race, sex, religion, national origin, marital status, or age
- Deal breaker responses are reviewed for ECOA compliance before sending
- Every engagement decision is logged with full decision factors for fair lending audit

### DNC (Do Not Call)

- The DNC registry is checked before every outbound dial
- Both per-organization DNC lists and the national registry are consulted
- DNC freshness checks are blocking -- if the DNC scrub data is stale, the call is rejected entirely (not just logged as a warning)

### A2P 10DLC (Application-to-Person SMS)

- STOP/HELP keyword handling is automatic and immediate
- Every opt-out is recorded in the SMS consent table with timestamps
- Auto-reply messages comply with carrier requirements
- Full audit trail for every opt-out and opt-in action

### Rate Quotes

Aria never quotes specific interest rates, APRs, or fees in any channel. Rate-related content is framed as directional ("rates have improved", "you may be able to save") rather than specific.


---


## Monitoring and Health

### Health Dashboard

The engagement engine exposes a health check at `GET /api/v1/engagement/health` that reports the status of every subsystem:

- **Database connectivity** -- Can the engine read and write engagement data?
- **Anthropic API key** -- Is the AI (Claude) available for message composition?
- **Vapi API key** -- Is the voice calling system configured?
- **Telnyx API key** -- Is the SMS and telephony provider connected?
- **Microsoft Graph** -- Is the email delivery system configured?
- **Drip enrollments** -- How many active drip sequences are running?
- **Engagement events (24h)** -- How many engagement actions fired in the last 24 hours?
- **Speed-to-lead config** -- Is per-org speed-to-lead configuration present?

Overall status is reported as `healthy` or `degraded`.

### Engagement Dashboard

The engagement dashboard at `GET /api/v1/engagement-dashboard/summary` provides unified metrics:

- Total activities over the selected period
- Breakdown by channel: calls, texts, emails, meetings
- Unique leads contacted

### Event Logging

Every orchestration decision is recorded in the `engagement_events` table with:

- Trigger event that started it
- Channel chosen and why
- Action taken (dispatched, deferred, skipped)
- Result (success, failed, blocked)
- Full decision factors (AI score, stage, consent status, contacts today/week, time bucket)
- Next scheduled trigger and time

This audit trail supports both operational monitoring and fair lending compliance review.

### Circuit Breakers

If an external service goes down, the system degrades gracefully:

- **Telnyx outage** (5 consecutive failures) -- Circuit breaker opens for 30 seconds. Calls and SMS fall back to email-only.
- **Slybroadcast outage** (5 consecutive failures) -- Circuit breaker opens for 60 seconds. Voicemail drops fall back to SMS-only follow-up.
- **Claude AI unavailable** -- Email composition falls back to basic templates instead of AI-generated content.

Circuit breakers automatically attempt recovery after the cooldown period (half-open probe request).


---


## For Admins: Per-Tenant Configuration

Organization administrators can customize the engagement engine:

- **AI persona name** -- Default is "Aria"; can be renamed per organization
- **Qualifying questions** -- Add, remove, or reorder the questions Aria asks during qualification
- **Transfer qualification threshold** -- Define what combination of answers qualifies a lead for live transfer
- **Quiet hours** -- Per-state overrides for calling windows (some states have stricter rules)
- **Drip sequences** -- Enable or disable individual phases, customize message content and timing
- **Voicemail scripts** -- Different audio files per loan officer and per loan type
- **Fatigue limits** -- Adjust max contacts per day (default: 5) and per week (default: 15)
- **Channel preferences** -- Set default channel priority order for the organization
- **Suppression list management** -- Manage DNC entries and SMS opt-out lists
- **Speed-to-lead timing** -- Configure the target response time and fallback behavior

Configuration is managed through the Perennia dashboard under the organization settings.


---


## Quick Reference: What Happens When...

| Event | Aria Does |
|-------|-----------|
| New lead arrives | Call within 60 seconds. Qualify. Transfer or book appointment. |
| No answer on call | Voicemail drop. SMS follow-up in 15 minutes. |
| Borrower texts back | AI SMS conversation with qualification flow. Drip pauses. |
| Email opened | SMS escalation within 5 minutes. |
| No SMS response in 24 hours | Email follow-up with different angle. |
| Appointment missed | Re-engagement SMS in 30 minutes. Task created for LO. |
| Rates drop | Alert on borrower's preferred channel immediately. |
| Documents needed | Multi-channel request (email + SMS). |
| Lead goes stale (7 days) | Re-engagement nudge via SMS or email. |
| Lead goes stale (30 days) | Switch to long-term monthly nurture sequence. |
| Qualification complete | Push for appointment booking. |
| Deal breaker found | Turn-down with alternatives (credit repair referral, etc.). |
| Loan funded | Post-close referral sequence starts in 24 hours. |
| Call completed | Post-call summary email in 5 minutes. Task for LO to review. |
| Borrower replies STOP | All sequences halt immediately. Opt-out confirmed and logged. |


---


## Summary of Key Numbers

| Parameter | Default Value |
|-----------|---------------|
| Speed-to-lead target | 60 seconds |
| TCPA calling window | 8:00 AM - 9:00 PM borrower local time |
| Voicemail SMS follow-up delay | 15 minutes |
| Email-open SMS escalation | 5 minutes |
| Post-call email follow-up | 5 minutes |
| Appointment-missed re-engagement | 30 minutes |
| Post-funding referral sequence | 24 hours |
| Max contacts per day per lead | 5 |
| Max contacts per week per lead | 15 |
| Same-channel dedup window | 30 minutes |
| Trigger dedup window | 60 seconds |
| Telnyx circuit breaker threshold | 5 failures / 30 second recovery |
| Slybroadcast circuit breaker threshold | 5 failures / 60 second recovery |
| LO availability cache TTL | 30 seconds |
