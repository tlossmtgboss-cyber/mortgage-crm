import React, { useState, useEffect } from 'react';
import { decisionLabAPI } from '../../services/decisionLabApi';
import './ConfidenceResults.css';
import { toast } from '../../utils/toast';

const READINESS_LEVELS = {
  NOT_READY: { label: 'Not Ready Yet', color: '#ef4444', bg: '#fef2f2' },
  NEEDS_WORK: { label: 'Needs Work', color: '#f59e0b', bg: '#fffbeb' },
  ALMOST_READY: { label: 'Almost Ready', color: '#eab308', bg: '#fefce8' },
  READY: { label: 'Ready', color: '#22c55e', bg: '#f0fdf4' },
  HIGHLY_READY: { label: 'Highly Ready', color: '#16a34a', bg: '#dcfce7' },
};

const CATEGORY_INFO = {
  FINANCIAL_READINESS: {
    label: 'Financial Readiness',
    icon: '💰',
    description: 'Your financial preparation and stability',
  },
  CREDIT_UNDERSTANDING: {
    label: 'Credit Understanding',
    icon: '📊',
    description: 'Knowledge of credit scores and history',
  },
  MORTGAGE_KNOWLEDGE: {
    label: 'Mortgage Knowledge',
    icon: '🏠',
    description: 'Understanding of mortgage products and terms',
  },
  PROCESS_UNDERSTANDING: {
    label: 'Process Understanding',
    icon: '📋',
    description: 'Familiarity with the homebuying process',
  },
  EMOTIONAL_READINESS: {
    label: 'Emotional Readiness',
    icon: '💭',
    description: 'Confidence and comfort with the decision',
  },
};

function ConfidenceResults({ sessionId, score, onBuildScenario, onRetakeAssessment }) {
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedCategory, setExpandedCategory] = useState(null);

  useEffect(() => {
    if (sessionId) {
      fetchRecommendations();
    }
  }, [sessionId]);

  const fetchRecommendations = async () => {
    try {
      const data = await decisionLabAPI.getRecommendations(sessionId);
      setRecommendations(data.recommendations || []);
    } catch (err) {
      console.error('Failed to fetch recommendations:', err);
    } finally {
      setLoading(false);
    }
  };

  if (!score) {
    return (
      <div className="results-loading">
        <div className="loading-spinner" />
        <p>Calculating your results...</p>
      </div>
    );
  }

  const readinessLevel = READINESS_LEVELS[score.readiness_level] || READINESS_LEVELS.NEEDS_WORK;
  const overallScore = score.overall_score || 0;
  const categoryScores = score.category_scores || {};

  // Calculate score ring properties
  const circumference = 2 * Math.PI * 90;
  const progress = (overallScore / 100) * circumference;

  return (
    <div className="confidence-results">
      {/* Hero Section */}
      <div className="results-hero">
        <div className="score-circle-container">
          <svg className="score-circle" viewBox="0 0 200 200">
            <circle
              className="score-bg"
              cx="100"
              cy="100"
              r="90"
              fill="none"
              stroke="#e5e7eb"
              strokeWidth="12"
            />
            <circle
              className="score-progress"
              cx="100"
              cy="100"
              r="90"
              fill="none"
              stroke={readinessLevel.color}
              strokeWidth="12"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={circumference - progress}
              transform="rotate(-90 100 100)"
            />
          </svg>
          <div className="score-value">
            <span className="score-number">{Math.round(overallScore)}</span>
            <span className="score-label">out of 100</span>
          </div>
        </div>

        <div className="readiness-badge" style={{ backgroundColor: readinessLevel.bg, color: readinessLevel.color }}>
          {readinessLevel.label}
        </div>

        <h1 className="results-title">Your Mortgage Readiness Score</h1>
        <p className="results-subtitle">
          Based on your responses, here's an assessment of your preparedness for the mortgage process.
        </p>
      </div>

      {/* Category Breakdown */}
      <div className="category-breakdown">
        <h2>Score Breakdown</h2>
        <div className="categories-grid">
          {Object.entries(categoryScores).map(([category, catScore]) => {
            const info = CATEGORY_INFO[category] || { label: category, icon: '📊', description: '' };
            const percentage = typeof catScore === 'object' ? catScore.score : catScore;
            const isExpanded = expandedCategory === category;

            return (
              <div
                key={category}
                className={`category-card ${isExpanded ? 'expanded' : ''}`}
                onClick={() => setExpandedCategory(isExpanded ? null : category)}
              >
                <div className="category-header">
                  <span className="category-icon">{info.icon}</span>
                  <div className="category-info">
                    <h3>{info.label}</h3>
                    <p>{info.description}</p>
                  </div>
                  <div className="category-score">
                    <span className="score-value">{Math.round(percentage || 0)}%</span>
                  </div>
                </div>
                <div className="category-bar">
                  <div
                    className="bar-fill"
                    style={{
                      width: `${percentage || 0}%`,
                      backgroundColor: percentage >= 70 ? '#22c55e' : percentage >= 50 ? '#f59e0b' : '#ef4444',
                    }}
                  />
                </div>
                {isExpanded && (
                  <div className="category-details">
                    {percentage >= 70 ? (
                      <p className="detail-text success">
                        Great job! You have a strong understanding in this area.
                      </p>
                    ) : percentage >= 50 ? (
                      <p className="detail-text warning">
                        You're on the right track. A bit more preparation here could help.
                      </p>
                    ) : (
                      <p className="detail-text error">
                        This area needs attention. Review the educational content to improve.
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Recommendations */}
      <div className="recommendations-section">
        <h2>Recommended Next Steps</h2>
        {loading ? (
          <div className="recommendations-loading">
            <div className="loading-spinner small" />
            <span>Loading recommendations...</span>
          </div>
        ) : recommendations.length > 0 ? (
          <div className="recommendations-list">
            {recommendations.map((rec, index) => (
              <div key={index} className={`recommendation-card priority-${rec.priority || 'medium'}`}>
                <div className="rec-number">{index + 1}</div>
                <div className="rec-content">
                  <h3>{rec.title}</h3>
                  <p>{rec.description}</p>
                  {rec.action_type === 'scenario' && (
                    <button className="rec-action" onClick={onBuildScenario}>
                      Start Building
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M13 7l5 5m0 0l-5 5m5-5H6" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="default-recommendations">
            {overallScore >= 70 ? (
              <div className="recommendation-card priority-high">
                <div className="rec-number">1</div>
                <div className="rec-content">
                  <h3>Build Your Loan Scenarios</h3>
                  <p>You're well-prepared! Create loan scenarios to compare your options and find the best fit.</p>
                  <button className="rec-action" onClick={onBuildScenario}>
                    Build Scenarios
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="recommendation-card priority-high">
                  <div className="rec-number">1</div>
                  <div className="rec-content">
                    <h3>Review Key Concepts</h3>
                    <p>Take some time to learn about the areas where you scored lower. Knowledge is power!</p>
                  </div>
                </div>
                <div className="recommendation-card priority-medium">
                  <div className="rec-number">2</div>
                  <div className="rec-content">
                    <h3>Check Your Credit Report</h3>
                    <p>Understanding your credit is crucial. Get a free copy at AnnualCreditReport.com</p>
                  </div>
                </div>
                <div className="recommendation-card priority-low">
                  <div className="rec-number">3</div>
                  <div className="rec-content">
                    <h3>Build a Budget</h3>
                    <p>Calculate how much house you can afford based on your income and expenses.</p>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="results-actions">
        <button className="secondary-action" onClick={onRetakeAssessment}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Retake Assessment
        </button>
        <button className="primary-action" onClick={onBuildScenario}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
          Build Loan Scenarios
        </button>
      </div>

      {/* Share/Save */}
      <div className="share-section">
        <p>Save your results or share with your loan officer</p>
        <div className="share-actions">
          <button className="share-btn" onClick={() => window.print()}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
            </svg>
            Print Results
          </button>
          <button
            className="share-btn"
            onClick={() => {
              navigator.clipboard.writeText(window.location.href);
              toast.success('Link copied to clipboard!');
            }}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
            </svg>
            Share Results
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfidenceResults;
