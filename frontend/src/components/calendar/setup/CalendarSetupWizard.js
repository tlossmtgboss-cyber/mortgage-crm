/**
 * Perennia AI - Calendar Setup Wizard
 *
 * Guided 10-step setup wizard for Smart Calendar configuration.
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
 *   5. Notifications
 *   6. Integrations
 *   7. Cancellation Policy
 *   8. Team Setup
 *   9. Advanced Features
 *  10. Review & Activate
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '../../../utils/toast';
import SetupProgress from './SetupProgress';
import SetupStepWrapper from './SetupStepWrapper';
import WelcomeStepContent from './steps/WelcomeStep';
import '../../../styles/calendar-setup.css';

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
    id: 'notifications',
    number: 5,
    title: 'Notifications',
    label: 'Notify',
    description: 'Configure email and SMS reminders so your clients never miss an appointment.',
    icon: 'fa-bell',
    helpText: 'Set up automatic reminders at 24 hours, 2 hours, or 15 minutes before appointments. You can enable both email and SMS.',
    skippable: true,
  },
  {
    id: 'integrations',
    number: 6,
    title: 'Integrations',
    label: 'Integrate',
    description: 'Connect Google Calendar, Outlook, or other services to sync your appointments across platforms.',
    icon: 'fa-plug',
    helpText: 'Syncing with your existing calendar prevents double-bookings and keeps everything in one place.',
    skippable: true,
  },
  {
    id: 'cancellation-policy',
    number: 7,
    title: 'Cancellation Policy',
    label: 'Policy',
    description: 'Set your cancellation and rescheduling policies, including minimum notice requirements.',
    icon: 'fa-shield-alt',
    helpText: 'Define how far in advance clients must cancel or reschedule. This helps protect your time.',
    skippable: true,
  },
  {
    id: 'team-setup',
    number: 8,
    title: 'Team Setup',
    label: 'Team',
    description: 'Configure team scheduling, assignment strategies, and capacity limits for your team members.',
    icon: 'fa-users',
    helpText: 'If you manage a team, set up round-robin or load-balanced appointment distribution.',
    skippable: true,
  },
  {
    id: 'advanced-features',
    number: 9,
    title: 'Advanced Features',
    label: 'Advanced',
    description: 'Enable power features like buffer times, booking windows, waitlists, and recurring availability.',
    icon: 'fa-cogs',
    helpText: 'These optional features give you more control over your scheduling workflow.',
    skippable: true,
  },
  {
    id: 'review-activate',
    number: 10,
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
      <div className="placeholder-icon">
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

// ============================================================================
// Welcome step (imported from steps/WelcomeStep.js)
// ============================================================================
// WelcomeStepContent is imported at the top of this file.
// It provides timezone selection, schedule preset picker, and user
// personalization — replacing the original placeholder welcome screen.

// ============================================================================
// Review step
// ============================================================================

function ReviewStep({ stepData, completedSteps }) {
  const configuredCount = completedSteps.length;
  const skippedSteps = SETUP_STEPS.filter(
    s => s.number > 1 && s.number < 10 && !completedSteps.includes(s.number)
  );

  return (
    <div className="cal-setup-review">
      <div className="review-icon">
        <i className="fas fa-clipboard-check"></i>
      </div>
      <h2>Review Your Setup</h2>
      <p className="review-summary">
        You have configured {configuredCount} of {TOTAL_STEPS} steps.
        {skippedSteps.length > 0 && ' You can always come back to the skipped steps from Calendar Settings.'}
      </p>

      <div className="review-checklist">
        {SETUP_STEPS.slice(1, -1).map(step => {
          const isCompleted = completedSteps.includes(step.number);
          return (
            <div key={step.id} className={`review-item ${isCompleted ? 'completed' : 'skipped'}`}>
              <i className={`fas ${isCompleted ? 'fa-check-circle' : 'fa-circle'}`}></i>
              <span>{step.title}</span>
              <span className="review-status">
                {isCompleted ? 'Configured' : 'Skipped'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================================
// Celebration overlay
// ============================================================================

function CelebrationOverlay({ onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 4000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  return (
    <div className="cal-setup-celebration" role="alert" aria-live="assertive">
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
        <div className="celebration-icon">
          <i className="fas fa-check-circle"></i>
        </div>
        <h2>Your Calendar is Live!</h2>
        <p>Clients can now book appointments with you online.</p>
        <button className="btn-primary" onClick={onDismiss}>
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
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.currentStep) setCurrentStep(parsed.currentStep);
        if (parsed.stepData) setStepData(parsed.stepData);
        if (parsed.completedSteps) setCompletedSteps(parsed.completedSteps);
        if (parsed.skippedSteps) setSkippedSteps(parsed.skippedSteps);
      }
    } catch (e) {
      console.error('Failed to load setup progress:', e);
    }
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
    transitionTo(currentStep - 1, 'backward');
  }, [currentStep, transitionTo]);

  const handleSkip = useCallback(() => {
    if (currentStep >= TOTAL_STEPS) return;
    const stepDef = SETUP_STEPS[currentStep - 1];
    if (!stepDef.skippable) return;

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
    persistProgress();
    setAutoSaveStatus('Progress saved');
    toast.success('Your setup progress has been saved. You can resume anytime.');
    setTimeout(() => {
      navigate('/calendar-settings');
    }, 500);
  }, [persistProgress, navigate]);

  const handleActivate = useCallback(() => {
    // Mark step 10 as completed
    setCompletedSteps(prev => {
      if (prev.includes(TOTAL_STEPS)) return prev;
      return [...prev, TOTAL_STEPS];
    });

    // Clear stored progress
    localStorage.removeItem(STORAGE_KEY);

    // Show celebration
    setShowCelebration(true);
  }, []);

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

  function renderStepContent() {
    // Check for a custom component passed via stepComponents prop
    const CustomComponent = stepComponents[stepDef.id];
    if (CustomComponent) {
      return (
        <CustomComponent
          stepData={stepData[stepDef.id] || {}}
          onChange={(data) => handleStepDataChange(stepDef.id, data)}
          allStepData={stepData}
        />
      );
    }

    // Built-in steps
    if (currentStep === 1) {
      return (
        <WelcomeStepContent
          stepData={stepData['welcome'] || {}}
          onChange={(data) => handleStepDataChange('welcome', data)}
          allStepData={stepData}
        />
      );
    }

    if (currentStep === TOTAL_STEPS) {
      return (
        <ReviewStep
          stepData={stepData}
          completedSteps={completedSteps}
        />
      );
    }

    // Placeholder for unimplemented steps
    return <PlaceholderStep step={stepDef} />;
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
            <span className={`cal-setup-autosave ${autoSaveStatus === 'Saved' ? 'saved' : ''}`}>
              {autoSaveStatus === 'Saving...' && <i className="fas fa-spinner fa-spin"></i>}
              {autoSaveStatus === 'Saved' && <i className="fas fa-check"></i>}
              {' '}{autoSaveStatus}
            </span>
          )}
          <button
            onClick={handleSaveAndExit}
            className="btn-secondary cal-setup-save-exit"
          >
            <i className="fas fa-sign-out-alt"></i>
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
              <i className="fas fa-arrow-left"></i> Back
            </button>
          )}
        </div>
        <div className="cal-setup-footer-center">
          <span className="cal-setup-progress-text">
            {progressPercent}% complete
          </span>
        </div>
        <div className="cal-setup-footer-right">
          {isLastStep ? (
            <button
              onClick={handleActivate}
              className="btn-primary cal-setup-activate-btn"
              disabled={isAnimating}
            >
              <i className="fas fa-rocket"></i> Activate Calendar
            </button>
          ) : (
            <button
              onClick={handleNext}
              className="btn-primary"
              disabled={isAnimating}
              aria-label={`Continue to step ${currentStep + 1}`}
            >
              {isFirstStep ? 'Get Started' : 'Next'} <i className="fas fa-arrow-right"></i>
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
