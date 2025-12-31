/**
 * IntakeScorePanel - Displays real-time scores, coaching suggestions, and flags
 */

import React, { useState } from 'react';
import './IntakeScorePanel.css';

function IntakeScorePanel({ scores, coaching, flags }) {
  const [expandedSection, setExpandedSection] = useState('scores');

  // Get color class based on score band
  const getBandColor = (band) => {
    const bandLower = (band || '').toLowerCase();
    if (bandLower === 'green') return 'band-green';
    if (bandLower === 'yellow' || bandLower === 'orange') return 'band-yellow';
    if (bandLower === 'red') return 'band-red';
    return 'band-neutral';
  };

  // Get color for numeric score (truth/readiness = higher is better)
  const getScoreColor = (score, inverse = false) => {
    if (inverse) {
      // For hesitation - lower is better
      if (score <= 20) return 'score-green';
      if (score <= 40) return 'score-yellow';
      return 'score-red';
    }
    // For truth/readiness - higher is better
    if (score >= 70) return 'score-green';
    if (score >= 50) return 'score-yellow';
    return 'score-red';
  };

  const toggleSection = (section) => {
    setExpandedSection(expandedSection === section ? null : section);
  };

  return (
    <div className="intake-score-panel">
      {/* Main Scores Section */}
      <div className="score-section">
        <div
          className="section-header"
          onClick={() => toggleSection('scores')}
        >
          <h3>Live Scores</h3>
          <span className={`toggle-icon ${expandedSection === 'scores' ? 'expanded' : ''}`}>
            ▼
          </span>
        </div>

        {expandedSection === 'scores' && (
          <div className="section-content">
            {/* Truth Score - Primary */}
            <div className="score-card primary">
              <div className="score-header">
                <span className="score-name">Truth Score</span>
                <span className={`score-band ${getBandColor(scores.truth_band)}`}>
                  {scores.truth_band || 'N/A'}
                </span>
              </div>
              <div className={`score-value ${getScoreColor(scores.truth_score || 0)}`}>
                {Math.round(scores.truth_score || 0)}%
              </div>
              <div className="score-bar">
                <div
                  className={`score-bar-fill ${getScoreColor(scores.truth_score || 0)}`}
                  style={{ width: `${scores.truth_score || 0}%` }}
                />
              </div>
            </div>

            {/* Secondary Scores */}
            <div className="score-row">
              <div className="score-card small">
                <span className="score-name">Readiness</span>
                <span className={`score-value ${getScoreColor(scores.readiness_score || 0)}`}>
                  {Math.round(scores.readiness_score || 0)}%
                </span>
              </div>

              <div className="score-card small">
                <span className="score-name">Hesitation</span>
                <span className={`score-value ${getScoreColor(scores.hesitation_score || 0, true)}`}>
                  {Math.round(scores.hesitation_score || 0)}%
                </span>
              </div>
            </div>

            {/* Score Breakdown */}
            {scores.breakdown && Object.keys(scores.breakdown).length > 0 && (
              <div className="score-breakdown">
                <h4>Breakdown</h4>
                <div className="breakdown-list">
                  {Object.entries(scores.breakdown).map(([key, value]) => (
                    <div key={key} className="breakdown-item">
                      <span className="breakdown-label">
                        {key.replace(/_/g, ' ')}
                      </span>
                      <span className="breakdown-value">
                        {typeof value === 'number' ? `${Math.round(value * 100)}%` : value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Coaching Section */}
      <div className="score-section">
        <div
          className="section-header"
          onClick={() => toggleSection('coaching')}
        >
          <h3>
            Coaching
            {coaching?.suggestions?.length > 0 && (
              <span className="badge">{coaching.suggestions.length}</span>
            )}
          </h3>
          <span className={`toggle-icon ${expandedSection === 'coaching' ? 'expanded' : ''}`}>
            ▼
          </span>
        </div>

        {expandedSection === 'coaching' && (
          <div className="section-content">
            {coaching?.suggestions?.length > 0 ? (
              <ul className="coaching-list">
                {coaching.suggestions.map((suggestion, idx) => (
                  <li key={idx} className="coaching-item">
                    <span className="coaching-icon">💡</span>
                    <span className="coaching-text">
                      {typeof suggestion === 'object' ? suggestion.text || suggestion.message : suggestion}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-message">No coaching suggestions yet</p>
            )}
          </div>
        )}
      </div>

      {/* Flags Section */}
      <div className="score-section">
        <div
          className="section-header"
          onClick={() => toggleSection('flags')}
        >
          <h3>
            Flags
            {flags?.flags?.length > 0 && (
              <span className="badge warning">{flags.flags.length}</span>
            )}
          </h3>
          <span className={`toggle-icon ${expandedSection === 'flags' ? 'expanded' : ''}`}>
            ▼
          </span>
        </div>

        {expandedSection === 'flags' && (
          <div className="section-content">
            {flags?.flags?.length > 0 ? (
              <ul className="flags-list">
                {flags.flags.map((flag, idx) => (
                  <li key={idx} className={`flag-item severity-${flag.severity || 'medium'}`}>
                    <span className="flag-icon">⚠️</span>
                    <div className="flag-content">
                      <span className="flag-type">{flag.type || 'Flag'}</span>
                      <span className="flag-message">
                        {typeof flag === 'object' ? flag.message || flag.description : flag}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-message">No flags detected</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default IntakeScorePanel;
