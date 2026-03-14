/**
 * Perennia AI - Smart Calendar Setup Steps
 *
 * Barrel export for all 10 guided setup step components.
 * Also exports STEP_CONFIG, the metadata array consumed by
 * CalendarSetupWizard to drive step rendering, navigation,
 * and progress tracking.
 */

// ============================================================================
// Step components
// ============================================================================

export { default as WelcomeStep } from './WelcomeStep';
export { default as WorkingHoursStep } from './WorkingHoursStep';
export { default as AppointmentTypesStep } from './AppointmentTypesStep';
export { default as BookingPageStep } from './BookingPageStep';
export { default as NotificationsStep } from './NotificationsStep';
export { default as IntegrationsStep } from './IntegrationsStep';
export { default as CancellationPolicyStep } from './CancellationPolicyStep';
export { default as TeamSetupStep } from './TeamSetupStep';
export { default as AdvancedFeaturesStep } from './AdvancedFeaturesStep';
export { default as ReviewStep } from './ReviewStep';

// ============================================================================
// Step configuration metadata
// ============================================================================

/**
 * Each entry describes one step of the guided setup flow.
 *
 * Fields:
 *   number       - 1-based step ordinal
 *   id           - slug used as key in stepData and localStorage
 *   title        - full title shown in the step header
 *   label        - short label for progress stepper
 *   description  - one-line description shown beneath the title
 *   icon         - FontAwesome class (without "fas" prefix) for the step icon
 *   required     - if true, the step must be completed before activation
 *   skippable    - if true, the user can skip this step
 *   component    - name of the exported component, or null if handled inline
 */
export const STEP_CONFIG = [
  {
    number: 1,
    id: 'welcome',
    title: 'Welcome',
    label: 'Welcome',
    description: 'Welcome to Smart Calendar setup. We will walk you through everything you need.',
    icon: 'fa-hand-sparkles',
    required: true,
    skippable: false,
    component: 'WelcomeStep',
  },
  {
    number: 2,
    id: 'timezone-hours',
    title: 'Timezone & Business Hours',
    label: 'Hours',
    description: 'Set your timezone and define when you are available for appointments.',
    icon: 'fa-clock',
    required: true,
    skippable: false,
    component: 'WorkingHoursStep',
  },
  {
    number: 3,
    id: 'appointment-types',
    title: 'Appointment Types',
    label: 'Types',
    description: 'Create the types of appointments clients can book.',
    icon: 'fa-list-alt',
    required: true,
    skippable: true,
    component: 'AppointmentTypesStep',
  },
  {
    number: 4,
    id: 'booking-page',
    title: 'Booking Page',
    label: 'Booking',
    description: 'Customize the appearance of your public booking page.',
    icon: 'fa-palette',
    required: false,
    skippable: true,
    component: 'BookingPageStep',
  },
  {
    number: 5,
    id: 'notifications',
    title: 'Notifications',
    label: 'Notify',
    description: 'Configure email and SMS reminders so clients never miss an appointment.',
    icon: 'fa-bell',
    required: false,
    skippable: true,
    component: 'NotificationsStep',
  },
  {
    number: 6,
    id: 'integrations',
    title: 'Integrations',
    label: 'Integrate',
    description: 'Connect Google Calendar, Outlook, or other services to sync events.',
    icon: 'fa-plug',
    required: false,
    skippable: true,
    component: 'IntegrationsStep',
  },
  {
    number: 7,
    id: 'cancellation-policy',
    title: 'Cancellation Policy',
    label: 'Policy',
    description: 'Set your cancellation and rescheduling policies.',
    icon: 'fa-shield-alt',
    required: false,
    skippable: true,
    component: 'CancellationPolicyStep',
  },
  {
    number: 8,
    id: 'team-setup',
    title: 'Team Setup',
    label: 'Team',
    description: 'Configure team scheduling, assignment strategies, and capacity limits.',
    icon: 'fa-users',
    required: false,
    skippable: true,
    component: 'TeamSetupStep',
  },
  {
    number: 9,
    id: 'advanced-features',
    title: 'Advanced Features',
    label: 'Advanced',
    description: 'Enable power features like buffer times, waitlists, and recurring availability.',
    icon: 'fa-cogs',
    required: false,
    skippable: true,
    component: 'AdvancedFeaturesStep',
  },
  {
    number: 10,
    id: 'review-activate',
    title: 'Review & Activate',
    label: 'Activate',
    description: 'Review your configuration and activate your Smart Calendar.',
    icon: 'fa-rocket',
    required: true,
    skippable: false,
    component: 'ReviewStep',
  },
];

export const TOTAL_STEPS = STEP_CONFIG.length;
