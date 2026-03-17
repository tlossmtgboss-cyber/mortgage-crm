/**
 * Calendar page tests.
 *
 * The Calendar component fetches events via unifiedCalendarAPI.getAll(),
 * renders month/week/day views, and supports navigation, search, and tabs.
 */
import React from 'react';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, mockAppointment, mockCalendarEvent } from '../test/testUtils';

// ---------------------------------------------------------------------------
// Mock the API layer that Calendar imports
// ---------------------------------------------------------------------------
const mockGetAll = vi.fn();
const mockCreateEvent = vi.fn();
const mockDeleteEvent = vi.fn();
const mockCreateAppointment = vi.fn();
const mockCancelAppointment = vi.fn();
const mockUpdateAppointment = vi.fn();
const mockGetMembers = vi.fn();

vi.mock('../services/api', () => ({
  calendarAPI: {
    create: (...args) => mockCreateEvent(...args),
    delete: (...args) => mockDeleteEvent(...args),
  },
  unifiedCalendarAPI: {
    getAll: (...args) => mockGetAll(...args),
  },
  schedulerAPI: {
    createAppointment: (...args) => mockCreateAppointment(...args),
    cancelAppointment: (...args) => mockCancelAppointment(...args),
    updateAppointment: (...args) => mockUpdateAppointment(...args),
  },
  teamAPI: {
    getMembers: (...args) => mockGetMembers(...args),
  },
}));

// Lazy-import after mocks are registered
let Calendar;
beforeAll(async () => {
  const mod = await import('../pages/Calendar');
  Calendar = mod.default;
});

// ---------------------------------------------------------------------------
// Reset mocks between tests
// ---------------------------------------------------------------------------
beforeEach(() => {
  vi.clearAllMocks();

  // Default: return empty events
  mockGetAll.mockResolvedValue({ events: [] });
  mockGetMembers.mockResolvedValue([]);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Calendar Page', () => {
  // ------ Rendering ------

  it('renders the calendar page without crashing', async () => {
    renderWithProviders(<Calendar />);
    expect(screen.getByText('Calendar')).toBeInTheDocument();
  });

  it('shows current month and year in the header', async () => {
    renderWithProviders(<Calendar />);

    const now = new Date();
    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ];
    const expectedText = `${monthNames[now.getMonth()]} ${now.getFullYear()}`;

    await waitFor(() => {
      expect(screen.getByText(expectedText)).toBeInTheDocument();
    });
  });

  it('shows loading state while fetching events', () => {
    // Make getAll hang (never resolve)
    mockGetAll.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Calendar />);

    expect(screen.getByText('Loading events...')).toBeInTheDocument();
  });

  it('displays error banner when API call fails', async () => {
    mockGetAll.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText(/Unable to load calendar events/i)).toBeInTheDocument();
    });
  });

  it('displays retry button in error banner', async () => {
    mockGetAll.mockRejectedValue(new Error('fail'));
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });

    // Clicking retry should re-fetch (more calls than before the click)
    const callsBefore = mockGetAll.mock.calls.length;
    mockGetAll.mockResolvedValue({ events: [] });
    fireEvent.click(screen.getByText('Retry'));

    await waitFor(() => {
      expect(mockGetAll.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  // ------ View Switching ------

  it('renders view switcher with Day, Week, Month tabs', () => {
    renderWithProviders(<Calendar />);

    expect(screen.getByRole('tab', { name: 'Day' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Week' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Month' })).toBeInTheDocument();
  });

  it('defaults to month view', () => {
    renderWithProviders(<Calendar />);
    const monthTab = screen.getByRole('tab', { name: 'Month' });
    expect(monthTab).toHaveAttribute('aria-selected', 'true');
  });

  it('switches to day view when Day tab is clicked', async () => {
    mockGetAll.mockResolvedValue({ events: [] });
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.queryByText('Loading events...')).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('tab', { name: 'Day' }));
    const dayTab = screen.getByRole('tab', { name: 'Day' });
    expect(dayTab).toHaveAttribute('aria-selected', 'true');

    // Day view shows hour labels (e.g., "10 AM")
    expect(screen.getByText('10 AM')).toBeInTheDocument();
  });

  it('switches to week view when Week tab is clicked', async () => {
    mockGetAll.mockResolvedValue({ events: [] });
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.queryByText('Loading events...')).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('tab', { name: 'Week' }));
    const weekTab = screen.getByRole('tab', { name: 'Week' });
    expect(weekTab).toHaveAttribute('aria-selected', 'true');

    // Week view shows abbreviated day names
    expect(screen.getByText('Sun')).toBeInTheDocument();
    expect(screen.getByText('Mon')).toBeInTheDocument();
  });

  // ------ Navigation ------

  it('navigates to today when Today button is clicked', async () => {
    mockGetAll.mockResolvedValue({ events: [] });
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.queryByText('Loading events...')).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Today'));

    const now = new Date();
    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ];
    const expected = `${monthNames[now.getMonth()]} ${now.getFullYear()}`;
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it('has previous and next navigation buttons', () => {
    renderWithProviders(<Calendar />);

    // Month view uses aria-labels
    expect(screen.getByLabelText(/Previous month/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Next month/i)).toBeInTheDocument();
  });

  // ------ Events Rendering in Sidebar ------

  it('renders events in the sidebar appointment list', async () => {
    const events = [
      {
        ...mockAppointment,
        id: 'appt-appt-1',
      },
      {
        ...mockCalendarEvent,
        id: 'event-event-42',
      },
    ];
    mockGetAll.mockResolvedValue({ events });

    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByText('Consultation with John')).toBeInTheDocument();
      expect(screen.getByText('Team standup')).toBeInTheDocument();
    });
  });

  it('shows empty state when no events exist', async () => {
    mockGetAll.mockResolvedValue({ events: [] });
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByText('No appointments scheduled')).toBeInTheDocument();
    });
  });

  // ------ Tabs ------

  it('renders appointment filter tabs', async () => {
    mockGetAll.mockResolvedValue({ events: [] });
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Appointments' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'Closings' })).toBeInTheDocument();
    });
  });

  it('filters events when a tab is clicked', async () => {
    const events = [
      {
        ...mockAppointment,
        id: 'appt-1',
        title: 'Closing Event',
        event_type: 'closing',
      },
      {
        ...mockCalendarEvent,
        id: 'event-2',
        title: 'Regular Meeting',
        event_type: 'meeting',
      },
    ];
    mockGetAll.mockResolvedValue({ events });

    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByText('Closing Event')).toBeInTheDocument();
      expect(screen.getByText('Regular Meeting')).toBeInTheDocument();
    });

    // Click the Closings tab
    fireEvent.click(screen.getByRole('tab', { name: 'Closings' }));

    await waitFor(() => {
      expect(screen.getByText('Closing Event')).toBeInTheDocument();
      expect(screen.queryByText('Regular Meeting')).not.toBeInTheDocument();
    });
  });

  // ------ Search ------

  it('filters events by search query', async () => {
    const events = [
      {
        ...mockAppointment,
        id: 'appt-1',
        title: 'Mortgage consultation',
        attendee_name: 'Alice',
      },
      {
        ...mockCalendarEvent,
        id: 'event-2',
        title: 'Team standup',
      },
    ];
    mockGetAll.mockResolvedValue({ events });

    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByText('Mortgage consultation')).toBeInTheDocument();
      expect(screen.getByText('Team standup')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search events...');
    await userEvent.type(searchInput, 'mortgage');

    await waitFor(() => {
      expect(screen.getByText('Mortgage consultation')).toBeInTheDocument();
      expect(screen.queryByText('Team standup')).not.toBeInTheDocument();
    });
  });

  it('shows "No matching events" when search has no results', async () => {
    const events = [{ ...mockCalendarEvent, id: 'event-1' }];
    mockGetAll.mockResolvedValue({ events });

    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByText('Team standup')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search events...');
    await userEvent.type(searchInput, 'nonexistentxyz');

    await waitFor(() => {
      expect(screen.getByText('No matching events')).toBeInTheDocument();
    });
  });

  // ------ Add Event Modal ------

  it('opens add event modal when "+ Add Event" is clicked', async () => {
    mockGetAll.mockResolvedValue({ events: [] });
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.queryByText('Loading events...')).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('+ Add Event'));

    // The AddEventModal should appear with heading "Add Event"
    await waitFor(() => {
      expect(screen.getByText('Add Event', { selector: 'h3' })).toBeInTheDocument();
    });
  });

  // ------ Day View Events ------

  it('renders events in day view time slots', async () => {
    // Event at 10:00 AM UTC
    const events = [
      {
        ...mockAppointment,
        id: 'appt-appt-1',
        start_time: new Date(2026, 2, 15, 10, 0, 0).toISOString(),
        end_time: new Date(2026, 2, 15, 10, 30, 0).toISOString(),
      },
    ];
    mockGetAll.mockResolvedValue({ events });

    renderWithProviders(<Calendar />);

    // Wait for loading to finish
    await waitFor(() => {
      expect(screen.queryByText('Loading events...')).not.toBeInTheDocument();
    });

    // Switch to day view
    fireEvent.click(screen.getByRole('tab', { name: 'Day' }));

    // Should show hour labels
    expect(screen.getByText('10 AM')).toBeInTheDocument();
    expect(screen.getByText('11 AM')).toBeInTheDocument();
  });

  // ------ Delete / Cancel Event ------

  it('shows delete button on each event in sidebar', async () => {
    const events = [
      {
        ...mockAppointment,
        id: 'appt-appt-1',
        title: 'Test Appointment',
      },
    ];
    mockGetAll.mockResolvedValue({ events });

    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByText('Test Appointment')).toBeInTheDocument();
    });

    // The delete button uses aria-label
    const deleteBtn = screen.getByLabelText(/Cancel appointment: Test Appointment/i);
    expect(deleteBtn).toBeInTheDocument();
  });

  // ------ API calls on mount ------

  it('calls unifiedCalendarAPI.getAll on mount', async () => {
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      // Should be called at least twice: loadEvents + loadAllEvents
      expect(mockGetAll).toHaveBeenCalledTimes(2);
    });
  });

  it('calls teamAPI.getMembers on mount', async () => {
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(mockGetMembers).toHaveBeenCalledTimes(1);
    });
  });
});
