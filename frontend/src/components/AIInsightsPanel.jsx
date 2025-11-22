import React, { useState, useEffect } from 'react';
import { profitabilityAPI } from '../services/api';
import './AIInsightsPanel.css';

const AIInsightsPanel = ({ month, onInsightGenerated }) => {
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState([]);
  const [quickInsights, setQuickInsights] = useState(null);

  useEffect(() => {
    loadSuggestedQuestions();
    loadQuickInsights();
  }, [month]);

  const loadSuggestedQuestions = async () => {
    try {
      const data = await profitabilityAPI.getSuggestedQuestions();
      setSuggestedQuestions(data.questions || []);
    } catch (err) {
      console.error('Failed to load suggested questions:', err);
    }
  };

  const loadQuickInsights = async () => {
    try {
      const data = await profitabilityAPI.getQuickInsights(month);
      setQuickInsights(data);
    } catch (err) {
      console.error('Failed to load quick insights:', err);
    }
  };

  const handleQuery = async (questionText = null) => {
    const text = questionText || query;
    if (!text.trim()) return;

    try {
      setLoading(true);
      const result = await profitabilityAPI.queryAI(text, month);
      setResponse(result);
      setQuery('');
      if (onInsightGenerated) onInsightGenerated(result);
    } catch (err) {
      console.error('AI query failed:', err);
      setResponse({
        question: text,
        answer: 'Sorry, I was unable to process your question. Please try again.',
        error: true
      });
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleQuery();
    }
  };

  return (
    <div className="ai-insights-panel">
      <div className="panel-header">
        <h3>AI Insights Assistant</h3>
        <span className="ai-badge">Powered by Claude</span>
      </div>

      {/* Quick Insights */}
      {quickInsights && quickInsights.alerts && quickInsights.alerts.length > 0 && (
        <div className="quick-alerts">
          <h4>Alerts</h4>
          {quickInsights.alerts.map((alert, idx) => (
            <div key={idx} className={`alert-item ${alert.severity}`}>
              <span className="alert-type">{alert.type}</span>
              <p>{alert.description}</p>
            </div>
          ))}
        </div>
      )}

      {/* Query Input */}
      <div className="query-section">
        <div className="query-input-wrapper">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about your profitability data..."
            disabled={loading}
            rows={2}
          />
          <button
            className="query-btn"
            onClick={() => handleQuery()}
            disabled={loading || !query.trim()}
          >
            {loading ? (
              <span className="loading-dots">...</span>
            ) : (
              <span>Ask</span>
            )}
          </button>
        </div>
      </div>

      {/* Suggested Questions */}
      {!response && suggestedQuestions.length > 0 && (
        <div className="suggested-section">
          <h4>Suggested Questions</h4>
          <div className="question-grid">
            {suggestedQuestions.slice(0, 2).map((category, idx) => (
              <div key={idx} className="question-category">
                <span className="category-name">{category.category}</span>
                {category.questions.slice(0, 2).map((q, qIdx) => (
                  <button
                    key={qIdx}
                    className="question-btn"
                    onClick={() => handleQuery(q)}
                    disabled={loading}
                  >
                    {q}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Response */}
      {response && (
        <div className={`response-section ${response.error ? 'error' : ''}`}>
          <div className="response-question">
            <strong>Q:</strong> {response.question}
          </div>
          <div className="response-answer">
            {response.answer.split('\n').map((line, i) => (
              <p key={i}>{line}</p>
            ))}
          </div>
          <button
            className="clear-btn"
            onClick={() => setResponse(null)}
          >
            Ask Another Question
          </button>
        </div>
      )}

      {/* Quick Actions */}
      <div className="quick-actions">
        <button
          className="action-btn"
          onClick={() => handleQuery("What are my top opportunities for improvement?")}
          disabled={loading}
        >
          Find Opportunities
        </button>
        <button
          className="action-btn"
          onClick={() => handleQuery("Give me a summary of this month's performance")}
          disabled={loading}
        >
          Monthly Summary
        </button>
      </div>
    </div>
  );
};

export default AIInsightsPanel;
