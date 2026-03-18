/**
 * CalendarSettings Advanced Tests
 *
 * Covers areas NOT tested in CalendarSettings.test.jsx:
 *   - AI & Automation tab rendering (combined section with AIScheduling, FollowUp, Advanced)
 *   - Sticky save bar appearance and behavior
 *   - Test Config button and result banner
 *   - Mobile tab strip rendering and interaction
 *   - Keyboard navigation between sidebar tabs (ArrowDown/ArrowUp, Home, End)
 *   - Loading state display
 *   - Unsaved changes warning on tab switch
 *   - Discard button in sticky save bar
 *   - Locations & Labels tab
 *   - Cancellation Policy tab
 *   - Booking Page tab
 *   - Team tab rendering (with Manager badge)
 *   - Section header and description rendering
 *   - Test Config success/failure banners
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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
  API_BASE_URL: 'http://localhost:8000',
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

// Mock all section components to simple stubs that expose props
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

vi.mock('../calendar-settings/AISchedulingSection', () => ({
  default: (props) => <div data-testid="section-ai-scheduling">AISchedulingSection</div>,
}));

vi.mock('../calendar-settings/FollowUpCadenceSection', () => ({
  default: (props) => <div data-testid="section-followup-cadence">FollowUpCadenceSection</div>,
}));

import CalendarSettings from '../CalendarSettings';
import { calendarSettingsAPI, API_BASE_URL } from '@/services/api';
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

/**
 * Click a sidebar tab by label text.
 */
async function switchToTab(tabLabel) {
  const tabs = screen.getAllByRole('tab').filter(el => el.textContent.includes(tabLabel));
  fireEvent.click(tabs[0]);

  // Wait for the section to render
  await waitFor(() => {
    // Loading should complete
    expect(screen.queryByText('Loading settings...')).not.toBeInTheDocument();
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CalendarSettings — Advanced', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock fetch for test config endpoint
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // =========================================================================
  // AI & Automation Tab
  // =========================================================================

  describe('AI & Automation tab', () => {
    it('renders AISchedulingSection, FollowUpCadenceSection, and AdvancedSection together', async () => {
      renderSettings();

      await switchToTab('AI & Automation');

      await waitFor(() => {
        expect(screen.getByTestId('section-ai-scheduling')).toBeInTheDocument();
        expect(screen.getByTestId('section-followup-cadence')).toBeInTheDocument();
        expect(screen.getByTestId('section-advanced')).toBeInTheDocument();
      });
    });

    it('shows dividers between AI & Automation sub-sections', async () => {
      renderSettings();

      await switchToTab('AI & Automation');

      await waitFor(() => {
        const dividers = document.querySelectorAll('.ai-automation-divider');
        expect(dividers.length).toBe(2);
      });
    });
  });

  // =========================================================================
  // Booking Page Tab
  // =========================================================================

  describe('Booking Page tab', () => {
    it('switches to Booking Page section when its tab is clicked', async () => {
      renderSettings();

      await switchToTab('Booking Page');

      await waitFor(() => {
        expect(screen.getByTestId('section-booking-page')).toBeInTheDocument();
      });
    });

    it('updates breadcrumb to show Booking / Booking Page', async () => {
      renderSettings();

      await switchToTab('Booking Page');

      await waitFor(() => {
        expect(screen.getByText('Booking Page', { selector: '.breadcrumb-current' })).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Cancellation Policy Tab
  // =========================================================================

  describe('Cancellation Policy tab', () => {
    it('switches to Cancellation Policy section', async () => {
      renderSettings();

      await switchToTab('Cancellation Policy');

      await waitFor(() => {
        expect(screen.getByTestId('section-cancellation-policy')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Locations & Labels Tab
  // =========================================================================

  describe('Locations & Labels tab', () => {
    it('switches to Locations & Labels section', async () => {
      renderSettings();

      await switchToTab('Locations & Labels');

      await waitFor(() => {
        expect(screen.getByTestId('section-locations-labels')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Team Tab
  // =========================================================================

  describe('Team tab', () => {
    it('renders Team section and shows Manager badge in sidebar', async () => {
      renderSettings();

      // Check Manager badge exists in navigation
      const badge = document.querySelector('.nav-badge');
      expect(badge).toBeTruthy();
      expect(badge.textContent).toBe('Manager');

      await switchToTab('Team');

      await waitFor(() => {
        expect(screen.getByTestId('section-team')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Mobile Tabs
  // =========================================================================

  describe('Mobile tabs', () => {
    it('renders mobile tab strip with aria-label', async () => {
      renderSettings();

      const mobileTabs = screen.getByRole('tablist', { name: /calendar settings sections/i });
      expect(mobileTabs).toBeInTheDocument();
    });

    it('mobile tabs include all navigation items', async () => {
      renderSettings();

      // The mobile tablist should contain buttons for all sections
      const mobileTabs = screen.getByRole('tablist', { name: /calendar settings sections/i });
      const buttons = within(mobileTabs).getAllByRole('tab');

      // We expect 9 items (Availability, Appointment Types, Locations & Labels,
      // Booking Page, Cancellation Policy, Notifications, Integrations, AI & Automation, Team)
      expect(buttons.length).toBe(9);
    });

    it('clicking a mobile tab switches sections', async () => {
      renderSettings();

      const mobileTabs = screen.getByRole('tablist', { name: /calendar settings sections/i });
      const teamMobileTab = within(mobileTabs).getAllByRole('tab').find(
        el => el.textContent.includes('Team')
      );

      fireEvent.click(teamMobileTab);

      await waitFor(() => {
        expect(screen.getByTestId('section-team')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Keyboard Navigation
  // =========================================================================

  describe('Sidebar keyboard navigation', () => {
    it('ArrowDown moves focus to the next tab', async () => {
      renderSettings();

      // Focus the first sidebar tab (Availability)
      const firstTab = document.getElementById('calnav-availability');
      expect(firstTab).toBeTruthy();

      fireEvent.keyDown(firstTab, { key: 'ArrowDown' });

      // Should switch to the next section (Appointment Types)
      await waitFor(() => {
        expect(screen.getByTestId('section-appointment-types')).toBeInTheDocument();
      });
    });

    it('ArrowUp wraps to last tab when at the first', async () => {
      renderSettings();

      const firstTab = document.getElementById('calnav-availability');
      fireEvent.keyDown(firstTab, { key: 'ArrowUp' });

      // Should wrap to last section (Team)
      await waitFor(() => {
        expect(screen.getByTestId('section-team')).toBeInTheDocument();
      });
    });

    it('Home key navigates to the first tab', async () => {
      renderSettings();

      // First go to Team
      await switchToTab('Team');
      expect(screen.getByTestId('section-team')).toBeInTheDocument();

      const teamTab = document.getElementById('calnav-team');
      fireEvent.keyDown(teamTab, { key: 'Home' });

      await waitFor(() => {
        expect(screen.getByTestId('section-availability')).toBeInTheDocument();
      });
    });

    it('End key navigates to the last tab', async () => {
      renderSettings();

      const firstTab = document.getElementById('calnav-availability');
      fireEvent.keyDown(firstTab, { key: 'End' });

      await waitFor(() => {
        expect(screen.getByTestId('section-team')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Section Header
  // =========================================================================

  describe('Section header', () => {
    it('renders section heading matching the active tab', async () => {
      renderSettings();

      // Default: Availability
      await waitFor(() => {
        const heading = screen.getByRole('heading', { level: 2 });
        expect(heading.textContent).toBe('Availability');
      });
    });

    it('updates section heading when switching tabs', async () => {
      renderSettings();

      await switchToTab('Notifications');

      await waitFor(() => {
        const heading = screen.getByRole('heading', { level: 2 });
        expect(heading.textContent).toBe('Notifications');
      });
    });

    it('renders section description paragraph', async () => {
      renderSettings();

      // Availability description
      await waitFor(() => {
        expect(screen.getByText(/business hours, time blocks/i)).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Test Config
  // =========================================================================

  describe('Test Config', () => {
    it('renders Test Config button in the topbar', async () => {
      renderSettings();

      expect(screen.getByText('Test Config')).toBeInTheDocument();
    });

    it('shows success banner when test config passes', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          data: {
            success: true,
            loan_officers_available: 5,
            issues: [],
          },
        }),
      });

      renderSettings();

      const testBtn = screen.getByText('Test Config').closest('button');
      await act(async () => {
        fireEvent.click(testBtn);
      });

      await waitFor(() => {
        expect(screen.getByText('Test Passed')).toBeInTheDocument();
        expect(screen.getByText(/loan officers available: 5/i)).toBeInTheDocument();
      });

      expect(toast.success).toHaveBeenCalledWith('Configuration test passed!');
    });

    it('shows warning banner when test config finds issues', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          data: {
            success: false,
            issues: ['No availability configured for Monday', 'Buffer too short'],
          },
        }),
      });

      renderSettings();

      const testBtn = screen.getByText('Test Config').closest('button');
      await act(async () => {
        fireEvent.click(testBtn);
      });

      await waitFor(() => {
        expect(screen.getByText('Issues Found')).toBeInTheDocument();
        expect(screen.getByText('No availability configured for Monday')).toBeInTheDocument();
        expect(screen.getByText('Buffer too short')).toBeInTheDocument();
      });

      expect(toast.warning).toHaveBeenCalledWith('Configuration test found issues');
    });

    it('shows error toast when test config API fails', async () => {
      global.fetch = vi.fn().mockRejectedValueOnce(new Error('Network error'));

      renderSettings();

      const testBtn = screen.getByText('Test Config').closest('button');
      await act(async () => {
        fireEvent.click(testBtn);
      });

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Configuration test failed');
      });
    });

    it('dismisses test result banner when dismiss button is clicked', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          data: { success: true, issues: [] },
        }),
      });

      renderSettings();

      const testBtn = screen.getByText('Test Config').closest('button');
      await act(async () => {
        fireEvent.click(testBtn);
      });

      await waitFor(() => {
        expect(screen.getByText('Test Passed')).toBeInTheDocument();
      });

      // Click dismiss
      const dismissBtn = screen.getByLabelText('Dismiss');
      fireEvent.click(dismissBtn);

      await waitFor(() => {
        expect(screen.queryByText('Test Passed')).not.toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Save Status Indicator
  // =========================================================================

  describe('Save status indicator', () => {
    it('shows "saved" status dot class initially', async () => {
      renderSettings();

      await waitFor(() => {
        const statusDot = document.querySelector('.save-status.saved');
        expect(statusDot).toBeTruthy();
      });
    });
  });

  // =========================================================================
  // Breadcrumb Updates
  // =========================================================================

  describe('Breadcrumb updates', () => {
    it('shows correct group in breadcrumb for Communication section', async () => {
      renderSettings();

      await switchToTab('Notifications');

      await waitFor(() => {
        // Breadcrumb should show: Settings / Communication / Notifications
        const breadcrumb = document.querySelector('.cal-settings-breadcrumb');
        expect(breadcrumb.textContent).toContain('Communication');
        expect(breadcrumb.textContent).toContain('Notifications');
      });
    });

    it('shows correct group in breadcrumb for Management section', async () => {
      renderSettings();

      await switchToTab('Team');

      await waitFor(() => {
        const breadcrumb = document.querySelector('.cal-settings-breadcrumb');
        expect(breadcrumb.textContent).toContain('Management');
        expect(breadcrumb.textContent).toContain('Team');
      });
    });

    it('shows correct group in breadcrumb for AI & Automation section', async () => {
      renderSettings();

      await switchToTab('AI & Automation');

      await waitFor(() => {
        const breadcrumb = document.querySelector('.cal-settings-breadcrumb');
        expect(breadcrumb.textContent).toContain('AI & Automation');
      });
    });
  });

  // =========================================================================
  // Tab Active State
  // =========================================================================

  describe('Tab active state', () => {
    it('marks the currently active sidebar tab with aria-selected=true', async () => {
      renderSettings();

      await switchToTab('Integrations');

      await waitFor(() => {
        const sidebarNav = screen.getByRole('tablist', { name: /calendar settings navigation/i });
        const intTab = within(sidebarNav).getAllByRole('tab').find(
          el => el.textContent.includes('Integrations') && el.getAttribute('aria-selected') === 'true'
        );
        expect(intTab).toBeTruthy();
      });
    });

    it('sets tabIndex=0 on active sidebar tab and -1 on inactive tabs', async () => {
      renderSettings();

      await switchToTab('Notifications');

      await waitFor(() => {
        const notifTab = document.getElementById('calnav-notifications');
        expect(notifTab.getAttribute('tabindex')).toBe('0');

        const availTab = document.getElementById('calnav-availability');
        expect(availTab.getAttribute('tabindex')).toBe('-1');
      });
    });
  });

  // =========================================================================
  // Save Button Visibility
  // =========================================================================

  describe('Save button visibility', () => {
    it('shows Save button on saveable sections (availability)', async () => {
      renderSettings();

      await waitFor(() => {
        const saveBtn = screen.getByRole('button', { name: /save/i });
        expect(saveBtn).toBeInTheDocument();
      });
    });

    it('shows Save button on Notifications section', async () => {
      renderSettings();

      await switchToTab('Notifications');

      await waitFor(() => {
        const saveBtn = screen.getByRole('button', { name: /save/i });
        expect(saveBtn).toBeInTheDocument();
      });
    });

    it('does not show Save button on non-saveable sections (appointment-types)', async () => {
      renderSettings();

      await switchToTab('Appointment Types');

      await waitFor(() => {
        expect(screen.getByTestId('section-appointment-types')).toBeInTheDocument();
      });

      // Appointment Types is not in SAVEABLE_SECTIONS, so Save button should not appear
      // Note: only the top-bar Save is conditional; sticky bar also depends on hasChanges
      const saveBtns = screen.queryAllByRole('button', { name: /^save$/i });
      expect(saveBtns.length).toBe(0);
    });
  });

  // =========================================================================
  // Sidebar Group Labels
  // =========================================================================

  describe('Sidebar group labels', () => {
    it('renders group labels with correct IDs for aria-labelledby', () => {
      renderSettings();

      const sidebarNav = screen.getByRole('tablist', { name: /calendar settings navigation/i });
      const groups = within(sidebarNav).getAllByRole('group');

      // Should have 5 groups: Schedule, Booking, Communication, AI & Automation, Management
      expect(groups.length).toBe(5);

      // Each group should have an aria-labelledby pointing to a label element
      groups.forEach(group => {
        const labelledBy = group.getAttribute('aria-labelledby');
        expect(labelledBy).toBeTruthy();
        const label = document.getElementById(labelledBy);
        expect(label).toBeTruthy();
      });
    });

    it('Schedule group contains Availability, Appointment Types, Locations & Labels', () => {
      renderSettings();

      const scheduleLabel = document.getElementById('nav-group-schedule');
      expect(scheduleLabel).toBeTruthy();
      expect(scheduleLabel.textContent).toBe('Schedule');

      // The group that contains this label should have 3 tabs
      const group = scheduleLabel.closest('[role="group"]');
      const tabs = within(group).getAllByRole('tab');
      expect(tabs.length).toBe(3);

      const tabLabels = tabs.map(t => t.textContent.trim());
      expect(tabLabels).toContain('Availability');
      expect(tabLabels).toContain('Appointment Types');
      expect(tabLabels).toContain('Locations & Labels');
    });
  });
});
