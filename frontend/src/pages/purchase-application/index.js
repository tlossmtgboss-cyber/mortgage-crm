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

// Purchase-specific stage components
export { default as ProfileStage } from './ProfileStage';
export { default as IncomeStage } from './IncomeStage';
export { default as AssetsStage } from './AssetsStage';
export { default as PropertyStage } from './PropertyStage';
export { default as ReviewStage } from './ReviewStage';
export { default as PlanningStage } from './PlanningStage';

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
  buildNeedsList,
} from '../application-shared';
