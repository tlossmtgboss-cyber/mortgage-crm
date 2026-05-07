# Aria Inline Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Calendar tab's navigate-away behavior in Aria with a full-screen slide-up sheet panel that shows events inline, without leaving the voice assistant context.

**Architecture:** New `AriaCalendarSheet` component renders a fixed-position panel with CSS translateY animation. It contains two sub-views (list and detail) that swap via CSS translateX push transitions. `AriaTabNav` gets a callback prop to intercept the calendar tap. `AriaVoiceHome` manages the open/close state.

**Tech Stack:** React 18, CSS animations (no animation library), existing `schedulerAPI` and `api` service clients.

**Spec:** `docs/superpowers/specs/2026-05-07-aria-inline-calendar-design.md`

---

### Task 1: Add `onCalendarPress` callback to AriaTabNav

**Files:**
- Modify: `frontend/src/components/mobile/AriaTabNav.jsx`

- [ ] **Step 1: Add the `onCalendarPress` prop**

In `frontend/src/components/mobile/AriaTabNav.jsx`, update the component signature and the `handleTabPress` callback:

```jsx
// Update the destructured props (line ~86):
export default function AriaTabNav({
  variant = 'dark',
  activeTab = 'home',
  showFab = false,
  onFabPress,
  onCalendarPress,
}) {
```

Then update `handleTabPress` to intercept the calendar tab:

```jsx
  const handleTabPress = useCallback((tab) => {
    haptics.light();
    if (tab.key === 'calendar' && onCalendarPress) {
      onCalendarPress();
      return;
    }
    navigate(tab.path);
  }, [navigate, onCalendarPress]);
```

- [ ] **Step 2: Verify existing behavior is unchanged**

Run the dev server and confirm:
- On `/aria-mobile`, Calendar tab still navigates to `/mobile-calendar` (no `onCalendarPress` passed yet)
- All other tabs still work

```bash
cd frontend && npm start
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/mobile/AriaTabNav.jsx
git commit -m "feat: add onCalendarPress callback prop to AriaTabNav"
```

---

### Task 2: Create AriaCalendarSheet CSS

**Files:**
- Create: `frontend/src/pages/aria-mobile/AriaCalendarSheet.css`

- [ ] **Step 1: Write the stylesheet**

Create `frontend/src/pages/aria-mobile/AriaCalendarSheet.css`:

```css
/* =============================================================================
   AriaCalendarSheet.css — Slide-over calendar panel for Aria mobile
   ============================================================================= */

/* ---------------------------------------------------------------------------
   Panel overlay + container
   --------------------------------------------------------------------------- */

.acs-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  pointer-events: none;
}

.acs-overlay--open {
  pointer-events: auto;
}

.acs-panel {
  position: absolute;
  inset: 0;
  background: #F5F5F7;
  transform: translateY(100%);
  transition: transform 300ms cubic-bezier(0.32, 0.72, 0, 1);
  display: flex;
  flex-direction: column;
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  -webkit-font-smoothing: antialiased;
}

.acs-overlay--open .acs-panel {
  transform: translateY(0);
}

/* ---------------------------------------------------------------------------
   View container (push transitions)
   --------------------------------------------------------------------------- */

.acs-views {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.acs-view {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  transition: transform 300ms cubic-bezier(0.32, 0.72, 0, 1), opacity 300ms ease;
}

/* List view states */
.acs-view--list {
  transform: translateX(0);
  opacity: 1;
}

.acs-view--list-pushed {
  transform: translateX(-30%);
  opacity: 0.5;
}

/* Detail view states */
.acs-view--detail {
  transform: translateX(0);
  opacity: 1;
}

.acs-view--detail-offscreen {
  transform: translateX(100%);
  opacity: 1;
}

/* ---------------------------------------------------------------------------
   List view header
   --------------------------------------------------------------------------- */

.acs-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #fff;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  padding-top: env(safe-area-inset-top, 0px);
}

.acs-header-top {
  padding: 14px 16px 0;
}

.acs-month-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.acs-month-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.acs-month-label {
  font-size: 20px;
  font-weight: 700;
  color: #111;
  letter-spacing: -0.02em;
}

.acs-month-chevron {
  transition: transform 0.2s ease;
}

.acs-month-chevron--open {
  transform: rotate(180deg);
}

.acs-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 44px;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  background: #fafafa;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.acs-close-btn:active {
  background: #f0f0f0;
}

/* Month navigation (collapsible) */
.acs-month-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 10px 0 4px;
  animation: acs-slideDown 0.15s ease;
}

@keyframes acs-slideDown {
  from { opacity: 0; transform: translateY(-6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.acs-nav-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 44px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  background: #f0f0f2;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: background 0.15s ease;
}

.acs-nav-arrow:active {
  background: #e0e0e2;
}

.acs-today-btn {
  font-size: 13px;
  font-weight: 600;
  color: #1a73e8;
  background: rgba(26, 115, 232, 0.08);
  border: none;
  border-radius: 16px;
  padding: 6px 16px;
  min-height: 44px;
  min-width: 44px;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.acs-today-btn:active {
  background: rgba(26, 115, 232, 0.15);
}

/* Tabs */
.acs-tabs {
  display: flex;
  padding: 0 16px;
}

.acs-tab {
  flex: 1;
  padding: 12px 0 10px;
  font-size: 14px;
  font-weight: 500;
  color: #888;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  text-align: center;
  -webkit-tap-highlight-color: transparent;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.acs-tab--active {
  color: #1a73e8;
  border-bottom-color: #1a73e8;
  font-weight: 600;
}

/* ---------------------------------------------------------------------------
   List view body
   --------------------------------------------------------------------------- */

.acs-body {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding: 12px 16px;
  padding-bottom: calc(20px + env(safe-area-inset-bottom, 0px));
}

/* Date groups */
.acs-date-group {
  margin-bottom: 20px;
}

.acs-date-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 2px 0;
}

.acs-date-text {
  font-size: 13px;
  font-weight: 600;
  color: #555;
  letter-spacing: 0.01em;
}

.acs-today-badge {
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: #1a73e8;
  border-radius: 10px;
  padding: 2px 8px;
  line-height: 1.4;
}

/* Appointment cards */
.acs-card {
  display: block;
  width: 100%;
  text-align: left;
  background: #fff;
  border: none;
  border-radius: 14px;
  border-left: 4px solid #7EB8F7;
  padding: 14px 16px;
  margin-bottom: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.1s ease, box-shadow 0.1s ease;
}

.acs-card:active {
  transform: scale(0.985);
  box-shadow: 0 0 1px rgba(0, 0, 0, 0.04);
}

.acs-card-name {
  font-size: 15px;
  font-weight: 600;
  color: #111;
  line-height: 1.3;
  margin-bottom: 3px;
}

.acs-card-type {
  font-size: 13px;
  font-weight: 400;
  color: #666;
  line-height: 1.3;
  margin-bottom: 2px;
}

.acs-card-time {
  font-size: 12px;
  font-weight: 400;
  color: #888;
  line-height: 1.3;
}

/* Empty state */
.acs-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 24px 40px;
  text-align: center;
}

.acs-empty-icon {
  margin-bottom: 16px;
  opacity: 0.5;
}

.acs-empty-text {
  font-size: 15px;
  font-weight: 500;
  color: #999;
  margin: 0;
}

/* Loading skeleton */
.acs-skeleton {
  padding: 4px 0;
}

.acs-skeleton-group {
  margin-bottom: 24px;
}

.acs-skeleton-date {
  width: 160px;
  height: 14px;
  background: #e8e8ea;
  border-radius: 6px;
  margin-bottom: 10px;
  animation: acs-pulse 1.2s ease-in-out infinite;
}

.acs-skeleton-card {
  width: 100%;
  height: 72px;
  background: #eeeef0;
  border-radius: 14px;
  margin-bottom: 8px;
  animation: acs-pulse 1.2s ease-in-out infinite;
  animation-delay: 0.1s;
}

@keyframes acs-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ---------------------------------------------------------------------------
   Detail view
   --------------------------------------------------------------------------- */

.acs-detail {
  display: flex;
  flex-direction: column;
  background: #fff;
}

.acs-detail-header {
  padding: 12px 16px 14px;
  padding-top: calc(12px + env(safe-area-inset-top, 0px));
  background: #fff;
}

.acs-back-btn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: none;
  border: none;
  color: #1a73e8;
  font-size: 15px;
  font-family: 'DM Sans', sans-serif;
  font-weight: 500;
  padding: 4px 0;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  min-height: 44px;
}

.acs-back-chevron {
  font-size: 22px;
  line-height: 1;
  margin-right: 2px;
}

.acs-detail-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.acs-detail-status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.acs-detail-title {
  font-size: 19px;
  font-weight: 700;
  color: #111;
  margin: 0;
  line-height: 1.25;
}

.acs-detail-subtitle {
  font-size: 14px;
  color: #666;
  margin: 6px 0 0;
  line-height: 1.4;
}

/* Detail tabs */
.acs-detail-tabs {
  display: flex;
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  padding: 0 16px;
  background: #fff;
}

.acs-detail-tab {
  flex: 1;
  text-align: center;
  padding: 10px 0;
  font-size: 14px;
  font-weight: 500;
  font-family: 'DM Sans', sans-serif;
  color: #888;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  min-height: 44px;
  transition: color 0.15s, border-color 0.15s;
}

.acs-detail-tab--active {
  color: #1a73e8;
  border-bottom-color: #1a73e8;
}

/* Detail body */
.acs-detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 16px 120px;
  -webkit-overflow-scrolling: touch;
}

/* Sections */
.acs-section {
  padding: 16px 0 8px;
}

.acs-section__title {
  font-size: 13px;
  font-weight: 700;
  color: #444;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 12px;
}

/* Rows */
.acs-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.acs-row:last-child {
  border-bottom: none;
}

.acs-row__icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: #F0F4FF;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.acs-row__content {
  flex: 1;
  min-width: 0;
}

.acs-row__text {
  font-size: 15px;
  color: #222;
  line-height: 1.4;
}

.acs-row__text--muted {
  color: #999;
  font-style: italic;
}

/* Links */
.acs-link {
  color: #1a73e8;
  text-decoration: none;
  font-size: 15px;
  font-weight: 500;
}

.acs-link:active {
  opacity: 0.7;
}

/* Avatar */
.acs-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
  line-height: 1;
}

.acs-avatar--invitee {
  background: #E8F0FE;
  color: #1a73e8;
}

.acs-avatar--host {
  background: #1a73e8;
  color: #fff;
}

.acs-invitee-name {
  font-size: 15px;
  font-weight: 600;
  color: #1a73e8;
}

/* Host card */
.acs-host-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #FAFBFC;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.06);
}

.acs-host-card__info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.acs-host-card__name {
  font-size: 15px;
  font-weight: 600;
  color: #222;
}

.acs-host-card__badge {
  font-size: 12px;
  color: #888;
  font-weight: 500;
}

/* Detail footer */
.acs-detail-footer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
  background: #fff;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  z-index: 10;
}

.acs-action-btn {
  flex: 1;
  padding: 13px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  font-family: 'DM Sans', sans-serif;
  cursor: pointer;
  border: none;
  min-height: 44px;
  -webkit-tap-highlight-color: transparent;
  transition: opacity 0.15s;
}

.acs-action-btn:active {
  opacity: 0.8;
}

.acs-action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.acs-action-btn--ghost {
  background: #F5F5F7;
  color: #444;
}

.acs-action-btn--primary {
  background: #1a73e8;
  color: #fff;
}

/* Confirm modal */
.acs-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(6, 10, 16, 0.72);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  animation: acs-overlay-in 0.18s ease-out;
}

@keyframes acs-overlay-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.acs-confirm-dialog {
  width: 100%;
  max-width: 340px;
  background: #0D1520;
  border: 1px solid #1E3050;
  border-radius: 16px;
  padding: 24px;
  animation: acs-dialog-in 0.2s ease-out;
}

@keyframes acs-dialog-in {
  from { opacity: 0; transform: scale(0.95) translateY(8px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}

.acs-confirm-dialog__title {
  font-size: 17px;
  font-weight: 700;
  color: #E8F0FF;
  margin: 0 0 8px;
  line-height: 1.3;
}

.acs-confirm-dialog__message {
  font-size: 14px;
  color: #9CB3D4;
  margin: 0 0 20px;
  line-height: 1.5;
}

.acs-confirm-dialog__actions {
  display: flex;
  gap: 10px;
}

.acs-confirm-dialog__btn {
  flex: 1;
  padding: 12px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  font-family: 'DM Sans', sans-serif;
  cursor: pointer;
  border: none;
  min-height: 44px;
  -webkit-tap-highlight-color: transparent;
  transition: opacity 0.15s;
}

.acs-confirm-dialog__btn:active {
  opacity: 0.8;
}

.acs-confirm-dialog__btn--cancel {
  background: #1E3050;
  color: #E8F0FF;
}

.acs-confirm-dialog__btn--destructive {
  background: #F87171;
  color: #fff;
}

/* Detail placeholder for Notes/History tabs */
.acs-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.acs-placeholder__text {
  font-size: 15px;
  color: #999;
  font-style: italic;
}

/* Detail skeleton */
.acs-detail-skeleton {
  padding: 16px;
}

.acs-detail-skeleton__block {
  background: linear-gradient(90deg, #f0f0f0 25%, #e8e8e8 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: acs-shimmer 1.4s ease-in-out infinite;
  border-radius: 6px;
}

@keyframes acs-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ---------------------------------------------------------------------------
   Reduced motion
   --------------------------------------------------------------------------- */

@media (prefers-reduced-motion: reduce) {
  .acs-panel {
    transition: none;
  }

  .acs-view {
    transition: none;
  }

  .acs-month-chevron {
    transition: none;
  }

  .acs-month-nav {
    animation: none;
  }

  .acs-nav-arrow,
  .acs-tab,
  .acs-detail-tab,
  .acs-action-btn,
  .acs-confirm-dialog__btn {
    transition: none;
  }

  .acs-card {
    transition: none;
  }

  .acs-card:active {
    transform: none;
  }

  .acs-skeleton-date,
  .acs-skeleton-card {
    animation: none;
    opacity: 0.7;
  }

  .acs-detail-skeleton__block {
    animation: none;
  }

  .acs-confirm-overlay {
    animation: none;
  }

  .acs-confirm-dialog {
    animation: none;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/aria-mobile/AriaCalendarSheet.css
git commit -m "feat: add CSS for AriaCalendarSheet slide-over panel"
```

---

### Task 3: Create AriaCalendarSheet component — List View

**Files:**
- Create: `frontend/src/pages/aria-mobile/AriaCalendarSheet.jsx`

This task builds the list view. Task 4 adds the detail view.

- [ ] **Step 1: Create the component file**

Create `frontend/src/pages/aria-mobile/AriaCalendarSheet.jsx`:

```jsx
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { schedulerAPI } from '../../services/api';
import api from '../../services/api';
import { toast } from '../../utils/toast';
import PullToRefreshContainer from '../../components/mobile/PullToRefreshContainer';
import './AriaCalendarSheet.css';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const DAY_NAMES = [
  'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday',
  'Friday', 'Saturday',
];

const TABS = [
  { key: 'appointments', label: 'Appointments' },
  { key: 'closings', label: 'Closings' },
];

const BORDER_COLORS = {
  pre_purchase: '#7EB8F7',
  pre_purchase_consultation: '#7EB8F7',
  initial_discovery: '#f44336',
  annual_review: '#FBBC04',
  closing: '#34A853',
  pending: '#FBBC04',
  high_priority: '#f44336',
  default: '#7EB8F7',
};

const STATUS_COLORS = {
  scheduled: '#f44336',
  completed: '#34A853',
  in_progress: '#ff9800',
  no_show: '#9e9e9e',
  cancelled: '#9e9e9e',
};

const MAX_CACHE_SIZE = 6;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isSameDay(d1, d2) {
  return (
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate()
  );
}

function isToday(date) {
  return isSameDay(date, new Date());
}

function formatDateHeader(dateStr) {
  const d = new Date(dateStr);
  const dayName = DAY_NAMES[d.getDay()];
  const month = MONTH_NAMES[d.getMonth()].slice(0, 3);
  return `${dayName}, ${month} ${d.getDate()}, ${d.getFullYear()}`;
}

function formatTime(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

function formatDateRange(scheduledAt, endTime) {
  if (!scheduledAt) return '';
  const start = new Date(scheduledAt);
  const opts = { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' };
  const datePart = start.toLocaleDateString('en-US', opts);
  const timeOpts = { hour: 'numeric', minute: '2-digit', hour12: true };
  const startTime = start.toLocaleTimeString('en-US', timeOpts);
  let endTimePart = '';
  if (endTime) {
    endTimePart = new Date(endTime).toLocaleTimeString('en-US', timeOpts);
  }
  let tzAbbr = '';
  try {
    tzAbbr = start.toLocaleTimeString('en-US', { timeZoneName: 'short' }).split(' ').pop();
  } catch { /* noop */ }
  if (endTimePart) {
    return `${datePart}\n${startTime} – ${endTimePart} ${tzAbbr}`;
  }
  return `${datePart}\n${startTime} ${tzAbbr}`;
}

function getBorderColor(appointment) {
  if (appointment.priority === 'high' || appointment.is_urgent) return BORDER_COLORS.high_priority;
  if (appointment.status === 'pending') return BORDER_COLORS.pending;
  const type = (appointment.appointment_type || appointment.type || '').toLowerCase().replace(/\s+/g, '_');
  if (type.includes('closing')) return BORDER_COLORS.closing;
  if (type.includes('initial') || type.includes('discovery')) return BORDER_COLORS.initial_discovery;
  if (type.includes('annual') || type.includes('review')) return BORDER_COLORS.annual_review;
  if (type.includes('pre_purchase') || type.includes('consultation')) return BORDER_COLORS.pre_purchase;
  return BORDER_COLORS.default;
}

function groupByDate(items) {
  const groups = {};
  items.forEach((item) => {
    const dateKey = new Date(item.start_time || item.scheduled_date || item.date).toLocaleDateString('en-US');
    if (!groups[dateKey]) {
      groups[dateKey] = { dateKey, dateStr: item.start_time || item.scheduled_date || item.date, items: [] };
    }
    groups[dateKey].items.push(item);
  });
  return Object.values(groups).sort((a, b) => new Date(a.dateStr) - new Date(b.dateStr));
}

function getInitials(name) {
  if (!name) return '?';
  return name.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2);
}

function formatPhone(phone) {
  if (!phone) return '';
  const digits = phone.replace(/\D/g, '');
  if (digits.length === 10) return `+1 (${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  if (digits.length === 11 && digits[0] === '1') return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  return phone;
}

function statusLabel(status) {
  if (!status) return 'Unknown';
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Icons (inline SVG)
// ---------------------------------------------------------------------------

const CloseIcon = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <path d="M4.5 4.5L13.5 13.5M13.5 4.5L4.5 13.5" stroke="#666" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);

const PhoneIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.79 19.79 0 012.12 4.18 2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.362 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.338 1.85.573 2.81.7A2 2 0 0122 16.92z" />
  </svg>
);

const MailIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="4" width="20" height="16" rx="2" />
    <path d="M22 7l-10 7L2 7" />
  </svg>
);

const GlobeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10A15.3 15.3 0 0112 2z" />
  </svg>
);

const CheckCircleIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#34A853" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
    <path d="M22 4L12 14.01l-3-3" />
  </svg>
);

const ChevronRightIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#999" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 18l6-6-6-6" />
  </svg>
);

const LocationIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
    <circle cx="12" cy="10" r="3" />
  </svg>
);

// ---------------------------------------------------------------------------
// Sub-components: Loading skeletons
// ---------------------------------------------------------------------------

function ListSkeleton() {
  return (
    <div className="acs-skeleton">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="acs-skeleton-group">
          <div className="acs-skeleton-date" />
          <div className="acs-skeleton-card" />
          {i % 2 === 0 && <div className="acs-skeleton-card" />}
        </div>
      ))}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="acs-detail-skeleton">
      <div className="acs-detail-skeleton__block" style={{ width: 60, height: 16 }} />
      <div className="acs-detail-skeleton__block" style={{ width: '80%', height: 22, marginTop: 12 }} />
      <div className="acs-detail-skeleton__block" style={{ width: '60%', height: 14, marginTop: 8 }} />
      <div className="acs-detail-skeleton__block" style={{ width: 100, height: 13, marginTop: 24 }} />
      <div className="acs-detail-skeleton__block" style={{ width: '90%', height: 16, marginTop: 10 }} />
      <div className="acs-detail-skeleton__block" style={{ width: 120, height: 13, marginTop: 24 }} />
      <div className="acs-detail-skeleton__block" style={{ width: '70%', height: 16, marginTop: 10 }} />
      <div className="acs-detail-skeleton__block" style={{ width: '70%', height: 16, marginTop: 8 }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Empty state
// ---------------------------------------------------------------------------

function EmptyState({ activeTab }) {
  return (
    <div className="acs-empty">
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="acs-empty-icon">
        <rect x="6" y="10" width="36" height="32" rx="4" stroke="#ccc" strokeWidth="2" fill="none" />
        <line x1="6" y1="18" x2="42" y2="18" stroke="#ccc" strokeWidth="2" />
        <line x1="16" y1="6" x2="16" y2="14" stroke="#ccc" strokeWidth="2" strokeLinecap="round" />
        <line x1="32" y1="6" x2="32" y2="14" stroke="#ccc" strokeWidth="2" strokeLinecap="round" />
        <circle cx="24" cy="30" r="4" stroke="#ccc" strokeWidth="1.5" fill="none" />
        <line x1="27" y1="33" x2="31" y2="37" stroke="#ccc" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <p className="acs-empty-text">
        No {activeTab === 'closings' ? 'closings' : 'appointments'} this month
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Appointment card
// ---------------------------------------------------------------------------

function AppointmentCard({ appointment, onClick }) {
  const borderColor = getBorderColor(appointment);
  const type = appointment.appointment_type || appointment.type || 'Appointment';
  const name =
    appointment.client_name ||
    appointment.lead_name ||
    appointment.contact_name ||
    appointment.title ||
    'Untitled';
  const timeStr = formatTime(appointment.start_time || appointment.scheduled_date);
  const endTimeStr = formatTime(appointment.end_time);

  return (
    <button
      className="acs-card"
      style={{ borderLeftColor: borderColor }}
      onClick={onClick}
      type="button"
    >
      <div className="acs-card-name">{name}</div>
      <div className="acs-card-type">{type}</div>
      <div className="acs-card-time">
        {timeStr}
        {endTimeStr ? ` – ${endTimeStr}` : ''}
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Confirm modal
// ---------------------------------------------------------------------------

function ConfirmModal({ open, title, message, confirmLabel, cancelLabel, destructive, onConfirm, onCancel }) {
  const cancelRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="acs-confirm-overlay" onClick={onCancel}>
      <div
        className="acs-confirm-dialog"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="acs-confirm-dialog__title">{title}</h2>
        <p className="acs-confirm-dialog__message">{message}</p>
        <div className="acs-confirm-dialog__actions">
          <button
            ref={cancelRef}
            className="acs-confirm-dialog__btn acs-confirm-dialog__btn--cancel"
            onClick={onCancel}
          >
            {cancelLabel || 'Cancel'}
          </button>
          <button
            className={`acs-confirm-dialog__btn ${destructive ? 'acs-confirm-dialog__btn--destructive' : ''}`}
            onClick={onConfirm}
          >
            {confirmLabel || 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Detail view
// ---------------------------------------------------------------------------

function DetailView({ appointmentId, onBack }) {
  const navigate = useNavigate();
  const [appointment, setAppointment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('details');
  const [actionLoading, setActionLoading] = useState(false);
  const [confirmModal, setConfirmModal] = useState({ open: false });

  const fetchAppointment = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.get(`/api/v1/scheduler/appointments/${appointmentId}`);
      setAppointment(res.data);
    } catch (err) {
      setError(err?.response?.status === 404 ? 'Appointment not found' : 'Failed to load details');
    } finally {
      setLoading(false);
    }
  }, [appointmentId]);

  useEffect(() => {
    if (appointmentId) fetchAppointment();
  }, [appointmentId, fetchAppointment]);

  const handleMarkNoShow = () => {
    setConfirmModal({
      open: true,
      title: 'Mark as No-Show',
      message: 'Are you sure you want to mark this appointment as no-show? This action cannot be undone.',
      confirmLabel: 'Mark No-Show',
      cancelLabel: 'Cancel',
      destructive: true,
      onConfirm: async () => {
        setConfirmModal({ open: false });
        try {
          setActionLoading(true);
          await api.patch(`/api/v1/scheduler/appointments/${appointmentId}`, { status: 'no_show' });
          toast.success('Marked as no-show');
          onBack();
        } catch {
          toast.error('Failed to update appointment status.');
        } finally {
          setActionLoading(false);
        }
      },
    });
  };

  const handleBookFollowUp = () => {
    navigate('/calendar');
  };

  if (loading) {
    return (
      <div className="acs-detail">
        <div className="acs-detail-header">
          <button className="acs-back-btn" onClick={onBack} type="button">
            <span className="acs-back-chevron">&lsaquo;</span> Back
          </button>
        </div>
        <DetailSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="acs-detail">
        <div className="acs-detail-header">
          <button className="acs-back-btn" onClick={onBack} type="button">
            <span className="acs-back-chevron">&lsaquo;</span> Back
          </button>
        </div>
        <div className="acs-placeholder">
          <p className="acs-placeholder__text">{error}</p>
        </div>
      </div>
    );
  }

  const title = appointment?.title || appointment?.name || 'Untitled Appointment';
  const status = appointment?.status || 'scheduled';
  const dateRange = formatDateRange(appointment?.scheduled_at, appointment?.end_time);

  const attendees = appointment?.attendees || [];
  const primaryAttendee = attendees[0] || null;
  const inviteeName = primaryAttendee?.name || primaryAttendee?.first_name
    ? `${primaryAttendee?.first_name || ''} ${primaryAttendee?.last_name || ''}`.trim()
    : appointment?.contact_name || '';
  const inviteeEmail = primaryAttendee?.email || appointment?.email || '';
  const inviteePhone = primaryAttendee?.phone || appointment?.phone || '';
  const inviteeTimezone = primaryAttendee?.timezone || appointment?.timezone || '';
  const hostName = appointment?.host_name || appointment?.loan_officer_name || '';
  const hostPhone = appointment?.host_phone || appointment?.phone || '';
  const location = appointment?.location || '';

  return (
    <div className="acs-detail">
      <div className="acs-detail-header">
        <button className="acs-back-btn" onClick={onBack} type="button">
          <span className="acs-back-chevron">&lsaquo;</span> Back
        </button>
        <div className="acs-detail-title-row">
          <span className="acs-detail-status-dot" style={{ backgroundColor: STATUS_COLORS[status] || '#888' }} />
          <h1 className="acs-detail-title">{title}</h1>
        </div>
        {dateRange && <p className="acs-detail-subtitle" style={{ whiteSpace: 'pre-line' }}>{dateRange}</p>}
      </div>

      <div className="acs-detail-tabs">
        {['details', 'notes', 'history'].map((tab) => (
          <button
            key={tab}
            className={`acs-detail-tab ${activeTab === tab ? 'acs-detail-tab--active' : ''}`}
            onClick={() => setActiveTab(tab)}
            type="button"
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      <div className="acs-detail-body">
        {activeTab === 'details' ? (
          <>
            <section className="acs-section">
              <h2 className="acs-section__title">Location</h2>
              <div className="acs-row">
                <div className="acs-row__icon"><LocationIcon /></div>
                <div className="acs-row__content">
                  {location ? (
                    <span className="acs-row__text">{location}</span>
                  ) : hostPhone ? (
                    <span className="acs-row__text">
                      Host will call{' '}
                      <a className="acs-link" href={`tel:${hostPhone}`}>{formatPhone(hostPhone)}</a>
                    </span>
                  ) : (
                    <span className="acs-row__text acs-row__text--muted">No location specified</span>
                  )}
                </div>
              </div>
            </section>

            {(inviteeName || inviteeEmail || inviteePhone) && (
              <section className="acs-section">
                <h2 className="acs-section__title">Invitee Details</h2>
                <div className="acs-row">
                  <div className="acs-avatar acs-avatar--invitee">{getInitials(inviteeName)}</div>
                  <div className="acs-row__content">
                    <span className="acs-invitee-name">{inviteeName || 'Unknown invitee'}</span>
                  </div>
                </div>
                <div className="acs-row">
                  <div className="acs-row__icon"><CheckCircleIcon /></div>
                  <div className="acs-row__content">
                    <span className="acs-row__text">{statusLabel(status)}</span>
                  </div>
                </div>
                {inviteeEmail && (
                  <div className="acs-row">
                    <div className="acs-row__icon"><MailIcon /></div>
                    <div className="acs-row__content">
                      <a className="acs-link" href={`mailto:${inviteeEmail}`}>{inviteeEmail}</a>
                    </div>
                  </div>
                )}
                {inviteePhone && (
                  <div className="acs-row">
                    <div className="acs-row__icon"><PhoneIcon /></div>
                    <div className="acs-row__content">
                      <a className="acs-link" href={`tel:${inviteePhone}`}>{formatPhone(inviteePhone)}</a>
                    </div>
                  </div>
                )}
                {inviteeTimezone && (
                  <div className="acs-row">
                    <div className="acs-row__icon"><GlobeIcon /></div>
                    <div className="acs-row__content">
                      <span className="acs-row__text">{inviteeTimezone}</span>
                    </div>
                  </div>
                )}
              </section>
            )}

            {hostName && (
              <section className="acs-section">
                <h2 className="acs-section__title">Host</h2>
                <div className="acs-host-card">
                  <div className="acs-avatar acs-avatar--host">{getInitials(hostName)}</div>
                  <div className="acs-host-card__info">
                    <span className="acs-host-card__name">{hostName}</span>
                    <span className="acs-host-card__badge">Host</span>
                  </div>
                  <ChevronRightIcon />
                </div>
              </section>
            )}
          </>
        ) : (
          <div className="acs-placeholder">
            <p className="acs-placeholder__text">Coming soon</p>
          </div>
        )}
      </div>

      <div className="acs-detail-footer">
        <button
          className="acs-action-btn acs-action-btn--ghost"
          onClick={handleMarkNoShow}
          disabled={actionLoading}
          type="button"
        >
          {actionLoading ? 'Updating...' : 'Mark as no-show'}
        </button>
        <button
          className="acs-action-btn acs-action-btn--primary"
          onClick={handleBookFollowUp}
          type="button"
        >
          Book follow-up
        </button>
      </div>

      <ConfirmModal
        open={confirmModal.open}
        title={confirmModal.title}
        message={confirmModal.message}
        confirmLabel={confirmModal.confirmLabel}
        cancelLabel={confirmModal.cancelLabel}
        destructive={confirmModal.destructive}
        onConfirm={confirmModal.onConfirm || (() => setConfirmModal({ open: false }))}
        onCancel={() => setConfirmModal({ open: false })}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component: AriaCalendarSheet
// ---------------------------------------------------------------------------

export default function AriaCalendarSheet({ open, onClose }) {
  const [view, setView] = useState('list');
  const [selectedAppointmentId, setSelectedAppointmentId] = useState(null);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [activeTab, setActiveTab] = useState('appointments');
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showMonthNav, setShowMonthNav] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const cacheRef = useRef(new Map());

  const monthLabel = `${MONTH_NAMES[currentDate.getMonth()]} ${currentDate.getFullYear()}`;
  const month = currentDate.getMonth() + 1;
  const year = currentDate.getFullYear();

  // Lock body scroll when open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  // Reset to list view when panel closes
  useEffect(() => {
    if (!open) {
      const timer = setTimeout(() => {
        setView('list');
        setSelectedAppointmentId(null);
      }, 350);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // Cache helpers
  const getCacheKey = useCallback((m, y, tab) => `${y}-${String(m).padStart(2, '0')}:${tab}`, []);

  const trimCache = useCallback(() => {
    const cache = cacheRef.current;
    while (cache.size > MAX_CACHE_SIZE) {
      const firstKey = cache.keys().next().value;
      cache.delete(firstKey);
    }
  }, []);

  // Data fetching
  const processResponse = useCallback((data, tab) => {
    const items = Array.isArray(data) ? data : (data?.appointments || data?.items || []);
    if (tab === 'closings') {
      return items.filter((item) => {
        const t = (item.appointment_type || item.type || '').toLowerCase();
        return t.includes('closing') || t.includes('close');
      });
    }
    return items;
  }, []);

  const fetchData = useCallback(async () => {
    const key = getCacheKey(month, year, activeTab);
    const cached = cacheRef.current.get(key);

    if (cached) {
      setAppointments(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }

    try {
      const params = { month, year };
      if (activeTab === 'closings') params.type = 'closing';
      const data = await schedulerAPI.getAppointments(params);
      const filtered = processResponse(data, activeTab);
      cacheRef.current.set(key, filtered);
      trimCache();
      setAppointments((prev) => {
        const prevJson = JSON.stringify(prev);
        const newJson = JSON.stringify(filtered);
        return prevJson === newJson ? prev : filtered;
      });
    } catch (err) {
      console.error('Failed to fetch appointments:', err);
      if (!cached) setAppointments([]);
    } finally {
      setLoading(false);
    }
  }, [month, year, activeTab, getCacheKey, processResponse, trimCache]);

  useEffect(() => {
    if (open) fetchData();
  }, [open, fetchData]);

  // Pull-to-refresh
  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try { await fetchData(); } finally { setRefreshing(false); }
  }, [fetchData]);

  // Month navigation
  const goToPrevMonth = useCallback(() => {
    setCurrentDate((prev) => { const d = new Date(prev); d.setMonth(d.getMonth() - 1); return d; });
  }, []);
  const goToNextMonth = useCallback(() => {
    setCurrentDate((prev) => { const d = new Date(prev); d.setMonth(d.getMonth() + 1); return d; });
  }, []);
  const goToToday = useCallback(() => { setCurrentDate(new Date()); }, []);

  // Grouped data
  const dateGroups = useMemo(() => groupByDate(appointments), [appointments]);

  // Card tap → detail
  const handleCardTap = useCallback((appointment) => {
    setSelectedAppointmentId(appointment.id);
    setView('detail');
  }, []);

  // Detail → back to list
  const handleBackToList = useCallback(() => {
    setView('list');
    setSelectedAppointmentId(null);
  }, []);

  const showDetail = view === 'detail';

  return (
    <div className={`acs-overlay ${open ? 'acs-overlay--open' : ''}`}>
      <div className="acs-panel">
        <div className="acs-views">
          {/* === List View === */}
          <div className={`acs-view ${showDetail ? 'acs-view--list-pushed' : 'acs-view--list'}`}>
            <header className="acs-header">
              <div className="acs-header-top">
                <div className="acs-month-row">
                  <button
                    className="acs-month-toggle"
                    onClick={() => setShowMonthNav((v) => !v)}
                    type="button"
                  >
                    <span className="acs-month-label">{monthLabel}</span>
                    <svg
                      width="12" height="12" viewBox="0 0 12 12" fill="none"
                      className={`acs-month-chevron ${showMonthNav ? 'acs-month-chevron--open' : ''}`}
                    >
                      <path d="M3 4.5L6 7.5L9 4.5" stroke="#333" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                  <button className="acs-close-btn" onClick={onClose} type="button" aria-label="Close calendar">
                    <CloseIcon />
                  </button>
                </div>
                {showMonthNav && (
                  <div className="acs-month-nav">
                    <button className="acs-nav-arrow" onClick={goToPrevMonth} type="button" aria-label="Previous month">
                      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                        <path d="M12 4L6 10L12 16" stroke="#333" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                    <button className="acs-today-btn" onClick={goToToday} type="button">Today</button>
                    <button className="acs-nav-arrow" onClick={goToNextMonth} type="button" aria-label="Next month">
                      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                        <path d="M8 4L14 10L8 16" stroke="#333" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                  </div>
                )}
              </div>
              <div className="acs-tabs">
                {TABS.map((tab) => (
                  <button
                    key={tab.key}
                    className={`acs-tab ${activeTab === tab.key ? 'acs-tab--active' : ''}`}
                    onClick={() => setActiveTab(tab.key)}
                    type="button"
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </header>

            <PullToRefreshContainer onRefresh={handleRefresh} className="acs-body">
              {loading ? (
                <ListSkeleton />
              ) : appointments.length === 0 ? (
                <EmptyState activeTab={activeTab} />
              ) : (
                dateGroups.map((group) => {
                  const groupDate = new Date(group.dateStr);
                  const todayFlag = isToday(groupDate);
                  return (
                    <section key={group.dateKey} className="acs-date-group">
                      <div className="acs-date-header">
                        <span className="acs-date-text">{formatDateHeader(group.dateStr)}</span>
                        {todayFlag && <span className="acs-today-badge">Today</span>}
                      </div>
                      {group.items.map((appt) => (
                        <AppointmentCard
                          key={appt.id || `${appt.start_time}-${appt.client_name}`}
                          appointment={appt}
                          onClick={() => handleCardTap(appt)}
                        />
                      ))}
                    </section>
                  );
                })
              )}
            </PullToRefreshContainer>
          </div>

          {/* === Detail View === */}
          <div className={`acs-view ${showDetail ? 'acs-view--detail' : 'acs-view--detail-offscreen'}`}>
            {selectedAppointmentId && (
              <DetailView
                appointmentId={selectedAppointmentId}
                onBack={handleBackToList}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the file has no syntax errors**

```bash
cd frontend && npx -y acorn --ecma2020 --module --jsx src/pages/aria-mobile/AriaCalendarSheet.jsx 2>&1 | tail -5
```

If acorn isn't available or doesn't support JSX, just verify the dev server compiles it without errors (done in Task 5).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/aria-mobile/AriaCalendarSheet.jsx
git commit -m "feat: add AriaCalendarSheet component with list and detail views"
```

---

### Task 4: Wire AriaCalendarSheet into AriaVoiceHome

**Files:**
- Modify: `frontend/src/pages/aria-mobile/AriaVoiceHome.jsx`

- [ ] **Step 1: Add the import and state**

At the top of `AriaVoiceHome.jsx`, add the import alongside the existing imports (after the `CallIntelligenceSlidePanel` import, around line 21):

```jsx
import AriaCalendarSheet from './AriaCalendarSheet';
```

Inside the `AriaVoiceHome` component (around line 434, after the `ciPanelOpen` state), add:

```jsx
  const [calendarOpen, setCalendarOpen] = useState(false);
```

- [ ] **Step 2: Pass onCalendarPress to AriaTabNav**

Find the `AriaTabNav` render near the bottom of the component (line ~771). Change it from:

```jsx
      <AriaTabNav variant="dark" activeTab="home" />
```

to:

```jsx
      <AriaTabNav
        variant="dark"
        activeTab={calendarOpen ? 'calendar' : 'home'}
        onCalendarPress={() => setCalendarOpen(true)}
      />
```

- [ ] **Step 3: Render AriaCalendarSheet before the closing `</div>` of `aria-voice-home`**

Find the `AriaTabNav` render you just modified. Immediately after it (and before the closing `</div>` of the `aria-voice-home` div), add:

```jsx
      <AriaCalendarSheet
        open={calendarOpen}
        onClose={() => setCalendarOpen(false)}
      />
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/aria-mobile/AriaVoiceHome.jsx
git commit -m "feat: wire AriaCalendarSheet into AriaVoiceHome with tab callback"
```

---

### Task 5: Manual testing in browser

**Files:** None (verification only)

- [ ] **Step 1: Start the dev server**

```bash
cd frontend && npm start
```

- [ ] **Step 2: Test the list view**

Navigate to `http://localhost:3000/aria-mobile` (or whatever port Vite uses). Verify:

1. The Aria voice home loads normally with the mic button
2. Tap the Calendar icon in the bottom tab nav
3. The calendar sheet slides up from the bottom, covering the full screen
4. The month header shows the current month with a chevron
5. Tapping the chevron reveals Previous / Today / Next month navigation
6. Appointments/Closings tabs filter correctly
7. Events are grouped by date with date headers
8. "Today" badge appears next to today's date
9. Tapping the X button closes the sheet with a slide-down animation
10. After closing, the Aria mic is visible again and functional

- [ ] **Step 3: Test the detail view**

1. Open the calendar sheet
2. Tap an appointment card
3. The detail view slides in from the right
4. Back button slides back to the list
5. Location, Invitee Details, Host sections render correctly
6. "Mark as no-show" shows a confirmation modal
7. "Book follow-up" navigates to `/calendar`

- [ ] **Step 4: Test edge cases**

1. Open and close the panel rapidly — no stale views
2. Navigate months — Previous/Next load correctly
3. Empty month — shows "No appointments this month"
4. All other bottom nav tabs still navigate normally (Home, History, Tasks, Profile)
5. The panel doesn't break the LiveKit or SSE voice flows

- [ ] **Step 5: Commit all files together**

If any adjustments were needed during testing, commit them:

```bash
git add -A frontend/src/pages/aria-mobile/ frontend/src/components/mobile/AriaTabNav.jsx
git commit -m "feat: Aria inline calendar slide-over panel complete"
```
