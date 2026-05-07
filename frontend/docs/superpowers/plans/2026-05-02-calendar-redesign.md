# Calendar Page — Borrower Portal Implementation Plan

**Date:** 2026-05-02
**Prototype:** `frontend/public/calendar-redesign-prototype.html`
**Design system:** Shared with POS (cream/green/gold palette, Fraunces + Geist fonts)

## Overview

Add a Calendar page to the borrower portal at `/apply/v3/calendar`. Unifies three event sources — scheduler appointments, SLA milestones, and task deadlines — into a single timeline view. Shares the TopNav and Sidebar shell with the POS Application page.

The Calendar prototype shows:
- **Hero card** — countdown to closing + "up next" preview
- **Month grid** — interactive calendar with color-coded event bars
- **Day panel** — sticky panel showing events for the selected day
- **Upcoming list** — filterable event rows grouped by day
- **Past activity** — completed events with strikethrough
- **Event detail slide-over** — full event info, attendee card, actions
- **Sync calendar slide-over** — Google/Apple/Outlook subscribe, .ics download
- **Schedule meeting slide-over** — meeting type → day → time → confirm
- **Aria chat panel** — already built in POS, reused here with calendar context

## Architecture

```
frontend/src/features/calendar/
├── components/
│   ├── CalendarContainer.tsx    # Main layout: hero + grid + lists + panels
│   ├── CalendarHero.tsx         # Countdown + up-next card
│   ├── MonthGrid.tsx            # Interactive month grid with event bars
│   ├── DayPanel.tsx             # Selected day events + schedule CTA
│   ├── UpcomingList.tsx         # Filterable upcoming events
│   ├── PastList.tsx             # Completed events
│   ├── EventRow.tsx             # Shared event row (upcoming + past)
│   ├── EventDetailPanel.tsx     # Slide-over: event info + actions
│   ├── SyncCalendarPanel.tsx    # Slide-over: subscribe options
│   └── ScheduleMeetingPanel.tsx # Slide-over: book a meeting
├── calendar.css                 # All calendar-specific styles
├── types.ts                     # CalendarEvent, EventType, EventSource, etc.
├── demo-events.ts               # Demo data matching prototype
└── index.ts                     # Public exports

frontend/src/pages/calendar/
└── CalendarEntryPage.tsx         # Route entry point (reads URL params)
```

## Task Breakdown

---

### Task 1 — Shared Shell Enhancements + Calendar CSS

**Goal:** Make POSSidebar reusable across borrower portal pages. Add all calendar-specific CSS.

**1a. POSSidebar — add `activePage` prop**

Currently `NavItem label="Application" active` is hardcoded. Add an `activePage` prop so Calendar (and future pages) can set their own active state.

Also add a "Calendar" nav item with CalendarIcon, and the LO card at sidebar bottom (from prototype).

```tsx
// POSSidebar.tsx changes:
export interface POSSidebarProps {
  application: ApplicationResponse | null;
  onAskAria: () => void;
  activePage?: string; // NEW — 'Application' | 'Calendar' | 'Documents' | etc.
  loanOfficer?: { name: string; initials: string; nmls: string }; // NEW
}

// NavItem gets active from: label === activePage
<NavItem icon={<CalendarIcon />} label="Calendar" active={activePage === 'Calendar'} />

// Bottom of sidebar: LO card
{loanOfficer && (
  <div className="pos-sidebar__footer">
    <span className="pos-nav__section-title">Your loan officer</span>
    <div className="pos-sidebar__lo-card">
      <div className="pos-seal" style={{ width: 38, height: 38, fontSize: 13 }}>
        {loanOfficer.initials}
      </div>
      <div className="pos-sidebar__lo-info">
        <span className="pos-sidebar__lo-name">{loanOfficer.name}</span>
        <span className="pos-sidebar__lo-nmls">NMLS {loanOfficer.nmls}</span>
      </div>
    </div>
  </div>
)}
```

Update POSContainer to pass `activePage="Application"`.

**1b. CalendarIcon** — add to POSSidebar's icon set:
```tsx
const CalendarIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
  </svg>
);
```

**1c. Calendar CSS** — create `features/calendar/calendar.css` with all calendar-specific styles from the prototype:
- Calendar hero (`.calendar-hero`, `.hero-inner`, `.countdown-row`, `.hero-up-next`)
- Month grid (`.month-card`, `.month-grid`, `.month-cell`, `.event-bar`)
- Day panel (`.day-panel`, `.event-card`, `.schedule-cta`)
- Event filters (`.event-filters`, `.event-filter`)
- Event rows (`.event-row`, `.event-row__*`)
- Slide-over shared chassis already in pos.css — reuse those classes
- Sync rows (`.sync-row`)
- Schedule panel (`.schedule-day-btn`, `.schedule-time-btn`, `.meeting-type-card`)
- Status pills (`.status-pill`, `.status-pill-*`)
- Timeline (`.timeline`, `.timeline__*`)
- Section headers (`.section-header`, `.section-title`, `.section-line`)
- Why card (`.why-card`)
- Slide-over inner sections (`.so-label`, `.so-section`)

**1d. Sidebar footer CSS** — append to pos.css:
```css
.pos-sidebar__footer {
  margin-top: auto;
  padding: 16px;
  border-top: 1px solid var(--bt-border);
}
.pos-sidebar__lo-card {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}
.pos-sidebar__lo-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.pos-sidebar__lo-name {
  font-size: 13.5px;
  font-weight: 500;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pos-sidebar__lo-nmls {
  font-size: 11.5px;
  color: var(--bt-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

---

### Task 2 — Calendar Types + Demo Data + Hero Component

**Goal:** Define the data model, create demo events, build the hero countdown card.

**2a. `types.ts`** — calendar event model:

```ts
export type EventType = 'meeting' | 'milestone' | 'deadline';
export type EventSource = 'scheduler' | 'sla' | 'tasks';
export type EventStatus = 'confirmed' | 'completed' | 'expected' | 'pending' | 'cancelled';
export type AttendeeKind = 'lo' | 'ext' | 'neutral';

export interface EventAttendee {
  name: string;
  initials: string;
  kind: AttendeeKind;
  nmls?: string;
}

export interface EventSourceRef {
  table: string;
  id: string | number;
}

export type EventAction =
  | 'confirm_access' | 'reschedule' | 'cancel' | 'add_to_calendar'
  | 'directions' | 'closing_checklist' | 'view_recording' | 'view_notes'
  | 'view_when_ready' | 'view_order' | 'upload' | 'view_task';

export interface CalendarEvent {
  id: string;
  type: EventType;
  source: EventSource;
  sourceRef: EventSourceRef;
  title: string;
  description: string;
  start: string;          // ISO date or datetime
  end?: string;           // ISO datetime (meetings only)
  allDay?: boolean;
  location?: string;
  attendee?: EventAttendee;
  icsUrl?: string;
  status: EventStatus;
  urgency?: 'soon' | 'normal';
  isClosing?: boolean;
  actions: EventAction[];
}

export interface LoanContext {
  fileNumber: string;
  closingDate: string;  // ISO date
  loanOfficer: EventAttendee & { nmls: string };
}
```

**2b. `demo-events.ts`** — copy all 14 events from prototype JS, typed as `CalendarEvent[]`.

**2c. `CalendarHero.tsx`**:

```tsx
export interface CalendarHeroProps {
  daysToClose: number;
  closingDate: Date;
  closingLocation: string;
  nextEvent: CalendarEvent;
  onViewEvent: (eventId: string) => void;
}
```

Renders the split hero card: left side = countdown number + "days until closing" + meta rows (date, location). Right side = "Up next" with event title, description, detail rows, "View details" CTA button.

---

### Task 3 — MonthGrid + DayPanel

**Goal:** Interactive calendar grid with event rendering, plus day detail panel.

**3a. `MonthGrid.tsx`**:

```tsx
export interface MonthGridProps {
  events: CalendarEvent[];
  viewYear: number;
  viewMonth: number;      // 0-indexed
  selectedDate: string;   // YYYY-MM-DD
  today: Date;
  closingDate: Date;
  onSelectDate: (dateKey: string) => void;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onToday: () => void;
}
```

Renders:
- Month header with Today button, prev/next arrows, month label, legend (Meeting/Milestone/Deadline dots)
- 7-column weekday header
- Month grid cells with: date number, up to 2 event bars (with `+N more` overflow), cell states (empty, past, today, selected, closing)
- Event bars: `.event-bar--meeting` (green bg), `.event-bar--milestone` (gold bg with dot), `.event-bar--deadline` (gold border, left-thick), `.event-bar--done` (strikethrough)
- Click on a cell → `onSelectDate(dateKey)`

**3b. `DayPanel.tsx`**:

```tsx
export interface DayPanelProps {
  selectedDate: string;
  events: CalendarEvent[];
  today: Date;
  onViewEvent: (eventId: string) => void;
  onSchedule: () => void;
}
```

Renders:
- Header: eyebrow (Today/Tomorrow/weekday name), title (full date), sub (N events)
- Event cards: border-left color by type, time + duration, title, description
- Empty state: calendar icon, "Nothing scheduled", contextual sub-text
- Footer: "Schedule with Sarah" CTA button

---

### Task 4 — UpcomingList + PastList + EventRow

**Goal:** Filterable upcoming events grouped by day, past completed events.

**4a. `EventRow.tsx`** — shared between upcoming and past lists:

```tsx
export interface EventRowProps {
  event: CalendarEvent;
  isPast?: boolean;
  today: Date;
  onClick: () => void;
}
```

Renders the 5-column grid row: time (primary + sub), icon (type-colored square), main (title + description + meta chips), attendee (name + seal), arrow chevron. Hover lifts with shadow. Past variant has strikethrough title and check icon.

Meta chips show source label ("Smart Calendar" / "AI Operations" / "From Tasks"), location, and closing-day badge.

**4b. `UpcomingList.tsx`**:

```tsx
export interface UpcomingListProps {
  events: CalendarEvent[];
  today: Date;
  filter: string;
  onFilterChange: (filter: string) => void;
  onViewEvent: (eventId: string) => void;
}
```

Renders:
- Section header: "Upcoming" title + item count chip + section line + filter pills
- Filter pills: All / Meetings / Milestones / Deadlines
- Events grouped by day with day-group headers (date, weekday, relative label like "Today"/"Tomorrow")
- Each event as EventRow

**4c. `PastList.tsx`**:

```tsx
export interface PastListProps {
  events: CalendarEvent[];
  today: Date;
  onViewEvent: (eventId: string) => void;
}
```

Renders: section header "Past Activity" + count chip, reverse-chronological EventRow list with `isPast`.

---

### Task 5 — Slide-over Panels

**Goal:** Three slide-over panels for event detail, calendar sync, and meeting scheduling.

**5a. `EventDetailPanel.tsx`**:

```tsx
export interface EventDetailPanelProps {
  event: CalendarEvent | null;
  isOpen: boolean;
  onClose: () => void;
  onOpenAria: () => void;
}
```

Renders slide-over with:
- Header: status pill (Meeting/Milestone/Deadline/Completed/Cancelled), closing-day chip, title, date/time mono
- Body sections: "What this is" why-card, "Where" location row, attendee card (with Message button for LO), "Source" chip + table reference, "Ask Aria about this" CTA
- Footer: action buttons vary by type+status:
  - Confirmed meeting: Add to calendar / Reschedule / Cancel
  - Closing meeting: View closing checklist / Get directions
  - Deadline: Open in Tasks / Message Sarah
  - Completed: View recording / View notes
  - Milestone: View related

**5b. `SyncCalendarPanel.tsx`**:

```tsx
export interface SyncCalendarPanelProps {
  isOpen: boolean;
  onClose: () => void;
  loanFileNumber: string;
}
```

Static panel with:
- Header: title + description
- One-tap subscribe: Google Calendar, Apple Calendar, Outlook rows
- Other options: Download .ics file, Copy webcal:// URL
- Info card explaining what gets synced

**5c. `ScheduleMeetingPanel.tsx`**:

```tsx
export interface ScheduleMeetingPanelProps {
  isOpen: boolean;
  onClose: () => void;
  today: Date;
}
```

Interactive panel with local state:
- Meeting type cards: Quick check-in (15 min), Status review (30 min, recommended), Full discussion (60 min)
- Day picker: next 7 weekdays
- Time slots: 9:00 AM – 4:00 PM in 30-min increments (some "booked")
- Confirm button: disabled until day+time selected, then shows "Confirm [type] · [time]"

**5d. Shared slide-over wrapper** — reuse the slide-over CSS from pos.css (`.slide-overlay`, `.slide-panel`, `.slide-header`, `.slide-body`, `.slide-footer`). Create a lightweight `<SlideOver>` wrapper if helpful:

```tsx
const SlideOver: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  width?: number;
  children: React.ReactNode;
}> = ({ isOpen, onClose, width = 540, children }) => (
  <>
    <div className={`slide-overlay${isOpen ? ' is-open' : ''}`} onClick={onClose} />
    <aside
      className={`slide-panel${isOpen ? ' is-open' : ''}`}
      style={{ width }}
      role="dialog"
    >
      {children}
    </aside>
  </>
);
```

---

### Task 6 — CalendarContainer + Route Wiring

**Goal:** Assemble all components into the Calendar page and wire the route.

**6a. `CalendarContainer.tsx`**:

```tsx
export interface CalendarContainerProps {
  loanId?: number;
  borrowerName: string;
  userInitials: string;
}
```

State:
- `viewYear`, `viewMonth` — month navigation
- `selectedDate` — YYYY-MM-DD key
- `filter` — event filter ('all' | 'meeting' | 'milestone' | 'deadline')
- `openPanel` — which slide-over is open (null | 'event' | 'sync' | 'schedule' | 'aria')
- `selectedEventId` — for event detail panel

Layout:
```
TopNav (saveState="idle")
├── POSSidebar (activePage="Calendar", loanOfficer={...})
└── main.pos-main
    ├── Page header (chip + title + description + Sync/Schedule buttons)
    ├── CalendarHero
    ├── Grid: MonthGrid + DayPanel
    ├── UpcomingList
    ├── PastList
    └── Footnote
EventDetailPanel (slide-over)
SyncCalendarPanel (slide-over)
ScheduleMeetingPanel (slide-over)
AriaPanel (slide-over, reused from POS)
AriaFAB
```

**6b. `CalendarEntryPage.tsx`**:

```tsx
const CalendarEntryPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const loanId = searchParams.get('loan_id') ? parseInt(searchParams.get('loan_id')!, 10) : undefined;
  const borrowerName = searchParams.get('name') || 'there';
  const initials = searchParams.get('initials') || '';

  return (
    <CalendarContainer
      loanId={loanId}
      borrowerName={borrowerName}
      userInitials={initials}
    />
  );
};
```

**6c. Route wiring** — add to `routes/index.jsx`:

```jsx
const CalendarEntryPage = lazyRetry(() => import('../pages/calendar/CalendarEntryPage'));

// Add above v2 routes, near the POS route:
<Route key="/apply/v3/calendar" path="/apply/v3/calendar" element={<LazyPage><CalendarEntryPage /></LazyPage>} />
```

**6d. `index.ts`** — public exports:
```ts
export { CalendarContainer } from './components/CalendarContainer';
export type { CalendarEvent, EventType, EventSource, LoanContext } from './types';
```

---

### Task 7 — Visual Verification

**Goal:** Start dev server, compare React implementation side-by-side with prototype.

**Checklist:**
- [ ] Navigate to `/apply/v3/calendar?name=Timothy&initials=TL`
- [ ] Hero card: countdown number, "days" label, closing date/location, up next event
- [ ] Month grid: event bars with correct colors, today highlight, click to select
- [ ] Day panel: updates on cell click, shows event cards, empty state
- [ ] Upcoming list: filters work (All/Meetings/Milestones/Deadlines), day group headers
- [ ] Past activity: strikethrough titles, checkmark icons
- [ ] Event detail panel: opens from event card/row/hero CTA, status pill, attendee, actions
- [ ] Sync panel: opens from "Sync calendar" button, shows provider rows
- [ ] Schedule panel: opens from "Schedule a meeting" button, day/time picker works
- [ ] Aria FAB: opens slide-over, reused from POS
- [ ] Sidebar: "Calendar" nav item highlighted, LO card at bottom
- [ ] TopNav: consistent with POS
- [ ] Responsive: 1024px and 768px breakpoints
- [ ] Compare with prototype at `/calendar-redesign-prototype.html`

---

## Cross-cutting Notes

- **No Tailwind** — the prototype uses Tailwind for layout utility classes. The React implementation uses BEM CSS classes (matching the POS approach). Convert all Tailwind utilities to proper CSS.
- **Slide-over CSS** — already exists in `pos.css` (`.slide-overlay`, `.slide-panel`, etc.). Reuse directly.
- **Aria panel** — reuse `AriaPanel` from `features/pos`. Pass calendar-specific suggestions.
- **Event data** — Task 2 creates demo/mock data. In production, this would come from API calls to scheduler, SLA, and tasks endpoints.
- **Font grain texture** — the prototype has a `body::before` grain overlay. This is already part of the borrower theme; no extra work needed.
- **escapeHtml** — React auto-escapes JSX expressions, so no manual escaping needed (unlike the prototype's vanilla JS).
