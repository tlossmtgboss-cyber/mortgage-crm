import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockSchedulerAPI = {
  getAppointments: vi.fn(),
};
const mockTasksAPI = {
  getAll: vi.fn(),
};
const mockLeadsAPI = {
  getAll: vi.fn(),
};
const mockLoansAPI = {
  getAll: vi.fn(),
};

vi.mock('../../../services/api', () => ({
  schedulerAPI: {
    getAppointments: (...args) => mockSchedulerAPI.getAppointments(...args),
  },
  tasksAPI: {
    getAll: (...args) => mockTasksAPI.getAll(...args),
  },
  leadsAPI: {
    getAll: (...args) => mockLeadsAPI.getAll(...args),
  },
  loansAPI: {
    getAll: (...args) => mockLoansAPI.getAll(...args),
  },
}));

vi.mock('../CommandCenterHeader.css', () => ({}));

import CommandCenterHeader from '../CommandCenterHeader';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderHeader(props = {}) {
  return render(
    <MemoryRouter>
      <CommandCenterHeader {...props} />
    </MemoryRouter>
  );
}

function resolveAllAPIs() {
  mockSchedulerAPI.getAppointments.mockResolvedValue([]);
  mockTasksAPI.getAll.mockResolvedValue([]);
  mockLeadsAPI.getAll.mockResolvedValue([]);
  mockLoansAPI.getAll.mockResolvedValue([]);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CommandCenterHeader', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // =========================================================================
  // Greeting
  // =========================================================================

  describe('Greeting based on time of day', () => {
    it('renders "Good morning" before noon', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 9, 0, 0)); // 9 AM
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByText(/Good morning/)).toBeInTheDocument();
    });

    it('renders "Good afternoon" between noon and 5 PM', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 14, 0, 0)); // 2 PM
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByText(/Good afternoon/)).toBeInTheDocument();
    });

    it('renders "Good evening" at or after 5 PM', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 19, 0, 0)); // 7 PM
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByText(/Good evening/)).toBeInTheDocument();
    });

    it('renders "Good morning" at midnight (hour 0)', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 0, 0, 0));
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByText(/Good morning/)).toBeInTheDocument();
    });

    it('renders "Good afternoon" at exactly noon', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 12, 0, 0));
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByText(/Good afternoon/)).toBeInTheDocument();
    });

    it('renders "Good evening" at exactly 5 PM', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 17, 0, 0));
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByText(/Good evening/)).toBeInTheDocument();
    });
  });

  // =========================================================================
  // User Name
  // =========================================================================

  describe('User name from localStorage', () => {
    it('renders user first_name from localStorage', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 9, 0, 0));
      localStorage.setItem('user', JSON.stringify({ first_name: 'Timothy' }));
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByText(/Timothy/)).toBeInTheDocument();
    });

    it('falls back to name field if first_name is missing', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 9, 0, 0));
      localStorage.setItem('user', JSON.stringify({ name: 'Tim Loss' }));
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByText(/Tim Loss/)).toBeInTheDocument();
    });

    it('renders greeting without name when localStorage is empty', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 9, 0, 0));
      resolveAllAPIs();
      renderHeader();
      const heading = screen.getByRole('heading');
      expect(heading.textContent).toBe('Good morning');
    });

    it('handles invalid JSON in localStorage gracefully', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 9, 0, 0));
      localStorage.setItem('user', 'not-valid-json');
      resolveAllAPIs();
      renderHeader();
      const heading = screen.getByRole('heading');
      expect(heading.textContent).toBe('Good morning');
    });
  });

  // =========================================================================
  // Loading State
  // =========================================================================

  describe('Loading state', () => {
    it('shows dash placeholders for all stats while loading', () => {
      // APIs that never resolve
      mockSchedulerAPI.getAppointments.mockReturnValue(new Promise(() => {}));
      mockTasksAPI.getAll.mockReturnValue(new Promise(() => {}));
      mockLeadsAPI.getAll.mockReturnValue(new Promise(() => {}));
      mockLoansAPI.getAll.mockReturnValue(new Promise(() => {}));

      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      renderHeader();

      // All stat values should show '-' while loading
      const dashes = screen.getAllByText('-');
      expect(dashes.length).toBe(4);
    });
  });

  // =========================================================================
  // Stat values after fetch
  // =========================================================================

  describe('Stat values after fetch', () => {
    it('shows correct appointment count after fetch', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockResolvedValue([
        { id: '1', start_time: '2026-03-14T11:00:00', end_time: '2026-03-14T12:00:00' },
        { id: '2', start_time: '2026-03-14T14:00:00', end_time: '2026-03-14T15:00:00' },
        { id: '3', start_time: '2026-03-14T16:00:00', end_time: '2026-03-14T17:00:00' },
      ]);
      mockTasksAPI.getAll.mockResolvedValue([]);
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockResolvedValue([]);

      renderHeader();

      await waitFor(() => {
        expect(screen.getByText('3')).toBeInTheDocument();
      });
    });

    it('shows correct tasks due count after fetch', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockResolvedValue([]);
      mockTasksAPI.getAll.mockResolvedValue([
        { id: '1', status: 'pending', due_date: '2026-03-14T00:00:00' },
        { id: '2', status: 'pending', due_date: '2026-03-14T00:00:00' },
        { id: '3', status: 'completed', due_date: '2026-03-14T00:00:00' },
      ]);
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockResolvedValue([]);

      renderHeader();

      await waitFor(() => {
        expect(screen.getByText('2')).toBeInTheDocument();
      });
    });

    it('shows overdue count as sublabel for tasks', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockResolvedValue([]);
      mockTasksAPI.getAll.mockResolvedValue([
        { id: '1', status: 'pending', due_date: '2026-03-12T00:00:00' }, // 2 days overdue
        { id: '2', status: 'pending', due_date: '2026-03-13T00:00:00' }, // 1 day overdue
        { id: '3', status: 'pending', due_date: '2026-03-14T00:00:00' }, // due today
      ]);
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockResolvedValue([]);

      renderHeader();

      await waitFor(() => {
        expect(screen.getByText('2 overdue')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // StatCard rendering
  // =========================================================================

  describe('StatCard rendering', () => {
    it('renders stat cards with correct color variants', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      resolveAllAPIs();

      const { container } = renderHeader();

      await waitFor(() => {
        const statCards = container.querySelectorAll('.cc-stat-card');
        expect(statCards.length).toBe(4);
        // First card (appointments) should have primary color
        expect(statCards[0].classList.contains('cc-stat-card--primary')).toBe(true);
      });
    });

    it('stat card with "to" prop renders as a Link', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      resolveAllAPIs();

      const { container } = renderHeader();

      await waitFor(() => {
        // Tasks Due card links to /tasks
        const links = container.querySelectorAll('a.cc-stat-link');
        expect(links.length).toBeGreaterThanOrEqual(1);
        const taskLink = Array.from(links).find(l => l.getAttribute('href') === '/tasks');
        expect(taskLink).toBeTruthy();
      });
    });

    it('stat card without "to" prop does not render as a Link', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      resolveAllAPIs();

      const { container } = renderHeader();

      await waitFor(() => {
        // The appointments stat card does not have a `to` prop, so it should not be a link
        const primaryCards = container.querySelectorAll('.cc-stat-card--primary');
        expect(primaryCards.length).toBe(1);
        // Its parent should NOT be an anchor
        expect(primaryCards[0].parentElement.tagName).not.toBe('A');
      });
    });
  });

  // =========================================================================
  // Next appointment sublabel
  // =========================================================================

  describe('Next appointment sublabel', () => {
    it('shows "Next at" sublabel when there is an upcoming appointment', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockResolvedValue([
        { id: '1', start_time: '2026-03-14T08:00:00', end_time: '2026-03-14T09:00:00' }, // past
        { id: '2', start_time: '2026-03-14T14:00:00', end_time: '2026-03-14T15:00:00' }, // upcoming
      ]);
      mockTasksAPI.getAll.mockResolvedValue([]);
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockResolvedValue([]);

      renderHeader();

      await waitFor(() => {
        expect(screen.getByText(/Next at/)).toBeInTheDocument();
      });
    });

    it('does not show "Next at" when all appointments are in the past', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 18, 0, 0)); // 6 PM
      mockSchedulerAPI.getAppointments.mockResolvedValue([
        { id: '1', start_time: '2026-03-14T08:00:00', end_time: '2026-03-14T09:00:00' },
        { id: '2', start_time: '2026-03-14T14:00:00', end_time: '2026-03-14T15:00:00' },
      ]);
      mockTasksAPI.getAll.mockResolvedValue([]);
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockResolvedValue([]);

      renderHeader();

      await waitFor(() => {
        // Should show the count but no "Next at"
        expect(screen.getByText('2')).toBeInTheDocument();
      });
      expect(screen.queryByText(/Next at/)).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // API error handling
  // =========================================================================

  describe('API error handling', () => {
    it('shows 0 for appointments when API fails', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockRejectedValue(new Error('Network error'));
      mockTasksAPI.getAll.mockResolvedValue([]);
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockResolvedValue([]);

      renderHeader();

      await waitFor(() => {
        // Should not have any dashes left (all loaded)
        expect(screen.queryAllByText('-').length).toBeLessThan(4);
      });

      // The appointments value should be 0
      const statValues = screen.getAllByText('0');
      expect(statValues.length).toBeGreaterThanOrEqual(1);
    });

    it('shows 0 for tasks when API fails', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockResolvedValue([]);
      mockTasksAPI.getAll.mockRejectedValue(new Error('Network error'));
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockResolvedValue([]);

      renderHeader();

      await waitFor(() => {
        // Tasks due value should be 0
        expect(screen.queryAllByText('-').length).toBeLessThan(4);
      });
    });

    it('shows 0 for SLA alerts when loans API fails', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockResolvedValue([]);
      mockTasksAPI.getAll.mockResolvedValue([]);
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockRejectedValue(new Error('Network error'));

      renderHeader();

      await waitFor(() => {
        expect(screen.queryAllByText('-').length).toBeLessThan(4);
      });
    });

    it('shows 0 for leads when API fails', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockResolvedValue([]);
      mockTasksAPI.getAll.mockResolvedValue([]);
      mockLeadsAPI.getAll.mockRejectedValue(new Error('Network error'));
      mockLoansAPI.getAll.mockResolvedValue([]);

      renderHeader();

      await waitFor(() => {
        expect(screen.queryAllByText('-').length).toBeLessThan(4);
      });
    });

    it('handles all APIs failing simultaneously', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockRejectedValue(new Error('fail'));
      mockTasksAPI.getAll.mockRejectedValue(new Error('fail'));
      mockLeadsAPI.getAll.mockRejectedValue(new Error('fail'));
      mockLoansAPI.getAll.mockRejectedValue(new Error('fail'));

      renderHeader();

      await waitFor(() => {
        // All stats should show 0 (no dashes remaining)
        expect(screen.queryAllByText('-')).toHaveLength(0);
      });
    });
  });

  // =========================================================================
  // onStatsFetched callback
  // =========================================================================

  describe('onStatsFetched callback', () => {
    it('calls onStatsFetched when all stats are loaded', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      resolveAllAPIs();
      const onStatsFetched = vi.fn();

      renderHeader({ onStatsFetched });

      await waitFor(() => {
        expect(onStatsFetched).toHaveBeenCalledTimes(1);
      });

      const calledWith = onStatsFetched.mock.calls[0][0];
      expect(calledWith).toHaveProperty('appointments');
      expect(calledWith).toHaveProperty('tasks');
      expect(calledWith).toHaveProperty('sla');
      expect(calledWith).toHaveProperty('leads');
      expect(calledWith.appointments.loading).toBe(false);
      expect(calledWith.tasks.loading).toBe(false);
      expect(calledWith.sla.loading).toBe(false);
      expect(calledWith.leads.loading).toBe(false);
    });

    it('does not call onStatsFetched while stats are still loading', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockReturnValue(new Promise(() => {}));
      mockTasksAPI.getAll.mockResolvedValue([]);
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockResolvedValue([]);

      const onStatsFetched = vi.fn();
      renderHeader({ onStatsFetched });

      // Should not be called yet since appointments is still loading
      expect(onStatsFetched).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // SLA alerts logic
  // =========================================================================

  describe('SLA alerts computation', () => {
    it('counts SLA alerts for loans near or past their SLA target', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockResolvedValue([]);
      mockTasksAPI.getAll.mockResolvedValue([]);
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockResolvedValue([
        // APPLICATION stage, SLA target = 3 days, changed 5 days ago -> remaining = -2 (alert + critical)
        { id: '1', stage: 'APPLICATION', stage_changed_at: '2026-03-09T10:00:00' },
        // PROCESSING stage, SLA target = 7 days, changed 1 day ago -> remaining = 6 (no alert)
        { id: '2', stage: 'PROCESSING', stage_changed_at: '2026-03-13T10:00:00' },
        // FUNDED (terminal) - should be ignored
        { id: '3', stage: 'FUNDED', stage_changed_at: '2026-03-01T10:00:00' },
        // SUBMITTED stage, SLA target = 2 days, changed 1 day ago -> remaining = 1 (alert, not critical)
        { id: '4', stage: 'SUBMITTED', stage_changed_at: '2026-03-13T10:00:00' },
      ]);

      renderHeader();

      await waitFor(() => {
        // 2 SLA alerts expected
        expect(screen.getByText('2')).toBeInTheDocument();
      });
    });

    it('shows critical count sublabel for overdue loans', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockResolvedValue([]);
      mockTasksAPI.getAll.mockResolvedValue([]);
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockResolvedValue([
        // APPLICATION, SLA=3, changed 10 days ago -> remaining = -7 -> critical
        { id: '1', stage: 'APPLICATION', stage_changed_at: '2026-03-04T10:00:00' },
        // SUBMITTED, SLA=2, changed 5 days ago -> remaining = -3 -> critical
        { id: '2', stage: 'SUBMITTED', stage_changed_at: '2026-03-09T10:00:00' },
      ]);

      renderHeader();

      await waitFor(() => {
        expect(screen.getByText('2 critical')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Leads follow-up logic
  // =========================================================================

  describe('Leads follow-up computation', () => {
    it('counts leads with no contact in 3+ days', async () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      mockSchedulerAPI.getAppointments.mockResolvedValue([]);
      mockTasksAPI.getAll.mockResolvedValue([]);
      mockLoansAPI.getAll.mockResolvedValue([]);
      mockLeadsAPI.getAll.mockResolvedValue([
        { id: '1', stage: 'New', last_contact: '2026-03-10T10:00:00' }, // 4 days ago -> needs follow-up
        { id: '2', stage: 'New', last_contact: '2026-03-13T10:00:00' }, // 1 day ago -> fine
        { id: '3', stage: 'New', last_contact: null }, // no contact -> needs follow-up
        { id: '4', stage: 'Funded', last_contact: '2026-03-01T10:00:00' }, // closed stage -> skip
      ]);

      renderHeader();

      await waitFor(() => {
        expect(screen.getByText('2')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Banner structure
  // =========================================================================

  describe('Banner structure', () => {
    it('renders the banner with role="banner"', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByRole('banner')).toBeInTheDocument();
    });

    it('renders the stats strip with role="region"', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByRole('region', { name: /daily overview/i })).toBeInTheDocument();
    });

    it('renders quick action links (Analytics, Team, Settings)', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByText('Analytics')).toBeInTheDocument();
      expect(screen.getByText('Team')).toBeInTheDocument();
      expect(screen.getByText('Settings')).toBeInTheDocument();
    });

    it('renders the formatted date string', () => {
      vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0)); // Saturday, March 14, 2026
      resolveAllAPIs();
      renderHeader();
      expect(screen.getByText(/March/)).toBeInTheDocument();
      expect(screen.getByText(/2026/)).toBeInTheDocument();
    });
  });
});
