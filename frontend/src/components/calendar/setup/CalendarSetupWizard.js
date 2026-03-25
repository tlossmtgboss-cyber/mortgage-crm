/**
 * Perennia AI - Calendar Setup Wizard
 *
 * Guided 6-step setup wizard for Smart Calendar configuration.
 * Persists progress to localStorage so users can resume later.
 * Accepts step components as configuration — actual step content
 * will be built by other agents. Placeholder content is rendered
 * for steps that have not yet been implemented.
 *
 * Steps:
 *   1. Welcome
 *   2. Timezone & Hours
 *   3. Appointment Types
 *   4. Booking Page
 *   5. Integrations
 *   6. Review & Activate
 *
 * Steps moved to Calendar Settings (configurable post-setup):
 *   - Notifications
 *   - Cancellation Policy
 *   - Team Setup
 *   - Advanced Features
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '../../../utils/toast';
import { trackFeature } from '../../../services/analytics';
import ErrorBoundary from '../../common/ErrorBoundary';
import SetupProgress from './SetupProgress';
import SetupStepWrapper from './SetupStepWrapper';
import WelcomeStepContent from './steps/WelcomeStep';
import WorkingHoursStepContent from './steps/WorkingHoursStep';
import AppointmentTypesStepContent from './steps/AppointmentTypesStep';
import BookingPageStepContent from './steps/BookingPageStep';
import IntegrationsStepContent from './steps/IntegrationsStep';
import ReviewStepContent from './steps/ReviewStep';
import '../../../styles/calendar-setup.css';

// ============================================================================
// Wizard analytics utility
// ============================================================================

function trackWizardEvent(eventName, data = {}) {
  try {
    window.dispatchEvent(new CustomEvent('perennia:analytics', {
      detail: {
        category: 'calendar_setup_wizard',
        event: eventName,
        timestamp: new Date().toISOString(),
        ...data,
      }
    }));
    // Also store in localStorage for internal dashboard consumption
    const key = 'perennia_wizard_analytics';
    const existing = JSON.parse(localStorage.getItem(key) || '[]');
    existing.push({ event: eventName, ...data, timestamp: new Date().toISOString() });
    // Keep last 100 events
    if (existing.length > 100) existing.splice(0, existing.length - 100);
    localStorage.setItem(key, JSON.stringify(existing));
  } catch {
    // Analytics should never break the app
  }
  // Also fire through the shared analytics service (fire-and-forget)
  try {
    trackFeature('calendar_setup_wizard', eventName, data);
  } catch {
    // Silently ignore
  }
}

// ============================================================================
// Step definitions
// ============================================================================

const SETUP_STEPS = [
  {
    id: 'welcome',
    number: 1,
    title: 'Welcome',
    label: 'Welcome',
    description: 'Welcome to Smart Calendar setup. We will walk you through everything you need to get your calendar ready for clients.',
    icon: 'fa-hand-sparkles',
    helpText: 'This is a quick overview of what to expect during setup. You can skip any step and come back later.',
    skippable: false,
  },
  {
    id: 'timezone-hours',
    number: 2,
    title: 'Timezone & Business Hours',
    label: 'Hours',
    description: 'Set your timezone and define when you are available for appointments each day of the week.',
    icon: 'fa-clock',
    helpText: 'Your timezone determines how appointment times are displayed to clients. Business hours control when bookings can be made.',
    skippable: false,
  },
  {
    id: 'appointment-types',
    number: 3,
    title: 'Appointment Types',
    label: 'Types',
    description: 'Create the types of appointments clients can book, such as consultations, pre-approval reviews, or closing walkthroughs.',
    icon: 'fa-list-alt',
    helpText: 'You can create multiple appointment types with different durations, colors, and descriptions. These appear on your public booking page.',
    skippable: true,
  },
  {
    id: 'booking-page',
    number: 4,
    title: 'Booking Page',
    label: 'Booking',
    description: 'Customize the appearance of your public booking page with your branding, logo, and personal tagline.',
    icon: 'fa-palette',
    helpText: 'Your booking page is the link you share with clients. Make it look professional with your branding.',
    skippable: true,
  },
  {
    id: 'integrations',
    number: 5,
    title: 'Integrations',
    label: 'Integrate',
    description: 'Connect Google Calendar, Outlook, or other services to sync your appointments across platforms.',
    icon: 'fa-plug',
    helpText: 'Syncing with your existing calendar prevents double-bookings and keeps everything in one place.',
    skippable: true,
  },
  {
    id: 'review-activate',
    number: 6,
    title: 'Review & Activate',
    label: 'Activate',
    description: 'Review your configuration and activate your Smart Calendar. You can always adjust settings later.',
    icon: 'fa-rocket',
    helpText: 'Take a final look at everything before going live. Nothing is permanent — you can change any setting from Calendar Settings.',
    skippable: false,
  },
];

const TOTAL_STEPS = SETUP_STEPS.length;
const STORAGE_KEY = 'perennia_calendar_setup_progress';

// ============================================================================
// Default placeholder step component
// ============================================================================

function PlaceholderStep({ step }) {
  return (
    <div className="cal-setup-placeholder">
      <div className="placeholder-icon" aria-hidden="true">
        <i className={`fas ${step.icon}`}></i>
      </div>
      <h3>{step.title}</h3>
      <p>{step.description}</p>
      <p className="placeholder-hint">
        This step will be configured with detailed options. For now, you can skip ahead or proceed to continue setup.
      </p>
    </div>
  );
}

// All 6 wizard step components are imported at the top of this file:
//   WelcomeStepContent, WorkingHoursStepContent, AppointmentTypesStepContent,
//   BookingPageStepContent, IntegrationsStepContent, ReviewStepContent
//
// Steps moved to Calendar Settings (still importable from ./steps/):
//   NotificationsStep, CancellationPolicyStep, TeamSetupStep, AdvancedFeaturesStep

// ============================================================================
// Celebration overlay
// ============================================================================

function CelebrationOverlay({ onDismiss }) {
  const dismissBtnRef = useRef(null);

  useEffect(() => {
    const timer = setTimeout(onDismiss, 4000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  // Focus the dismiss button on mount for keyboard accessibility
  useEffect(() => {
    if (dismissBtnRef.current) {
      dismissBtnRef.current.focus();
    }
  }, []);

  // Allow Escape to dismiss
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        onDismiss();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onDismiss]);

  return (
    <div
      className="cal-setup-celebration"
      role="alertdialog"
      aria-live="assertive"
      aria-label="Calendar activated successfully"
    >
      <div className="celebration-content">
        <div className="celebration-particles" aria-hidden="true">
          {Array.from({ length: 30 }).map((_, i) => (
            <span
              key={i}
              className="particle"
              style={{
                '--x': `${Math.random() * 100}%`,
                '--delay': `${Math.random() * 0.5}s`,
                '--color': ['#3b82f6', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'][i % 5],
              }}
            />
          ))}
        </div>
        <div className="celebration-icon" aria-hidden="true">
          <i className="fas fa-check-circle"></i>
        </div>
        <h2>Your Calendar is Live!</h2>
        <p>Clients can now book appointments with you online.</p>
        <button ref={dismissBtnRef} className="btn-primary" onClick={onDismiss}>
          Go to Calendar
        </button>
      </div>
    </div>
  );
}

// ============================================================================
// Main wizard component
// ============================================================================

export default function CalendarSetupWizard({ stepComponents = {} }) {
  const navigate = useNavigate();
  const contentRef = useRef(null);
  const announceRef = useRef(null);
  const wizardStartTime = useRef(Date.now());
  const stepStartTime = useRef(Date.now());

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  const [currentStep, setCurrentStep] = useState(1);
  const [stepData, setStepData] = useState({});
  const [completedSteps, setCompletedSteps] = useState([]);
  const [skippedSteps, setSkippedSteps] = useState([]);
  const [direction, setDirection] = useState('forward');
  const [isAnimating, setIsAnimating] = useState(false);
  const [showCelebration, setShowCelebration] = useState(false);
  const [autoSaveStatus, setAutoSaveStatus] = useState('');

  // ---------------------------------------------------------------------------
  // Load persisted progress on mount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    let resumed = false;
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.currentStep) setCurrentStep(parsed.currentStep);
        if (parsed.stepData) setStepData(parsed.stepData);
        if (parsed.completedSteps) setCompletedSteps(parsed.completedSteps);
        if (parsed.skippedSteps) setSkippedSteps(parsed.skippedSteps);
        resumed = !!(parsed.currentStep && parsed.currentStep > 1);
        if (resumed) {
          try {
            trackWizardEvent('wizard_resumed', {
              step: parsed.currentStep,
              stepName: SETUP_STEPS[parsed.currentStep - 1]?.label,
              stepsCompleted: (parsed.completedSteps || []).length,
            });
          } catch { /* analytics should never break the app */ }
        }
      }
    } catch (e) {
      console.error('Failed to load setup progress:', e);
    }
    // Track wizard start (fires on every mount, resumed or fresh)
    try {
      trackWizardEvent('wizard_started', { resumed });
    } catch { /* analytics should never break the app */ }
  }, []);

  // ---------------------------------------------------------------------------
  // Persist progress whenever it changes
  // ---------------------------------------------------------------------------
  const persistProgress = useCallback(() => {
    try {
      const payload = { currentStep, stepData, completedSteps, skippedSteps, updatedAt: new Date().toISOString() };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch (e) {
      console.error('Failed to save setup progress:', e);
    }
  }, [currentStep, stepData, completedSteps, skippedSteps]);

  useEffect(() => {
    persistProgress();
  }, [persistProgress]);

  // ---------------------------------------------------------------------------
  // Announce step changes to screen readers
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const stepDef = SETUP_STEPS[currentStep - 1];
    if (announceRef.current && stepDef) {
      announceRef.current.textContent = `Step ${currentStep} of ${TOTAL_STEPS}: ${stepDef.title}. ${stepDef.description}`;
    }
  }, [currentStep]);

  // ---------------------------------------------------------------------------
  // Focus management on step change
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (contentRef.current) {
      const heading = contentRef.current.querySelector('h2, h3');
      if (heading) {
        heading.setAttribute('tabIndex', '-1');
        heading.focus({ preventScroll: true });
      }
    }
    // Reset per-step timer on every step change
    stepStartTime.current = Date.now();
  }, [currentStep]);

  // ---------------------------------------------------------------------------
  // Keyboard navigation
  // ---------------------------------------------------------------------------
  useEffect(() => {
    function handleKeyDown(e) {
      // Do not intercept if user is in an input, textarea, or select
      const tag = e.target.tagName;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return;

      if (e.altKey && e.key === 'ArrowRight') {
        e.preventDefault();
        handleNext();
      } else if (e.altKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        handleBack();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep, completedSteps]);

  // ---------------------------------------------------------------------------
  // Step transition helper
  // ---------------------------------------------------------------------------
  const transitionTo = useCallback((nextStep, dir) => {
    if (isAnimating) return;
    setIsAnimating(true);
    setDirection(dir);

    // After the CSS exit animation completes, update the step
    setTimeout(() => {
      setCurrentStep(nextStep);
      setIsAnimating(false);
      // Scroll to top of wizard content
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }, 300);
  }, [isAnimating]);

  // ---------------------------------------------------------------------------
  // Navigation handlers
  // ---------------------------------------------------------------------------
  const handleNext = useCallback(() => {
    if (currentStep >= TOTAL_STEPS) return;

    // Track step completion
    try {
      trackWizardEvent('step_completed', {
        step: currentStep,
        stepName: SETUP_STEPS[currentStep - 1]?.label,
        timeOnStep: Date.now() - stepStartTime.current,
      });
    } catch { /* analytics should never break the app */ }

    // Mark current step as completed (unless already there)
    setCompletedSteps(prev => {
      if (prev.includes(currentStep)) return prev;
      return [...prev, currentStep];
    });

    // Remove from skipped if it was skipped before
    setSkippedSteps(prev => prev.filter(s => s !== currentStep));

    transitionTo(currentStep + 1, 'forward');
  }, [currentStep, transitionTo]);

  const handleBack = useCallback(() => {
    if (currentStep <= 1) return;

    try {
      trackWizardEvent('step_back', {
        step: currentStep,
        stepName: SETUP_STEPS[currentStep - 1]?.label,
        timeOnStep: Date.now() - stepStartTime.current,
      });
    } catch { /* analytics should never break the app */ }

    transitionTo(currentStep - 1, 'backward');
  }, [currentStep, transitionTo]);

  const handleSkip = useCallback(() => {
    if (currentStep >= TOTAL_STEPS) return;
    const stepDef = SETUP_STEPS[currentStep - 1];
    if (!stepDef.skippable) return;

    // Track skip
    try {
      trackWizardEvent('step_skipped', {
        step: currentStep,
        stepName: stepDef.label,
        timeOnStep: Date.now() - stepStartTime.current,
      });
    } catch { /* analytics should never break the app */ }

    // Mark as skipped
    setSkippedSteps(prev => {
      if (prev.includes(currentStep)) return prev;
      return [...prev, currentStep];
    });

    transitionTo(currentStep + 1, 'forward');
  }, [currentStep, transitionTo]);

  const handleGoToStep = useCallback((stepNumber) => {
    // Only allow going to completed steps or the current step + 1
    if (stepNumber === currentStep) return;
    if (completedSteps.includes(stepNumber) || skippedSteps.includes(stepNumber) || stepNumber <= Math.max(...completedSteps, 0) + 1) {
      const dir = stepNumber > currentStep ? 'forward' : 'backward';
      transitionTo(stepNumber, dir);
    }
  }, [currentStep, completedSteps, skippedSteps, transitionTo]);

  const handleSaveAndExit = useCallback(() => {
    // Track abandonment
    try {
      trackWizardEvent('wizard_abandoned', {
        lastStep: currentStep,
        lastStepName: SETUP_STEPS[currentStep - 1]?.label,
        stepsCompleted: completedSteps.length,
        stepsSkipped: skippedSteps.length,
        totalTime: Date.now() - wizardStartTime.current,
        timeOnStep: Date.now() - stepStartTime.current,
      });
    } catch { /* analytics should never break the app */ }

    persistProgress();
    setAutoSaveStatus('Progress saved');
    toast.success('Your setup progress has been saved. You can resume anytime.');
    setTimeout(() => {
      navigate('/calendar-settings');
    }, 500);
  }, [persistProgress, navigate, currentStep, completedSteps, skippedSteps]);

  const handleActivate = useCallback(() => {
    // Track wizard completion
    try {
      trackWizardEvent('wizard_completed', {
        totalTime: Date.now() - wizardStartTime.current,
        stepsCompleted: completedSteps.length + 1, // +1 for this final step
        stepsSkipped: skippedSteps.length,
        timeOnStep: Date.now() - stepStartTime.current,
      });
    } catch { /* analytics should never break the app */ }

    // Mark final step as completed
    setCompletedSteps(prev => {
      if (prev.includes(TOTAL_STEPS)) return prev;
      return [...prev, TOTAL_STEPS];
    });

    // Clear stored progress
    localStorage.removeItem(STORAGE_KEY);

    // Show celebration
    setShowCelebration(true);
  }, [completedSteps, skippedSteps]);

  const handleCelebrationDismiss = useCallback(() => {
    setShowCelebration(false);
    navigate('/calendar');
  }, [navigate]);

  // ---------------------------------------------------------------------------
  // Step data change handler (passed to step components)
  // ---------------------------------------------------------------------------
  const handleStepDataChange = useCallback((stepId, data) => {
    setStepData(prev => ({
      ...prev,
      [stepId]: { ...prev[stepId], ...data },
    }));

    // Visual auto-save feedback
    setAutoSaveStatus('Saving...');
    setTimeout(() => {
      setAutoSaveStatus('Saved');
      setTimeout(() => setAutoSaveStatus(''), 2000);
    }, 300);
  }, []);

  // ---------------------------------------------------------------------------
  // Resolve the component for the current step
  // ---------------------------------------------------------------------------
  const stepDef = SETUP_STEPS[currentStep - 1];
  const isFirstStep = currentStep === 1;
  const isLastStep = currentStep === TOTAL_STEPS;
  const canSkip = stepDef && stepDef.skippable;

  // ---------------------------------------------------------------------------
  // Stable onChange callbacks per step ID.
  // Inline arrow functions like (data) => handleStepDataChange('welcome', data)
  // create a new reference on every render, which causes infinite render loops
  // in step components that include onChange in useEffect dependency arrays.
  // These memoized callbacks maintain a stable reference.
  // ---------------------------------------------------------------------------
  const onChangeWelcome = useCallback((data) => handleStepDataChange('welcome', data), [handleStepDataChange]);
  const onChangeTimezone = useCallback((data) => handleStepDataChange('timezone-hours', data), [handleStepDataChange]);
  const onChangeAppointmentTypes = useCallback((types) => handleStepDataChange('appointment-types', { types }), [handleStepDataChange]);
  const onChangeBookingPage = useCallback((data) => handleStepDataChange('booking-page', data), [handleStepDataChange]);
  const onChangeIntegrations = useCallback((data) => handleStepDataChange('integrations', data), [handleStepDataChange]);
  const noopDirty = useCallback(() => {}, []);

  // Stable empty-object references to avoid re-renders from new {} on each render
  const emptyObj = useMemo(() => ({}), []);

  // Error boundary fallback for step crashes
  const stepErrorFallback = useCallback((error, resetFn) => (
    <div className="cal-setup-step-error">
      <div className="cal-setup-step-error-icon" aria-hidden="true">
        <i className="fas fa-exclamation-triangle"></i>
      </div>
      <h3>Something went wrong</h3>
      <p>This step encountered an error. Your progress on other steps is safe.</p>
      <button onClick={resetFn} className="btn-secondary">
        Try Again
      </button>
    </div>
  ), []);

  function renderStepContent() {
    let content;

    // Check for a custom component passed via stepComponents prop
    const CustomComponent = stepComponents[stepDef.id];
    if (CustomComponent) {
      content = (
        <CustomComponent
          stepData={stepData[stepDef.id] || emptyObj}
          onChange={onChangeWelcome}
          allStepData={stepData}
        />
      );
    }

    // Step 1: Welcome & Timezone
    else if (currentStep === 1) {
      content = (
        <WelcomeStepContent
          stepData={stepData['welcome'] || emptyObj}
          onChange={onChangeWelcome}
          allStepData={stepData}
        />
      );
    }

    // Step 2: Working Hours
    else if (currentStep === 2) {
      content = (
        <WorkingHoursStepContent
          stepData={stepData['timezone-hours'] || emptyObj}
          onChange={onChangeTimezone}
          allStepData={stepData}
        />
      );
    }

    // Step 3: Appointment Types (legacy props: onStepComplete, initialTypes)
    else if (currentStep === 3) {
      content = (
        <AppointmentTypesStepContent
          onStepComplete={onChangeAppointmentTypes}
          initialTypes={(stepData['appointment-types'] || emptyObj).types || null}
        />
      );
    }

    // Step 4: Booking Page (legacy props: onStepComplete, onDirty, initialData)
    else if (currentStep === 4) {
      content = (
        <BookingPageStepContent
          onStepComplete={onChangeBookingPage}
          onDirty={noopDirty}
          initialData={stepData['booking-page'] || null}
        />
      );
    }

    // Step 5: Integrations (wizard props)
    else if (currentStep === 5) {
      content = (
        <IntegrationsStepContent
          stepData={stepData['integrations'] || emptyObj}
          onChange={onChangeIntegrations}
          allStepData={stepData}
        />
      );
    }

    // Step 6: Review & Activate
    else if (currentStep === TOTAL_STEPS) {
      content = (
        <ReviewStepContent
          stepData={stepData}
          completedSteps={completedSteps}
          onGoToStep={handleGoToStep}
          onActivate={handleActivate}
        />
      );
    }

    // Fallback placeholder for any unexpected step
    else {
      content = <PlaceholderStep step={stepDef} />;
    }

    // Wrap every step in an ErrorBoundary so one crashing step
    // does not tear down the entire wizard
    return (
      <ErrorBoundary
        key={currentStep}
        fallback={stepErrorFallback}
        resetKeys={[currentStep]}
      >
        {content}
      </ErrorBoundary>
    );
  }

  // ---------------------------------------------------------------------------
  // Determine animation class
  // ---------------------------------------------------------------------------
  const animationClass = isAnimating
    ? direction === 'forward'
      ? 'cal-setup-slide-exit-left'
      : 'cal-setup-slide-exit-right'
    : direction === 'forward'
      ? 'cal-setup-slide-enter-right'
      : 'cal-setup-slide-enter-left';

  // ---------------------------------------------------------------------------
  // Progress percentage
  // ---------------------------------------------------------------------------
  const progressPercent = Math.round((completedSteps.length / TOTAL_STEPS) * 100);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="cal-setup-wizard">
      {/* Screen reader announcement region */}
      <div
        ref={announceRef}
        className="sr-only"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      />

      {/* Header */}
      <div className="cal-setup-header">
        <div className="cal-setup-header-left">
          <button
            onClick={() => navigate('/calendar-settings')}
            className="cal-setup-back-btn"
            aria-label="Back to Calendar Settings"
          >
            <i className="fas fa-arrow-left"></i>
          </button>
          <div>
            <h1>Calendar Setup</h1>
            <p className="cal-setup-subtitle">
              {isLastStep
                ? 'Almost there — review and activate.'
                : `Step ${currentStep} of ${TOTAL_STEPS}`
              }
            </p>
          </div>
        </div>
        <div className="cal-setup-header-right">
          {autoSaveStatus && (
            <span className={`cal-setup-autosave ${autoSaveStatus === 'Saved' ? 'saved' : ''}`} role="status" aria-live="polite">
              {autoSaveStatus === 'Saving...' && <i className="fas fa-spinner fa-spin" aria-hidden="true"></i>}
              {autoSaveStatus === 'Saved' && <i className="fas fa-check" aria-hidden="true"></i>}
              {' '}{autoSaveStatus}
            </span>
          )}
          <button
            onClick={handleSaveAndExit}
            className="btn-secondary cal-setup-save-exit"
          >
            <i className="fas fa-sign-out-alt" aria-hidden="true"></i>
            <span className="btn-label">Save & Exit</span>
          </button>
        </div>
      </div>

      {/* Progress */}
      <SetupProgress
        currentStep={currentStep}
        totalSteps={TOTAL_STEPS}
        completedSteps={completedSteps}
        skippedSteps={skippedSteps}
        steps={SETUP_STEPS}
        onStepClick={handleGoToStep}
      />

      {/* Step content */}
      <div className="cal-setup-content-area" ref={contentRef}>
        <div className={`cal-setup-step-animate ${animationClass}`}>
          <SetupStepWrapper
            step={stepDef}
            currentStep={currentStep}
            totalSteps={TOTAL_STEPS}
            canSkip={canSkip}
            onSkip={handleSkip}
          >
            {renderStepContent()}
          </SetupStepWrapper>
        </div>
      </div>

      {/* Footer navigation */}
      <div className="cal-setup-footer" role="navigation" aria-label="Setup step navigation">
        <div className="cal-setup-footer-left">
          {!isFirstStep && (
            <button
              onClick={handleBack}
              className="btn-secondary"
              disabled={isAnimating}
              aria-label={`Go back to step ${currentStep - 1}`}
            >
              <i className="fas fa-arrow-left" aria-hidden="true"></i> Back
            </button>
          )}
        </div>
        <div className="cal-setup-footer-center">
          <span className="cal-setup-progress-text" role="status" aria-live="polite" aria-atomic="true">
            {progressPercent}% complete
          </span>
        </div>
        <div className="cal-setup-footer-right">
          {isLastStep ? (
            <button
              onClick={handleActivate}
              className="btn-primary cal-setup-activate-btn"
              disabled={isAnimating}
              aria-label="Activate your Smart Calendar"
            >
              <i className="fas fa-rocket" aria-hidden="true"></i> Activate Calendar
            </button>
          ) : (
            <button
              onClick={handleNext}
              className="btn-primary"
              disabled={isAnimating}
              aria-label={`Continue to step ${currentStep + 1}`}
            >
              {isFirstStep ? 'Get Started' : 'Next'} <i className="fas fa-arrow-right" aria-hidden="true"></i>
            </button>
          )}
        </div>
      </div>

      {/* Celebration overlay */}
      {showCelebration && (
        <CelebrationOverlay onDismiss={handleCelebrationDismiss} />
      )}
    </div>
  );
}
