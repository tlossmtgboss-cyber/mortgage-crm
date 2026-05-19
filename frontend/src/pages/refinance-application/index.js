/**
 * Refinance Application - Module Index
 *
 * Exports all refinance-specific configuration (stages, questions,
 * document requirements) and re-exports shared components.
 */

// Refinance-specific configuration
export { STAGES, VISIBLE_STAGES, CATEGORY_UNLOCK_STAGE } from './stages';
export { DECLARATION_QUESTIONS } from './declarationQuestions';
export { PLANNING_QUESTIONS } from './planningQuestions';
export { getRequiredDocuments } from './documentRequirements';

// Refinance-specific stage components
export { default as ProfileStage } from './ProfileStage';
export { default as IncomeStage } from './IncomeStage';
export { default as PropertyStage } from './PropertyStage';
export { default as GoalsStage } from './GoalsStage';
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
