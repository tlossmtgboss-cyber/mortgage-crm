import React, { useState, useEffect } from 'react';
import { profitabilityAPI } from '../services/api';
import './SmartRecommendations.css';

const SmartRecommendations = ({ month, autoLoad = false, maxItems = 5 }) => {
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastGenerated, setLastGenerated] = useState(null);

  useEffect(() => {
    if (autoLoad) {
      loadRecommendations();
    }
  }, [month, autoLoad]);

  const loadRecommendations = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await profitabilityAPI.getAIRecommendations(month);
      setRecommendations(data.recommendations || []);
      setLastGenerated(new Date().toLocaleTimeString());
    } catch (err) {
      console.error('Failed to load recommendations:', err);
      setError('Failed to generate recommendations. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const getPriorityIcon = (priority) => {
    switch (priority) {
      case 'high': return '🔴';
      case 'medium': return '🟡';
      case 'low': return '🟢';
      default: return '⚪';
    }
  };

  const getPriorityClass = (priority) => {
    return `priority-${priority || 'medium'}`;
  };

  return (
    <div className="smart-recommendations">
      <div className="recommendations-header">
        <div className="header-left">
          <h3>Smart Recommendations</h3>
          {lastGenerated && (
            <span className="last-updated">Updated {lastGenerated}</span>
          )}
        </div>
        <button
          className="generate-btn"
          onClick={loadRecommendations}
          disabled={loading}
        >
          {loading ? 'Generating...' : 'Generate'}
        </button>
      </div>

      {error && (
        <div className="recommendations-error">
          <p>{error}</p>
        </div>
      )}

      {loading && recommendations.length === 0 && (
        <div className="recommendations-loading">
          <div className="loading-spinner"></div>
          <p>Analyzing your data...</p>
        </div>
      )}

      {!loading && recommendations.length === 0 && !error && (
        <div className="recommendations-empty">
          <p>Click "Generate" to get AI-powered recommendations based on your profitability data.</p>
        </div>
      )}

      {recommendations.length > 0 && (
        <div className="recommendations-list">
          {recommendations.slice(0, maxItems).map((rec, idx) => (
            <div key={idx} className={`recommendation-item ${getPriorityClass(rec.priority)}`}>
              <div className="rec-header">
                <span className="rec-priority">
                  {getPriorityIcon(rec.priority)} {rec.priority?.toUpperCase()}
                </span>
                <span className="rec-number">#{idx + 1}</span>
              </div>
              <h4 className="rec-title">{rec.title}</h4>
              <p className="rec-action">{rec.action}</p>
              <div className="rec-details">
                <div className="rec-impact">
                  <strong>Expected Impact:</strong>
                  <span>{rec.impact}</span>
                </div>
                <div className="rec-rationale">
                  <strong>Why:</strong>
                  <span>{rec.rationale}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {recommendations.length > maxItems && (
        <div className="recommendations-footer">
          <span>{recommendations.length - maxItems} more recommendations available</span>
        </div>
      )}
    </div>
  );
};

export default SmartRecommendations;
