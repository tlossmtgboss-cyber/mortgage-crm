import React, { useState, useEffect } from 'react';
import { rateLockAPI } from '../services/rateLockApi';
import './RateLockRecommendation.css';

function RateLockRecommendation({ loan }) {
  const [recommendation, setRecommendation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    if (loan && loan.amount) {
      loadRecommendation();
    }
  }, [loan?.id, loan?.amount, loan?.rate, loan?.closing_date]);

  const loadRecommendation = async () => {
    setLoading(true);
    setError(null);
    try {
      const rec = await rateLockAPI.getQuickRecommendation({
        amount: loan.amount,
        ltv: loan.ltv,
        rate: loan.rate,
        closingDate: loan.closing_date,
        program: loan.program || loan.loan_type,
        dti: loan.dti,
        appraisal_value: loan.appraisal_value,
      });
      setRecommendation(rec);
    } catch (err) {
      console.error('Failed to get rate lock recommendation:', err);
      setError('Unable to get recommendation');
    } finally {
      setLoading(false);
    }
  };

  const getUrgencyColor = (urgency) => {
    switch (urgency) {
      case 'immediate': return 'urgency-immediate';
      case 'high': return 'urgency-high';
      case 'moderate': return 'urgency-moderate';
      case 'low': return 'urgency-low';
      default: return 'urgency-low';
    }
  };

  const getActionIcon = (action) => {
    if (!action) return '❓';
    if (action === 'lock_now') return '🔒';
    if (action.includes && action.includes('float')) return '⏳';
    return '👁️';
  };

  const formatAction = (action) => {
    if (!action) return 'Unknown';
    return action
      .replace(/_/g, ' ')
      .replace(/\b\w/g, l => l.toUpperCase());
  };

  if (!loan || !loan.amount) {
    return null;
  }

  if (loading) {
    return (
      <div className="rate-lock-widget loading">
        <div className="widget-header">
          <h3>Rate Lock Guidance</h3>
        </div>
        <div className="widget-content">
          <div className="loading-spinner"></div>
          <p>Analyzing loan data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rate-lock-widget error">
        <div className="widget-header">
          <h3>Rate Lock Guidance</h3>
        </div>
        <div className="widget-content">
          <p className="error-message">{error}</p>
          <button className="retry-btn" onClick={loadRecommendation}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!recommendation) {
    return null;
  }

  return (
    <div className={`rate-lock-widget ${getUrgencyColor(recommendation.urgency)}`}>
      <div className="widget-header">
        <h3>Rate Lock Guidance</h3>
        <span className="urgency-badge">{recommendation.urgency?.toUpperCase()}</span>
      </div>

      <div className="widget-content">
        {/* Main Recommendation */}
        <div className="recommendation-main">
          <span className="action-icon">{getActionIcon(recommendation.recommendation)}</span>
          <div className="action-text">
            <div className="action-name">{formatAction(recommendation.recommendation)}</div>
            <div className="confidence">
              <span className="confidence-label">Confidence:</span>
              <span className="confidence-value">{recommendation.confidence_score}%</span>
            </div>
          </div>
        </div>

        {/* Key Reasons */}
        {recommendation.key_reasons && recommendation.key_reasons.length > 0 && (
          <div className="key-reasons">
            <ul>
              {recommendation.key_reasons.slice(0, 3).map((reason, idx) => (
                <li key={idx}>{reason}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Quantitative Summary */}
        {recommendation.quantitative_summary && (
          <div className="quant-summary">
            <div className="summary-row">
              <span>Days to Close:</span>
              <strong>{recommendation.quantitative_summary.days_to_close}</strong>
            </div>
            <div className="summary-row">
              <span>Extension Risk:</span>
              <strong>{recommendation.quantitative_summary.extension_risk_percentage?.toFixed(1)}%</strong>
            </div>
            {recommendation.suggested_lock_term_days && (
              <div className="summary-row">
                <span>Suggested Lock:</span>
                <strong>{recommendation.suggested_lock_term_days} days</strong>
              </div>
            )}
          </div>
        )}

        {/* Toggle Details */}
        <button
          className="toggle-details-btn"
          onClick={() => setShowDetails(!showDetails)}
        >
          {showDetails ? 'Hide Details' : 'Show Details'}
        </button>

        {/* Expanded Details */}
        {showDetails && recommendation.quantitative_summary && (
          <div className="expanded-details">
            <div className="detail-row">
              <span>Loan Risk Score:</span>
              <strong>{recommendation.quantitative_summary.loan_risk_score?.toFixed(0)}/100</strong>
            </div>
            <div className="detail-row">
              <span>Market Volatility:</span>
              <strong>{recommendation.quantitative_summary.market_volatility_score?.toFixed(0)}/100</strong>
            </div>
            <div className="detail-row">
              <span>Expected Value:</span>
              <strong>${recommendation.quantitative_summary.net_expected_value?.toFixed(0)}</strong>
            </div>
          </div>
        )}

        {/* Action Button */}
        {recommendation.recommendation === 'lock_now' && (
          <button className="action-btn-primary">
            Lock Rate Now
          </button>
        )}

        {/* Refresh Button */}
        <button className="refresh-btn" onClick={loadRecommendation}>
          Refresh Analysis
        </button>
      </div>
    </div>
  );
}

export default RateLockRecommendation;
