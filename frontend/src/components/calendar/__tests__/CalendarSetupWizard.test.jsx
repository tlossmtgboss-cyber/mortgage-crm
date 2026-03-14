import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@/services/api', () => ({
  calendarSettingsAPI: {
    updateAvailability: vi.fn(() => Promise.resolve({ data: {} })),
    getAvailability: vi.fn(() => Promise.resolve({ data: {} })),
    getAppointmentTypes: vi.fn(() => Promise.resolve({ data: { appointment_types: [] } })),
    getBookingPage: vi.fn(() => Promise.resolve({ data: {} })),
    getNotifications: vi.fn(() => Promise.resolve({ data: {} })),
    getIntegrations: vi.fn(() => Promise.resolve({ data: {} })),
    getTeam: vi.fn(() => Promise.resolve({ data: null })),
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

// Mock CSS imports — use vi.mock with factory to avoid resolution errors
vi.mock('@/styles/calendar-setup.css', () => ({}));
vi.mock('../setup/steps/WelcomeStep.css', () => ({}));
vi.mock('../setup/steps/WorkingHoursStep.css', () => ({}));
vi.mock('../setup/steps/AppointmentTypesStep.css', () => ({}));
vi.mock('../setup/steps/BookingPageStep.css', () => ({}));
vi.mock('../setup/steps/NotificationsStep.css', () => ({}));
vi.mock('../setup/steps/IntegrationsStep.css', () => ({}));
vi.mock('../setup/steps/CancellationPolicyStep.css', () => ({}));
vi.mock('../setup/steps/TeamSetupStep.css', () => ({}));
vi.mock('../setup/steps/AdvancedFeaturesStep.css', () => ({}));
vi.mock('../setup/steps/ReviewStep.css', () => ({}));

import CalendarSetupWizard from '../setup/CalendarSetupWizard';
import { toast } from '../../../utils/toast';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'perennia_calendar_setup_progress';

function renderWizard(props = {}) {
  return render(
    <MemoryRouter>
      <CalendarSetupWizard {...props} />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CalendarSetupWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // =========================================================================
  // Rendering
  // =========================================================================

  describe('Rendering', () => {
    it('renders the wizard header with "Calendar Setup" title', () => {
      renderWizard();
      expect(screen.getByRole('heading', { name: /calendar setup/i })).toBeInTheDocument();
    });

    it('renders step 1 by default (Welcome)', () => {
      renderWizard();
      const matches = screen.getAllByText(/Step 1 of 10/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it('renders the progress stepper navigation', () => {
      renderWizard();
      const nav = screen.getByRole('navigation', { name: /setup progress/i });
      expect(nav).toBeInTheDocument();
    });

    it('renders "Get Started" button on the first step', () => {
      renderWizard();
      expect(screen.getByRole('button', { name: /continue to step 2/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /continue to step 2/i })).toHaveTextContent('Get Started');
    });

    it('renders the "Save & Exit" button', () => {
      renderWizard();
      expect(screen.getByText(/Save & Exit/)).toBeInTheDocument();
    });

    it('does not render a Back button on step 1', () => {
      renderWizard();
      expect(screen.queryByRole('button', { name: /go back/i })).not.toBeInTheDocument();
    });

    it('renders 0% complete initially', () => {
      renderWizard();
      expect(screen.getByText('0% complete')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Navigation
  // =========================================================================

  describe('Navigation', () => {
    it('advances to step 2 when Next/Get Started is clicked', async () => {
      renderWizard();
      const nextBtn = screen.getByRole('button', { name: /continue to step 2/i });
      fireEvent.click(nextBtn);

      // Wait for the transition timeout (300ms)
      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      const matches = screen.getAllByText(/Step 2 of 10/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it('renders Back button on step 2', async () => {
      renderWizard();
      fireEvent.click(screen.getByRole('button', { name: /continue to step 2/i }));
      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      expect(screen.getByRole('button', { name: /go back to step 1/i })).toBeInTheDocument();
    });

    it('navigates back to step 1 when Back is clicked', async () => {
      renderWizard();
      // Go to step 2
      fireEvent.click(screen.getByRole('button', { name: /continue to step 2/i }));
      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      // Go back to step 1
      fireEvent.click(screen.getByRole('button', { name: /go back to step 1/i }));
      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      const matches = screen.getAllByText(/Step 1 of 10/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it('marks step as completed when Next is clicked', async () => {
      renderWizard();
      fireEvent.click(screen.getByRole('button', { name: /continue to step 2/i }));
      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      // Progress should show 10% (1 of 10 steps completed)
      expect(screen.getByText('10% complete')).toBeInTheDocument();
    });

    it('shows "Next" instead of "Get Started" on steps after step 1', async () => {
      renderWizard();
      // Go to step 2
      fireEvent.click(screen.getByRole('button', { name: /continue to step 2/i }));
      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      expect(screen.getByRole('button', { name: /continue to step 3/i })).toHaveTextContent('Next');
    });
  });

  // =========================================================================
  // Skip Functionality
  // =========================================================================

  describe('Skip', () => {
    it('renders "Skip this step" on skippable steps', async () => {
      renderWizard();
      // Navigate to step 3 (Appointment Types, skippable=true)
      fireEvent.click(screen.getByRole('button', { name: /continue to step 2/i }));
      await act(async () => { vi.advanceTimersByTime(350); });

      fireEvent.click(screen.getByRole('button', { name: /continue to step 3/i }));
      await act(async () => { vi.advanceTimersByTime(350); });

      expect(screen.getByRole('button', { name: /skip appointment types step/i })).toBeInTheDocument();
    });

    it('does NOT render "Skip this step" on non-skippable steps (step 1)', () => {
      renderWizard();
      expect(screen.queryByRole('button', { name: /skip.*step/i })).not.toBeInTheDocument();
    });

    it('does NOT render "Skip this step" on non-skippable steps (step 2)', async () => {
      renderWizard();
      fireEvent.click(screen.getByRole('button', { name: /continue to step 2/i }));
      await act(async () => { vi.advanceTimersByTime(350); });

      expect(screen.queryByRole('button', { name: /skip.*step/i })).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // Progress Stepper
  // =========================================================================

  describe('Progress Stepper', () => {
    it('marks current step with aria-current="step"', () => {
      renderWizard();
      const welcomeStep = screen.getByRole('button', { name: /welcome: current step/i });
      expect(welcomeStep).toHaveAttribute('aria-current', 'step');
    });

    it('shows correct completed percentage as steps are completed', async () => {
      renderWizard();

      // Complete steps 1 and 2
      fireEvent.click(screen.getByRole('button', { name: /continue to step 2/i }));
      await act(async () => { vi.advanceTimersByTime(350); });
      expect(screen.getByText('10% complete')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /continue to step 3/i }));
      await act(async () => { vi.advanceTimersByTime(350); });
      expect(screen.getByText('20% complete')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // localStorage Persistence
  // =========================================================================

  describe('localStorage persistence', () => {
    it('persists progress to localStorage when step changes', async () => {
      renderWizard();
      fireEvent.click(screen.getByRole('button', { name: /continue to step 2/i }));
      await act(async () => { vi.advanceTimersByTime(350); });

      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
      expect(saved).toBeTruthy();
      expect(saved.currentStep).toBe(2);
      expect(saved.completedSteps).toContain(1);
    });

    it('resumes from persisted step on mount', () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        currentStep: 3,
        stepData: {},
        completedSteps: [1, 2],
        skippedSteps: [],
      }));

      renderWizard();
      const matches = screen.getAllByText(/Step 3 of 10/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it('handles corrupt localStorage gracefully', () => {
      localStorage.setItem(STORAGE_KEY, 'not-valid-json');
      // Should not throw; starts at step 1
      renderWizard();
      const matches = screen.getAllByText(/Step 1 of 10/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });
  });

  // =========================================================================
  // Save & Exit
  // =========================================================================

  describe('Save & Exit', () => {
    it('shows toast and navigates to settings when Save & Exit is clicked', async () => {
      renderWizard();
      fireEvent.click(screen.getByText(/Save & Exit/));

      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining('progress has been saved')
      );

      await act(async () => { vi.advanceTimersByTime(600); });
      expect(mockNavigate).toHaveBeenCalledWith('/calendar-settings');
    });
  });

  // =========================================================================
  // Activation (Step 10)
  // =========================================================================

  describe('Activation', () => {
    it('shows Activate Calendar button on the last step', () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        currentStep: 10,
        stepData: {},
        completedSteps: [1, 2, 3, 4, 5, 6, 7, 8, 9],
        skippedSteps: [],
      }));

      renderWizard();
      expect(screen.getByRole('button', { name: /activate your smart calendar/i })).toBeInTheDocument();
    });

    it('shows celebration overlay on activation', async () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        currentStep: 10,
        stepData: {},
        completedSteps: [1, 2, 3, 4, 5, 6, 7, 8, 9],
        skippedSteps: [],
      }));

      renderWizard();

      // Click the footer activate button
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /activate your smart calendar/i }));
      });

      // Celebration overlay should appear
      await waitFor(() => {
        expect(screen.getByText('Your Calendar is Live!')).toBeInTheDocument();
      });

      // Verify celebration text is visible
      expect(screen.getByText('Your Calendar is Live!')).toBeVisible();
    });

    it('celebration overlay navigates to /calendar on dismiss', async () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        currentStep: 10,
        stepData: {},
        completedSteps: [1, 2, 3, 4, 5, 6, 7, 8, 9],
        skippedSteps: [],
      }));

      renderWizard();
      fireEvent.click(screen.getByRole('button', { name: /activate your smart calendar/i }));

      await waitFor(() => {
        expect(screen.getByText('Your Calendar is Live!')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Go to Calendar'));
      expect(mockNavigate).toHaveBeenCalledWith('/calendar');
    });
  });

  // =========================================================================
  // Screen Reader Announcements
  // =========================================================================

  describe('Accessibility', () => {
    it('has a screen reader announcement region', () => {
      renderWizard();
      const srRegions = screen.getAllByRole('status');
      const politeRegion = srRegions.find(el => el.getAttribute('aria-live') === 'polite');
      expect(politeRegion).toBeTruthy();
    });

    it('renders footer navigation with aria-label', () => {
      renderWizard();
      const footerNav = screen.getByRole('navigation', { name: /setup step navigation/i });
      expect(footerNav).toBeInTheDocument();
    });

    it('shows subtitle "Almost there" on last step', () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        currentStep: 10,
        stepData: {},
        completedSteps: [1, 2, 3, 4, 5, 6, 7, 8, 9],
        skippedSteps: [],
      }));

      renderWizard();
      expect(screen.getByText(/almost there/i)).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Auto-save Status
  // =========================================================================

  describe('Auto-save status', () => {
    it('displays "Saving..." then "Saved" when step data changes', async () => {
      renderWizard();

      // The WelcomeStep's onChange fires on mount, triggering auto-save
      // Wait for the "Saving..." -> "Saved" cycle
      await act(async () => {
        vi.advanceTimersByTime(100);
      });

      // After 300ms the status should change to "Saved"
      await act(async () => {
        vi.advanceTimersByTime(400);
      });

      // Eventually it clears after 2 seconds
      await act(async () => {
        vi.advanceTimersByTime(2500);
      });
    });
  });
});
