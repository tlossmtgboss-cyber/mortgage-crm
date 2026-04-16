import React, { useState, useEffect } from 'react';
import { getCurrentUserId } from '../../utils/auth';
import './AssessmentQuizModal.css';
import { getToken } from '../../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const CATEGORY_LABELS = {
  production: 'Production',
  disc: 'DISC Personality',
  character: 'Character',
  skills: 'Skills',
  culture_fit: 'Culture Fit'
};

const CATEGORY_ICONS = {
  production: '📊',
  disc: '🧠',
  character: '💎',
  skills: '🛠️',
  culture_fit: '🤝'
};

const AssessmentQuizModal = ({
  isOpen,
  onClose,
  candidateId,
  candidateName,
  disposition,
  onQuizComplete
}) => {
  const [quiz, setQuiz] = useState(null);
  const [responses, setResponses] = useState({});
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen && disposition) {
      fetchQuiz();
    }
  }, [isOpen, disposition]);

  const fetchQuiz = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const token = getToken();
      const response = await fetch(`${API_URL}/api/v1/recruiting/quiz/${disposition}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to load quiz');
      }

      const data = await response.json();
      setQuiz(data);
      setResponses({});
      setCurrentQuestionIndex(0);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleResponse = (templateId, value, score) => {
    setResponses(prev => ({
      ...prev,
      [templateId]: { value, score }
    }));
  };

  const handleNext = () => {
    if (currentQuestionIndex < quiz.questions.length - 1) {
      setCurrentQuestionIndex(prev => prev + 1);
    }
  };

  const handlePrevious = () => {
    if (currentQuestionIndex > 0) {
      setCurrentQuestionIndex(prev => prev - 1);
    }
  };

  const handleSubmit = async () => {
    // Check all questions answered
    const unanswered = quiz.questions.filter(q => !responses[q.id]);
    if (unanswered.length > 0) {
      setError(`Please answer all questions (${unanswered.length} remaining)`);
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const token = getToken();
      const userId = getCurrentUserId() || 1;

      const submission = {
        disposition: disposition,
        responses: Object.entries(responses).map(([templateId, data]) => ({
          template_id: parseInt(templateId),
          response_value: data.value,
          numeric_score: data.score
        }))
      };

      const response = await fetch(
        `${API_URL}/api/v1/recruiting/candidates/${candidateId}/quiz?responded_by=${userId}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(submission)
        }
      );

      if (!response.ok) {
        throw new Error('Failed to submit quiz');
      }

      const scores = await response.json();
      onQuizComplete(scores);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const currentQuestion = quiz?.questions?.[currentQuestionIndex];
  const answeredCount = Object.keys(responses).length;
  const totalQuestions = quiz?.questions?.length || 0;
  const progress = totalQuestions > 0 ? (answeredCount / totalQuestions) * 100 : 0;

  return (
    <div className="quiz-modal-overlay" onClick={onClose}>
      <div className="quiz-modal" onClick={e => e.stopPropagation()}>
        <div className="quiz-modal-header">
          <div className="quiz-header-info">
            <h2>Assessment Quiz</h2>
            <p className="quiz-subtitle">
              {candidateName} - {quiz?.disposition_label || disposition}
            </p>
          </div>
          <button className="quiz-close-btn" onClick={onClose}>&times;</button>
        </div>

        {isLoading ? (
          <div className="quiz-loading">
            <div className="quiz-spinner"></div>
            <p>Loading quiz questions...</p>
          </div>
        ) : error && !quiz ? (
          <div className="quiz-error">
            <p>{error}</p>
            <button onClick={fetchQuiz}>Retry</button>
          </div>
        ) : quiz && currentQuestion ? (
          <>
            <div className="quiz-progress-section">
              <div className="quiz-progress-bar">
                <div
                  className="quiz-progress-fill"
                  style={{ width: `${progress}%` }}
                ></div>
              </div>
              <span className="quiz-progress-text">
                {answeredCount} of {totalQuestions} answered
              </span>
            </div>

            <div className="quiz-question-section">
              <div className="quiz-question-header">
                <span className="quiz-category-badge">
                  {CATEGORY_ICONS[currentQuestion.category]} {CATEGORY_LABELS[currentQuestion.category]}
                </span>
                <span className="quiz-question-number">
                  Question {currentQuestionIndex + 1} of {totalQuestions}
                </span>
              </div>

              <h3 className="quiz-question-text">{currentQuestion.question_text}</h3>

              <div className="quiz-options">
                {currentQuestion.options?.map((option) => (
                  <button
                    key={option.value}
                    className={`quiz-option ${responses[currentQuestion.id]?.value === option.value ? 'selected' : ''}`}
                    onClick={() => handleResponse(currentQuestion.id, option.value, option.score)}
                  >
                    <span className="option-label">{option.label}</span>
                    {currentQuestion.question_type === 'likert' && (
                      <span className="option-indicator">
                        {'★'.repeat(parseInt(option.value))}{'☆'.repeat(5 - parseInt(option.value))}
                      </span>
                    )}
                  </button>
                ))}
              </div>

              {error && (
                <div className="quiz-inline-error">{error}</div>
              )}
            </div>

            <div className="quiz-navigation">
              <button
                className="quiz-nav-btn prev"
                onClick={handlePrevious}
                disabled={currentQuestionIndex === 0}
              >
                Previous
              </button>

              <div className="quiz-dots">
                {quiz.questions.map((q, idx) => (
                  <button
                    key={q.id}
                    className={`quiz-dot ${idx === currentQuestionIndex ? 'active' : ''} ${responses[q.id] ? 'answered' : ''}`}
                    onClick={() => setCurrentQuestionIndex(idx)}
                  />
                ))}
              </div>

              {currentQuestionIndex === totalQuestions - 1 ? (
                <button
                  className="quiz-nav-btn submit"
                  onClick={handleSubmit}
                  disabled={isSubmitting || answeredCount < totalQuestions}
                >
                  {isSubmitting ? 'Submitting...' : 'Submit Quiz'}
                </button>
              ) : (
                <button
                  className="quiz-nav-btn next"
                  onClick={handleNext}
                >
                  Next
                </button>
              )}
            </div>
          </>
        ) : (
          <div className="quiz-empty">
            <p>No quiz questions available for this stage.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default AssessmentQuizModal;
