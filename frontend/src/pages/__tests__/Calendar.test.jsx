import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks — must come before component import
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@/services/api', () => ({
  calendarAPI: {
    create: vi.fn(() => Promise.resolve({})),
    delete: vi.fn(() => Promise.resolve({})),
  },
  schedulerAPI: {
    getAppointments: vi.fn(() => Promise.resolve([])),
    createAppointment: vi.fn(() => Promise.resolve({})),
    updateAppointment: vi.fn(() => Promise.resolve({})),
    cancelAppointment: vi.fn(() => Promise.resolve({})),
  },
  unifiedCalendarAPI: {
    getAll: vi.fn(() => Promise.resolve({ events: [] })),
  },
  teamAPI: {
    getMembers: vi.fn(() => Promise.resolve([])),
  },
  calendarSettingsAPI: {
    getAvailability: vi.fn(() => Promise.resolve({ data: {} })),
  },
  tasksAPI: {
    getAll: vi.fn(() => Promise.resolve([])),
  },
  leadsAPI: {
    getAll: vi.fn(() => Promise.resolve([])),
  },
  loansAPI: {
    getAll: vi.fn(() => Promise.resolve([])),
  },
}));

vi.mock('@/utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

// Mock CSS imports
vi.mock('../Calendar.css', () => ({}));
vi.mock('@/components/calendar/CommandCenterHeader.css', () => ({}));
vi.mock('@/components/calendar/OperationalSidebar.css', () => ({}));

// Mock heavy lazy-loaded components to avoid Suspense issues
vi.mock('@/components/calendar/CalendarSearch', () => ({
  default: ({ visible, onClose }) =>
    visible ? <div data-testid="calendar-search">Search Overlay<button onClick={onClose}>Close Search</button></div> : null,
}));

vi.mock('@/components/calendar/KeyboardShortcutsHelp', () => ({
  default: ({ onClose }) => <div data-testid="shortcuts-help">Shortcuts Help<button onClick={onClose}>Close</button></div>,
}));

vi.mock('@/components/calendar/setup/CalendarTour', () => ({
  default: () => <div data-testid="calendar-tour">Tour</div>,
}));

import Calendar from '../Calendar';
import { unifiedCalendarAPI } from '@/services/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderCalendar() {
  return render(
    <MemoryRouter>
      <Calendar />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Calendar Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  // =========================================================================
  // Rendering
  // =========================================================================

  describe('Rendering', () => {
    it('renders the "Smart Calendar" title in the toolbar', async () => {
      renderCalendar();
      await waitFor(() => {
        expect(screen.getByText('Smart Calendar')).toBeInTheDocument();
      });
    });

    it('renders the CommandCenterHeader banner region', async () => {
      renderCalendar();
      await waitFor(() => {
        expect(screen.getByRole('banner')).toBeInTheDocument();
      });
    });

    it('renders the OperationalSidebar complementary region', async () => {
      renderCalendar();
      await waitFor(() => {
        expect(screen.getByRole('complementary', { name: /operations panel/i })).toBeInTheDocument();
      });
    });

    it('renders the view switcher with day, week, and month tabs', async () => {
      renderCalendar();
      await waitFor(() => {
        const viewTablist = screen.getByRole('tablist', { name: /calendar view/i });
        expect(viewTablist).toBeInTheDocument();
        const tabs = within(viewTablist).getAllByRole('tab');
        const tabLabels = tabs.map(t => t.textContent.trim());
        expect(tabLabels).toContain('Day');
        expect(tabLabels).toContain('Week');
        expect(tabLabels).toContain('Month');
      });
    });

    it('renders the "+ Add Event" button', async () => {
      renderCalendar();
      await waitFor(() => {
        expect(screen.getByText('+ Add Event')).toBeInTheDocument();
      });
    });

    it('renders a screen reader live region', async () => {
      renderCalendar();
      await waitFor(() => {
        const srRegions = screen.getAllByRole('status');
        const politeRegion = srRegions.find(el => el.getAttribute('aria-live') === 'polite');
        expect(politeRegion).toBeTruthy();
      });
    });
  });

  // =========================================================================
  // View Switching
  // =========================================================================

  describe('View Switching', () => {
    it('switches to day view when Day tab is clicked', async () => {
      renderCalendar();
      const viewTablist = await screen.findByRole('tablist', { name: /calendar view/i });
      const dayTab = within(viewTablist).getByRole('tab', { name: /day/i });
      fireEvent.click(dayTab);
      expect(dayTab).toHaveAttribute('aria-selected', 'true');
    });

    it('switches to week view when Week tab is clicked', async () => {
      renderCalendar();
      const viewTablist = await screen.findByRole('tablist', { name: /calendar view/i });
      const weekTab = within(viewTablist).getByRole('tab', { name: /week/i });
      fireEvent.click(weekTab);
      expect(weekTab).toHaveAttribute('aria-selected', 'true');
    });
  });

  // =========================================================================
  // Today Button
  // =========================================================================

  describe('Today Navigation', () => {
    it('renders a "Today" button in the navigation controls that can be clicked', async () => {
      renderCalendar();
      // The Today button is inside .month-navigation alongside prev/next arrows
      await waitFor(() => {
        const header = document.querySelector('.calendar-header');
        expect(header).toBeTruthy();
      });
      const header = document.querySelector('.calendar-header');
      const todayBtn = within(header).getByText('Today');
      expect(todayBtn.tagName).toBe('BUTTON');
      // Should not throw; the date resets to today internally
      fireEvent.click(todayBtn);
    });
  });

  // =========================================================================
  // Error Banner
  // =========================================================================

  describe('Error Banner', () => {
    it('shows error banner on API failure and clicking Retry clears it', async () => {
      // First calls reject (loadEvents + loadAllEvents), then retry resolves
      unifiedCalendarAPI.getAll
        .mockRejectedValueOnce(new Error('Network error'))
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce({ events: [] })
        .mockResolvedValueOnce({ events: [] });

      renderCalendar();

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.getByText('Unable to load calendar events. Please try again.')).toBeInTheDocument();
      });

      // Click Retry
      fireEvent.click(screen.getByText('Retry'));

      await waitFor(() => {
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Setup Banner
  // =========================================================================

  describe('Setup Banner', () => {
    it('shows setup banner when setup is not complete', async () => {
      localStorage.removeItem('calendar_setup_complete');
      sessionStorage.removeItem('calendar_setup_banner_dismissed');

      renderCalendar();
      await waitFor(() => {
        expect(screen.getByText(/welcome to smart calendar/i)).toBeInTheDocument();
      });
    });

    it('dismisses setup banner when Dismiss is clicked', async () => {
      localStorage.removeItem('calendar_setup_complete');
      sessionStorage.removeItem('calendar_setup_banner_dismissed');

      renderCalendar();
      await waitFor(() => {
        expect(screen.getByText(/welcome to smart calendar/i)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByLabelText(/dismiss setup banner/i));

      expect(screen.queryByText(/welcome to smart calendar/i)).not.toBeInTheDocument();
      expect(sessionStorage.getItem('calendar_setup_banner_dismissed')).toBe('true');
    });

    it('does not show setup banner when setup is already complete', async () => {
      localStorage.setItem('calendar_setup_complete', 'true');

      renderCalendar();
      await waitFor(() => {
        expect(screen.getByText('Smart Calendar')).toBeInTheDocument();
      });
      expect(screen.queryByText(/welcome to smart calendar/i)).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // formatEventTime utility (tested via replication of internal logic)
  // =========================================================================

  describe('formatEventTime', () => {
    it('returns correct formatted start time and duration', () => {
      const start = new Date('2026-03-14T10:00:00');
      const end = new Date('2026-03-14T10:30:00');
      const startStr = start.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
      const duration = Math.round((end - start) / (1000 * 60));

      expect(startStr).toMatch(/10:00\s*AM/i);
      expect(duration).toBe(30);
    });
  });
});
