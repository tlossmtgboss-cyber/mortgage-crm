/**
 * Calendar page tests.
 *
 * The Calendar page (src/pages/Calendar.js) is composed of focused child
 * components and hooks:
 *   - CommandCenterHeader  -> "Smart Calendar" page title
 *   - CalendarToolbar      -> Day/Week/Month view tabs (role="tab"),
 *                             prev/next nav ("Previous period"/"Next period"),
 *                             "Today" button, "+ Add Event" action,
 *                             and the current-period label (headerSubtitle)
 *   - AppointmentListPanel -> searchable master list ("Search appointments..."),
 *                             empty state "No appointments found",
 *                             item titles, "+ Add" button
 *   - AppointmentDetailPanel -> detail/edit/delete for the selected item
 *
 * Event data is loaded via useCalendarEvents -> unifiedCalendarAPI.getAll(),
 * team members via teamAPI.getMembers(), and view hours via
 * calendarSettingsAPI.getAvailability(). The sidebar list is filtered by the
 * search input (title / attendee_name / location).
 */
import React from 'react';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/testUtils';

// ---------------------------------------------------------------------------
// jsdom does not implement window.matchMedia, which the Calendar page relies on
// via the useIsMobile() / useMediaQuery() hook. Provide a minimal stub so the
// component can mount in tests. matches:false keeps the desktop master-detail
// layout (the mobile branch renders a different component tree).
// ---------------------------------------------------------------------------
if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {}, // deprecated
    removeListener: () => {}, // deprecated
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

// ---------------------------------------------------------------------------
// Local event fixtures. The sidebar renders each event's `title` (and optional
// `attendee_name`); search matches on title/attendee_name/location.
// ---------------------------------------------------------------------------
const mockAppointment = {
  id: 'appt-1',
  title: 'Consultation with John',
  attendee_name: 'John Doe',
  start_time: new Date(2026, 4, 20, 10, 0, 0).toISOString(),
  end_time: new Date(2026, 4, 20, 10, 30, 0).toISOString(),
  is_appointment: true,
};

const mockCalendarEvent = {
  id: 'event-1',
  title: 'Team standup',
  start_time: new Date(2026, 4, 21, 9, 0, 0).toISOString(),
  end_time: new Date(2026, 4, 21, 9, 15, 0).toISOString(),
  source: 'calendar',
};

// ---------------------------------------------------------------------------
// Mock the API layer that the Calendar hooks import
// ---------------------------------------------------------------------------
const mockGetAll = vi.fn();
const mockCreateEvent = vi.fn();
const mockDeleteEvent = vi.fn();
const mockCreateAppointment = vi.fn();
const mockCancelAppointment = vi.fn();
const mockUpdateAppointment = vi.fn();
const mockGetMembers = vi.fn();
const mockGetAvailability = vi.fn();

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
  calendarSettingsAPI: {
    getAvailability: (...args) => mockGetAvailability(...args),
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
  mockGetAvailability.mockResolvedValue({ data: {} });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Calendar Page', () => {
  // ------ Rendering ------

  it('renders the calendar page without crashing', async () => {
    renderWithProviders(<Calendar />);
    // Page title comes from CommandCenterHeader.
    expect(screen.getByText('Smart Calendar')).toBeInTheDocument();
  });

  it('shows current month and year in the header', async () => {
    renderWithProviders(<Calendar />);

    const now = new Date();
    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ];
    // Month view -> headerSubtitle is "Month Year".
    const expectedText = `${monthNames[now.getMonth()]} ${now.getFullYear()}`;

    await waitFor(() => {
      expect(screen.getByText(expectedText)).toBeInTheDocument();
    });
  });

  it('renders the calendar toolbar while events are being fetched', () => {
    // Make getAll hang (never resolve). The page mounts the toolbar
    // immediately; the desktop layout has no separate "loading" text node.
    mockGetAll.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Calendar />);

    // The CalendarToolbar's view switcher is a tablist labelled "Calendar view".
    expect(screen.getByRole('tablist', { name: /calendar view/i })).toBeInTheDocument();
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
      expect(screen.getByRole('tab', { name: 'Month' })).toHaveAttribute('aria-selected', 'true');
    });

    fireEvent.click(screen.getByRole('tab', { name: 'Day' }));

    const dayTab = screen.getByRole('tab', { name: 'Day' });
    expect(dayTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Month' })).toHaveAttribute('aria-selected', 'false');
  });

  it('switches to week view when Week tab is clicked', async () => {
    mockGetAll.mockResolvedValue({ events: [] });
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Month' })).toHaveAttribute('aria-selected', 'true');
    });

    fireEvent.click(screen.getByRole('tab', { name: 'Week' }));

    const weekTab = screen.getByRole('tab', { name: 'Week' });
    expect(weekTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Month' })).toHaveAttribute('aria-selected', 'false');
  });

  // ------ Navigation ------

  it('has a Today button', () => {
    mockGetAll.mockResolvedValue({ events: [] });
    renderWithProviders(<Calendar />);

    // The Today button still mounts and is clickable.
    const todayBtn = screen.getByText('Today');
    expect(todayBtn).toBeInTheDocument();
    fireEvent.click(todayBtn);
    expect(todayBtn).toBeInTheDocument();
  });

  it('has previous and next navigation buttons', () => {
    renderWithProviders(<Calendar />);

    // The toolbar nav buttons use aria-labels parameterised by the current view
    // ("Previous month" / "Next month" since the default view is month).
    expect(screen.getByLabelText(/Previous month/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Next month/i)).toBeInTheDocument();
  });

  // ------ Events Rendering in Sidebar ------

  it('renders events in the sidebar appointment list', async () => {
    const events = [
      { ...mockAppointment },
      { ...mockCalendarEvent },
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
      expect(screen.getByText('No appointments')).toBeInTheDocument();
    });
  });

  // ------ Search ------

  it('filters events by search query', async () => {
    const events = [
      { ...mockAppointment, title: 'Mortgage consultation', attendee_name: 'Alice' },
      { ...mockCalendarEvent, title: 'Team standup' },
    ];
    mockGetAll.mockResolvedValue({ events });

    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByText('Mortgage consultation')).toBeInTheDocument();
      expect(screen.getByText('Team standup')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search appointments...');
    await userEvent.type(searchInput, 'mortgage');

    await waitFor(() => {
      expect(screen.getByText('Mortgage consultation')).toBeInTheDocument();
      expect(screen.queryByText('Team standup')).not.toBeInTheDocument();
    });
  });

  it('shows the empty list state when search has no results', async () => {
    const events = [{ ...mockCalendarEvent }];
    mockGetAll.mockResolvedValue({ events });

    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByText('Team standup')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search appointments...');
    await userEvent.type(searchInput, 'nonexistentxyz');

    await waitFor(() => {
      expect(screen.getByText('No matching appointments')).toBeInTheDocument();
    });
  });

  // ------ Add Event ------

  it('exposes an "+ Add Event" action in the toolbar', async () => {
    mockGetAll.mockResolvedValue({ events: [] });
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Month' })).toHaveAttribute('aria-selected', 'true');
    });

    // The toolbar add-event control is labelled "Add event".
    const addBtn = screen.getByRole('button', { name: /add event/i });
    expect(addBtn).toBeInTheDocument();
    // Clicking it should not throw (opens the add-event modal flow).
    fireEvent.click(addBtn);
  });

  // ------ Detail panel / delete ------

  it('shows Edit and Cancel actions in the detail panel when an appointment is selected', async () => {
    const events = [{ ...mockAppointment, title: 'Test Appointment', is_appointment: true }];
    mockGetAll.mockResolvedValue({ events });

    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(screen.getByText('Test Appointment')).toBeInTheDocument();
    });

    // Each list row is a role="button"; clicking it selects the appointment and
    // populates the AppointmentDetailPanel. That panel only renders its
    // Edit/Cancel footer actions when the mapped event.isAppointment is true
    // (set from is_appointment by useCalendarEvents' mapper).
    const listItem = screen.getByRole('button', { name: /Test Appointment/i });
    fireEvent.click(listItem);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    });
  });

  // ------ API calls on mount ------

  it('calls unifiedCalendarAPI.getAll on mount', async () => {
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(mockGetAll).toHaveBeenCalled();
    });
  });

  it('calls teamAPI.getMembers on mount', async () => {
    renderWithProviders(<Calendar />);

    await waitFor(() => {
      expect(mockGetMembers).toHaveBeenCalledTimes(1);
    });
  });
});
