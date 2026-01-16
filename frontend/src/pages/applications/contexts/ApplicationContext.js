/**
 * Application Context
 * Provides application state and actions to all child components
 */

import React, { createContext, useContext, useReducer, useCallback, useMemo } from 'react';
import { applicationReducer, createInitialState, ActionTypes } from './applicationReducer';

// Create context
const ApplicationContext = createContext(null);

// Provider component
export function ApplicationProvider({
  children,
  applicationType = 'purchase',
  initialState = null,
  workspaceSlug = null,
}) {
  // Initialize state
  const [state, dispatch] = useReducer(
    applicationReducer,
    initialState || createInitialState(applicationType)
  );

  // Set workspace slug if provided
  React.useEffect(() => {
    if (workspaceSlug && workspaceSlug !== state.workspaceSlug) {
      dispatch({
        type: ActionTypes.SET_FIELDS,
        fields: { workspaceSlug }
      });
    }
  }, [workspaceSlug, state.workspaceSlug]);

  // Action creators for cleaner API
  const actions = useMemo(() => ({
    // Field setters
    setField: (field, value) => {
      dispatch({ type: ActionTypes.SET_FIELD, field, value });
    },

    setFields: (fields) => {
      dispatch({ type: ActionTypes.SET_FIELDS, fields });
    },

    setBorrowerField: (field, value, borrowerIndex = null) => {
      dispatch({
        type: ActionTypes.SET_BORROWER_FIELD,
        field,
        value,
        borrowerIndex
      });
    },

    // Navigation
    setStage: (stage) => {
      dispatch({ type: ActionTypes.SET_STAGE, stage });
    },

    nextQuestion: () => {
      dispatch({ type: ActionTypes.NEXT_QUESTION });
    },

    prevQuestion: () => {
      dispatch({ type: ActionTypes.PREV_QUESTION });
    },

    setQuestionIndex: (index) => {
      dispatch({ type: ActionTypes.SET_QUESTION_INDEX, index });
    },

    // Multi-borrower
    setBorrowerIndex: (index) => {
      dispatch({ type: ActionTypes.SET_BORROWER_INDEX, index });
    },

    addBorrower: () => {
      dispatch({ type: ActionTypes.ADD_BORROWER });
    },

    removeBorrower: (index) => {
      dispatch({ type: ActionTypes.REMOVE_BORROWER, index });
    },

    // Validation
    setValidationError: (field, error) => {
      dispatch({ type: ActionTypes.SET_VALIDATION_ERROR, field, error });
    },

    clearValidationError: (field) => {
      dispatch({ type: ActionTypes.CLEAR_VALIDATION_ERROR, field });
    },

    clearAllErrors: () => {
      dispatch({ type: ActionTypes.CLEAR_ALL_ERRORS });
    },

    // Stage completion
    markStageComplete: (stage) => {
      dispatch({ type: ActionTypes.MARK_STAGE_COMPLETE, stage });
    },

    markStageIncomplete: (stage) => {
      dispatch({ type: ActionTypes.MARK_STAGE_INCOMPLETE, stage });
    },

    // Submission
    setSubmitting: (value) => {
      dispatch({ type: ActionTypes.SET_SUBMITTING, value });
    },

    setSubmitted: (result) => {
      dispatch({ type: ActionTypes.SET_SUBMITTED, result });
    },

    setSubmissionError: (error) => {
      dispatch({ type: ActionTypes.SET_SUBMISSION_ERROR, error });
    },

    // Persistence
    restoreState: (savedState) => {
      dispatch({ type: ActionTypes.RESTORE_STATE, savedState });
    },

    setLastSaved: (timestamp) => {
      dispatch({ type: ActionTypes.SET_LAST_SAVED, timestamp });
    },

    // Reset
    resetApplication: () => {
      dispatch({ type: ActionTypes.RESET_APPLICATION });
    },
  }), []);

  // Computed values
  const computed = useMemo(() => ({
    // Current borrower data
    currentBorrower: state.formData.borrowers[state.currentBorrowerIndex] || {},

    // Total borrower count
    borrowerCount: state.formData.borrowers.length,

    // Is multi-borrower application
    isMultiBorrower: state.formData.borrower_count &&
      ['2', '3', '4+'].includes(state.formData.borrower_count),

    // Has validation errors
    hasErrors: Object.keys(state.validationErrors).length > 0,

    // Is stage completed
    isStageCompleted: (stage) => state.completedStages.includes(stage),

    // Get field value (with support for borrower-specific fields)
    getFieldValue: (field, borrowerIndex = null) => {
      if (borrowerIndex !== null) {
        return state.formData.borrowers[borrowerIndex]?.[field];
      }
      return state.formData[field];
    },

    // Get validation error for field
    getFieldError: (field) => state.validationErrors[field],
  }), [state]);

  // Context value
  const value = useMemo(() => ({
    state,
    dispatch,
    actions,
    computed,
  }), [state, actions, computed]);

  return (
    <ApplicationContext.Provider value={value}>
      {children}
    </ApplicationContext.Provider>
  );
}

// Custom hook for using the context
export function useApplication() {
  const context = useContext(ApplicationContext);

  if (!context) {
    throw new Error('useApplication must be used within an ApplicationProvider');
  }

  return context;
}

// Convenience hooks for common use cases
export function useApplicationState() {
  const { state } = useApplication();
  return state;
}

export function useApplicationActions() {
  const { actions } = useApplication();
  return actions;
}

export function useApplicationComputed() {
  const { computed } = useApplication();
  return computed;
}

// Export for external use
export { ActionTypes };
export default ApplicationContext;
