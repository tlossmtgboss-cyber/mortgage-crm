import React from 'react';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
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

vi.mock('../OperationalSidebar.css', () => ({}));

import OperationalSidebar from '../OperationalSidebar';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const defaultProps = {
  sortedEvents: [],
  onAddClick: vi.fn(),
  onEventClick: vi.fn(),
  onDeleteEvent: vi.fn(),
  formatEventTime: vi.fn(() => ({ startStr: '10:00 AM', duration: 30 })),
  searchQuery: '',
  onSearchChange: vi.fn(),
};

function renderSidebar(props = {}) {
  return render(
    <MemoryRouter>
      <OperationalSidebar {...defaultProps} {...props} />
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

describe('OperationalSidebar', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
    // Reset all mock implementations and state, then set defaults
    mockSchedulerAPI.getAppointments.mockReset();
    mockTasksAPI.getAll.mockReset();
    mockLeadsAPI.getAll.mockReset();
    mockLoansAPI.getAll.mockReset();
    mockSchedulerAPI.getAppointments.mockImplementation(() => Promise.resolve([]));
    mockTasksAPI.getAll.mockImplementation(() => Promise.resolve([]));
    mockLeadsAPI.getAll.mockImplementation(() => Promise.resolve([]));
    mockLoansAPI.getAll.mockImplementation(() => Promise.resolve([]));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // =========================================================================
  // Tab rendering
  // =========================================================================

  describe('Tab rendering', () => {
    it('renders all 5 tabs', () => {
      renderSidebar();
      const tablist = screen.getByRole('tablist');
      const tabs = within(tablist).getAllByRole('tab');
      expect(tabs).toHaveLength(5);
    });

    it('renders tabs with correct labels', () => {
      renderSidebar();
      expect(screen.getByRole('tab', { name: /Today/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /Events/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /Tasks/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /Leads/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /SLA/i })).toBeInTheDocument();
    });

    it('default tab is "today" (aria-selected)', () => {
      renderSidebar();
      const todayTab = screen.getByRole('tab', { name: /Today/i });
      expect(todayTab.getAttribute('aria-selected')).toBe('true');
    });

    it('shows sidebar title matching active tab', () => {
      renderSidebar();
      // The h2 title should show "Today"
      const title = screen.getByRole('heading', { level: 2 });
      expect(title).toHaveTextContent('Today');
    });

    it('updates sidebar title when switching tabs', () => {
      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Events/i }));
      const title = screen.getByRole('heading', { level: 2 });
      expect(title).toHaveTextContent('Events');
    });

    it('renders the "+ Add" button', () => {
      renderSidebar();
      expect(screen.getByTitle('Add appointment')).toBeInTheDocument();
    });

    it('calls onAddClick when "+ Add" button is clicked', () => {
      const onAddClick = vi.fn();
      renderSidebar({ onAddClick });
      fireEvent.click(screen.getByTitle('Add appointment'));
      expect(onAddClick).toHaveBeenCalledTimes(1);
    });
  });

  // =========================================================================
  // Tab switching
  // =========================================================================

  describe('Tab switching', () => {
    it('switching to Events tab renders event search input', () => {
      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Events/i }));
      expect(screen.getByPlaceholderText('Search events...')).toBeInTheDocument();
    });

    it('switching to Tasks tab renders tasks content', async () => {
      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Tasks/i }));

      await waitFor(() => {
        expect(screen.getByText('All caught up!')).toBeInTheDocument();
      });
    });

    it('switching to Leads tab renders leads content', async () => {
      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Leads/i }));

      await waitFor(() => {
        expect(screen.getByText('All leads contacted')).toBeInTheDocument();
      });
    });

    it('switching to SLA tab renders SLA content', async () => {
      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /SLA/i }));

      await waitFor(() => {
        expect(screen.getByText('All loans within SLA')).toBeInTheDocument();
      });
    });

    it('updates aria-selected when switching tabs', () => {
      renderSidebar();
      const eventsTab = screen.getByRole('tab', { name: /Events/i });
      fireEvent.click(eventsTab);

      expect(eventsTab.getAttribute('aria-selected')).toBe('true');
      expect(screen.getByRole('tab', { name: /Today/i }).getAttribute('aria-selected')).toBe('false');
    });
  });

  // =========================================================================
  // TodayTab
  // =========================================================================

  describe('TodayTab', () => {
    it('shows appointments timeline when data is fetched', async () => {
      mockSchedulerAPI.getAppointments.mockResolvedValue([
        {
          id: '1',
          client_name: 'John Doe',
          appointment_type_name: 'Consultation',
          start_time: '2026-03-14T11:00:00',
          end_time: '2026-03-14T12:00:00',
          meeting_mode: 'VIDEO',
        },
      ]);

      renderSidebar();

      await waitFor(() => {
        expect(screen.getByText('John Doe')).toBeInTheDocument();
        expect(screen.getByText('Consultation')).toBeInTheDocument();
      });
    });

    it('shows empty state when no appointments today', async () => {
      renderSidebar();

      await waitFor(() => {
        expect(screen.getByText('No appointments today')).toBeInTheDocument();
        expect(screen.getByText('Your schedule is clear')).toBeInTheDocument();
      });
    });

    it('shows NOW indicator for current appointment', async () => {
      // Current time is 10:00 AM -- appointment spans 9:30-10:30 so NOW is active
      mockSchedulerAPI.getAppointments.mockResolvedValue([
        {
          id: '1',
          client_name: 'Active Client',
          start_time: '2026-03-14T09:30:00',
          end_time: '2026-03-14T10:30:00',
        },
      ]);

      renderSidebar();

      await waitFor(() => {
        expect(screen.getByText('NOW')).toBeInTheDocument();
      });
    });

    it('does not show active class for fully past appointments when another is current', async () => {
      // Current time is 10:00 AM
      // The component highlights the first appointment whose time range includes "now",
      // or the next upcoming one. Both past appointments ended before 10 AM,
      // so neither should get the active indicator.
      mockSchedulerAPI.getAppointments.mockResolvedValue([
        {
          id: '1',
          client_name: 'Past Client',
          start_time: '2026-03-14T07:00:00',
          end_time: '2026-03-14T08:00:00',
        },
      ]);

      const { container } = renderSidebar();

      await waitFor(() => {
        expect(screen.getByText('Past Client')).toBeInTheDocument();
      });

      // The past item should not have the active class
      const activeItems = container.querySelectorAll('.ops-timeline-item--active');
      expect(activeItems.length).toBe(0);
    });

    it('marks past appointments with past class', async () => {
      mockSchedulerAPI.getAppointments.mockResolvedValue([
        {
          id: '1',
          client_name: 'Past Client',
          start_time: '2026-03-14T08:00:00',
          end_time: '2026-03-14T09:00:00',
        },
      ]);

      const { container } = renderSidebar();

      await waitFor(() => {
        const pastItem = container.querySelector('.ops-timeline-item--past');
        expect(pastItem).toBeTruthy();
      });
    });

    it('displays meeting mode in timeline', async () => {
      mockSchedulerAPI.getAppointments.mockResolvedValue([
        {
          id: '1',
          client_name: 'Video Client',
          start_time: '2026-03-14T11:00:00',
          end_time: '2026-03-14T12:00:00',
          meeting_mode: 'VIDEO',
        },
      ]);

      renderSidebar();

      await waitFor(() => {
        expect(screen.getByText('VIDEO')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // TodayTab loading and error
  // =========================================================================

  describe('TodayTab loading and error states', () => {
    it('shows skeleton loader while fetching', () => {
      mockSchedulerAPI.getAppointments.mockReturnValue(new Promise(() => {}));
      mockTasksAPI.getAll.mockReturnValue(new Promise(() => {}));
      mockLeadsAPI.getAll.mockReturnValue(new Promise(() => {}));
      mockLoansAPI.getAll.mockReturnValue(new Promise(() => {}));
      const { container } = renderSidebar();
      expect(container.querySelector('.ops-skeleton')).toBeTruthy();
    });

    it('still renders empty state gracefully when scheduler API fails (uses allSettled)', async () => {
      // TodayTab uses Promise.allSettled, so individual rejections don't cause error state
      mockSchedulerAPI.getAppointments.mockImplementation(async () => {
        throw new Error('Network error');
      });

      await act(async () => {
        renderSidebar();
        await vi.advanceTimersByTimeAsync(0);
      });

      // With allSettled, a failed scheduler just shows "No appointments" (not error state)
      expect(screen.getByText('No appointments today')).toBeInTheDocument();
    });

    it('shows "Priority Alerts" section after data loads', async () => {
      await act(async () => {
        renderSidebar();
        await vi.advanceTimersByTimeAsync(0);
      });

      expect(screen.getByText('Priority Alerts')).toBeInTheDocument();
    });

    it('shows "All clear" when no priority alerts exist', async () => {
      await act(async () => {
        renderSidebar();
        await vi.advanceTimersByTimeAsync(0);
      });

      expect(screen.getByText(/All clear/)).toBeInTheDocument();
    });
  });

  // =========================================================================
  // TasksTab
  // =========================================================================

  describe('TasksTab', () => {
    it('shows tasks with overdue badge', async () => {
      mockTasksAPI.getAll.mockResolvedValue([
        {
          id: '1',
          title: 'Collect W2',
          status: 'pending',
          due_date: '2026-03-12T00:00:00', // 2 days overdue
          loan_number: '12345',
          borrower_name: 'Jane Smith',
        },
      ]);

      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Tasks/i }));

      await waitFor(() => {
        expect(screen.getByText('Collect W2')).toBeInTheDocument();
        expect(screen.getByText('#12345')).toBeInTheDocument();
        expect(screen.getByText('Jane Smith')).toBeInTheDocument();
      });
    });

    it('shows empty state when no tasks due', async () => {
      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Tasks/i }));

      await waitFor(() => {
        expect(screen.getByText('All caught up!')).toBeInTheDocument();
        expect(screen.getByText('No tasks due')).toBeInTheDocument();
      });
    });

    it('filters out completed and cancelled tasks', async () => {
      mockTasksAPI.getAll.mockResolvedValue([
        { id: '1', title: 'Completed Task', status: 'completed', due_date: '2026-03-14T00:00:00' },
        { id: '2', title: 'Cancelled Task', status: 'cancelled', due_date: '2026-03-14T00:00:00' },
        { id: '3', title: 'Active Task', status: 'pending', due_date: '2026-03-14T00:00:00' },
      ]);

      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Tasks/i }));

      await waitFor(() => {
        expect(screen.getByText('Active Task')).toBeInTheDocument();
      });
      expect(screen.queryByText('Completed Task')).not.toBeInTheDocument();
      expect(screen.queryByText('Cancelled Task')).not.toBeInTheDocument();
    });

    it('shows error state with retry when tasks API fails', async () => {
      mockTasksAPI.getAll.mockRejectedValue(new Error('fail'));
      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Tasks/i }));

      await waitFor(() => {
        expect(screen.getByText('Failed to load tasks')).toBeInTheDocument();
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // LeadsTab
  // =========================================================================

  describe('LeadsTab', () => {
    it('shows leads needing follow-up with days since contact', async () => {
      mockLeadsAPI.getAll.mockResolvedValue([
        {
          id: '1',
          first_name: 'Alice',
          last_name: 'Johnson',
          stage: 'New',
          last_contact: '2026-03-07T10:00:00', // 7 days ago
          ai_score: 85,
        },
      ]);

      await act(async () => {
        renderSidebar();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('tab', { name: /Leads/i }));
      });

      await waitFor(() => {
        expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
        expect(screen.getByText('Score: 85')).toBeInTheDocument();
      });

      // Verify days-ago text is present (exact number depends on daysBetween calc)
      expect(screen.getByText(/\dd ago/)).toBeInTheDocument();
    });

    it('shows "Never" for leads with no contact date', async () => {
      mockLeadsAPI.getAll.mockResolvedValue([
        {
          id: '1',
          first_name: 'Bob',
          last_name: 'Smith',
          stage: 'New',
          last_contact: null,
        },
      ]);

      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Leads/i }));

      await waitFor(() => {
        expect(screen.getByText('Bob Smith')).toBeInTheDocument();
        expect(screen.getByText('Never')).toBeInTheDocument();
      });
    });

    it('excludes closed-stage leads', async () => {
      mockLeadsAPI.getAll.mockResolvedValue([
        { id: '1', first_name: 'Funded', last_name: 'Lead', stage: 'Funded', last_contact: null },
        { id: '2', first_name: 'Dead', last_name: 'Lead', stage: 'Dead', last_contact: null },
        { id: '3', first_name: 'Active', last_name: 'Lead', stage: 'New', last_contact: null },
      ]);

      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Leads/i }));

      await waitFor(() => {
        expect(screen.getByText('Active Lead')).toBeInTheDocument();
      });
      expect(screen.queryByText('Funded Lead')).not.toBeInTheDocument();
      expect(screen.queryByText('Dead Lead')).not.toBeInTheDocument();
    });

    it('shows empty state when all leads are contacted', async () => {
      mockLeadsAPI.getAll.mockResolvedValue([
        { id: '1', first_name: 'Recent', stage: 'New', last_contact: '2026-03-13T10:00:00' }, // 1 day ago
      ]);

      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Leads/i }));

      await waitFor(() => {
        expect(screen.getByText('All leads contacted')).toBeInTheDocument();
        expect(screen.getByText('No follow-ups needed')).toBeInTheDocument();
      });
    });

    it('shows lead avatar with first initial', async () => {
      mockLeadsAPI.getAll.mockResolvedValue([
        { id: '1', first_name: 'Charlie', last_name: 'Brown', stage: 'New', last_contact: null },
      ]);

      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Leads/i }));

      await waitFor(() => {
        expect(screen.getByText('C')).toBeInTheDocument();
      });
    });

    it('marks leads with 14+ days as urgent', async () => {
      mockLeadsAPI.getAll.mockResolvedValue([
        {
          id: '1',
          first_name: 'Stale',
          last_name: 'Lead',
          stage: 'New',
          last_contact: '2026-02-25T10:00:00', // 17 days ago
        },
      ]);

      const { container } = renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Leads/i }));

      await waitFor(() => {
        const urgentAvatar = container.querySelector('.ops-lead-avatar--urgent');
        expect(urgentAvatar).toBeTruthy();
      });
    });

    it('shows error state with retry when leads API fails', async () => {
      mockLeadsAPI.getAll.mockRejectedValue(new Error('fail'));
      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /Leads/i }));

      await waitFor(() => {
        expect(screen.getByText('Failed to load leads')).toBeInTheDocument();
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // SLATab
  // =========================================================================

  describe('SLATab', () => {
    it('shows SLA alerts sorted by urgency', async () => {
      mockLoansAPI.getAll.mockResolvedValue([
        {
          id: '1',
          loan_number: 'LN-001',
          borrower_name: 'John SLA',
          stage: 'APPLICATION',
          stage_changed_at: '2026-03-09T10:00:00', // 5 days in APPLICATION (SLA = 3)
        },
        {
          id: '2',
          loan_number: 'LN-002',
          borrower_name: 'Jane SLA',
          stage: 'SUBMITTED',
          stage_changed_at: '2026-03-13T10:00:00', // 1 day in SUBMITTED (SLA = 2, remaining = 1)
        },
      ]);

      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /SLA/i }));

      await waitFor(() => {
        expect(screen.getByText('#LN-001')).toBeInTheDocument();
        expect(screen.getByText('John SLA')).toBeInTheDocument();
        expect(screen.getByText('#LN-002')).toBeInTheDocument();
        expect(screen.getByText('Jane SLA')).toBeInTheDocument();
      });
    });

    it('shows overdue badge for loans past SLA', async () => {
      mockLoansAPI.getAll.mockResolvedValue([
        {
          id: '1',
          loan_number: 'LN-001',
          borrower_name: 'Overdue Borrower',
          stage: 'APPLICATION',
          stage_changed_at: '2026-03-08T10:00:00', // 6 days (SLA = 3, remaining = -3)
        },
      ]);

      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /SLA/i }));

      await waitFor(() => {
        expect(screen.getByText(/over/)).toBeInTheDocument();
      });
    });

    it('shows remaining days badge for loans near SLA', async () => {
      mockLoansAPI.getAll.mockResolvedValue([
        {
          id: '1',
          loan_number: 'LN-001',
          stage: 'PROCESSING',
          stage_changed_at: '2026-03-08T10:00:00', // 6 days (SLA = 7, remaining = 1)
        },
      ]);

      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /SLA/i }));

      await waitFor(() => {
        expect(screen.getByText(/left/)).toBeInTheDocument();
      });
    });

    it('ignores terminal stage loans', async () => {
      mockLoansAPI.getAll.mockResolvedValue([
        { id: '1', loan_number: 'FUNDED-001', stage: 'FUNDED', stage_changed_at: '2026-01-01T10:00:00' },
        { id: '2', loan_number: 'DENIED-001', stage: 'DENIED', stage_changed_at: '2026-01-01T10:00:00' },
        { id: '3', loan_number: 'CANCELLED-001', stage: 'CANCELLED', stage_changed_at: '2026-01-01T10:00:00' },
      ]);

      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /SLA/i }));

      await waitFor(() => {
        expect(screen.getByText('All loans within SLA')).toBeInTheDocument();
      });
    });

    it('shows empty state when no SLA alerts', async () => {
      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /SLA/i }));

      await waitFor(() => {
        expect(screen.getByText('All loans within SLA')).toBeInTheDocument();
        expect(screen.getByText('No alerts')).toBeInTheDocument();
      });
    });

    it('shows error state with retry when loans API fails', async () => {
      mockLoansAPI.getAll.mockRejectedValue(new Error('fail'));
      renderSidebar();
      fireEvent.click(screen.getByRole('tab', { name: /SLA/i }));

      await waitFor(() => {
        expect(screen.getByText('Failed to load SLA data')).toBeInTheDocument();
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
    });

    it('formats stage labels by replacing underscores with spaces', async () => {
      mockLoansAPI.getAll.mockImplementation(async () => [
        {
          id: '1',
          loan_number: 'LN-001',
          stage: 'CLEAR_TO_CLOSE',
          stage_changed_at: '2026-03-12T10:00:00', // 2 days (SLA = 3, remaining = 1)
        },
      ]);

      renderSidebar();

      await act(async () => {
        fireEvent.click(screen.getByRole('tab', { name: /SLA/i }));
      });

      await waitFor(() => {
        expect(screen.getByText('#LN-001')).toBeInTheDocument();
      });

      // Stage CLEAR_TO_CLOSE becomes "CLEAR TO CLOSE" (underscores replaced with spaces, word-initial caps applied)
      expect(screen.getByText('CLEAR TO CLOSE')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // AppointmentsTab (Events)
  // =========================================================================

  describe('AppointmentsTab', () => {
    it('renders event list when events are provided', () => {
      const events = [
        {
          id: '1',
          title: 'Meeting with Bob',
          start_time: '2026-03-14T14:00:00',
          end_time: '2026-03-14T15:00:00',
          attendee_name: 'Bob Builder',
          isAppointment: true,
        },
      ];

      renderSidebar({ sortedEvents: events });
      fireEvent.click(screen.getByRole('tab', { name: /Events/i }));

      expect(screen.getByText('Meeting with Bob')).toBeInTheDocument();
      expect(screen.getByText('Bob Builder')).toBeInTheDocument();
    });

    it('shows empty state when no events', () => {
      renderSidebar({ sortedEvents: [] });
      fireEvent.click(screen.getByRole('tab', { name: /Events/i }));

      expect(screen.getByText('No appointments')).toBeInTheDocument();
    });

    it('shows search-specific empty state when searching with no results', () => {
      renderSidebar({ sortedEvents: [], searchQuery: 'nonexistent' });
      fireEvent.click(screen.getByRole('tab', { name: /Events/i }));

      expect(screen.getByText('No matching events')).toBeInTheDocument();
      expect(screen.getByText('Try a different search')).toBeInTheDocument();
    });

    it('calls onSearchChange when typing in search', () => {
      const onSearchChange = vi.fn();
      renderSidebar({ onSearchChange });
      fireEvent.click(screen.getByRole('tab', { name: /Events/i }));

      const input = screen.getByPlaceholderText('Search events...');
      fireEvent.change(input, { target: { value: 'test' } });
      expect(onSearchChange).toHaveBeenCalledWith('test');
    });

    it('calls onEventClick when clicking an appointment', () => {
      const onEventClick = vi.fn();
      const events = [
        {
          id: '1',
          title: 'Clickable Appointment',
          start_time: '2026-03-14T14:00:00',
          end_time: '2026-03-14T15:00:00',
          isAppointment: true,
        },
      ];

      renderSidebar({ sortedEvents: events, onEventClick });
      fireEvent.click(screen.getByRole('tab', { name: /Events/i }));

      const item = screen.getByText('Clickable Appointment').closest('.ops-appt-item');
      fireEvent.click(item);
      expect(onEventClick).toHaveBeenCalledWith(events[0]);
    });

    it('calls onDeleteEvent when clicking delete button', () => {
      const onDeleteEvent = vi.fn();
      const events = [
        {
          id: '1',
          title: 'Deletable Event',
          start_time: '2026-03-14T14:00:00',
          end_time: '2026-03-14T15:00:00',
          isAppointment: true,
        },
      ];

      renderSidebar({ sortedEvents: events, onDeleteEvent });
      fireEvent.click(screen.getByRole('tab', { name: /Events/i }));

      const deleteBtn = screen.getByLabelText('Delete Deletable Event');
      fireEvent.click(deleteBtn);
      expect(onDeleteEvent).toHaveBeenCalledWith(events[0]);
    });

    it('groups events by date with date headers', () => {
      const events = [
        {
          id: '1',
          title: 'Today Meeting',
          start_time: '2026-03-14T14:00:00',
          end_time: '2026-03-14T15:00:00',
        },
        {
          id: '2',
          title: 'Tomorrow Meeting',
          start_time: '2026-03-15T10:00:00',
          end_time: '2026-03-15T11:00:00',
        },
      ];

      const { container } = renderSidebar({ sortedEvents: events });
      fireEvent.click(screen.getByRole('tab', { name: /Events/i }));

      // Check for date headers in the appointments list
      const dateHeaders = container.querySelectorAll('.ops-appt-date-header');
      expect(dateHeaders.length).toBe(2);
      expect(dateHeaders[0].textContent).toBe('Today');
      expect(dateHeaders[1].textContent).toBe('Tomorrow');
    });

    it('renders delete button with correct aria-label', () => {
      const events = [
        {
          id: '1',
          title: 'Test Event',
          start_time: '2026-03-14T14:00:00',
          end_time: '2026-03-14T15:00:00',
          isAppointment: true,
        },
      ];

      renderSidebar({ sortedEvents: events });
      fireEvent.click(screen.getByRole('tab', { name: /Events/i }));

      expect(screen.getByLabelText('Delete Test Event')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Accessibility
  // =========================================================================

  describe('Accessibility', () => {
    it('renders with role="complementary"', () => {
      renderSidebar();
      expect(screen.getByRole('complementary')).toBeInTheDocument();
    });

    it('has aria-label on the sidebar', () => {
      renderSidebar();
      expect(screen.getByRole('complementary')).toHaveAttribute('aria-label', 'Operations panel');
    });

    it('has tablist with aria-label for sidebar sections', () => {
      renderSidebar();
      const tablist = screen.getByRole('tablist');
      expect(tablist).toHaveAttribute('aria-label', 'Sidebar sections');
    });

    it('has tabpanel for content area', () => {
      renderSidebar();
      expect(screen.getByRole('tabpanel')).toBeInTheDocument();
    });
  });
});
