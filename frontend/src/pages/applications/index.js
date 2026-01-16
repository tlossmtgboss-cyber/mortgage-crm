/**
 * Applications Module Export
 * Central export point for all application-related components
 */

// Entry points
export { default as NewPurchaseApplication } from './NewPurchaseApplication';
export { default as NewRefinanceApplication } from './NewRefinanceApplication';
export { default as ApplicationDemo } from './ApplicationDemo';

// Context
export { ApplicationProvider, useApplication } from './contexts/ApplicationContext';
export { ActionTypes, createInitialState } from './contexts/applicationReducer';

// Hooks
export { useQuestionNavigation } from './hooks/useQuestionNavigation';
export { useApplicationPersistence } from './hooks/useApplicationPersistence';
export {
  useDocumentChecklist,
  getRequiredDocuments,
  DocumentCategories,
} from './hooks/useDocumentChecklist';

// Config
export { PURCHASE_STAGES, REFINANCE_STAGES, getStages, getVisibleStages } from './config/stageConfig';
export { allPurchaseQuestions, QuestionTypes } from './config/purchaseQuestions';
export { allRefinanceQuestions } from './config/refinanceQuestions';

// Components
export { default as ApplicationShell } from './components/ApplicationShell';
export { default as QuestionRenderer } from './components/QuestionRenderer';
export { default as StageRenderer } from './components/StageRenderer';

// Input components
export * from './components/inputs';

// Stage components
export { ReviewStage } from './components/stages';
