/**
 * Purchase Application - Module Index
 *
 * Exports all purchase-specific configuration (stages, questions,
 * document requirements) and re-exports shared components.
 */

// Purchase-specific configuration
export { STAGES, VISIBLE_STAGES, CATEGORY_UNLOCK_STAGE } from './stages';
export { DECLARATION_QUESTIONS } from './declarationQuestions';
export { PLANNING_QUESTIONS } from './planningQuestions';
export { getRequiredDocuments } from './documentRequirements';

// Re-export shared components for convenience
export {
  Icon,
  ProgressHeader,
  DocumentsSidebar,
  SaveProgressModal,
  SubmissionSuccess,
  MicroWinToast,
  AccountStage,
  DeclarationsStage,
  ScheduleStage,
  COMMON_EMPLOYERS,
  US_STATES,
  getApiUrl,
  shouldShowQuestion,
  getVisibleQuestions,
  calculateProgress,
  getStageMicroWin,
  getEnabledStages,
  getEnabledQuestions,
  buildRedirectUrl,
} from '../application-shared';
