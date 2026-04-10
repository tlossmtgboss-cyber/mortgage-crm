# Aria Mobile App Redesign — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Replace the current chat-based mobile experience with a voice-first 5-screen app matching the Perennia AI prototype.

**Architecture:** 6 new React components (5 screens + shared tab nav) in `frontend/src/pages/aria-mobile/` and `frontend/src/components/mobile/`. Each screen is a self-contained page component with its own CSS. Shared `AriaTabNav` handles bottom navigation with dark/light variants. Connects to existing API services (`schedulerAPI`, `tasksAPI`, `callMonitoringAPI`, `mobileAriaApi`). Login redirects to `/aria-voice` on native.

**Tech Stack:** React 18, CSS custom properties, Capacitor (iOS), existing axios API client with auto-auth.

---

## File Structure

```
frontend/src/pages/aria-mobile/
├── AriaVoiceHome.jsx        # Screen 1: Voice assistant with mic orb
├── AriaVoiceHome.css        # Dark theme (#060A10)
├── MobileCalendar.jsx       # Screen 2: Appointments + Closings tabs
├── MobileCalendar.css       # Light theme (#F5F5F7)
├── MobileTasks.jsx          # Screen 3: Overdue/Today/Upcoming sections
├── MobileTasks.css          # Light theme (#F5F5F7)
├── MobileAppointmentDetail.jsx  # Screen 4: Detail/Notes/History
├── MobileAppointmentDetail.css  # White background
├── MobileCallIntel.jsx      # Screen 5: Live call monitoring + recent
└── MobileCallIntel.css      # Dark theme (#060A10)

frontend/src/components/mobile/
└── AriaTabNav.jsx           # Bottom tab nav (dark + light variants)
└── AriaTabNav.css

frontend/public/index.html   # Add Google Fonts (Cormorant Garamond, DM Sans)
frontend/src/App.jsx          # Add routes for all 5 screens
frontend/src/pages/Login.js   # Change native redirect to /aria-voice
```

## API Mapping

| Screen | API | Endpoint |
|--------|-----|----------|
| Calendar - Appointments | `schedulerAPI.getAppointments(params)` | GET /api/v1/scheduler/appointments |
| Calendar - Closings | `unifiedCalendarAPI.getAll({ type: 'closing' })` | GET /api/v1/calendar/unified |
| Tasks | `tasksAPI.getAll(params)` | GET /api/v1/tasks |
| Task Toggle | `tasksAPI.update(id, { is_completed })` | PATCH /api/v1/tasks/{id} |
| Appointment Detail | `schedulerAPI.getAppointmentById(id)` | GET /api/v1/scheduler/appointments/{id} |
| Call Intel - Sessions | `callMonitoringAPI.listSessions(params)` | GET /api/v1/call-monitoring/sessions |
| Voice Session | `mobileAriaApi.sendMessage()` | POST /api/v1/ai/orchestrator-chat |
| Voice Input | `useAriaVoice` hook | Native Speech / Web Speech API |

---

### Task 1: Add Google Fonts to index.html

**Files:**
- Modify: `frontend/public/index.html`

- [ ] Add Cormorant Garamond + DM Sans + DM Mono font imports to `<head>`

---

### Task 2: Build AriaTabNav (shared bottom navigation)

**Files:**
- Create: `frontend/src/components/mobile/AriaTabNav.jsx`
- Create: `frontend/src/components/mobile/AriaTabNav.css`

**Behavior:**
- 4 tabs: Home, Calendar, Tasks, Profile
- `variant` prop: `"dark"` (Aria/CI screens) or `"light"` (Calendar/Tasks/Detail)
- `activeTab` prop: which tab is highlighted
- `showFab` prop: show + FAB button (Calendar/Tasks screens only)
- `onFabPress` prop: callback when FAB tapped
- Dark variant: bg `rgba(8,13,22,0.97)`, active color `#7EB8F7`, inactive `rgba(255,255,255,0.3)`
- Light variant: bg `white`, active color `#1a73e8`, inactive `#999`
- Safe area bottom padding via `env(safe-area-inset-bottom)`
- Navigate via `useNavigate()` from react-router-dom

---

### Task 3: Build AriaVoiceHome (Screen 1)

**Files:**
- Create: `frontend/src/pages/aria-mobile/AriaVoiceHome.jsx`
- Create: `frontend/src/pages/aria-mobile/AriaVoiceHome.css`

**Behavior:**
- Dark background with radial gradients (`#060A10` base)
- "Aria" title in Cormorant Garamond 56px with gradient text
- Concentric mic orb rings (180px → 138px → 100px) with `#7EB8F7` accents
- Mic states: idle, listening (pulse animation), processing (spinner)
- Uses `useAriaVoice` hook for voice input
- On final transcript: sends to `mobileAriaApi.sendMessage()`, shows response as overlay
- Call Intelligence button (top-right) navigates to `/mobile-ci`
- "Powered by Perennia AI" footer text
- AriaTabNav with variant="dark", activeTab="home"

---

### Task 4: Build MobileCalendar (Screen 2)

**Files:**
- Create: `frontend/src/pages/aria-mobile/MobileCalendar.jsx`
- Create: `frontend/src/pages/aria-mobile/MobileCalendar.css`

**Behavior:**
- Light theme (#F5F5F7 background)
- Month header with dropdown arrow (current month)
- Two tabs: Appointments | Closings
- Appointments: `schedulerAPI.getAppointments()` grouped by date
- Closings: filter unified calendar events for closing type
- Appointment cards with left border color by type:
  - `#7EB8F7` = Pre-Purchase, `#9B7FE8` = Annual Review, `#f44336` = High priority, `#34A853` = Closing
- "Today" badge on current date group
- Card tap → navigate to `/mobile-appointment/{id}`
- AriaTabNav with variant="light", activeTab="calendar", showFab=true
- FAB opens create appointment (navigate to `/calendar?action=new`)

---

### Task 5: Build MobileTasks (Screen 3)

**Files:**
- Create: `frontend/src/pages/aria-mobile/MobileTasks.jsx`
- Create: `frontend/src/pages/aria-mobile/MobileTasks.css`

**Behavior:**
- Light theme (#F5F5F7)
- Header: "Tasks" + "X due today · Y overdue" summary
- Three sections: Overdue, Today, Upcoming (sorted by due_date)
- Task cards with checkbox, name, subtitle, badge
- Checkbox tap: optimistic toggle via `tasksAPI.update(id, { is_completed: !current })`
- Completed tasks show strikethrough + green "Done" badge
- Badge colors: red=Overdue, blue=category, green=Done, yellow=Pending
- Card tap: could navigate to task detail (future)
- AriaTabNav with variant="light", activeTab="tasks", showFab=true
- FAB navigates to `/tasks?action=new`

---

### Task 6: Build MobileAppointmentDetail (Screen 4)

**Files:**
- Create: `frontend/src/pages/aria-mobile/MobileAppointmentDetail.jsx`
- Create: `frontend/src/pages/aria-mobile/MobileAppointmentDetail.css`

**Behavior:**
- White background, route: `/mobile-appointment/:id`
- Back button → navigate(-1) to Calendar
- Status dot: red=scheduled, green=completed, orange=in_progress
- Appointment title + date/time
- Three sub-tabs: Details | Notes | History (Details active by default)
- Details tab: Location, Invitee (avatar + name + email + phone + timezone), Host
- Phone tap → `window.open('tel:...')`, Email tap → `window.open('mailto:...')`
- Footer: "Mark as no-show" (ghost) + "Book follow-up" (primary) buttons
- No-show: confirm alert → `schedulerAPI.updateAppointment(id, { status: 'no_show' })`
- Book follow-up: navigate to booking page with prefilled borrower

---

### Task 7: Build MobileCallIntel (Screen 5)

**Files:**
- Create: `frontend/src/pages/aria-mobile/MobileCallIntel.jsx`
- Create: `frontend/src/pages/aria-mobile/MobileCallIntel.css`

**Behavior:**
- Dark theme (#060A10 with radial gradient overlay)
- Back button → navigate to `/aria-voice`
- "Live" badge with red pulse (only when active call)
- Title: "Call Intelligence" in Cormorant Garamond
- Active call card: caller name, duration, phone number
- 5 AI agent rows with status dots + names + status text
- Agent dots: green=Sentiment, blue=Objection, purple=Coaching, yellow=Compliance, blue=Summary
- Recent calls section (reduced opacity cards)
- Uses `callMonitoringAPI.listSessions()` for recent calls
- Polling for active session status

---

### Task 8: Wire routes and update Login redirect

**Files:**
- Modify: `frontend/src/App.jsx` — add routes for all 5 screens
- Modify: `frontend/src/pages/Login.js` — change native redirect from `/mobile-aria` to `/aria-voice`

**Routes to add:**
- `/aria-voice` → AriaVoiceHome
- `/mobile-calendar` → MobileCalendar
- `/mobile-tasks` → MobileTasks
- `/mobile-appointment/:id` → MobileAppointmentDetail
- `/mobile-ci` → MobileCallIntel

---

### Task 9: Build, verify, commit

- [ ] Run `npx vite build` to verify no errors
- [ ] Commit all new files
- [ ] Push to deploy
