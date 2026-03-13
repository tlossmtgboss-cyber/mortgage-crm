/**
 * useCalendarTour - Tour state management hook
 *
 * Tracks current step, active/completed status, and persists
 * completion to localStorage so the tour is only auto-shown once.
 *
 * Provides: start, next, back, skip, complete, restart
 */

import { useState, useCallback, useEffect, useRef } from 'react';

const STORAGE_KEY = 'perennia_calendar_tour';
const SETUP_STORAGE_KEY = 'perennia_calendar_setup_progress';

/**
 * Tour step definitions.
 * `target` is a CSS selector for the element to spotlight.
 * Falls back gracefully if the element is not in the DOM.
 */
export const TOUR_STEPS = [
  {
    id: 'calendar-grid',
    target: '.calendar-main',
    title: 'Your Calendar',
    description:
      'This is your calendar view. You can see all your appointments, meetings, and events at a glance. Click any date to add a new event.',
    placement: 'left',
  },
  {
    id: 'view-switcher',
    target: '.view-switcher',
    title: 'View Switcher',
    description:
      'Switch between Day, 3-Day, Week, and Month views to see your schedule the way that works best for you.',
    placement: 'bottom',
  },
  {
    id: 'add-event',
    target: '.btn-add-event',
    title: 'Add Appointment',
    description:
      'Click here to quickly add a new appointment or calendar event. You can also click directly on a time slot in Day or Week views.',
    placement: 'bottom',
  },
  {
    id: 'sidebar',
    target: '.appointments-sidebar',
    title: 'Appointments Sidebar',
    description:
      'Your upcoming appointments are listed here. Filter by type, search by name, or use labels to organize them.',
    placement: 'right',
  },
  {
    id: 'search',
    target: '.btn-calendar-search',
    title: 'Search',
    description:
      'Find any appointment instantly. Use the search button or press Ctrl+K (Cmd+K on Mac) to open the advanced search overlay.',
    placement: 'bottom',
  },
  {
    id: 'quick-actions',
    target: '.calendar-main',
    title: 'Quick Actions',
    description:
      'Right-click on any time slot or appointment to access quick actions: block time, duplicate, reschedule, and more.',
    placement: 'left',
  },
  {
    id: 'drag-drop',
    target: '.calendar-main',
    title: 'Drag & Drop',
    description:
      'In Day and Week views, drag any appointment to a new time slot to reschedule it. A confirmation dialog keeps things safe.',
    placement: 'left',
  },
  {
    id: 'settings',
    target: '.btn-calendar-settings',
    title: 'Settings',
    description:
      'Configure your availability, appointment types, booking page, notifications, and integrations from Calendar Settings.',
    placement: 'bottom',
  },
  {
    id: 'shortcuts',
    target: '.calendar-header',
    title: 'Keyboard Shortcuts',
    description:
      'Power user? Press "?" to see all keyboard shortcuts. Navigate with arrow keys, switch views with 1-4, and more.',
    placement: 'bottom',
  },
  {
    id: 'all-set',
    target: '.calendar-header',
    title: "You're All Set!",
    description: null, // Custom content rendered by the component
    placement: 'bottom',
    isFinal: true,
  },
];

/**
 * Read persisted tour state from localStorage.
 */
function getPersistedState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return JSON.parse(raw);
    }
  } catch {
    // ignore
  }
  return null;
}

/**
 * Persist tour state to localStorage.
 */
function persistState(state) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
}

/**
 * Check whether the calendar setup wizard has been completed.
 */
function isSetupWizardComplete() {
  try {
    const raw = localStorage.getItem(SETUP_STORAGE_KEY);
    if (raw) {
      const data = JSON.parse(raw);
      return data.completed === true;
    }
  } catch {
    // ignore
  }
  // If there is no setup progress at all, we still allow the tour
  // (the user may have dismissed or never seen the wizard).
  return true;
}

export default function useCalendarTour() {
  const [currentStep, setCurrentStep] = useState(0);
  const [isActive, setIsActive] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [dontShowAgain, setDontShowAgain] = useState(false);
  const hasAutoStarted = useRef(false);

  // Restore persisted state on mount
  useEffect(() => {
    const saved = getPersistedState();
    if (saved) {
      setIsCompleted(saved.completed || false);
      setDontShowAgain(saved.dontShowAgain || false);
    }
  }, []);

  // Auto-start logic: show tour on first visit if setup is done and tour not completed
  useEffect(() => {
    if (hasAutoStarted.current) return;
    const saved = getPersistedState();
    const alreadyDone = saved?.completed || saved?.dontShowAgain;
    if (!alreadyDone && isSetupWizardComplete()) {
      // Small delay so the calendar has time to render its elements
      const timer = setTimeout(() => {
        setIsActive(true);
        setCurrentStep(0);
        hasAutoStarted.current = true;
      }, 800);
      return () => clearTimeout(timer);
    }
    hasAutoStarted.current = true;
  }, []);

  const start = useCallback(() => {
    setCurrentStep(0);
    setIsActive(true);
    setIsCompleted(false);
  }, []);

  const next = useCallback(() => {
    setCurrentStep((prev) => {
      const nextIdx = prev + 1;
      if (nextIdx >= TOUR_STEPS.length) {
        // Tour finished
        setIsActive(false);
        setIsCompleted(true);
        persistState({ completed: true, dontShowAgain, completedAt: new Date().toISOString() });
        return prev;
      }
      return nextIdx;
    });
  }, [dontShowAgain]);

  const back = useCallback(() => {
    setCurrentStep((prev) => Math.max(0, prev - 1));
  }, []);

  const skip = useCallback(() => {
    setIsActive(false);
    // Mark as completed so it does not auto-start again
    setIsCompleted(true);
    persistState({ completed: true, dontShowAgain: false, skippedAt: new Date().toISOString() });
  }, []);

  const complete = useCallback(() => {
    setIsActive(false);
    setIsCompleted(true);
    persistState({ completed: true, dontShowAgain, completedAt: new Date().toISOString() });
  }, [dontShowAgain]);

  const toggleDontShowAgain = useCallback((value) => {
    setDontShowAgain(value);
  }, []);

  // Restart is used from Settings or the "?" button when the tour is already done
  const restart = useCallback(() => {
    setCurrentStep(0);
    setIsActive(true);
    setIsCompleted(false);
    setDontShowAgain(false);
  }, []);

  return {
    // State
    currentStep,
    isActive,
    isCompleted,
    dontShowAgain,
    totalSteps: TOUR_STEPS.length,
    steps: TOUR_STEPS,
    currentStepData: TOUR_STEPS[currentStep] || null,

    // Actions
    start,
    next,
    back,
    skip,
    complete,
    restart,
    toggleDontShowAgain,
  };
}
