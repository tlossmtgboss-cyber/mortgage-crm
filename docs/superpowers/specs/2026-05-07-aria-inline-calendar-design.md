# Aria Inline Calendar — Slide-Over Panel

## Problem

Tapping the Calendar tab in Aria's bottom nav navigates away to `/mobile-calendar`, breaking the voice assistant context. Users want to check their schedule without leaving Aria.

## Solution

A full-screen slide-up sheet panel that opens inline within the Aria mobile page. Contains an event list view and a drill-down event detail view. Dismissible via close button or swipe-down gesture.

## Components

### AriaCalendarSheet (`pages/aria-mobile/AriaCalendarSheet.jsx`)

Container component for the slide-over panel.

**Props:**
- `open: boolean` — controls visibility
- `onClose: () => void` — dismiss callback

**Internal state:**
- `view: 'list' | 'detail'` — which sub-view is active
- `selectedAppointmentId: string | null` — the event being viewed
- `currentDate: Date` — month being viewed
- `activeTab: 'appointments' | 'closings'` — filter tab

**Animation:**
- Panel uses CSS `transform: translateY(100%)` when closed, `translateY(0)` when open
- `transition: transform 300ms cubic-bezier(0.32, 0.72, 0, 1)` (iOS spring curve)
- Body scroll locked when panel is open (`overflow: hidden` on parent)

**Data fetching:**
- Uses `schedulerAPI.getAppointments({ month, year })` — same endpoint as MobileCalendar
- LRU cache (max 6 month/tab combos) to avoid redundant fetches
- Pull-to-refresh support via existing `PullToRefreshContainer`

### List View (inside AriaCalendarSheet)

Rendered when `view === 'list'`.

**Header:**
- Month label with dropdown chevron (e.g., "May 2026 ▼")
- Close button (X) top-right
- Collapsible month nav: Previous / Today / Next buttons
- Appointments | Closings tab bar

**Body:**
- Date-grouped sections with headers: "Wednesday, May 7, 2026" + "Today" badge
- Appointment cards with:
  - Color-coded left border (blue=consultation, red=discovery, yellow=review, green=closing)
  - Client name (bold)
  - Appointment type
  - Time range (e.g., "11:00 – 11:15 AM")
- Tap a card → sets `selectedAppointmentId`, transitions `view` to `'detail'`
- Empty state: calendar icon + "No appointments this month"
- Loading state: 4 skeleton cards

### Detail View (inside AriaCalendarSheet)

Rendered when `view === 'detail'`.

**Transition:** Slides in from right via CSS `translateX`. Back button slides back to list.

**Header:**
- "‹" back button → sets `view` back to `'list'`
- Status dot (color-coded) + appointment title
- Date and time range with timezone abbreviation

**Sections:**
- **Location**: Address, or "Host will call [phone link]", or "No location specified"
- **Invitee Details**: Avatar initials circle, name, status badge, email (mailto link), phone (tel link), timezone
- **Host**: Avatar initials + name + "Host" badge

**Footer actions:**
- "Mark as no-show" (ghost button, red border) — with confirmation modal
- "Book follow-up" (primary blue button) — navigates to `/calendar`

**Data fetching:**
- `api.get(/api/v1/scheduler/appointments/${id})` for full appointment details
- Loading skeleton while fetching

### AriaTabNav Changes

**New prop:** `onCalendarPress: (() => void) | undefined`

**Behavior:** When `onCalendarPress` is provided, tapping the Calendar tab calls it instead of navigating to `/mobile-calendar`. All other tabs navigate normally.

### Aria Home Page Changes

The Aria mobile home page (wherever it renders AriaTabNav with `activeTab="home"`) adds state:

```
const [calendarOpen, setCalendarOpen] = useState(false);
```

Passes `onCalendarPress={() => setCalendarOpen(true)}` to AriaTabNav and renders `<AriaCalendarSheet open={calendarOpen} onClose={() => setCalendarOpen(false)} />`.

## Styling

New CSS file: `AriaCalendarSheet.css`

- Panel: `position: fixed; inset: 0; z-index: 1000; background: #fff;`
- Backdrop: semi-transparent overlay behind panel (optional, panel is full-screen so may not need)
- Reuses color palette from existing MobileCalendar.css (border colors, skeleton animations, card styles)
- Light theme only (white background, matching the screenshots)

## Files Changed

| File | Change |
|------|--------|
| `pages/aria-mobile/AriaCalendarSheet.jsx` | **New** — slide-over panel with list + detail views |
| `pages/aria-mobile/AriaCalendarSheet.css` | **New** — panel styles, animations, list/detail layouts |
| `components/mobile/AriaTabNav.jsx` | Add `onCalendarPress` prop, use it for calendar tab |
| `pages/aria-mobile/AriaVoiceHome.jsx` | Add calendarOpen state, render AriaCalendarSheet, pass onCalendarPress to AriaTabNav |

## What Stays

- `/mobile-calendar` route and `MobileCalendar.jsx` continue to work unchanged
- `/mobile-appointment/:id` route and `MobileAppointmentDetail.jsx` continue to work unchanged
- All other AriaTabNav tabs navigate normally
- Same backend API endpoints, no backend changes needed
