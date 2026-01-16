/**
 * StageRenderer - Renders all questions for a stage with navigation
 * Integrates with ApplicationContext for state management
 */

import React, { useMemo, useCallback } from 'react';
import { useApplication } from '../contexts/ApplicationContext';
import { useQuestionNavigation } from '../hooks/useQuestionNavigation';
import { getNextStage, getPrevStage } from '../config/stageConfig';
import QuestionRenderer from './QuestionRenderer';
import './StageRenderer.css';

const StageRenderer = ({
  questions,
  stageId,
  onStageComplete,
  onStagePrevious,
}) => {
  const { state, actions, computed } = useApplication();
  const { formData, applicationType, currentQuestionIndex, validationErrors } = state;
  const { currentBorrower } = computed;

  // Use question navigation hook
  const {
    visibleQuestions,
    currentQuestion,
    totalQuestions,
    isFirstQuestion,
    isLastQuestion,
    currentValue,
    goToNextQuestion,
    goToPrevQuestion,
    setAnswer,
  } = useQuestionNavigation(questions, stageId);

  // Handle value change
  const handleChange = useCallback((value) => {
    if (!currentQuestion) return;
    setAnswer(value, false); // Don't auto-advance, QuestionRenderer handles it
  }, [currentQuestion, setAnswer]);

  // Handle next question
  const handleNext = useCallback(() => {
    if (isLastQuestion) {
      // Mark stage complete and notify parent
      actions.markStageComplete(stageId);

      // Get next stage
      const nextStage = getNextStage(applicationType, stageId, formData);
      if (nextStage) {
        actions.setStage(nextStage.id);
        actions.setQuestionIndex(0);
      } else {
        // No more stages - application complete
        onStageComplete?.();
      }
    } else {
      goToNextQuestion();
    }
  }, [isLastQuestion, actions, stageId, applicationType, formData, goToNextQuestion, onStageComplete]);

  // Handle previous question
  const handleBack = useCallback(() => {
    if (isFirstQuestion) {
      // Go to previous stage
      const prevStage = getPrevStage(applicationType, stageId, formData);
      if (prevStage) {
        actions.setStage(prevStage.id);
        // Go to last question of previous stage
        actions.setQuestionIndex(999); // Will be clamped to last question
      } else {
        // No previous stage - exit or go to start
        onStagePrevious?.();
      }
    } else {
      goToPrevQuestion();
    }
  }, [isFirstQuestion, applicationType, stageId, formData, goToPrevQuestion, actions, onStagePrevious]);

  // Get current error
  const currentError = currentQuestion
    ? validationErrors[currentQuestion.id]
    : null;

  if (visibleQuestions.length === 0) {
    return (
      <div className="stage-empty">
        <p>No questions to display for this stage.</p>
        <button onClick={handleNext} className="skip-btn">
          Continue to Next Section →
        </button>
      </div>
    );
  }

  return (
    <div className="stage-renderer">
      <QuestionRenderer
        question={currentQuestion}
        value={currentValue}
        onChange={handleChange}
        onNext={handleNext}
        onBack={handleBack}
        isFirst={isFirstQuestion}
        isLast={isLastQuestion}
        error={currentError}
        currentIndex={currentQuestionIndex}
        totalQuestions={totalQuestions}
        autoAdvance={true}
      />
    </div>
  );
};

export default StageRenderer;
