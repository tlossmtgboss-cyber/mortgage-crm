import React, { useState, useEffect, useCallback } from 'react';
import { decisionLabAPI } from '../../services/decisionLabApi';
import EducationOverlay from './EducationOverlay';
import './ConfidenceAssessment.css';

function ConfidenceAssessment({ sessionId, onComplete, onBack }) {
  const [currentQuestion, setCurrentQuestion] = useState(null);
  const [selectedAnswer, setSelectedAnswer] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState({ answered: 0, total: 8 });
  const [showOverlay, setShowOverlay] = useState(false);
  const [overlay, setOverlay] = useState(null);
  const [isComplete, setIsComplete] = useState(false);

  // Fetch next question
  const fetchNextQuestion = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await decisionLabAPI.getNextQuestion(sessionId);

      // Check if assessment is complete (question is null)
      if (data.complete || !data.question) {
        // Assessment complete - calculate score
        setIsComplete(true);
        try {
          const score = await decisionLabAPI.calculateScore(sessionId);
          onComplete(score);
        } catch (scoreErr) {
          console.error('Score calculation failed:', scoreErr);
          // Still call onComplete with partial data
          onComplete({ overall_score: 0, message: 'Score calculation in progress' });
        }
        return;
      }

      setCurrentQuestion(data.question);
      setSelectedAnswer('');

      // Check for education overlay
      if (data.education_overlay) {
        setOverlay(data.education_overlay);
        setShowOverlay(true);
      } else {
        setOverlay(null);
        setShowOverlay(false);
      }

      // Update progress from API response
      const progressData = await decisionLabAPI.getProgress(sessionId).catch(() => null);
      if (progressData) {
        setProgress({
          answered: progressData.answered || 0,
          total: progressData.total || 8,
        });
      }
    } catch (err) {
      setError('Failed to load question. Please try again.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [sessionId, onComplete]);

  useEffect(() => {
    if (sessionId) {
      fetchNextQuestion();
    }
  }, [sessionId, fetchNextQuestion]);

  // Handle answer selection
  const handleAnswerSelect = (value) => {
    setSelectedAnswer(value);
  };

  // Submit response
  const handleSubmit = async () => {
    if (!selectedAnswer) {
      setError('Please select an answer');
      return;
    }

    setSubmitting(true);
    setError('');

    try {
      await decisionLabAPI.submitResponse(
        sessionId,
        currentQuestion.id,
        selectedAnswer,
        3 // Default confidence level
      );

      // Fetch next question
      fetchNextQuestion();
    } catch (err) {
      setError('Failed to submit answer. Please try again.');
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  // Handle overlay close
  const handleOverlayClose = () => {
    setShowOverlay(false);
  };

  // Render loading state
  if (loading && !currentQuestion) {
    return (
      <div className="assessment-loading">
        <div className="loading-spinner" />
        <p>Loading your assessment...</p>
      </div>
    );
  }

  // Render complete state
  if (isComplete) {
    return (
      <div className="assessment-complete">
        <div className="complete-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h2>Assessment Complete!</h2>
        <p>Calculating your confidence score...</p>
        <div className="loading-spinner" />
      </div>
    );
  }

  return (
    <div className="confidence-assessment">
      {/* Progress Bar */}
      <div className="assessment-progress">
        <div className="progress-header">
          <span className="progress-label">Question {progress.answered + 1} of {progress.total}</span>
          <span className="progress-percent">{Math.round((progress.answered / progress.total) * 100)}%</span>
        </div>
        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${(progress.answered / progress.total) * 100}%` }}
          />
        </div>
      </div>

      {/* Question Card */}
      {currentQuestion && (
        <div className="question-card">
          <div className="question-category">
            <span className={`category-badge ${currentQuestion.category?.toLowerCase()}`}>
              {currentQuestion.category?.replace('_', ' ')}
            </span>
          </div>

          <h2 className="question-text">{currentQuestion.question_text}</h2>

          {currentQuestion.help_text && (
            <p className="question-help">{currentQuestion.help_text}</p>
          )}

          {/* Answer Options */}
          <div className="answer-options">
            {(currentQuestion.question_type === 'multiple_choice' || currentQuestion.question_type === 'single_choice') && currentQuestion.options && Array.isArray(currentQuestion.options) && (
              currentQuestion.options.map((option, index) => (
                <button
                  key={index}
                  className={`answer-option ${selectedAnswer === option.value ? 'selected' : ''}`}
                  onClick={() => handleAnswerSelect(option.value)}
                >
                  <span className="option-indicator">{String.fromCharCode(65 + index)}</span>
                  <span className="option-text">{option.label}</span>
                  {selectedAnswer === option.value && (
                    <svg className="check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
              ))
            )}

            {currentQuestion.question_type === 'scale' && (
              <div className="scale-options">
                {(() => {
                  const min = currentQuestion.options?.min || 1;
                  const max = currentQuestion.options?.max || 5;
                  const labels = currentQuestion.options?.labels || [];
                  const range = Array.from({ length: max - min + 1 }, (_, i) => min + i);
                  return range.map((num, idx) => (
                    <button
                      key={num}
                      className={`scale-option ${selectedAnswer === String(num) ? 'selected' : ''}`}
                      onClick={() => handleAnswerSelect(String(num))}
                      title={labels[idx] || ''}
                    >
                      <span className="scale-number">{num}</span>
                      {labels[idx] && <span className="scale-label-text">{labels[idx]}</span>}
                    </button>
                  ));
                })()}
              </div>
            )}

            {currentQuestion.question_type === 'yes_no' && (
              <div className="yes-no-options">
                <button
                  className={`answer-option ${selectedAnswer === 'yes' ? 'selected' : ''}`}
                  onClick={() => handleAnswerSelect('yes')}
                >
                  <span className="option-text">Yes</span>
                </button>
                <button
                  className={`answer-option ${selectedAnswer === 'no' ? 'selected' : ''}`}
                  onClick={() => handleAnswerSelect('no')}
                >
                  <span className="option-text">No</span>
                </button>
              </div>
            )}

            {currentQuestion.question_type === 'number' && (
              <div className="number-input-wrapper">
                <input
                  type="number"
                  className="number-input"
                  value={selectedAnswer}
                  onChange={(e) => handleAnswerSelect(e.target.value)}
                  placeholder="Enter a number"
                />
              </div>
            )}
          </div>


          {/* Error Message */}
          {error && <p className="error-message">{error}</p>}

          {/* Actions */}
          <div className="question-actions">
            <button className="back-button" onClick={onBack}>
              Back
            </button>
            <button
              className="submit-button"
              onClick={handleSubmit}
              disabled={!selectedAnswer || submitting}
            >
              {submitting ? 'Submitting...' : progress.answered === progress.total - 1 ? 'Complete Assessment' : 'Next Question'}
            </button>
          </div>
        </div>
      )}

      {/* Education Overlay */}
      {showOverlay && overlay && (
        <EducationOverlay
          overlay={overlay}
          onClose={handleOverlayClose}
        />
      )}
    </div>
  );
}

export default ConfidenceAssessment;
