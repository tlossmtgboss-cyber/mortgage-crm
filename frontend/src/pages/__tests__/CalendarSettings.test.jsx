import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
  calendarSettingsAPI: {
    getAvailability: vi.fn(() => Promise.resolve({ data: {} })),
    updateAvailability: vi.fn(() => Promise.resolve({ data: {} })),
    getAppointmentTypes: vi.fn(() => Promise.resolve({ data: { appointment_types: [] } })),
    getNotifications: vi.fn(() => Promise.resolve({ data: {} })),
    updateNotifications: vi.fn(() => Promise.resolve({ data: {} })),
    getBookingPage: vi.fn(() => Promise.resolve({ data: {} })),
    updateBookingPage: vi.fn(() => Promise.resolve({ data: {} })),
    getIntegrations: vi.fn(() => Promise.resolve({ data: {} })),
    getTeam: vi.fn(() => Promise.resolve({ data: null })),
    updateTeam: vi.fn(() => Promise.resolve({ data: {} })),
    getLocations: vi.fn(() => Promise.resolve({ data: { locations: [] } })),
    getLabels: vi.fn(() => Promise.resolve({ data: { labels: [] } })),
    getTemplates: vi.fn(() => Promise.resolve({ data: { templates: [] } })),
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
vi.mock('@/styles/calendar-settings.css', () => ({}));

// Mock all section components to simple stubs
vi.mock('../calendar-settings/AvailabilitySection', () => ({
  default: (props) => <div data-testid="section-availability">AvailabilitySection</div>,
}));

vi.mock('../calendar-settings/AppointmentTypesSection', () => ({
  default: (props) => <div data-testid="section-appointment-types">AppointmentTypesSection</div>,
}));

vi.mock('../calendar-settings/NotificationsSection', () => ({
  default: (props) => <div data-testid="section-notifications">NotificationsSection</div>,
}));

vi.mock('../calendar-settings/BookingPageSection', () => ({
  default: (props) => <div data-testid="section-booking-page">BookingPageSection</div>,
}));

vi.mock('../calendar-settings/CancellationPolicySection', () => ({
  default: (props) => <div data-testid="section-cancellation-policy">CancellationPolicySection</div>,
}));

vi.mock('../calendar-settings/IntegrationsSection', () => ({
  default: (props) => <div data-testid="section-integrations">IntegrationsSection</div>,
}));

vi.mock('../calendar-settings/TeamSection', () => ({
  default: (props) => <div data-testid="section-team">TeamSection</div>,
}));

vi.mock('../calendar-settings/LocationsLabelsSection', () => ({
  default: (props) => <div data-testid="section-locations-labels">LocationsLabelsSection</div>,
}));

vi.mock('../calendar-settings/AdvancedSection', () => ({
  default: (props) => <div data-testid="section-advanced">AdvancedSection</div>,
}));

import CalendarSettings from '../CalendarSettings';
import { calendarSettingsAPI } from '@/services/api';
import { toast } from '@/utils/toast';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderSettings() {
  return render(
    <MemoryRouter>
      <CalendarSettings />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CalendarSettings Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // =========================================================================
  // Rendering
  // =========================================================================

  describe('Rendering', () => {
    it('renders with "Smart Calendar Settings" heading', async () => {
      renderSettings();
      expect(screen.getByRole('heading', { name: /smart calendar settings/i })).toBeInTheDocument();
    });

    it('renders the Availability tab as active by default', async () => {
      renderSettings();

      // The sidebar nav tab for availability should be active
      await waitFor(() => {
        const availabilityTab = screen.getAllByRole('tab').find(
          el => el.textContent.includes('Availability') && el.getAttribute('aria-selected') === 'true'
        );
        expect(availabilityTab).toBeTruthy();
      });
    });

    it('renders the AvailabilitySection content by default', async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByTestId('section-availability')).toBeInTheDocument();
      });
    });

    it('renders navigation sidebar with all section groups', async () => {
      renderSettings();
      // Group labels appear in both sidebar and mobile tabs, so use getAllByText
      expect(screen.getAllByText('Schedule').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('Booking').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('Communication').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('Management').length).toBeGreaterThanOrEqual(1);

      // Confirm sidebar nav exists
      const sidebar = screen.getByRole('tablist', { name: /calendar settings navigation/i });
      expect(sidebar).toBeInTheDocument();
    });

    it('renders breadcrumb showing Settings / Schedule / Availability', async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText('Settings')).toBeInTheDocument();
        expect(screen.getByText('Availability', { selector: '.breadcrumb-current' })).toBeInTheDocument();
      });
    });

    it('renders Setup Wizard and Tour buttons in the top bar', () => {
      renderSettings();
      expect(screen.getByText('Setup Wizard')).toBeInTheDocument();
      expect(screen.getByText('Tour')).toBeInTheDocument();
    });

    it('renders the save status indicator showing "All changes saved" initially', async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText('All changes saved')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Tab Switching
  // =========================================================================

  describe('Tab Switching', () => {
    it('switches to Notifications section when Notifications tab is clicked', async () => {
      renderSettings();

      await waitFor(() => {
        expect(screen.getByTestId('section-availability')).toBeInTheDocument();
      });

      const notifTabs = screen.getAllByRole('tab').filter(el => el.textContent.includes('Notifications'));
      fireEvent.click(notifTabs[0]);

      await waitFor(() => {
        expect(screen.getByTestId('section-notifications')).toBeInTheDocument();
      });
      expect(calendarSettingsAPI.getNotifications).toHaveBeenCalled();
    });

    it('switches to Appointment Types section when its tab is clicked', async () => {
      renderSettings();

      await waitFor(() => {
        expect(screen.getByTestId('section-availability')).toBeInTheDocument();
      });

      const apptTabs = screen.getAllByRole('tab').filter(el => el.textContent.includes('Appointment Types'));
      fireEvent.click(apptTabs[0]);

      await waitFor(() => {
        expect(screen.getByTestId('section-appointment-types')).toBeInTheDocument();
      });
      expect(calendarSettingsAPI.getAppointmentTypes).toHaveBeenCalled();
    });

    it('loads data when switching to integrations tab', async () => {
      renderSettings();

      await waitFor(() => {
        expect(screen.getByTestId('section-availability')).toBeInTheDocument();
      });

      const intTabs = screen.getAllByRole('tab').filter(el => el.textContent.includes('Integrations'));
      fireEvent.click(intTabs[0]);

      await waitFor(() => {
        expect(screen.getByTestId('section-integrations')).toBeInTheDocument();
      });
      expect(calendarSettingsAPI.getIntegrations).toHaveBeenCalled();
    });
  });

  // =========================================================================
  // Save Functionality
  // =========================================================================

  describe('Save', () => {
    it('renders a disabled Save button when there are no unsaved changes', async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByTestId('section-availability')).toBeInTheDocument();
      });
      const saveBtn = screen.getByRole('button', { name: /save/i });
      expect(saveBtn).toBeDisabled();
    });
  });

  // =========================================================================
  // Navigation
  // =========================================================================

  describe('Navigation', () => {
    it('back button calls navigate(-1)', async () => {
      renderSettings();
      const backBtn = screen.getByLabelText('Go back');
      fireEvent.click(backBtn);
      expect(mockNavigate).toHaveBeenCalledWith(-1);
    });

    it('Setup Wizard button navigates to /calendar/setup', async () => {
      renderSettings();
      fireEvent.click(screen.getByText('Setup Wizard'));
      expect(mockNavigate).toHaveBeenCalledWith('/calendar/setup');
    });

    it('Tour button triggers toast info message', async () => {
      renderSettings();
      fireEvent.click(screen.getByText('Tour'));
      expect(toast.info).toHaveBeenCalledWith('Calendar tour starting...');
    });
  });
});
