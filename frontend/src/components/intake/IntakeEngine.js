/**
 * IntakeEngine - Main container for the conversational loan intake system
 * Provides a step-by-step Q&A interface with real-time scoring
 */

import React, { useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useIntakeSession } from '../../hooks/useIntakeSession';
import IntakeQuestion from './IntakeQuestion';
import IntakeProgressBar from './IntakeProgressBar';
import IntakeScorePanel from './IntakeScorePanel';
import './IntakeEngine.css';

function IntakeEngine({ leadId: propLeadId, loanId: propLoanId, onComplete }) {
  const params = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Get IDs from props, params, or query string
  const leadId = propLeadId || params.leadId || searchParams.get('leadId');
  const loanId = propLoanId || params.loanId || searchParams.get('loanId');
  const resumeSessionId = params.sessionId || searchParams.get('sessionId');

  // Local state for the current answer
  const [currentAnswer, setCurrentAnswer] = useState('');
  const [answerError, setAnswerError] = useState(null);

  // Use the intake session hook
  const {
    sessionId,
    currentQuestion,
    isCompleted,
    progress,
    scores,
    coaching,
    flags,
    loading,
    submitting,
    error,
    submitAnswer,
    skipQuestion
  } = useIntakeSession({
    leadId,
    loanId,
    sessionId: resumeSessionId
  });

  // Handle answer submission
  const handleSubmit = async (e) => {
    e?.preventDefault();
    setAnswerError(null);

    if (!currentQuestion) return;

    // Validate required questions
    if (currentQuestion.required && !currentAnswer && currentAnswer !== 0) {
      setAnswerError('This question requires an answer');
      return;
    }

    const result = await submitAnswer(currentQuestion.question_id, currentAnswer);

    if (result.success) {
      setCurrentAnswer(''); // Reset for next question

      if (result.completed && onComplete) {
        onComplete({ sessionId, scores });
      }
    } else {
      setAnswerError(result.error || 'Failed to submit answer');
    }
  };

  // Handle skip
  const handleSkip = async () => {
    if (currentQuestion?.required) {
      setAnswerError('This question is required and cannot be skipped');
      return;
    }

    const result = await skipQuestion();
    if (result.success) {
      setCurrentAnswer('');
      setAnswerError(null);
    }
  };

  // Handle exit
  const handleExit = () => {
    if (window.confirm('Are you sure you want to exit? Your progress will be saved.')) {
      navigate(-1);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="intake-engine">
        <div className="intake-loading">
          <div className="intake-spinner"></div>
          <p>Loading intake session...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !sessionId) {
    return (
      <div className="intake-engine">
        <div className="intake-error">
          <h2>Unable to Start Intake</h2>
          <p>{error}</p>
          <button className="btn btn-primary" onClick={() => navigate(-1)}>
            Go Back
          </button>
        </div>
      </div>
    );
  }

  // Completed state
  if (isCompleted) {
    return (
      <div className="intake-engine">
        <div className="intake-completed">
          <div className="completed-icon">✓</div>
          <h2>Intake Complete!</h2>
          <p>All questions have been answered.</p>

          <div className="completed-scores">
            <div className="score-summary">
              <h3>Final Scores</h3>
              <div className="score-grid">
                <div className="score-item">
                  <span className="score-label">Truth Score</span>
                  <span className={`score-value band-${scores.truth_band?.toLowerCase()}`}>
                    {Math.round(scores.truth_score)}%
                  </span>
                </div>
                <div className="score-item">
                  <span className="score-label">Readiness</span>
                  <span className="score-value">
                    {Math.round(scores.readiness_score)}%
                  </span>
                </div>
                <div className="score-item">
                  <span className="score-label">Hesitation</span>
                  <span className={`score-value band-${scores.hesitation_band?.toLowerCase()}`}>
                    {Math.round(scores.hesitation_score)}%
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="completed-actions">
            <button
              className="btn btn-primary"
              onClick={() => onComplete ? onComplete({ sessionId, scores }) : navigate(-1)}
            >
              Continue
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="intake-engine">
      {/* Header with progress and exit */}
      <div className="intake-header">
        <IntakeProgressBar progress={progress} />
        <button className="btn-exit" onClick={handleExit} title="Save and exit">
          <span className="exit-icon">×</span>
          <span className="exit-text">Exit</span>
        </button>
      </div>

      {/* Main content area */}
      <div className="intake-content">
        {/* Question panel */}
        <div className="intake-question-panel">
          {currentQuestion ? (
            <form onSubmit={handleSubmit}>
              <IntakeQuestion
                question={currentQuestion}
                value={currentAnswer}
                onChange={setCurrentAnswer}
                error={answerError}
                disabled={submitting}
              />

              <div className="intake-actions">
                {!currentQuestion.required && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleSkip}
                    disabled={submitting}
                  >
                    Skip
                  </button>
                )}
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={submitting}
                >
                  {submitting ? 'Saving...' : 'Next →'}
                </button>
              </div>
            </form>
          ) : (
            <div className="intake-no-question">
              <p>No more questions available.</p>
            </div>
          )}
        </div>

        {/* Score panel sidebar */}
        <div className="intake-score-sidebar">
          <IntakeScorePanel
            scores={scores}
            coaching={coaching}
            flags={flags}
          />
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="intake-error-banner">
          <span>{error}</span>
          <button onClick={() => window.location.reload()}>Retry</button>
        </div>
      )}
    </div>
  );
}

export default IntakeEngine;
