import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './IntelligencePanel.css';

const IntelligencePanel = ({ recordingId }) => {
  const [intelligence, setIntelligence] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    concerns: true,
    compliance: true,
    competitors: false,
    objections: false,
    effectiveness: false,
    details: false,
    nextSteps: false
  });

  useEffect(() => {
    if (recordingId) {
      loadIntelligence();
    }
  }, [recordingId]);

  const loadIntelligence = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await axios.get(
        `/api/v1/meetings/recordings/${recordingId}/intelligence`
      );
      setIntelligence(response.data);
      setLoading(false);
    } catch (err) {
      console.error('Error loading intelligence:', err);
      if (err.response?.status === 404) {
        setError('Intelligence analysis not available yet. Click "Analyze" to process this recording.');
      } else {
        setError('Failed to load intelligence data');
      }
      setLoading(false);
    }
  };

  const triggerAnalysis = async () => {
    try {
      setLoading(true);
      await axios.post(
        `/api/v1/meetings/recordings/${recordingId}/intelligence/analyze`
      );
      // Poll for results
      setTimeout(loadIntelligence, 3000);
    } catch (err) {
      setError('Failed to start analysis');
      setLoading(false);
    }
  };

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const formatTimestamp = (seconds) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'critical':
      case 'high': return '#ef4444';
      case 'medium': return '#f59e0b';
      case 'low': return '#2D7A52';
      default: return '#6b7280';
    }
  };

  const getRiskScoreColor = (score) => {
    if (score >= 0.6) return '#ef4444';
    if (score >= 0.3) return '#f59e0b';
    return '#2D7A52';
  };

  if (loading) {
    return (
      <div className="intelligence-loading">
        <div className="loading-spinner"></div>
        <p>Loading intelligence analysis...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="intelligence-error">
        <p>{error}</p>
        <button onClick={triggerAnalysis} className="analyze-button">
          Analyze Recording
        </button>
      </div>
    );
  }

  if (!intelligence) {
    return (
      <div className="intelligence-empty">
        <h3>No Intelligence Available</h3>
        <p>Run analysis to get mortgage-specific insights from this recording.</p>
        <button onClick={triggerAnalysis} className="analyze-button">
          Analyze Recording
        </button>
      </div>
    );
  }

  return (
    <div className="intelligence-panel">
      {/* Risk Score Header */}
      <div className="risk-score-header">
        <div className="risk-score-display">
          <span className="risk-label">Overall Risk Score</span>
          <span
            className="risk-value"
            style={{ color: getRiskScoreColor(intelligence.overall_risk_score) }}
          >
            {((intelligence.overall_risk_score || 0) * 100).toFixed(0)}%
          </span>
        </div>
        {intelligence.overall_risk_score > 0.3 && (
          <span className="risk-warning">⚠️ Elevated Risk - Review Recommended</span>
        )}
      </div>

      {/* Priority Flags */}
      {intelligence.priority_flags?.length > 0 && (
        <div className="priority-flags-section">
          <h3>⚡ Priority Alerts</h3>
          <div className="priority-flags">
            {intelligence.priority_flags.map((flag, idx) => (
              <div
                key={idx}
                className="priority-flag"
                style={{ borderLeftColor: getSeverityColor(flag.severity) }}
              >
                <div className="flag-header">
                  <span
                    className="flag-severity"
                    style={{ backgroundColor: getSeverityColor(flag.severity) }}
                  >
                    {flag.severity}
                  </span>
                  <span className="flag-type">{flag.type}</span>
                </div>
                <p className="flag-message">{flag.message}</p>
                {flag.action && (
                  <p className="flag-action">💡 {flag.action}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Borrower Concerns */}
      <div className="intelligence-section">
        <div
          className="section-header"
          onClick={() => toggleSection('concerns')}
        >
          <h3>🚨 Borrower Concerns ({intelligence.borrower_concerns?.length || 0})</h3>
          <span className="toggle-icon">{expandedSections.concerns ? '−' : '+'}</span>
        </div>
        {expandedSections.concerns && intelligence.borrower_concerns?.length > 0 && (
          <div className="section-content">
            {intelligence.borrower_concerns.map((concern, idx) => (
              <div
                key={idx}
                className={`concern-card severity-${concern.severity}`}
              >
                <div className="concern-header">
                  <span className="concern-type">
                    {concern.concern_type.replace(/_/g, ' ')}
                  </span>
                  <span className="concern-time">
                    {formatTimestamp(concern.timestamp)}
                  </span>
                </div>
                <p className="concern-context">"{concern.context}"</p>
                <p className="concern-speaker">— {concern.speaker}</p>
              </div>
            ))}
          </div>
        )}
        {expandedSections.concerns && intelligence.borrower_concerns?.length === 0 && (
          <p className="no-items">No borrower concerns detected ✓</p>
        )}
      </div>

      {/* Compliance Risks */}
      <div className="intelligence-section compliance-section">
        <div
          className="section-header"
          onClick={() => toggleSection('compliance')}
        >
          <h3>⚠️ Compliance Alerts ({intelligence.compliance_risks?.length || 0})</h3>
          <span className="toggle-icon">{expandedSections.compliance ? '−' : '+'}</span>
        </div>
        {expandedSections.compliance && intelligence.compliance_risks?.length > 0 && (
          <div className="section-content">
            {intelligence.compliance_risks.map((risk, idx) => (
              <div
                key={idx}
                className={`risk-card severity-${risk.severity}`}
              >
                <div className="risk-header">
                  <span className="risk-type">{risk.risk_type.replace(/_/g, ' ')}</span>
                  <span
                    className="risk-severity-badge"
                    style={{ backgroundColor: getSeverityColor(risk.severity) }}
                  >
                    {risk.severity}
                  </span>
                </div>
                <p className="risk-context">"{risk.context}"</p>
                <p className="risk-time">@ {formatTimestamp(risk.timestamp)}</p>
                <p className="risk-recommendation">
                  💡 {risk.recommendation}
                </p>
              </div>
            ))}
          </div>
        )}
        {expandedSections.compliance && intelligence.compliance_risks?.length === 0 && (
          <p className="no-items success">No compliance issues detected ✓</p>
        )}
      </div>

      {/* Competitor Intelligence */}
      <div className="intelligence-section">
        <div
          className="section-header"
          onClick={() => toggleSection('competitors')}
        >
          <h3>🏢 Competitor Mentions ({intelligence.competitor_mentions?.total_mentions || 0})</h3>
          <span className="toggle-icon">{expandedSections.competitors ? '−' : '+'}</span>
        </div>
        {expandedSections.competitors && intelligence.competitor_mentions?.summary && (
          <div className="section-content">
            {Object.keys(intelligence.competitor_mentions.summary).length > 0 ? (
              Object.entries(intelligence.competitor_mentions.summary).map(([competitor, data]) => (
                <div key={competitor} className="competitor-card">
                  <div className="competitor-header">
                    <h4>{competitor}</h4>
                    <span className="mention-count">
                      {data.count} mention{data.count !== 1 ? 's' : ''}
                    </span>
                  </div>
                  <div className="competitor-contexts">
                    {data.contexts.slice(0, 2).map((context, idx) => (
                      <p key={idx} className="context-snippet">"{context}"</p>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <p className="no-items">No competitors mentioned ✓</p>
            )}
          </div>
        )}
      </div>

      {/* Objection Handling */}
      <div className="intelligence-section">
        <div
          className="section-header"
          onClick={() => toggleSection('objections')}
        >
          <h3>💬 Objections & Responses ({intelligence.objections?.length || 0})</h3>
          <span className="toggle-icon">{expandedSections.objections ? '−' : '+'}</span>
        </div>
        {expandedSections.objections && intelligence.objections?.length > 0 && (
          <div className="section-content">
            {intelligence.objections.map((objection, idx) => (
              <div key={idx} className="objection-card">
                <div className="objection-header">
                  <span
                    className={`handling-badge ${objection.handled_well ? 'good' : 'needs-work'}`}
                  >
                    {objection.handled_well ? '✓ Well Handled' : '⚠ Needs Improvement'}
                  </span>
                  <span className="objection-time">
                    {formatTimestamp(objection.timestamp)}
                  </span>
                </div>
                <div className="objection-content">
                  <p className="objection-text">
                    <strong>Objection:</strong> "{objection.objection}"
                  </p>
                  <p className="response-text">
                    <strong>Response:</strong> "{objection.lo_response}"
                  </p>
                </div>
                {objection.handling_tips && (
                  <p className="handling-tips">💡 {objection.handling_tips}</p>
                )}
              </div>
            ))}
          </div>
        )}
        {expandedSections.objections && intelligence.objections?.length === 0 && (
          <p className="no-items">No objections detected</p>
        )}
      </div>

      {/* Explanation Effectiveness */}
      <div className="intelligence-section">
        <div
          className="section-header"
          onClick={() => toggleSection('effectiveness')}
        >
          <h3>📊 Explanation Effectiveness</h3>
          <span className="toggle-icon">{expandedSections.effectiveness ? '−' : '+'}</span>
        </div>
        {expandedSections.effectiveness && intelligence.explanation_effectiveness && (
          <div className="section-content">
            <div className="effectiveness-card">
              <div className="effectiveness-score">
                <span
                  className={`effectiveness-badge ${intelligence.explanation_effectiveness.effectiveness}`}
                >
                  {intelligence.explanation_effectiveness.effectiveness?.replace(/_/g, ' ')}
                </span>
                <span className="effectiveness-percentage">
                  {((intelligence.explanation_effectiveness.score || 0) * 100).toFixed(0)}%
                </span>
              </div>
              <div className="effectiveness-signals">
                <span className="signal positive">
                  ✅ {intelligence.explanation_effectiveness.positive_signals || 0} understanding signals
                </span>
                <span className="signal negative">
                  ❓ {intelligence.explanation_effectiveness.negative_signals || 0} confusion signals
                </span>
              </div>
              {intelligence.explanation_effectiveness.confusion_moments?.length > 0 && (
                <div className="confusion-moments">
                  <h4>Moments of Confusion:</h4>
                  {intelligence.explanation_effectiveness.confusion_moments.map((moment, idx) => (
                    <p key={idx} className="confusion-moment">
                      @ {formatTimestamp(moment.timestamp)}: "{moment.text}"
                    </p>
                  ))}
                </div>
              )}
              <p className="effectiveness-recommendation">
                {intelligence.explanation_effectiveness.recommendation}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Loan Details */}
      <div className="intelligence-section">
        <div
          className="section-header"
          onClick={() => toggleSection('details')}
        >
          <h3>📄 Loan Details Discussed</h3>
          <span className="toggle-icon">{expandedSections.details ? '−' : '+'}</span>
        </div>
        {expandedSections.details && intelligence.loan_details && (
          <div className="section-content">
            <div className="loan-details-grid">
              {intelligence.loan_details.loan_amount && (
                <div className="detail-item">
                  <span className="detail-label">Loan Amount</span>
                  <span className="detail-value">{intelligence.loan_details.loan_amount}</span>
                </div>
              )}
              {intelligence.loan_details.loan_type && (
                <div className="detail-item">
                  <span className="detail-label">Loan Type</span>
                  <span className="detail-value">{intelligence.loan_details.loan_type.toUpperCase()}</span>
                </div>
              )}
              {intelligence.loan_details.rate_mentioned && (
                <div className="detail-item">
                  <span className="detail-label">Rate</span>
                  <span className="detail-value">
                    {intelligence.loan_details.rate_value || 'Discussed'}
                  </span>
                </div>
              )}
              {intelligence.loan_details.term_mentioned && (
                <div className="detail-item">
                  <span className="detail-label">Term</span>
                  <span className="detail-value">{intelligence.loan_details.term_mentioned}</span>
                </div>
              )}
              {intelligence.loan_details.credit_score_mentioned && (
                <div className="detail-item">
                  <span className="detail-label">Credit Score</span>
                  <span className="detail-value">
                    {intelligence.loan_details.credit_score_value || 'Discussed'}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Next Steps Clarity */}
      <div className="intelligence-section">
        <div
          className="section-header"
          onClick={() => toggleSection('nextSteps')}
        >
          <h3>✅ Next Steps Clarity</h3>
          <span className="toggle-icon">{expandedSections.nextSteps ? '−' : '+'}</span>
        </div>
        {expandedSections.nextSteps && intelligence.next_steps_clarity && (
          <div className="section-content">
            <div className="next-steps-card">
              <div className="clarity-indicator">
                <span
                  className={`clarity-badge ${intelligence.next_steps_clarity.clear ? 'clear' : 'unclear'}`}
                >
                  {intelligence.next_steps_clarity.clear ? '✓ Clear' : '⚠ Unclear'}
                </span>
                <span className="clarity-score">
                  {((intelligence.next_steps_clarity.clarity_score || 0) * 100).toFixed(0)}%
                </span>
              </div>
              {intelligence.next_steps_clarity.next_steps?.length > 0 && (
                <div className="next-steps-list">
                  <h4>Mentioned Next Steps:</h4>
                  <ul>
                    {intelligence.next_steps_clarity.next_steps.map((step, idx) => (
                      <li key={idx}>{step}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="next-steps-recommendation">
                {intelligence.next_steps_clarity.recommendation}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default IntelligencePanel;
