/**
 * ReconciliationCenter - Module Index
 *
 * Exports all reconciliation-center configuration, helpers, tab panels, and modals.
 */

// Constants
export { ALL_STAGES, FIELD_TYPE_OPTIONS } from './constants';

// Helpers
export {
  cleanEmailPreview,
  getConfidenceColor,
  getConfidenceBadge,
  formatFieldName,
  extractNameFromEmail,
  formatFieldValue,
  formatDisplayValue,
} from './helpers';

// Shared sub-components
export { default as EntityTypeSelector } from './EntityTypeSelector';
export { default as EditableFieldsGrid } from './EditableFieldsGrid';

// Tab panels
export { default as NewTab } from './NewTab';
export { default as AutoProcessingTab } from './AutoProcessingTab';
export { default as PendingReviewTab } from './PendingReviewTab';
export { default as CompletedTab } from './CompletedTab';
export { default as CallDraftsTab } from './CallDraftsTab';

// Modals
export { default as NoMatchDialog } from './NoMatchDialog';
export { default as StatusCorrectionModal } from './StatusCorrectionModal';
export { default as AppliedDataModal } from './AppliedDataModal';

// Hook
export { default as useReconciliation } from './useReconciliation';
