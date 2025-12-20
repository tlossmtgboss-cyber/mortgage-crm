import React, { useState, useEffect } from 'react';
import './InlineFollowup.css';

/**
 * InlineFollowup - AI-powered follow-up questions component
 *
 * Displays clarifying questions inline after user answers trigger
 * complex situations (self-employment, gift funds, bankruptcy, etc.)
 */
const InlineFollowup = ({
  trigger,
  context,
  questions,
  onAnswersSubmit,
  onSkip,
}) => {
  const [answers, setAnswers] = useState({});
  const [isAnimating, setIsAnimating] = useState(true);

  useEffect(() => {
    // Animate in
    const timer = setTimeout(() => setIsAnimating(false), 100);
    return () => clearTimeout(timer);
  }, []);

  const handleChange = (questionId, value) => {
    setAnswers(prev => ({
      ...prev,
      [questionId]: value
    }));
  };

  const handleSubmit = () => {
    onAnswersSubmit(answers, trigger);
  };

  const allAnswered = questions.every(q => answers[q.id] && answers[q.id].trim() !== '');

  return (
    <div className={`inline-followup ${isAnimating ? 'animating' : ''}`}>
      <div className="followup-header">
        <div className="followup-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 16v-4M12 8h.01" />
          </svg>
        </div>
        <div className="followup-intro">
          <p className="followup-context">
            Since you mentioned <strong>{context}</strong>, we have a few quick questions:
          </p>
        </div>
      </div>

      <div className="followup-questions">
        {questions.map((question, index) => (
          <div key={question.id} className="followup-question" style={{ animationDelay: `${index * 100}ms` }}>
            <label className="question-label">{question.question}</label>

            {question.type === 'text' && (
              <input
                type="text"
                className="question-input"
                placeholder={question.placeholder || 'Type your answer...'}
                value={answers[question.id] || ''}
                onChange={(e) => handleChange(question.id, e.target.value)}
              />
            )}

            {question.type === 'select' && (
              <select
                className="question-select"
                value={answers[question.id] || ''}
                onChange={(e) => handleChange(question.id, e.target.value)}
              >
                <option value="">Select an option...</option>
                {question.options?.map(option => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            )}

            {question.type === 'radio' && (
              <div className="question-radio-group">
                {question.options?.map(option => (
                  <label key={option} className="radio-option">
                    <input
                      type="radio"
                      name={question.id}
                      value={option}
                      checked={answers[question.id] === option}
                      onChange={(e) => handleChange(question.id, e.target.value)}
                    />
                    <span className="radio-label">{option}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="followup-actions">
        <button
          className="btn-followup-submit"
          onClick={handleSubmit}
          disabled={!allAnswered}
        >
          {allAnswered ? 'Continue' : 'Please answer all questions'}
        </button>
        {onSkip && (
          <button className="btn-followup-skip" onClick={onSkip}>
            Skip for now
          </button>
        )}
      </div>
    </div>
  );
};

/**
 * Hook to check for follow-up triggers
 */
export const useFollowupCheck = (apiUrl) => {
  const [followupData, setFollowupData] = useState(null);
  const [isChecking, setIsChecking] = useState(false);

  const checkForFollowup = async (fieldName, fieldValue, applicationType = 'purchase', existingAnswers = null) => {
    if (!fieldValue) {
      setFollowupData(null);
      return null;
    }

    setIsChecking(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/borrower-auth/check-followup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          field_name: fieldName,
          field_value: fieldValue,
          application_type: applicationType,
          existing_answers: existingAnswers
        })
      });

      const data = await response.json();

      if (data.needs_followup && data.questions?.length > 0) {
        setFollowupData(data);
        return data;
      } else {
        setFollowupData(null);
        return null;
      }
    } catch (error) {
      console.error('Follow-up check failed:', error);
      setFollowupData(null);
      return null;
    } finally {
      setIsChecking(false);
    }
  };

  const clearFollowup = () => {
    setFollowupData(null);
  };

  return {
    followupData,
    isChecking,
    checkForFollowup,
    clearFollowup
  };
};

export default InlineFollowup;
