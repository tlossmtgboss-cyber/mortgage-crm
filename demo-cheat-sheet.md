# Demo Cheat Sheet — Perennia AI (30 min)

**Login:** https://app.perenniaai.com
**Account:** demo@perenniaai.com
**Password:** Password1!
**Role:** Manager (Alex Rivera, Branch Manager / SVP)
**Org:** Summit Home Loans

### Impersonation — Switching Views

You can impersonate any team member to show their personalized view:

| Name | Role | What to demo |
|------|------|-------------|
| Sarah Chen | Senior LO | Pipeline, tasks, calendar, SMS |
| Marcus Johnson | LO | Leads, borrower outreach, rate watch |
| Emily Park | Processor | Documents, conditions, loan checklist |
| Rachel Kim | Sr. Underwriter | Underwriting queue, risk review |
| James Mitchell | Underwriter | File review, compliance flags |
| David Torres | Ops Manager | Workflows, SLA tracking, team metrics |

**How:** Settings → Team → click "Impersonate" on any team member

---

## Step 1 — Login + Dashboard (2 min)

**Action:** Navigate to app.perenniaai.com, login
**Show:** Dashboard with pipeline metrics, today's tasks, team activity
**Talk track:** "This is your command center. Everything your team is doing, at a glance."

**If it breaks:** Refresh page. If auth fails, clear cookies and retry. Backup login: Tloss@cmgfi.com (original account).

---

## Step 2 — Pipeline / Leads (4 min)

**Action:** Click "Leads" in sidebar → show pipeline kanban view
**Show:** Lead stages (New → Application → Processing → Funded), drag-and-drop, quick filters
**Talk track:** "Every lead, every stage, real-time. Your whole pipeline in one view."

**Action:** Click into a lead → show detail view with timeline
**Show:** Activity timeline, auto-logged calls/emails, AI summaries

**If it breaks:** If pipeline is empty, switch to Loans view instead.

---

## Step 3 — Aria AI Chat (4 min)

**Action:** Open Aria chat (bottom-right or sidebar)
**Demo prompts:**
- "Show me my pipeline summary"
- "Which leads haven't been contacted in 7 days?"
- "Draft a follow-up email to [lead name]"
- "What's my conversion rate this month?"

**Talk track:** "This is Aria — your AI assistant that actually knows your pipeline. Ask anything."

**If it breaks:** If response hangs >10s, say "Aria is processing a complex query" and show a simpler prompt. If fully down, skip to next step: "Let me show you what Aria does with your calls instead."

---

## Step 4 — Call Intelligence (4 min)

**Action:** Navigate to Call Intelligence section
**Show:** Recent call list → click into an analyzed call
**Show:** AI-extracted data: borrower info, loan details, action items, compliance flags
**Talk track:** "Every call is automatically analyzed. Key data extracted, action items created, compliance checked."

**If it breaks:** Show a pre-existing analyzed call. If none exist, describe the feature and move on.

---

## Step 5 — Smart Calendar (3 min)

**Action:** Navigate to Calendar / Scheduler
**Show:** Weekly view with appointments, availability slots
**Show:** Booking link settings, appointment types
**Talk track:** "Borrowers self-schedule directly from your personalized link. Syncs with your actual calendar."

**If it breaks:** Show the calendar settings page instead of live availability.

---

## Step 6 — POS Borrower Portal (5 min)

**Action:** Open a new incognito tab → navigate to borrower portal link
**Show:** The borrower experience — application start, personal info, employment, assets
**Show:** Smart Calendar integration (Step 9 booking flow)
**Talk track:** "This is what your borrower sees. One link, complete application, meeting booked — all in one flow."

**If it breaks:** Show the POS prototype at `/pos-redesign-prototype.html` as a visual reference.

---

## Step 7 — Smart Docs (4 min)

**Action:** Back in CRM → navigate to Smart Docs for a loan file
**Show:** Document checklist, upload flow, AI categorization
**Talk track:** "Documents upload, AI classifies them, you get a checklist of what's still needed."

**If it breaks:** Show the document list for an existing loan file.

---

## Step 8 — SMS / Telephony (2 min)

**Action:** Show SMS conversations from sidebar
**Show:** Threaded conversations, AI-suggested replies, TCPA compliance badge
**Talk track:** "Text your leads directly from the platform. AI drafts responses, compliance handled automatically."

**If it breaks:** Show the conversation thread view without sending live messages.

---

## Step 9 — Mobile App (2 min)

**Action:** Show mobile app on phone or mention it
**Talk track:** "Everything you just saw — also on your phone. iOS app available now."

**If it breaks:** Show a screenshot or skip — this is a bonus, not critical path.

---

## Closing (2 min)

**Key points to hit:**
- All-in-one: replaces Velocify + Calendly + call analytics + doc management + SMS platform
- AI-first: Aria isn't a bolt-on, it's the core
- Compliance built in: TCPA, DNC, recording consent, all automatic
- One monthly subscription covers everything

**CTA:** "Want to set up a pilot with your team?"

---

## Emergency Fallbacks

| Scenario | Recovery |
|----------|----------|
| Backend completely down | Show frontend static pages + explain real-time features verbally |
| Aria not responding | "AI is processing — let me show you previous results" → show call intel |
| No data in pipeline | Switch to Loans view or show a specific lead by ID |
| Borrower portal broken | Show the prototype HTML (`/pos-redesign-prototype.html`) |
| Voice feature fails | "Let me show you what the AI produces" → show analyzed call results |
| Login fails | Clear cookies, try incognito, or show pre-captured screenshots |
