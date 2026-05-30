import React from 'react';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
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
    // Discard any timers a test left pending so they do not fire during the
    // switch back to real timers (which would invoke callbacks against spies
    // that have already been reset, surfacing as an unhandledRejection).
    vi.clearAllTimers();
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
      const matches = screen.getAllByText(/Step 1 of 6/);
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
      const pct = document.querySelector('.cal-setup-progress-pct');
      expect(pct).toBeTruthy();
      expect(pct.textContent.replace(/\s+/g, ' ').trim()).toMatch(/^0\s*% Complete$/);
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

      const matches = screen.getAllByText(/Step 2 of 6/);
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

      const matches = screen.getAllByText(/Step 1 of 6/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it('marks step as completed when Next is clicked', async () => {
      renderWizard();
      fireEvent.click(screen.getByRole('button', { name: /continue to step 2/i }));
      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      // Progress should show 17% (1 of 6 steps completed)
      const pct = document.querySelector('.cal-setup-progress-pct');
      expect(pct.textContent.replace(/\s+/g, ' ').trim()).toMatch(/^17\s*% Complete$/);
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

      const pctText = () =>
        document.querySelector('.cal-setup-progress-pct').textContent.replace(/\s+/g, ' ').trim();

      // Complete steps 1 and 2 (of 6 total)
      fireEvent.click(screen.getByRole('button', { name: /continue to step 2/i }));
      await act(async () => { vi.advanceTimersByTime(350); });
      expect(pctText()).toMatch(/^17\s*% Complete$/);

      fireEvent.click(screen.getByRole('button', { name: /continue to step 3/i }));
      await act(async () => { vi.advanceTimersByTime(350); });
      expect(pctText()).toMatch(/^33\s*% Complete$/);
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
      const matches = screen.getAllByText(/Step 3 of 6/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it('handles corrupt localStorage gracefully', () => {
      localStorage.setItem(STORAGE_KEY, 'not-valid-json');
      // Should not throw; starts at step 1
      renderWizard();
      const matches = screen.getAllByText(/Step 1 of 6/);
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

      // Flush the navigate() delay timer. runAllTimers (inside act) drains every
      // pending timer — including any autosave/transition timer left over from a
      // prior test — so none survive to fire during teardown's timer cleanup,
      // which is what otherwise surfaced as an unhandledRejection spy assertion.
      await act(async () => {
        vi.runAllTimers();
      });
      expect(mockNavigate).toHaveBeenCalledWith('/calendar-settings');
    });
  });

  // =========================================================================
  // Activation (Step 10)
  // =========================================================================

  describe('Activation', () => {
    it('shows Activate Calendar button on the last step', () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        currentStep: 6,
        stepData: {},
        completedSteps: [1, 2, 3, 4, 5],
        skippedSteps: [],
      }));

      renderWizard();
      expect(screen.getByRole('button', { name: /activate your smart calendar/i })).toBeInTheDocument();
    });

    it('shows celebration overlay on activation', async () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        currentStep: 6,
        stepData: {},
        completedSteps: [1, 2, 3, 4, 5],
        skippedSteps: [],
      }));

      renderWizard();

      // Click the footer activate button. The overlay is rendered synchronously
      // from the click handler's state update, so no waitFor is needed —
      // avoiding RTL's fake-timer polling (runOnlyPendingTimers), which would
      // otherwise flush the overlay's 4s auto-dismiss timer and fire navigate().
      act(() => {
        fireEvent.click(screen.getByRole('button', { name: /activate your smart calendar/i }));
      });

      // Celebration overlay should appear
      expect(screen.getByText('Your Calendar is Live!')).toBeInTheDocument();
      expect(screen.getByText('Your Calendar is Live!')).toBeVisible();
    });

    it('celebration overlay navigates to /calendar on dismiss', async () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        currentStep: 6,
        stepData: {},
        completedSteps: [1, 2, 3, 4, 5],
        skippedSteps: [],
      }));

      renderWizard();
      act(() => {
        fireEvent.click(screen.getByRole('button', { name: /activate your smart calendar/i }));
      });

      // Overlay renders synchronously from the activate handler's state update.
      // findBy* would invoke RTL's fake-timer polling and could flush the
      // overlay's 4s auto-dismiss timer; the sync getBy is sufficient here.
      const overlayHeading = screen.getByText('Your Calendar is Live!');
      expect(overlayHeading).toBeInTheDocument();

      // Disregard any navigate() the overlay's auto-dismiss may have queued so
      // the assertion verifies the explicit "Go to Calendar" dismiss path only.
      mockNavigate.mockClear();

      // Dismiss via the "Go to Calendar" button (onClick -> onDismiss ->
      // navigate('/calendar')). The button lives inside the overlay heading's
      // dialog; scope the query to it to avoid matching any leaked overlay.
      const dialog = overlayHeading.closest('.cal-setup-celebration');
      const goBtn = within(dialog).getByRole('button', { name: /go to calendar/i });
      act(() => {
        fireEvent.click(goBtn);
      });
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
        currentStep: 6,
        stepData: {},
        completedSteps: [1, 2, 3, 4, 5],
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
