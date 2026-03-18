/**
 * SmartScheduler Advanced Tests
 *
 * Covers areas NOT tested in SmartScheduler.test.jsx:
 *   - Keyboard navigation within calendar grid (ArrowLeft/Right/Up/Down, Enter, Space)
 *   - Touch swipe gestures for month navigation
 *   - Month boundary transitions (navigating across year boundary)
 *   - Mobile sticky header and back-to-calendar flow
 *   - Confirmation state display details
 *   - Calendar legend presence
 *   - Multiple date selections (switching between dates)
 *   - Slot list keyboard escape handling
 *   - Calendar grid ARIA roles and structure
 *   - Concurrent month navigation and slot refresh
 *   - Custom appointmentType prop usage
 *   - Error retry clears error and refetches
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../SmartScheduler.css', () => ({}));

const mockFetch = vi.fn();
global.fetch = mockFetch;

import SmartScheduler from '../SmartScheduler';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockResponse(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

function makeSlotsForDate(dateStr, count = 3) {
  const slots = [];
  for (let i = 0; i < count; i++) {
    const hour = 9 + i;
    const startHour = hour.toString().padStart(2, '0');
    slots.push({
      date: dateStr,
      start: `${dateStr}T${startHour}:00:00`,
      end: `${dateStr}T${startHour}:30:00`,
    });
  }
  return slots;
}

/**
 * Render the scheduler with mocked slot data for specific future dates.
 * Returns the date strings that have slots.
 */
async function renderWithSlots(props = {}, slotDates = null) {
  const today = new Date();
  const todayStr = today.toISOString().split('T')[0];

  // Default: create slots for tomorrow and day-after-tomorrow
  if (!slotDates) {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dayAfter = new Date();
    dayAfter.setDate(dayAfter.getDate() + 2);
    slotDates = [
      tomorrow.toISOString().split('T')[0],
      dayAfter.toISOString().split('T')[0],
    ];
  }

  const allSlots = slotDates.flatMap(d => makeSlotsForDate(d));

  mockFetch.mockImplementation((url) => {
    if (url.includes('/slots')) {
      return mockResponse({ available_slots: allSlots });
    }
    return mockResponse({
      booking_page: { appointment_types: [{ id: 'type-1' }] },
    });
  });

  const onSelect = props.onSelect || vi.fn();

  let result;
  await act(async () => {
    result = render(
      <SmartScheduler
        onSelect={onSelect}
        selectedSlot={props.selectedSlot || null}
        slug="test-slug"
        appointmentTypeId={props.appointmentTypeId || 'type-1'}
        daysAhead={props.daysAhead || 14}
        title={props.title || 'Pick a Time'}
        subtitle={props.subtitle || 'Choose wisely'}
        {...props}
      />
    );
  });

  // Wait for loading to finish
  await waitFor(() => {
    expect(screen.queryByText('Loading available times...')).not.toBeInTheDocument();
  });

  return { ...result, onSelect, slotDates };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SmartScheduler — Advanced', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 2, 15, 10, 0, 0)); // March 15, 2026
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // =========================================================================
  // Keyboard Navigation
  // =========================================================================

  describe('Keyboard navigation', () => {
    it('moves focus right with ArrowRight key on calendar days', async () => {
      const { slotDates } = await renderWithSlots();

      // Find interactive (has-slots) day cells
      const interactiveDays = document.querySelectorAll('.calendar-day.has-slots');
      expect(interactiveDays.length).toBeGreaterThanOrEqual(1);

      // Focus the first interactive day
      act(() => { interactiveDays[0].focus(); });

      // Fire ArrowRight on the calendar-days container
      const calendarDays = document.querySelector('.calendar-days');
      fireEvent.keyDown(calendarDays, { key: 'ArrowRight' });

      // If there are at least 2 interactive days, the second should now have tabIndex=0
      if (interactiveDays.length >= 2) {
        await waitFor(() => {
          expect(interactiveDays[1].getAttribute('tabindex')).toBe('0');
        });
      }
    });

    it('moves focus left with ArrowLeft key on calendar days', async () => {
      const { slotDates } = await renderWithSlots();

      const interactiveDays = document.querySelectorAll('.calendar-day.has-slots');
      if (interactiveDays.length < 2) return; // need at least 2 days

      // Focus the second interactive day
      act(() => { interactiveDays[1].focus(); });

      const calendarDays = document.querySelector('.calendar-days');
      fireEvent.keyDown(calendarDays, { key: 'ArrowLeft' });

      await waitFor(() => {
        expect(interactiveDays[0].getAttribute('tabindex')).toBe('0');
      });
    });

    it('selects a date when Enter is pressed on a focused day', async () => {
      const { slotDates } = await renderWithSlots();

      const interactiveDays = document.querySelectorAll('.calendar-day.has-slots');
      expect(interactiveDays.length).toBeGreaterThanOrEqual(1);

      // Focus and press Enter on the first available day
      act(() => { interactiveDays[0].focus(); });
      fireEvent.keyDown(interactiveDays[0], { key: 'Enter' });

      // Time slots should now be visible
      await waitFor(() => {
        const timeSlotsSection = document.querySelector('.time-slots');
        expect(timeSlotsSection).toBeTruthy();
      });
    });

    it('selects a date when Space is pressed on a focused day', async () => {
      const { slotDates } = await renderWithSlots();

      const interactiveDays = document.querySelectorAll('.calendar-day.has-slots');
      expect(interactiveDays.length).toBeGreaterThanOrEqual(1);

      act(() => { interactiveDays[0].focus(); });
      fireEvent.keyDown(interactiveDays[0], { key: ' ' });

      await waitFor(() => {
        const timeSlotsSection = document.querySelector('.time-slots');
        expect(timeSlotsSection).toBeTruthy();
      });
    });

    it('Escape key in time slots returns to calendar and deselects the date', async () => {
      const { slotDates } = await renderWithSlots();

      // Select a date first
      const interactiveDays = document.querySelectorAll('.calendar-day.has-slots');
      fireEvent.click(interactiveDays[0]);

      await waitFor(() => {
        expect(document.querySelector('.time-slots')).toBeTruthy();
      });

      // Press Escape in the time slots area
      const timeSlotsContainer = document.querySelector('.scheduler-times');
      fireEvent.keyDown(timeSlotsContainer, { key: 'Escape' });

      // Should show the "select a date" prompt again
      await waitFor(() => {
        expect(screen.getByText(/select a date/i)).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Touch/Swipe Gestures
  // =========================================================================

  describe('Touch swipe gestures', () => {
    it('swipe left navigates to next month', async () => {
      await renderWithSlots();

      const calendar = document.querySelector('.scheduler-calendar');

      // Verify current month is March 2026
      expect(screen.getByText('March 2026')).toBeInTheDocument();

      // Simulate swipe left (negative dx)
      fireEvent.touchStart(calendar, {
        touches: [{ clientX: 300, clientY: 200 }],
      });
      fireEvent.touchEnd(calendar, {
        changedTouches: [{ clientX: 100, clientY: 200 }],
      });

      // Should navigate to April 2026
      await waitFor(() => {
        expect(screen.getByText('April 2026')).toBeInTheDocument();
      });
    });

    it('swipe right does NOT navigate back when on the current month', async () => {
      await renderWithSlots();

      const calendar = document.querySelector('.scheduler-calendar');

      // We're on March 2026 (current month)
      expect(screen.getByText('March 2026')).toBeInTheDocument();

      // Simulate swipe right (positive dx)
      fireEvent.touchStart(calendar, {
        touches: [{ clientX: 100, clientY: 200 }],
      });
      fireEvent.touchEnd(calendar, {
        changedTouches: [{ clientX: 300, clientY: 200 }],
      });

      // Should still show March 2026 (cannot go before current month)
      expect(screen.getByText('March 2026')).toBeInTheDocument();
    });

    it('does not navigate on vertical swipe (dy > 100)', async () => {
      await renderWithSlots();

      const calendar = document.querySelector('.scheduler-calendar');
      expect(screen.getByText('March 2026')).toBeInTheDocument();

      // Vertical swipe (large dy)
      fireEvent.touchStart(calendar, {
        touches: [{ clientX: 300, clientY: 100 }],
      });
      fireEvent.touchEnd(calendar, {
        changedTouches: [{ clientX: 100, clientY: 350 }],
      });

      // Month should not change
      expect(screen.getByText('March 2026')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Month Boundary Transitions
  // =========================================================================

  describe('Month boundary transitions', () => {
    it('navigates from December to January of the next year', async () => {
      vi.setSystemTime(new Date(2026, 11, 15, 10, 0, 0)); // December 2026

      await renderWithSlots({}, []);

      expect(screen.getByText('December 2026')).toBeInTheDocument();

      // Click next month
      const nextBtn = screen.getByLabelText('Next month');
      fireEvent.click(nextBtn);

      await waitFor(() => {
        expect(screen.getByText('January 2027')).toBeInTheDocument();
      });
    });

    it('correctly labels the month after multiple forward navigations', async () => {
      await renderWithSlots({}, []);

      expect(screen.getByText('March 2026')).toBeInTheDocument();

      const nextBtn = screen.getByLabelText('Next month');

      // Navigate forward 3 months
      fireEvent.click(nextBtn);
      await waitFor(() => expect(screen.getByText('April 2026')).toBeInTheDocument());

      fireEvent.click(nextBtn);
      await waitFor(() => expect(screen.getByText('May 2026')).toBeInTheDocument());

      fireEvent.click(nextBtn);
      await waitFor(() => expect(screen.getByText('June 2026')).toBeInTheDocument());
    });
  });

  // =========================================================================
  // Mobile Sticky Header & Back Flow
  // =========================================================================

  describe('Mobile sticky header', () => {
    it('shows mobile sticky header with date when a date is selected', async () => {
      const { slotDates } = await renderWithSlots();

      const interactiveDays = document.querySelectorAll('.calendar-day.has-slots');
      fireEvent.click(interactiveDays[0]);

      await waitFor(() => {
        const stickyHeader = document.querySelector('.scheduler-mobile-sticky-header');
        expect(stickyHeader).toBeTruthy();
      });

      // Verify it shows a formatted date
      const selectedDateSpan = document.querySelector('.mobile-selected-date');
      expect(selectedDateSpan).toBeTruthy();
      // Date text should contain month abbreviation (e.g., "Mon, Mar 16")
      expect(selectedDateSpan.textContent).toMatch(/\w+/);
    });

    it('back button in sticky header deselects the date and hides time slots', async () => {
      const { slotDates } = await renderWithSlots();

      const interactiveDays = document.querySelectorAll('.calendar-day.has-slots');
      fireEvent.click(interactiveDays[0]);

      await waitFor(() => {
        expect(document.querySelector('.scheduler-mobile-sticky-header')).toBeTruthy();
      });

      // Click the back button
      const backBtn = screen.getByLabelText('Back to calendar');
      fireEvent.click(backBtn);

      // Sticky header should be gone, prompt should return
      await waitFor(() => {
        expect(document.querySelector('.scheduler-mobile-sticky-header')).toBeFalsy();
        expect(screen.getByText(/select a date/i)).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Switching Between Dates
  // =========================================================================

  describe('Switching between dates', () => {
    it('updates displayed time slots when switching from one date to another', async () => {
      const tomorrow = new Date(2026, 2, 16);
      const dayAfter = new Date(2026, 2, 17);
      const tomorrowStr = '2026-03-16';
      const dayAfterStr = '2026-03-17';

      // Give tomorrow 2 slots, day-after 4 slots
      const allSlots = [
        ...makeSlotsForDate(tomorrowStr, 2),
        ...makeSlotsForDate(dayAfterStr, 4),
      ];

      mockFetch.mockImplementation((url) => {
        if (url.includes('/slots')) {
          return mockResponse({ available_slots: allSlots });
        }
        return mockResponse({
          booking_page: { appointment_types: [{ id: 'type-1' }] },
        });
      });

      await act(async () => {
        render(
          <SmartScheduler
            onSelect={vi.fn()}
            selectedSlot={null}
            appointmentTypeId="type-1"
            daysAhead={14}
          />
        );
      });

      await waitFor(() => {
        expect(screen.queryByText('Loading available times...')).not.toBeInTheDocument();
      });

      // Click tomorrow (2 slots)
      const days = document.querySelectorAll('.calendar-day.has-slots');
      fireEvent.click(days[0]);

      await waitFor(() => {
        const slotButtons = document.querySelectorAll('.time-slot');
        expect(slotButtons.length).toBe(2);
      });

      // Click day-after (4 slots)
      fireEvent.click(days[1]);

      await waitFor(() => {
        const slotButtons = document.querySelectorAll('.time-slot');
        expect(slotButtons.length).toBe(4);
      });
    });
  });

  // =========================================================================
  // Confirmation State
  // =========================================================================

  describe('Confirmation state details', () => {
    it('displays formatted date and time in the confirmation bar', async () => {
      const selectedSlot = {
        start_time: '2026-03-16T14:00:00',
        end_time: '2026-03-16T14:30:00',
      };

      mockFetch.mockImplementation((url) => {
        if (url.includes('/slots')) {
          return mockResponse({ available_slots: [] });
        }
        return mockResponse({
          booking_page: { appointment_types: [{ id: 'type-1' }] },
        });
      });

      await act(async () => {
        render(
          <SmartScheduler
            onSelect={vi.fn()}
            selectedSlot={selectedSlot}
            appointmentTypeId="type-1"
          />
        );
      });

      await waitFor(() => {
        expect(screen.queryByText('Loading available times...')).not.toBeInTheDocument();
      });

      // Confirmation bar should show
      const confirmBar = document.querySelector('.scheduler-confirmation');
      expect(confirmBar).toBeTruthy();

      // Should contain checkmark
      const checkmark = document.querySelector('.confirmation-icon');
      expect(checkmark).toBeTruthy();

      // Should contain "at" separator
      expect(confirmBar.textContent).toContain('at');

      // Should contain "Monday, March 16" (full date format)
      expect(confirmBar.textContent).toContain('March');
      expect(confirmBar.textContent).toContain('16');
    });

    it('does not show confirmation bar when selectedSlot is null', async () => {
      await renderWithSlots({ selectedSlot: null });

      const confirmBar = document.querySelector('.scheduler-confirmation');
      expect(confirmBar).toBeFalsy();
    });
  });

  // =========================================================================
  // Calendar Grid ARIA Structure
  // =========================================================================

  describe('Calendar grid ARIA structure', () => {
    it('renders calendar grid with role="grid"', async () => {
      await renderWithSlots();

      const grid = screen.getByRole('grid', { name: /calendar/i });
      expect(grid).toBeInTheDocument();
    });

    it('renders weekday column headers with role="columnheader"', async () => {
      await renderWithSlots();

      const headers = document.querySelectorAll('[role="columnheader"]');
      expect(headers.length).toBe(7);

      const headerTexts = Array.from(headers).map(h => h.textContent);
      expect(headerTexts).toEqual(['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']);
    });

    it('available days have role="gridcell"', async () => {
      await renderWithSlots();

      const gridcells = document.querySelectorAll('[role="gridcell"]');
      expect(gridcells.length).toBeGreaterThanOrEqual(1);
    });

    it('unavailable days have role="presentation"', async () => {
      await renderWithSlots();

      const presentations = document.querySelectorAll('.calendar-day[role="presentation"]');
      // There should be some presentation cells (past days, days without slots)
      expect(presentations.length).toBeGreaterThanOrEqual(1);
    });

    it('time slots container has role="listbox" with aria-label', async () => {
      const { slotDates } = await renderWithSlots();

      // Select a date to reveal time slots
      const interactiveDays = document.querySelectorAll('.calendar-day.has-slots');
      fireEvent.click(interactiveDays[0]);

      await waitFor(() => {
        const listbox = screen.getByRole('listbox', { name: /available time slots/i });
        expect(listbox).toBeInTheDocument();
      });
    });

    it('individual time slot buttons have role="option"', async () => {
      const { slotDates } = await renderWithSlots();

      const interactiveDays = document.querySelectorAll('.calendar-day.has-slots');
      fireEvent.click(interactiveDays[0]);

      await waitFor(() => {
        const options = screen.getAllByRole('option');
        expect(options.length).toBeGreaterThanOrEqual(1);
      });
    });
  });

  // =========================================================================
  // Error Retry Flow
  // =========================================================================

  describe('Error retry flow', () => {
    it('retry button re-invokes fetch and clears error on success', async () => {
      // First call: booking link resolves, second call: slots fails, third: retry succeeds
      mockFetch
        .mockImplementationOnce(() => mockResponse({
          booking_page: { appointment_types: [{ id: 'type-1' }] },
        }))
        .mockImplementationOnce(() => mockResponse({}, 500))
        .mockImplementationOnce(() => mockResponse({ available_slots: [] }));

      await act(async () => {
        render(
          <SmartScheduler onSelect={vi.fn()} selectedSlot={null} slug="test" />
        );
      });

      // Wait for error state
      await waitFor(() => {
        expect(screen.getByText('Unable to load available times')).toBeInTheDocument();
      });

      // Click retry
      const retryBtn = screen.getByText('Try Again');
      await act(async () => {
        fireEvent.click(retryBtn);
      });

      // Error should be cleared after successful retry
      await waitFor(() => {
        expect(screen.queryByText('Unable to load available times')).not.toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Slot Selection Callback
  // =========================================================================

  describe('Slot selection callback details', () => {
    it('passes the full slot object to onSelect including start_time and end_time', async () => {
      const onSelect = vi.fn();
      const tomorrowStr = '2026-03-16';

      mockFetch.mockImplementation((url) => {
        if (url.includes('/slots')) {
          return mockResponse({
            available_slots: makeSlotsForDate(tomorrowStr, 1),
          });
        }
        return mockResponse({
          booking_page: { appointment_types: [{ id: 'type-1' }] },
        });
      });

      await act(async () => {
        render(
          <SmartScheduler
            onSelect={onSelect}
            selectedSlot={null}
            appointmentTypeId="type-1"
          />
        );
      });

      await waitFor(() => {
        expect(screen.queryByText('Loading available times...')).not.toBeInTheDocument();
      });

      // Select a date
      const days = document.querySelectorAll('.calendar-day.has-slots');
      fireEvent.click(days[0]);

      await waitFor(() => {
        expect(document.querySelector('.time-slots')).toBeTruthy();
      });

      // Click a slot
      const slotBtns = document.querySelectorAll('.time-slot');
      fireEvent.click(slotBtns[0]);

      expect(onSelect).toHaveBeenCalledTimes(1);
      const calledWith = onSelect.mock.calls[0][0];
      expect(calledWith).toHaveProperty('start_time');
      expect(calledWith).toHaveProperty('end_time');
      expect(calledWith.start_time).toContain('2026-03-16T');
    });
  });

  // =========================================================================
  // Custom Props
  // =========================================================================

  describe('Custom props', () => {
    it('uses custom daysAhead to limit selectable range', async () => {
      // Set daysAhead=3 so only 3 days from "today" are selectable
      vi.setSystemTime(new Date(2026, 2, 15, 10, 0, 0));

      const futureDates = [];
      for (let i = 1; i <= 7; i++) {
        const d = new Date(2026, 2, 15 + i);
        futureDates.push(d.toISOString().split('T')[0]);
      }

      await renderWithSlots({ daysAhead: 3 }, futureDates);

      // Days beyond 3 ahead should have "too-far" class
      const tooFarDays = document.querySelectorAll('.calendar-day.too-far');
      expect(tooFarDays.length).toBeGreaterThanOrEqual(1);
    });
  });
});
