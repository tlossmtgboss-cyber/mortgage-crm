import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import * as discApi from '../services/discApi';
import './DISCAssessment.css';

/**
 * Public DISC Assessment Page
 * Candidates access this page via token link to take the assessment
 */
function DISCAssessment() {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  const tokenFromQuery = searchParams.get('token');
  const assessmentToken = token || tokenFromQuery;

  const [session, setSession] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [results, setResults] = useState(null);
  const [questionStartTime, setQuestionStartTime] = useState(null);

  // Load session and questions
  useEffect(() => {
    async function loadAssessment() {
      try {
        setLoading(true);
        const sessionData = await discApi.getPublicSession(assessmentToken);
        setSession(sessionData);

        if (sessionData.status === 'completed') {
          setCompleted(true);
          setResults(sessionData.results);
        } else {
          const questionsData = await discApi.getSessionQuestions(sessionData.id);
          setQuestions(questionsData.questions || []);
          setCurrentQuestionIndex(sessionData.current_question || 0);
          setQuestionStartTime(Date.now());
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    if (assessmentToken) {
      loadAssessment();
    } else {
      setError('No assessment token provided');
      setLoading(false);
    }
  }, [assessmentToken]);

  const currentQuestion = questions[currentQuestionIndex];
  const progress = questions.length > 0 ? ((currentQuestionIndex + 1) / questions.length) * 100 : 0;

  // Handle answer selection for forced-choice questions
  const handleForcedChoiceSelect = useCallback((type, optionIndex) => {
    const questionId = currentQuestion.id;
    setAnswers(prev => ({
      ...prev,
      [questionId]: {
        ...prev[questionId],
        [type]: optionIndex
      }
    }));
  }, [currentQuestion]);

  // Handle Likert scale selection
  const handleLikertSelect = useCallback((value) => {
    const questionId = currentQuestion.id;
    setAnswers(prev => ({
      ...prev,
      [questionId]: { value }
    }));
  }, [currentQuestion]);

  // Check if current question is fully answered
  const isCurrentAnswered = useCallback(() => {
    if (!currentQuestion) return false;
    const answer = answers[currentQuestion.id];
    if (!answer) return false;

    if (currentQuestion.question_type === 'forced_choice') {
      return answer.most !== undefined && answer.least !== undefined && answer.most !== answer.least;
    } else {
      return answer.value !== undefined;
    }
  }, [currentQuestion, answers]);

  // Submit answer and move to next question
  const handleNext = async () => {
    if (!isCurrentAnswered()) return;

    const responseTimeMs = Date.now() - questionStartTime;
    const answer = answers[currentQuestion.id];

    try {
      setSubmitting(true);
      await discApi.submitAnswer(session.id, currentQuestion.id, answer, responseTimeMs);

      if (currentQuestionIndex < questions.length - 1) {
        setCurrentQuestionIndex(prev => prev + 1);
        setQuestionStartTime(Date.now());
      } else {
        // Complete assessment
        const result = await discApi.completeSession(session.id);
        setResults(result);
        setCompleted(true);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="disc-assessment-container">
        <div className="disc-assessment-loading">
          <div className="disc-loading-spinner" />
          <p>Loading assessment...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="disc-assessment-container">
        <div className="disc-assessment-error">
          <div className="disc-error-icon">⚠️</div>
          <h2>Assessment Error</h2>
          <p>{error}</p>
          <p className="disc-error-hint">
            Please contact your recruiter for a new assessment link.
          </p>
        </div>
      </div>
    );
  }

  // Completed state
  if (completed) {
    return (
      <div className="disc-assessment-container">
        <div className="disc-assessment-complete">
          <div className="disc-complete-icon">✓</div>
          <h2>Assessment Complete!</h2>
          <p>Thank you for completing the DISC + Motivators assessment.</p>

          {results && (
            <div className="disc-results-preview">
              <div className="disc-results-style">
                <span className="disc-results-label">Your Style:</span>
                <span className="disc-results-value">
                  {results.disc?.adapted_style}/{results.disc?.natural_style}
                </span>
              </div>
              {results.disc?.zone_name && (
                <div className="disc-results-zone">
                  <span className="disc-results-label">Behavioral Pattern:</span>
                  <span className="disc-results-value">{results.disc.zone_name}</span>
                </div>
              )}
              {results.motivators?.top_motivator && (
                <div className="disc-results-motivator">
                  <span className="disc-results-label">Top Motivator:</span>
                  <span className="disc-results-value">
                    {results.motivators.top_motivator}
                  </span>
                </div>
              )}
            </div>
          )}

          <p className="disc-complete-message">
            Your recruiter will be in touch to discuss your results.
          </p>
        </div>
      </div>
    );
  }

  // Assessment in progress
  return (
    <div className="disc-assessment-container">
      <div className="disc-assessment-header">
        <div className="disc-assessment-logo">
          <span className="disc-logo-text">Perennia AI</span>
        </div>
        <h1 className="disc-assessment-title">DISC + Motivators Assessment</h1>
        <p className="disc-assessment-subtitle">
          {session?.candidate_name && `Welcome, ${session.candidate_name}`}
        </p>
      </div>

      {/* Progress bar */}
      <div className="disc-progress-container">
        <div className="disc-progress-bar">
          <div className="disc-progress-fill" style={{ width: `${progress}%` }} />
        </div>
        <div className="disc-progress-text">
          Question {currentQuestionIndex + 1} of {questions.length}
        </div>
      </div>

      {/* Question card */}
      <div className="disc-question-card">
        {currentQuestion?.question_type === 'forced_choice' ? (
          <ForcedChoiceQuestion
            question={currentQuestion}
            answer={answers[currentQuestion.id]}
            onSelect={handleForcedChoiceSelect}
          />
        ) : (
          <LikertQuestion
            question={currentQuestion}
            answer={answers[currentQuestion.id]}
            onSelect={handleLikertSelect}
          />
        )}
      </div>

      {/* Navigation */}
      <div className="disc-navigation">
        <button
          className="disc-nav-btn disc-nav-next"
          onClick={handleNext}
          disabled={!isCurrentAnswered() || submitting}
        >
          {submitting ? (
            <span className="disc-btn-loading">...</span>
          ) : currentQuestionIndex === questions.length - 1 ? (
            'Complete Assessment'
          ) : (
            'Next Question'
          )}
        </button>
      </div>

      {/* Instructions */}
      <div className="disc-instructions">
        {currentQuestion?.question_type === 'forced_choice' ? (
          <p>Select which statement is <strong>MOST</strong> like you and which is <strong>LEAST</strong> like you.</p>
        ) : (
          <p>Rate how much you agree with this statement.</p>
        )}
      </div>
    </div>
  );
}

/**
 * Forced Choice Question Component
 */
function ForcedChoiceQuestion({ question, answer = {}, onSelect }) {
  const options = question.options || [];

  return (
    <div className="disc-forced-choice">
      <p className="disc-question-prompt">{question.prompt}</p>

      <div className="disc-options-header">
        <span className="disc-option-label">Statement</span>
        <span className="disc-option-label disc-label-most">MOST</span>
        <span className="disc-option-label disc-label-least">LEAST</span>
      </div>

      <div className="disc-options-list">
        {options.map((option, index) => (
          <div key={index} className="disc-option-row">
            <span className="disc-option-text">{option.text}</span>
            <button
              className={`disc-option-btn disc-option-most ${answer.most === index ? 'selected' : ''}`}
              onClick={() => onSelect('most', index)}
              disabled={answer.least === index}
            >
              {answer.most === index && '✓'}
            </button>
            <button
              className={`disc-option-btn disc-option-least ${answer.least === index ? 'selected' : ''}`}
              onClick={() => onSelect('least', index)}
              disabled={answer.most === index}
            >
              {answer.least === index && '✓'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Likert Scale Question Component
 */
function LikertQuestion({ question, answer = {}, onSelect }) {
  const labels = [
    'Strongly Disagree',
    'Disagree',
    'Neutral',
    'Agree',
    'Strongly Agree'
  ];

  return (
    <div className="disc-likert">
      <p className="disc-question-prompt">{question.prompt}</p>

      <div className="disc-likert-scale">
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            className={`disc-likert-option ${answer.value === value ? 'selected' : ''}`}
            onClick={() => onSelect(value)}
          >
            <span className="disc-likert-value">{value}</span>
            <span className="disc-likert-label">{labels[value - 1]}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default DISCAssessment;
