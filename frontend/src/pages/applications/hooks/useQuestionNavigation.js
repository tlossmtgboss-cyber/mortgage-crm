/**
 * useQuestionNavigation Hook
 * Handles question navigation, showIf/hideIf evaluation, and stage progression
 */

import { useMemo, useCallback } from 'react';
import { useApplication } from '../contexts/ApplicationContext';

/**
 * Evaluates a showIf condition against form data
 * @param {Object} condition - The showIf condition { field: 'value' } or { field: ['value1', 'value2'] }
 * @param {Object} formData - The current form data
 * @param {Object} currentBorrower - The current borrower data (for borrower-specific fields)
 * @returns {boolean} Whether the condition is met
 */
export function evaluateShowIf(condition, formData, currentBorrower = {}) {
  if (!condition) return true;

  // Handle function-based conditions
  if (typeof condition === 'function') {
    return condition(formData, currentBorrower);
  }

  // Handle object-based conditions (AND logic - all must match)
  return Object.entries(condition).every(([field, expectedValue]) => {
    // Check borrower-specific fields first, then general form data
    const actualValue = currentBorrower[field] !== undefined
      ? currentBorrower[field]
      : formData[field];

    // Handle array of acceptable values (OR logic)
    if (Array.isArray(expectedValue)) {
      return expectedValue.includes(actualValue);
    }

    // Handle boolean comparison
    if (typeof expectedValue === 'boolean') {
      return actualValue === expectedValue;
    }

    // Handle exact match
    return actualValue === expectedValue;
  });
}

/**
 * Evaluates a hideIf condition (inverse of showIf)
 */
export function evaluateHideIf(condition, formData, currentBorrower = {}) {
  if (!condition) return false;

  // If condition is met, hide the question (return true)
  return evaluateShowIf(condition, formData, currentBorrower);
}

/**
 * Determines if a question should be visible
 */
export function shouldShowQuestion(question, formData, currentBorrower = {}) {
  // hideIf takes precedence
  if (question.hideIf && evaluateHideIf(question.hideIf, formData, currentBorrower)) {
    return false;
  }

  // Then check showIf
  if (question.showIf && !evaluateShowIf(question.showIf, formData, currentBorrower)) {
    return false;
  }

  return true;
}

/**
 * Main hook for question navigation
 */
export function useQuestionNavigation(questions, stageId = null) {
  const { state, actions, computed } = useApplication();
  const { formData, currentQuestionIndex, currentBorrowerIndex, currentStage } = state;
  const { currentBorrower } = computed;

  // Filter questions to only visible ones based on showIf/hideIf conditions
  const visibleQuestions = useMemo(() => {
    if (!questions || !Array.isArray(questions)) return [];

    // Filter by stage if provided
    let stageQuestions = stageId
      ? questions.filter(q => q.stage === stageId)
      : questions;

    // Filter by visibility conditions
    return stageQuestions.filter(q =>
      shouldShowQuestion(q, formData, currentBorrower)
    );
  }, [questions, stageId, formData, currentBorrower]);

  // Clamp question index to valid range (handles index 999 from backward stage navigation)
  const clampedIndex = useMemo(() => {
    if (visibleQuestions.length === 0) return 0;
    return Math.min(currentQuestionIndex, visibleQuestions.length - 1);
  }, [currentQuestionIndex, visibleQuestions.length]);

  // Get current question using clamped index
  const currentQuestion = useMemo(() => {
    return visibleQuestions[clampedIndex] || null;
  }, [visibleQuestions, clampedIndex]);

  // Check if we're at the first question
  const isFirstQuestion = clampedIndex === 0;

  // Check if we're at the last question
  const isLastQuestion = clampedIndex >= visibleQuestions.length - 1;

  // Check if current question has a value
  const hasCurrentValue = useMemo(() => {
    if (!currentQuestion) return false;

    const value = currentQuestion.borrowerSpecific
      ? currentBorrower[currentQuestion.id]
      : formData[currentQuestion.id];

    // Check for non-empty values
    if (value === null || value === undefined || value === '') {
      return false;
    }

    // For arrays, check if not empty
    if (Array.isArray(value)) {
      return value.length > 0;
    }

    return true;
  }, [currentQuestion, formData, currentBorrower]);

  // Navigate to next question
  const goToNextQuestion = useCallback(() => {
    if (isLastQuestion) {
      return false; // Signal that we're done with this stage
    }
    actions.nextQuestion();
    return true;
  }, [isLastQuestion, actions]);

  // Navigate to previous question
  const goToPrevQuestion = useCallback(() => {
    if (isFirstQuestion) {
      return false; // Signal that we should go to previous stage
    }
    actions.prevQuestion();
    return true;
  }, [isFirstQuestion, actions]);

  // Go to specific question by ID
  const goToQuestion = useCallback((questionId) => {
    const index = visibleQuestions.findIndex(q => q.id === questionId);
    if (index >= 0) {
      actions.setQuestionIndex(index);
      return true;
    }
    return false;
  }, [visibleQuestions, actions]);

  // Set the answer for current question and optionally advance
  const setAnswer = useCallback((value, advance = false) => {
    if (!currentQuestion) return;

    if (currentQuestion.borrowerSpecific) {
      actions.setBorrowerField(currentQuestion.id, value);
    } else {
      actions.setField(currentQuestion.id, value);
    }

    // Clear any validation error for this field
    actions.clearValidationError(currentQuestion.id);

    // Optionally advance to next question
    if (advance && value !== null && value !== undefined && value !== '') {
      // Small delay for animation
      setTimeout(() => {
        goToNextQuestion();
      }, 300);
    }
  }, [currentQuestion, actions, goToNextQuestion]);

  // Get the current value for the current question
  const currentValue = useMemo(() => {
    if (!currentQuestion) return null;

    // Get the direct value for this field
    const directValue = currentQuestion.borrowerSpecific
      ? currentBorrower[currentQuestion.id]
      : formData[currentQuestion.id];

    // If there's a direct value, use it
    if (directValue !== null && directValue !== undefined && directValue !== '') {
      return directValue;
    }

    // Check for autoPopulateFrom config - allows fields to inherit values from other fields
    // e.g., employer_phone can auto-populate from employer_name.phone
    if (currentQuestion.autoPopulateFrom) {
      const { field, property } = currentQuestion.autoPopulateFrom;
      const sourceData = currentQuestion.borrowerSpecific ? currentBorrower : formData;
      const sourceValue = sourceData[field];

      if (sourceValue && property && sourceValue[property]) {
        return sourceValue[property];
      }
    }

    return directValue;
  }, [currentQuestion, formData, currentBorrower]);

  // Calculate progress within this stage
  const stageProgress = useMemo(() => {
    if (visibleQuestions.length === 0) return 0;
    return Math.round((clampedIndex / visibleQuestions.length) * 100);
  }, [clampedIndex, visibleQuestions.length]);

  // Calculate overall progress
  const calculateOverallProgress = useCallback((stages, currentStageId) => {
    if (!stages || stages.length === 0) return 0;

    const currentStageIndex = stages.findIndex(s => s.id === currentStageId);
    if (currentStageIndex === -1) return 0;

    const stageWeight = 100 / stages.length;
    const completedStagesProgress = currentStageIndex * stageWeight;
    const currentStageProgress = (stageProgress / 100) * stageWeight;

    return Math.round(completedStagesProgress + currentStageProgress);
  }, [stageProgress]);

  return {
    // Questions
    visibleQuestions,
    currentQuestion,
    totalQuestions: visibleQuestions.length,

    // Navigation state
    currentQuestionIndex: clampedIndex,
    isFirstQuestion,
    isLastQuestion,
    hasCurrentValue,

    // Current value
    currentValue,

    // Navigation actions
    goToNextQuestion,
    goToPrevQuestion,
    goToQuestion,
    setAnswer,

    // Progress
    stageProgress,
    calculateOverallProgress,

    // Utility functions (exported for direct use)
    shouldShowQuestion: (q) => shouldShowQuestion(q, formData, currentBorrower),
  };
}

export default useQuestionNavigation;
