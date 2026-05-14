/**
 * Shared components and utilities for mortgage application forms.
 * Used by both PurchaseApplication and RefinanceApplication.
 */

// Components
export { default as Icon } from './Icon';
export { default as ProgressHeader } from './ProgressHeader';
export { default as DocumentsSidebar } from './DocumentsSidebar';
export { default as SaveProgressModal } from './SaveProgressModal';
export { default as SubmissionSuccess } from './SubmissionSuccess';
export { default as MicroWinToast } from './MicroWinToast';
export { default as AccountStage } from './AccountStage';
export { default as DeclarationsStage } from './DeclarationsStage';
export { default as ScheduleStage } from './ScheduleStage';

// Constants
export { COMMON_EMPLOYERS, US_STATES, getApiUrl } from './constants';

// Helpers
export {
  shouldShowQuestion,
  getVisibleQuestions,
  calculateProgress,
  getStageMicroWin,
  getEnabledStages,
  getEnabledQuestions,
  buildRedirectUrl,
} from './helpers';
