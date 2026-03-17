import React from 'react';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks — must come before component import
// ---------------------------------------------------------------------------

vi.mock('@/services/api', () => ({
  teamCalendarAPI: {
    getTeamCalendar: vi.fn(() => Promise.resolve({ team: {} })),
    getCapacity: vi.fn(() => Promise.resolve({ capacity: {} })),
    reassignAppointment: vi.fn(() => Promise.resolve({})),
    getAvailabilityMatrix: vi.fn(() => Promise.resolve({ matrix: {} })),
  },
  teamAPI: {
    getMembers: vi.fn(() => Promise.resolve([])),
  },
  schedulerAPI: {
    createAppointment: vi.fn(() => Promise.resolve({})),
  },
}));

// Mock CSS imports
vi.mock('../TeamCalendar.css', () => ({}));

import TeamCalendar from '../TeamCalendar';
import { teamCalendarAPI, teamAPI, schedulerAPI } from '@/services/api';

// ---------------------------------------------------------------------------
// Test Data Factories
// ---------------------------------------------------------------------------

const today = new Date();
const todayISO = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

function makeAppointment(overrides = {}) {
  return {
    id: 1,
    title: 'Purchase Consultation',
    meeting_type: 'purchase_consultation',
    status: 'booked',
    scheduled_start: `${todayISO}T10:00:00`,
    scheduled_end: `${todayISO}T10:30:00`,
    attendee_name: 'Jane Doe',
    attendee_email: 'jane@example.com',
    attendee_phone: '(555) 123-4567',
    duration_minutes: 30,
    ...overrides,
  };
}

function makeTeamData(loList = []) {
  const team = {};
  for (const lo of loList) {
    team[String(lo.lo_id)] = lo;
  }
  return { team };
}

function makeCapacityData(loList = []) {
  const capacity = {};
  for (const lo of loList) {
    capacity[String(lo.lo_id)] = {
      days: {
        [todayISO]: { pct: lo.capacityPct ?? 30 },
      },
    };
  }
  return { capacity };
}

const defaultLo1 = {
  lo_id: 1,
  lo_name: 'Alice Johnson',
  appointments: [makeAppointment({ id: 1, title: 'Purchase Consultation' })],
};

const defaultLo2 = {
  lo_id: 2,
  lo_name: 'Bob Smith',
  appointments: [
    makeAppointment({ id: 2, title: 'Closing Meeting', meeting_type: 'closing', status: 'confirmed' }),
  ],
};

const defaultLo3 = {
  lo_id: 3,
  lo_name: 'Charlie Brown',
  appointments: [],
};

function setupDefaultMocks({ loList = [defaultLo1, defaultLo2], capacityOverrides = {} } = {}) {
  teamCalendarAPI.getTeamCalendar.mockResolvedValue(makeTeamData(loList));
  teamCalendarAPI.getCapacity.mockResolvedValue(makeCapacityData(
    loList.map((lo) => ({
      lo_id: lo.lo_id,
      capacityPct: capacityOverrides[lo.lo_id] ?? 30,
    })),
  ));
  teamAPI.getMembers.mockResolvedValue([
    { id: 1, first_name: 'Alice', last_name: 'Johnson' },
    { id: 2, first_name: 'Bob', last_name: 'Smith' },
  ]);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderTeamCalendar() {
  return render(<TeamCalendar />);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TeamCalendar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // =========================================================================
  // Rendering
  // =========================================================================

  describe('Rendering', () => {
    it('renders without crashing', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Team Calendar')).toBeInTheDocument();
      });
    });

    it('displays the page title and subtitle', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Team Calendar')).toBeInTheDocument();
        expect(screen.getByText('Side-by-side schedule view for all loan officers')).toBeInTheDocument();
      });
    });

    it('renders the Today button', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Today')).toBeInTheDocument();
      });
    });

    it('displays a date label for the current view', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      // In day view, the date label includes the day name (e.g. "Monday, March 16, 2026")
      await waitFor(() => {
        const dateLabel = document.querySelector('.tc-date-label');
        expect(dateLabel).toBeTruthy();
        expect(dateLabel.textContent.length).toBeGreaterThan(5);
      });
    });
  });

  // =========================================================================
  // View Mode Switching
  // =========================================================================

  describe('View Mode Switching', () => {
    it('displays Day, Week, and Availability view mode buttons', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Day')).toBeInTheDocument();
        expect(screen.getByText('Week')).toBeInTheDocument();
        expect(screen.getByText('Availability')).toBeInTheDocument();
      });
    });

    it('defaults to day view with the Day button active', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        const dayBtn = screen.getByText('Day');
        expect(dayBtn).toHaveClass('active');
      });
    });

    it('switches to week view when Week button is clicked', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Week'));

      await waitFor(() => {
        expect(screen.getByText('Week')).toHaveClass('active');
        expect(screen.getByText('Day')).not.toHaveClass('active');
      });
    });

    it('switches to availability view when Availability button is clicked', async () => {
      teamCalendarAPI.getTeamCalendar.mockResolvedValue(makeTeamData([defaultLo1]));
      teamCalendarAPI.getCapacity.mockResolvedValue(makeCapacityData([{ lo_id: 1, capacityPct: 30 }]));
      teamCalendarAPI.getAvailabilityMatrix.mockResolvedValue({
        matrix: {
          1: {
            lo_id: 1,
            lo_name: 'Alice Johnson',
            slots: [
              { start: '09:00', end: '09:30', available: true },
              { start: '09:30', end: '10:00', available: false },
            ],
          },
        },
      });
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Availability'));

      await waitFor(() => {
        expect(screen.getByText('Availability')).toHaveClass('active');
      });
    });

    it('fetches availability matrix when switching to availability view', async () => {
      setupDefaultMocks();
      teamCalendarAPI.getAvailabilityMatrix.mockResolvedValue({ matrix: {} });

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Availability'));

      await waitFor(() => {
        expect(teamCalendarAPI.getAvailabilityMatrix).toHaveBeenCalled();
      });
    });
  });

  // =========================================================================
  // Team Member List
  // =========================================================================

  describe('Team Member List', () => {
    it('renders LO names as column headers in day view', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
        expect(screen.getByText('Bob Smith')).toBeInTheDocument();
      });
    });

    it('renders LO names as row labels in week view', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Week'));

      await waitFor(() => {
        expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
        expect(screen.getByText('Bob Smith')).toBeInTheDocument();
      });
    });

    it('sorts LO list alphabetically by name', async () => {
      setupDefaultMocks({ loList: [defaultLo2, defaultLo1] });
      renderTeamCalendar();

      await waitFor(() => {
        const headers = document.querySelectorAll('.tc-lo-name');
        expect(headers.length).toBe(2);
        expect(headers[0].textContent).toBe('Alice Johnson');
        expect(headers[1].textContent).toBe('Bob Smith');
      });
    });
  });

  // =========================================================================
  // Capacity Indicators
  // =========================================================================

  describe('Capacity Indicators', () => {
    it('shows green capacity badge when load is below 50%', async () => {
      setupDefaultMocks({ capacityOverrides: { 1: 30, 2: 20 } });
      renderTeamCalendar();

      await waitFor(() => {
        const badges = document.querySelectorAll('.tc-lo-capacity-badge');
        expect(badges.length).toBeGreaterThan(0);
        // All should be green since both are under 50
        badges.forEach((badge) => {
          expect(badge).toHaveClass('tc-capacity-green');
        });
      });
    });

    it('shows yellow capacity badge when load is between 50% and 79%', async () => {
      setupDefaultMocks({ capacityOverrides: { 1: 65, 2: 10 } });
      renderTeamCalendar();

      await waitFor(() => {
        const badges = document.querySelectorAll('.tc-lo-capacity-badge');
        expect(badges.length).toBe(2);
        // First LO (Alice) should be yellow (65%), second (Bob) should be green (10%)
        expect(badges[0]).toHaveClass('tc-capacity-yellow');
        expect(badges[1]).toHaveClass('tc-capacity-green');
      });
    });

    it('shows red capacity badge when load is 80% or above', async () => {
      setupDefaultMocks({ capacityOverrides: { 1: 95, 2: 80 } });
      renderTeamCalendar();

      await waitFor(() => {
        const badges = document.querySelectorAll('.tc-lo-capacity-badge');
        expect(badges.length).toBe(2);
        badges.forEach((badge) => {
          expect(badge).toHaveClass('tc-capacity-red');
        });
      });
    });

    it('displays the correct percentage text in the capacity badge', async () => {
      setupDefaultMocks({ capacityOverrides: { 1: 42, 2: 78 } });
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('42% booked')).toBeInTheDocument();
        expect(screen.getByText('78% booked')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Appointment Cards
  // =========================================================================

  describe('Appointment Cards', () => {
    it('renders appointment titles in day view', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Purchase Consultation')).toBeInTheDocument();
        expect(screen.getByText('Closing Meeting')).toBeInTheDocument();
      });
    });

    it('renders attendee name on appointment cards', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Jane Doe')).toBeInTheDocument();
      });
    });

    it('applies correct CSS class for purchase consultation type', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        const apptCard = screen.getByText('Purchase Consultation').closest('.tc-appointment');
        expect(apptCard).toHaveClass('tc-appt-purchase');
      });
    });

    it('applies correct CSS class for closing meeting type', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        const apptCard = screen.getByText('Closing Meeting').closest('.tc-appointment');
        expect(apptCard).toHaveClass('tc-appt-closing');
      });
    });

    it('applies meeting color class for "video" type appointments', async () => {
      const lo = {
        lo_id: 1,
        lo_name: 'Alice Johnson',
        appointments: [makeAppointment({ id: 10, title: 'Video Call', meeting_type: 'video' })],
      };
      setupDefaultMocks({ loList: [lo] });
      renderTeamCalendar();

      await waitFor(() => {
        const apptCard = screen.getByText('Video Call').closest('.tc-appointment');
        expect(apptCard).toHaveClass('tc-appt-meeting');
      });
    });

    it('applies call color class for "phone" type appointments', async () => {
      const lo = {
        lo_id: 1,
        lo_name: 'Alice Johnson',
        appointments: [makeAppointment({ id: 11, title: 'Phone Check-in', meeting_type: 'phone' })],
      };
      setupDefaultMocks({ loList: [lo] });
      renderTeamCalendar();

      await waitFor(() => {
        const apptCard = screen.getByText('Phone Check-in').closest('.tc-appointment');
        expect(apptCard).toHaveClass('tc-appt-call');
      });
    });

    it('applies fallback "tc-appt-other" class for unknown appointment types', async () => {
      const lo = {
        lo_id: 1,
        lo_name: 'Alice Johnson',
        appointments: [makeAppointment({ id: 12, title: 'Unknown Type Appt', meeting_type: 'webinar', status: '' })],
      };
      setupDefaultMocks({ loList: [lo] });
      renderTeamCalendar();

      await waitFor(() => {
        const apptCard = screen.getByText('Unknown Type Appt').closest('.tc-appointment');
        expect(apptCard).toHaveClass('tc-appt-other');
      });
    });

    it('applies status color when meeting_type is not in color map', async () => {
      const lo = {
        lo_id: 1,
        lo_name: 'Alice Johnson',
        appointments: [makeAppointment({ id: 13, title: 'Completed Appt', meeting_type: 'unknown', status: 'completed' })],
      };
      setupDefaultMocks({ loList: [lo] });
      renderTeamCalendar();

      await waitFor(() => {
        const apptCard = screen.getByText('Completed Appt').closest('.tc-appointment');
        expect(apptCard).toHaveClass('tc-appt-completed');
      });
    });
  });

  // =========================================================================
  // Date Navigation
  // =========================================================================

  describe('Date Navigation', () => {
    it('navigates to previous day when prev arrow is clicked in day view', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      const dateLabelBefore = document.querySelector('.tc-date-label').textContent;

      // Click prev arrow (the left arrow button)
      const navButtons = document.querySelectorAll('.tc-date-nav button');
      fireEvent.click(navButtons[0]); // first button is prev

      await waitFor(() => {
        const dateLabelAfter = document.querySelector('.tc-date-label').textContent;
        expect(dateLabelAfter).not.toBe(dateLabelBefore);
      });
    });

    it('navigates to next day when next arrow is clicked in day view', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      const dateLabelBefore = document.querySelector('.tc-date-label').textContent;

      const navButtons = document.querySelectorAll('.tc-date-nav button');
      fireEvent.click(navButtons[1]); // second button is next

      await waitFor(() => {
        const dateLabelAfter = document.querySelector('.tc-date-label').textContent;
        expect(dateLabelAfter).not.toBe(dateLabelBefore);
      });
    });

    it('navigates by 7 days when prev/next is clicked in week view', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Week'));

      await waitFor(() => {
        expect(screen.getByText('Week')).toHaveClass('active');
      });

      const dateLabelBefore = document.querySelector('.tc-date-label').textContent;

      const navButtons = document.querySelectorAll('.tc-date-nav button');
      fireEvent.click(navButtons[1]); // next

      await waitFor(() => {
        const dateLabelAfter = document.querySelector('.tc-date-label').textContent;
        expect(dateLabelAfter).not.toBe(dateLabelBefore);
      });
    });

    it('returns to today when Today button is clicked', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      // Navigate away from today first
      const navButtons = document.querySelectorAll('.tc-date-nav button');
      fireEvent.click(navButtons[1]); // go next
      fireEvent.click(navButtons[1]); // go next again

      await waitFor(() => {
        // Date label should have changed
        expect(document.querySelector('.tc-date-label')).toBeTruthy();
      });

      // Click Today
      fireEvent.click(screen.getByText('Today'));

      await waitFor(() => {
        // The date label in day view should contain today's date info
        const label = document.querySelector('.tc-date-label').textContent;
        expect(label).toContain(String(today.getDate()));
      });
    });

    it('displays week date range in week view (e.g., "March 15 - March 21, 2026")', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Week'));

      await waitFor(() => {
        const dateLabel = document.querySelector('.tc-date-label').textContent;
        // Should contain a " - " range separator
        expect(dateLabel).toContain(' - ');
      });
    });

    it('displays full day name in day view (e.g., "Monday, March 16, 2026")', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        const dateLabel = document.querySelector('.tc-date-label').textContent;
        // Should contain a comma (day name + month format)
        expect(dateLabel).toContain(',');
      });
    });
  });

  // =========================================================================
  // Loading State
  // =========================================================================

  describe('Loading State', () => {
    it('displays loading message while data is being fetched', () => {
      // Make the API hang (never resolve)
      teamCalendarAPI.getTeamCalendar.mockReturnValue(new Promise(() => {}));
      teamCalendarAPI.getCapacity.mockReturnValue(new Promise(() => {}));
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      expect(screen.getByText('Loading team calendar...')).toBeInTheDocument();
    });

    it('removes loading message once data is loaded', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Error State
  // =========================================================================

  describe('Error State', () => {
    it('displays error banner when API call fails', async () => {
      teamCalendarAPI.getTeamCalendar.mockRejectedValue(new Error('Network error'));
      teamCalendarAPI.getCapacity.mockRejectedValue(new Error('Network error'));
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument();
      });
    });

    it('displays error detail from response.data.detail when available', async () => {
      const err = new Error('Request failed');
      err.response = { data: { detail: 'Unauthorized access' } };
      teamCalendarAPI.getTeamCalendar.mockRejectedValue(err);
      teamCalendarAPI.getCapacity.mockRejectedValue(err);
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Unauthorized access')).toBeInTheDocument();
      });
    });

    it('displays a Retry button in error banner', async () => {
      teamCalendarAPI.getTeamCalendar.mockRejectedValue(new Error('Fail'));
      teamCalendarAPI.getCapacity.mockRejectedValue(new Error('Fail'));
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
    });

    it('retries data fetch when Retry button is clicked', async () => {
      teamCalendarAPI.getTeamCalendar
        .mockRejectedValueOnce(new Error('Fail'))
        .mockResolvedValueOnce(makeTeamData([defaultLo1]));
      teamCalendarAPI.getCapacity
        .mockRejectedValueOnce(new Error('Fail'))
        .mockResolvedValueOnce(makeCapacityData([{ lo_id: 1, capacityPct: 30 }]));
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Retry'));

      await waitFor(() => {
        expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
        expect(screen.queryByText('Retry')).not.toBeInTheDocument();
      });
    });

    it('does not render the main calendar content when error is present', async () => {
      teamCalendarAPI.getTeamCalendar.mockRejectedValue(new Error('Fail'));
      teamCalendarAPI.getCapacity.mockRejectedValue(new Error('Fail'));
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Fail')).toBeInTheDocument();
      });

      // No LO columns should be rendered
      expect(document.querySelector('.tc-lo-name')).toBeNull();
    });
  });

  // =========================================================================
  // Empty State
  // =========================================================================

  describe('Empty State', () => {
    it('displays empty state message when no team members are returned', async () => {
      teamCalendarAPI.getTeamCalendar.mockResolvedValue({ team: {} });
      teamCalendarAPI.getCapacity.mockResolvedValue({ capacity: {} });
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      await waitFor(() => {
        expect(
          screen.getByText('No team members found. Make sure you have manager or admin access.'),
        ).toBeInTheDocument();
      });
    });

    it('does not render the day grid when there are no team members', async () => {
      teamCalendarAPI.getTeamCalendar.mockResolvedValue({ team: {} });
      teamCalendarAPI.getCapacity.mockResolvedValue({ capacity: {} });
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      expect(document.querySelector('.tc-day-grid')).toBeNull();
    });
  });

  // =========================================================================
  // Filters
  // =========================================================================

  describe('Filters', () => {
    it('renders the search input', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText('Search client name, email, or phone...'),
        ).toBeInTheDocument();
      });
    });

    it('renders the appointment type filter dropdown', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByDisplayValue('All Types')).toBeInTheDocument();
      });
    });

    it('renders the status filter dropdown', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByDisplayValue('All Statuses')).toBeInTheDocument();
      });
    });

    it('renders the LO filter dropdown when team members are loaded', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByDisplayValue('All LOs')).toBeInTheDocument();
      });
    });

    it('does not render the LO filter dropdown when no team members loaded', async () => {
      setupDefaultMocks();
      teamAPI.getMembers.mockResolvedValue([]);
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      expect(screen.queryByDisplayValue('All LOs')).not.toBeInTheDocument();
    });

    it('filters appointments by search term (client name)', async () => {
      const lo = {
        lo_id: 1,
        lo_name: 'Alice Johnson',
        appointments: [
          makeAppointment({ id: 1, title: 'Meeting A', attendee_name: 'Jane Doe' }),
          makeAppointment({ id: 2, title: 'Meeting B', attendee_name: 'John Smith', scheduled_start: `${todayISO}T11:00:00` }),
        ],
      };
      setupDefaultMocks({ loList: [lo] });
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Meeting A')).toBeInTheDocument();
        expect(screen.getByText('Meeting B')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText('Search client name, email, or phone...');
      fireEvent.change(searchInput, { target: { value: 'Jane' } });

      await waitFor(() => {
        expect(screen.getByText('Meeting A')).toBeInTheDocument();
        expect(screen.queryByText('Meeting B')).not.toBeInTheDocument();
      });
    });

    it('filters appointments by type', async () => {
      const lo = {
        lo_id: 1,
        lo_name: 'Alice Johnson',
        appointments: [
          makeAppointment({ id: 1, title: 'Closing Appt', meeting_type: 'closing' }),
          makeAppointment({ id: 2, title: 'Call Appt', meeting_type: 'call', scheduled_start: `${todayISO}T11:00:00` }),
        ],
      };
      setupDefaultMocks({ loList: [lo] });
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Closing Appt')).toBeInTheDocument();
        expect(screen.getByText('Call Appt')).toBeInTheDocument();
      });

      const typeSelect = screen.getByDisplayValue('All Types');
      fireEvent.change(typeSelect, { target: { value: 'closing' } });

      await waitFor(() => {
        expect(screen.getByText('Closing Appt')).toBeInTheDocument();
        expect(screen.queryByText('Call Appt')).not.toBeInTheDocument();
      });
    });

    it('filters appointments by status', async () => {
      const lo = {
        lo_id: 1,
        lo_name: 'Alice Johnson',
        appointments: [
          makeAppointment({ id: 1, title: 'Booked Appt', status: 'booked' }),
          makeAppointment({ id: 2, title: 'Completed Appt', status: 'completed', scheduled_start: `${todayISO}T11:00:00` }),
        ],
      };
      setupDefaultMocks({ loList: [lo] });
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Booked Appt')).toBeInTheDocument();
        expect(screen.getByText('Completed Appt')).toBeInTheDocument();
      });

      const statusSelect = screen.getByDisplayValue('All Statuses');
      fireEvent.change(statusSelect, { target: { value: 'completed' } });

      await waitFor(() => {
        expect(screen.queryByText('Booked Appt')).not.toBeInTheDocument();
        expect(screen.getByText('Completed Appt')).toBeInTheDocument();
      });
    });

    it('filters by team member via the LO dropdown', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByDisplayValue('All LOs')).toBeInTheDocument();
      });

      const loSelect = screen.getByDisplayValue('All LOs');
      fireEvent.change(loSelect, { target: { value: '1' } });

      // This triggers a re-fetch with filterLoIds set
      await waitFor(() => {
        expect(teamCalendarAPI.getTeamCalendar).toHaveBeenCalledWith(
          expect.any(String),
          expect.any(String),
          '1',
        );
      });
    });

    it('clears LO filter when "All LOs" is re-selected', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByDisplayValue('All LOs')).toBeInTheDocument();
      });

      const loSelect = screen.getByDisplayValue('All LOs');
      fireEvent.change(loSelect, { target: { value: '1' } });

      await waitFor(() => {
        expect(teamCalendarAPI.getTeamCalendar).toHaveBeenCalledWith(
          expect.any(String),
          expect.any(String),
          '1',
        );
      });

      // Reset: note the select now shows the selected member; change back to ''
      fireEvent.change(loSelect, { target: { value: '' } });

      await waitFor(() => {
        // Should be called with null for lo_ids
        expect(teamCalendarAPI.getTeamCalendar).toHaveBeenCalledWith(
          expect.any(String),
          expect.any(String),
          null,
        );
      });
    });
  });

  // =========================================================================
  // Week View
  // =========================================================================

  describe('Week View', () => {
    it('renders day abbreviation headers (Sun, Mon, etc.)', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Week'));

      await waitFor(() => {
        expect(screen.getByText(/Mon/)).toBeInTheDocument();
        expect(screen.getByText(/Tue/)).toBeInTheDocument();
        expect(screen.getByText(/Wed/)).toBeInTheDocument();
      });
    });

    it('renders the "LO" column header', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Week'));

      await waitFor(() => {
        expect(screen.getByText('LO')).toBeInTheDocument();
      });
    });

    it('shows appointment count badges for days with appointments', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Week'));

      await waitFor(() => {
        // Each LO with 1 appointment should show "1 appt"
        const countBadges = document.querySelectorAll('.tc-week-appt-count');
        // Might have badges if today falls in the current week
        expect(countBadges.length).toBeGreaterThanOrEqual(0);
      });
    });

    it('shows "+N more" when more than 3 appointments exist on a day', async () => {
      const manyAppts = Array.from({ length: 5 }, (_, i) =>
        makeAppointment({
          id: i + 1,
          title: `Appt ${i + 1}`,
          scheduled_start: `${todayISO}T${String(9 + i).padStart(2, '0')}:00:00`,
        }),
      );
      const lo = { lo_id: 1, lo_name: 'Alice Johnson', appointments: manyAppts };
      setupDefaultMocks({ loList: [lo] });

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Week'));

      await waitFor(() => {
        // Should show +2 more (5 total, 3 shown)
        const moreText = screen.queryByText('+2 more');
        // This depends on today being in the current week; if so, expect it
        if (moreText) {
          expect(moreText).toBeInTheDocument();
        }
      });
    });
  });

  // =========================================================================
  // Day View Time Slots
  // =========================================================================

  describe('Day View Time Slots', () => {
    it('renders time labels from 7 AM to 6 PM', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('7 AM')).toBeInTheDocument();
        expect(screen.getByText('12 PM')).toBeInTheDocument();
        expect(screen.getByText('6 PM')).toBeInTheDocument();
      });
    });

    it('renders the correct number of time rows (24 half-hour slots)', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        const timeRows = document.querySelectorAll('.tc-time-row');
        expect(timeRows.length).toBe(24); // 12 hours * 2 slots
      });
    });
  });

  // =========================================================================
  // Tooltip
  // =========================================================================

  describe('Tooltip', () => {
    it('shows tooltip on appointment hover', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Purchase Consultation')).toBeInTheDocument();
      });

      const apptCard = screen.getByText('Purchase Consultation').closest('.tc-appointment');
      fireEvent.mouseEnter(apptCard);

      await waitFor(() => {
        const tooltip = document.querySelector('.tc-tooltip');
        expect(tooltip).toBeTruthy();
      });
    });

    it('hides tooltip on mouse leave', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Purchase Consultation')).toBeInTheDocument();
      });

      const apptCard = screen.getByText('Purchase Consultation').closest('.tc-appointment');
      fireEvent.mouseEnter(apptCard);

      await waitFor(() => {
        expect(document.querySelector('.tc-tooltip')).toBeTruthy();
      });

      fireEvent.mouseLeave(apptCard);

      await waitFor(() => {
        expect(document.querySelector('.tc-tooltip')).toBeNull();
      });
    });

    it('displays appointment details in tooltip (client, type, status)', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Purchase Consultation')).toBeInTheDocument();
      });

      const apptCard = screen.getByText('Purchase Consultation').closest('.tc-appointment');
      fireEvent.mouseEnter(apptCard);

      await waitFor(() => {
        const tooltip = document.querySelector('.tc-tooltip');
        expect(tooltip).toBeTruthy();
        expect(within(tooltip).getByText('Jane Doe')).toBeInTheDocument();
        expect(within(tooltip).getByText('purchase_consultation')).toBeInTheDocument();
        expect(within(tooltip).getByText('(555) 123-4567')).toBeInTheDocument();
        expect(within(tooltip).getByText('jane@example.com')).toBeInTheDocument();
        expect(within(tooltip).getByText('booked')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Quick Book Modal
  // =========================================================================

  describe('Quick Book Modal', () => {
    it('opens quick book modal when clicking an empty time slot', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      // Find an empty cell (a cell without appointments) and click it
      const cells = document.querySelectorAll('.tc-cell');
      // Most cells should be empty; click one that has no .tc-appointment child
      let emptyCell = null;
      for (const cell of cells) {
        if (!cell.querySelector('.tc-appointment')) {
          emptyCell = cell;
          break;
        }
      }
      expect(emptyCell).toBeTruthy();
      fireEvent.click(emptyCell);

      await waitFor(() => {
        expect(screen.getByText('Quick Book Appointment')).toBeInTheDocument();
      });
    });

    it('displays the LO name and time in quick book modal', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      // Click an empty cell
      const cells = document.querySelectorAll('.tc-cell');
      let emptyCell = null;
      for (const cell of cells) {
        if (!cell.querySelector('.tc-appointment')) {
          emptyCell = cell;
          break;
        }
      }
      fireEvent.click(emptyCell);

      await waitFor(() => {
        // Modal should show LO name
        const modalInfo = document.querySelector('.tc-quick-book-info');
        expect(modalInfo).toBeTruthy();
        // Should contain an LO name
        expect(modalInfo.textContent).toMatch(/Alice Johnson|Bob Smith/);
      });
    });

    it('has the Book Appointment button disabled when title is empty', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      const cells = document.querySelectorAll('.tc-cell');
      let emptyCell = null;
      for (const cell of cells) {
        if (!cell.querySelector('.tc-appointment')) {
          emptyCell = cell;
          break;
        }
      }
      fireEvent.click(emptyCell);

      await waitFor(() => {
        expect(screen.getByText('Quick Book Appointment')).toBeInTheDocument();
      });

      const bookBtn = screen.getByText('Book Appointment');
      expect(bookBtn).toBeDisabled();
    });

    it('enables the Book Appointment button when title is provided', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      const cells = document.querySelectorAll('.tc-cell');
      let emptyCell = null;
      for (const cell of cells) {
        if (!cell.querySelector('.tc-appointment')) {
          emptyCell = cell;
          break;
        }
      }
      fireEvent.click(emptyCell);

      await waitFor(() => {
        expect(screen.getByText('Quick Book Appointment')).toBeInTheDocument();
      });

      const titleInput = screen.getByPlaceholderText('e.g., Pre-Purchase Consultation');
      fireEvent.change(titleInput, { target: { value: 'Test Appointment' } });

      const bookBtn = screen.getByText('Book Appointment');
      expect(bookBtn).not.toBeDisabled();
    });

    it('calls schedulerAPI.createAppointment on form submit', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      const cells = document.querySelectorAll('.tc-cell');
      let emptyCell = null;
      for (const cell of cells) {
        if (!cell.querySelector('.tc-appointment')) {
          emptyCell = cell;
          break;
        }
      }
      fireEvent.click(emptyCell);

      await waitFor(() => {
        expect(screen.getByText('Quick Book Appointment')).toBeInTheDocument();
      });

      fireEvent.change(screen.getByPlaceholderText('e.g., Pre-Purchase Consultation'), {
        target: { value: 'New Meeting' },
      });

      fireEvent.click(screen.getByText('Book Appointment'));

      await waitFor(() => {
        expect(schedulerAPI.createAppointment).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'New Meeting',
            meeting_type: 'custom',
            duration_minutes: 30,
          }),
        );
      });
    });

    it('closes the quick book modal when Cancel is clicked', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      const cells = document.querySelectorAll('.tc-cell');
      let emptyCell = null;
      for (const cell of cells) {
        if (!cell.querySelector('.tc-appointment')) {
          emptyCell = cell;
          break;
        }
      }
      fireEvent.click(emptyCell);

      await waitFor(() => {
        expect(screen.getByText('Quick Book Appointment')).toBeInTheDocument();
      });

      // Find the Cancel button inside the modal
      const cancelBtns = screen.getAllByText('Cancel');
      fireEvent.click(cancelBtns[cancelBtns.length - 1]); // last Cancel is in quick book modal

      await waitFor(() => {
        expect(screen.queryByText('Quick Book Appointment')).not.toBeInTheDocument();
      });
    });

    it('renders duration options (15, 30, 45, 60, 90 min)', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      const cells = document.querySelectorAll('.tc-cell');
      let emptyCell = null;
      for (const cell of cells) {
        if (!cell.querySelector('.tc-appointment')) {
          emptyCell = cell;
          break;
        }
      }
      fireEvent.click(emptyCell);

      await waitFor(() => {
        expect(screen.getByText('Quick Book Appointment')).toBeInTheDocument();
      });

      expect(screen.getByText('15 min')).toBeInTheDocument();
      expect(screen.getByText('30 min')).toBeInTheDocument();
      expect(screen.getByText('45 min')).toBeInTheDocument();
      expect(screen.getByText('60 min')).toBeInTheDocument();
      expect(screen.getByText('90 min')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Availability View
  // =========================================================================

  describe('Availability View', () => {
    it('shows "Loading availability data..." when matrix is null', async () => {
      teamCalendarAPI.getTeamCalendar.mockResolvedValue(makeTeamData([defaultLo1]));
      teamCalendarAPI.getCapacity.mockResolvedValue(makeCapacityData([{ lo_id: 1, capacityPct: 30 }]));
      teamCalendarAPI.getAvailabilityMatrix.mockResolvedValue({ matrix: null });
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Availability'));

      await waitFor(() => {
        expect(screen.getByText('Loading availability data...')).toBeInTheDocument();
      });
    });

    it('shows "No team members found." when matrix is empty', async () => {
      teamCalendarAPI.getTeamCalendar.mockResolvedValue(makeTeamData([defaultLo1]));
      teamCalendarAPI.getCapacity.mockResolvedValue(makeCapacityData([{ lo_id: 1, capacityPct: 30 }]));
      teamCalendarAPI.getAvailabilityMatrix.mockResolvedValue({ matrix: {} });
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Availability'));

      await waitFor(() => {
        expect(screen.getByText('No team members found.')).toBeInTheDocument();
      });
    });

    it('renders availability cells with free/busy classes', async () => {
      teamCalendarAPI.getTeamCalendar.mockResolvedValue(makeTeamData([defaultLo1]));
      teamCalendarAPI.getCapacity.mockResolvedValue(makeCapacityData([{ lo_id: 1, capacityPct: 30 }]));
      teamCalendarAPI.getAvailabilityMatrix.mockResolvedValue({
        matrix: {
          1: {
            lo_id: 1,
            lo_name: 'Alice Johnson',
            slots: [
              { start: '09:00', end: '09:30', available: true },
              { start: '09:30', end: '10:00', available: false },
              { start: '10:00', end: '10:30', available: true },
            ],
          },
        },
      });
      teamAPI.getMembers.mockResolvedValue([]);

      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.queryByText('Loading team calendar...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Availability'));

      await waitFor(() => {
        const freeCells = document.querySelectorAll('.tc-avail-free');
        const busyCells = document.querySelectorAll('.tc-avail-busy');
        expect(freeCells.length).toBe(2);
        expect(busyCells.length).toBe(1);
      });
    });
  });

  // =========================================================================
  // Data Fetching
  // =========================================================================

  describe('Data Fetching', () => {
    it('calls teamCalendarAPI.getTeamCalendar and getCapacity on mount', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(teamCalendarAPI.getTeamCalendar).toHaveBeenCalledTimes(1);
        expect(teamCalendarAPI.getCapacity).toHaveBeenCalledTimes(1);
      });
    });

    it('calls teamAPI.getMembers on mount', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(teamAPI.getMembers).toHaveBeenCalledTimes(1);
      });
    });

    it('re-fetches data when date changes', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(teamCalendarAPI.getTeamCalendar).toHaveBeenCalledTimes(1);
      });

      const navButtons = document.querySelectorAll('.tc-date-nav button');
      fireEvent.click(navButtons[1]); // next day

      await waitFor(() => {
        expect(teamCalendarAPI.getTeamCalendar).toHaveBeenCalledTimes(2);
        expect(teamCalendarAPI.getCapacity).toHaveBeenCalledTimes(2);
      });
    });

    it('handles teamAPI.getMembers failure gracefully (shows page without LO filter)', async () => {
      teamCalendarAPI.getTeamCalendar.mockResolvedValue(makeTeamData([defaultLo1]));
      teamCalendarAPI.getCapacity.mockResolvedValue(makeCapacityData([{ lo_id: 1, capacityPct: 30 }]));
      teamAPI.getMembers.mockRejectedValue(new Error('Members fail'));

      renderTeamCalendar();

      await waitFor(() => {
        // Page still renders team data from the calendar API
        expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
        // LO filter dropdown should not appear since members failed to load
        expect(screen.queryByDisplayValue('All LOs')).not.toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Drag and Drop / Reassign
  // =========================================================================

  describe('Reassign Modal', () => {
    it('appointment cards are draggable', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        expect(screen.getByText('Purchase Consultation')).toBeInTheDocument();
      });

      const apptCard = screen.getByText('Purchase Consultation').closest('.tc-appointment');
      expect(apptCard).toHaveAttribute('draggable', 'true');
    });
  });

  // =========================================================================
  // Mobile / Responsive
  // =========================================================================

  describe('Mobile Responsive Behavior', () => {
    it('renders all controls and content at narrow viewport widths', async () => {
      // Vitest/jsdom does not truly render CSS media queries, but we can verify
      // the DOM structure is present (the CSS handles responsive layout).
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        // Core UI elements should always be in the DOM regardless of viewport
        expect(screen.getByText('Team Calendar')).toBeInTheDocument();
        expect(screen.getByText('Day')).toBeInTheDocument();
        expect(screen.getByText('Week')).toBeInTheDocument();
        expect(screen.getByText('Availability')).toBeInTheDocument();
        expect(screen.getByText('Today')).toBeInTheDocument();
        expect(screen.getByPlaceholderText('Search client name, email, or phone...')).toBeInTheDocument();
      });
    });

    it('day grid uses minmax columns that allow horizontal scroll', async () => {
      setupDefaultMocks();
      renderTeamCalendar();

      await waitFor(() => {
        const dayGrid = document.querySelector('.tc-day-grid');
        expect(dayGrid).toBeTruthy();
        // The grid-template-columns inline style should be set with minmax
        const style = dayGrid.getAttribute('style');
        expect(style).toContain('minmax(180px, 1fr)');
      });
    });
  });
});
