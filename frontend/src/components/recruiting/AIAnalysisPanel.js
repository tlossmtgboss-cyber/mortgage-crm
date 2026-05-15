/**
 * AIAnalysisPanel - AI-powered candidate analysis display and controls
 * Shows AI-suggested scores, strengths/weaknesses, and hire recommendation
 */

import React, { useState, useCallback } from 'react';
import { runAIAnalysis, getGradeFromScore } from '../../services/candidateGradingApi';
import './AIAnalysisPanel.css';

const AIAnalysisPanel = ({
  candidateId,
  candidateName,
  currentAssessment,
  onApplyScores,
  onRefresh
}) => {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState(null);
  const [appliedCategories, setAppliedCategories] = useState({});
  const [applyingAll, setApplyingAll] = useState(false);

  const handleRunAnalysis = useCallback(async () => {
    setIsAnalyzing(true);
    setError(null);
    try {
      const result = await runAIAnalysis(candidateId);
      setAnalysis(result);
      setAppliedCategories({});
    } catch (err) {
      setError(err.message || 'Failed to run AI analysis');
    } finally {
      setIsAnalyzing(false);
    }
  }, [candidateId]);

  const handleApplyCategory = useCallback((category) => {
    if (!analysis?.score_suggestions) return;

    const suggestion = analysis.score_suggestions.find(s => s.category === category);
    if (!suggestion) return;

    setAppliedCategories(prev => ({ ...prev, [category]: true }));

    if (onApplyScores) {
      onApplyScores({
        [category]: {
          score: suggestion.suggested_score,
          reasoning: suggestion.reasoning
        }
      });
    }
  }, [analysis, onApplyScores]);

  const handleApplyAll = useCallback(async () => {
    if (!analysis?.score_suggestions) return;

    setApplyingAll(true);
    const allScores = {};

    for (const suggestion of analysis.score_suggestions) {
      allScores[suggestion.category] = {
        score: suggestion.suggested_score,
        reasoning: suggestion.reasoning
      };
      setAppliedCategories(prev => ({ ...prev, [suggestion.category]: true }));
    }

    if (onApplyScores) {
      await onApplyScores(allScores);
    }

    setApplyingAll(false);
    if (onRefresh) onRefresh();
  }, [analysis, onApplyScores, onRefresh]);

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.8) return '#2D7A52';
    if (confidence >= 0.6) return '#eab308';
    return '#f97316';
  };

  const getConfidenceLabel = (confidence) => {
    if (confidence >= 0.8) return 'High';
    if (confidence >= 0.6) return 'Medium';
    return 'Low';
  };

  const getRecommendationStyle = (recommendation) => {
    switch (recommendation?.toLowerCase()) {
      case 'strong_hire':
        return { bg: '#dcfce7', color: '#166534', label: 'Strong Hire' };
      case 'hire':
        return { bg: '#d1fae5', color: '#1F5A3A', label: 'Hire' };
      case 'maybe':
        return { bg: '#fef3c7', color: '#92400e', label: 'Maybe' };
      case 'no_hire':
        return { bg: '#fee2e2', color: '#991b1b', label: 'No Hire' };
      default:
        return { bg: '#f3f4f6', color: '#4b5563', label: 'Unknown' };
    }
  };

  // Category display names
  const categoryLabels = {
    production: 'Production',
    disc: 'DISC/Personality',
    character: 'Character',
    skills: 'Skills',
    culture_fit: 'Culture Fit'
  };

  return (
    <div className="ai-analysis-panel">
      <div className="ai-analysis-header">
        <div className="ai-analysis-title">
          <span className="ai-icon">🤖</span>
          <h3>AI Analysis</h3>
        </div>
        <button
          className={`ai-run-btn ${isAnalyzing ? 'analyzing' : ''}`}
          onClick={handleRunAnalysis}
          disabled={isAnalyzing}
        >
          {isAnalyzing ? (
            <>
              <span className="spinner"></span>
              Analyzing...
            </>
          ) : (
            <>
              <span>✨</span>
              {analysis ? 'Re-run Analysis' : 'Run AI Analysis'}
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="ai-error">
          <span>⚠️</span>
          {error}
        </div>
      )}

      {!analysis && !isAnalyzing && !error && (
        <div className="ai-empty-state">
          <div className="ai-empty-icon">🧠</div>
          <p>Run AI analysis to get intelligent scoring suggestions based on candidate data.</p>
          <p className="ai-empty-hint">
            Analysis reviews resume, social profiles, interview notes, and other available data.
          </p>
        </div>
      )}

      {analysis && (
        <div className="ai-analysis-results">
          {/* Confidence & Recommendation */}
          <div className="ai-summary-row">
            <div className="ai-confidence">
              <span className="ai-label">Confidence</span>
              <div className="ai-confidence-bar">
                <div
                  className="ai-confidence-fill"
                  style={{
                    width: `${(analysis.confidence || 0) * 100}%`,
                    backgroundColor: getConfidenceColor(analysis.confidence || 0)
                  }}
                />
              </div>
              <span
                className="ai-confidence-label"
                style={{ color: getConfidenceColor(analysis.confidence || 0) }}
              >
                {getConfidenceLabel(analysis.confidence || 0)} ({Math.round((analysis.confidence || 0) * 100)}%)
              </span>
            </div>

            {analysis.hire_recommendation && (
              <div
                className="ai-recommendation"
                style={{
                  backgroundColor: getRecommendationStyle(analysis.hire_recommendation).bg,
                  color: getRecommendationStyle(analysis.hire_recommendation).color
                }}
              >
                {getRecommendationStyle(analysis.hire_recommendation).label}
              </div>
            )}
          </div>

          {/* Score Suggestions */}
          {analysis.score_suggestions && analysis.score_suggestions.length > 0 && (
            <div className="ai-score-suggestions">
              <div className="ai-section-header">
                <h4>Score Suggestions</h4>
                <button
                  className="ai-apply-all-btn"
                  onClick={handleApplyAll}
                  disabled={applyingAll || Object.keys(appliedCategories).length === analysis.score_suggestions.length}
                >
                  {applyingAll ? 'Applying...' : 'Apply All'}
                </button>
              </div>

              <div className="ai-suggestions-grid">
                {analysis.score_suggestions.map((suggestion) => {
                  const gradeInfo = getGradeFromScore(suggestion.suggested_score);
                  const isApplied = appliedCategories[suggestion.category];
                  const currentScore = currentAssessment?.[`${suggestion.category}_score`];
                  const scoreDiff = currentScore != null
                    ? suggestion.suggested_score - currentScore
                    : null;

                  return (
                    <div
                      key={suggestion.category}
                      className={`ai-suggestion-card ${isApplied ? 'applied' : ''}`}
                    >
                      <div className="ai-suggestion-header">
                        <span className="ai-suggestion-category">
                          {categoryLabels[suggestion.category] || suggestion.category}
                        </span>
                        <div className="ai-suggestion-score-group">
                          <span
                            className="ai-suggestion-score"
                            style={{ color: gradeInfo.color }}
                          >
                            {suggestion.suggested_score}
                          </span>
                          <span
                            className="ai-suggestion-grade"
                            style={{ backgroundColor: gradeInfo.color }}
                          >
                            {gradeInfo.grade}
                          </span>
                        </div>
                      </div>

                      {scoreDiff !== null && (
                        <div className={`ai-score-diff ${scoreDiff > 0 ? 'positive' : scoreDiff < 0 ? 'negative' : ''}`}>
                          {scoreDiff > 0 ? '+' : ''}{scoreDiff.toFixed(0)} vs current
                        </div>
                      )}

                      <p className="ai-suggestion-reasoning">{suggestion.reasoning}</p>

                      <div className="ai-suggestion-confidence">
                        <div
                          className="ai-mini-confidence"
                          style={{ backgroundColor: getConfidenceColor(suggestion.confidence || 0.5) }}
                        />
                        <span>{Math.round((suggestion.confidence || 0.5) * 100)}% confident</span>
                      </div>

                      <div className="ai-suggestion-actions">
                        {isApplied ? (
                          <span className="ai-applied-badge">✓ Applied</span>
                        ) : (
                          <button
                            className="ai-apply-btn"
                            onClick={() => handleApplyCategory(suggestion.category)}
                          >
                            Apply Score
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* DISC Inference */}
          {analysis.disc_inference && (
            <div className="ai-disc-inference">
              <h4>DISC Profile Analysis</h4>
              <div className="ai-disc-grid">
                <div className="ai-disc-item">
                  <span className="ai-disc-label">D</span>
                  <div className="ai-disc-bar">
                    <div
                      className="ai-disc-fill d"
                      style={{ width: `${analysis.disc_inference.d_score || 0}%` }}
                    />
                  </div>
                  <span className="ai-disc-value">{analysis.disc_inference.d_score || 0}</span>
                </div>
                <div className="ai-disc-item">
                  <span className="ai-disc-label">I</span>
                  <div className="ai-disc-bar">
                    <div
                      className="ai-disc-fill i"
                      style={{ width: `${analysis.disc_inference.i_score || 0}%` }}
                    />
                  </div>
                  <span className="ai-disc-value">{analysis.disc_inference.i_score || 0}</span>
                </div>
                <div className="ai-disc-item">
                  <span className="ai-disc-label">S</span>
                  <div className="ai-disc-bar">
                    <div
                      className="ai-disc-fill s"
                      style={{ width: `${analysis.disc_inference.s_score || 0}%` }}
                    />
                  </div>
                  <span className="ai-disc-value">{analysis.disc_inference.s_score || 0}</span>
                </div>
                <div className="ai-disc-item">
                  <span className="ai-disc-label">C</span>
                  <div className="ai-disc-bar">
                    <div
                      className="ai-disc-fill c"
                      style={{ width: `${analysis.disc_inference.c_score || 0}%` }}
                    />
                  </div>
                  <span className="ai-disc-value">{analysis.disc_inference.c_score || 0}</span>
                </div>
              </div>
              <div className="ai-disc-styles">
                <span className="ai-disc-primary">
                  Primary: <strong>{analysis.disc_inference.primary_style}</strong>
                </span>
                {analysis.disc_inference.secondary_style && (
                  <span className="ai-disc-secondary">
                    Secondary: <strong>{analysis.disc_inference.secondary_style}</strong>
                  </span>
                )}
              </div>
              {analysis.disc_inference.notes && (
                <p className="ai-disc-notes">{analysis.disc_inference.notes}</p>
              )}
            </div>
          )}

          {/* Strengths & Weaknesses */}
          <div className="ai-traits-section">
            {analysis.strengths && analysis.strengths.length > 0 && (
              <div className="ai-traits-column">
                <h4>
                  <span className="trait-icon positive">💪</span>
                  Strengths
                </h4>
                <ul className="ai-traits-list">
                  {analysis.strengths.map((strength, idx) => (
                    <li key={idx} className="ai-trait-item positive">
                      <span className="ai-trait-text">{strength.trait}</span>
                      <span className="ai-trait-evidence">{strength.evidence}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {analysis.weaknesses && analysis.weaknesses.length > 0 && (
              <div className="ai-traits-column">
                <h4>
                  <span className="trait-icon negative">⚠️</span>
                  Areas of Concern
                </h4>
                <ul className="ai-traits-list">
                  {analysis.weaknesses.map((weakness, idx) => (
                    <li key={idx} className="ai-trait-item negative">
                      <span className="ai-trait-text">{weakness.trait}</span>
                      <span className="ai-trait-evidence">{weakness.evidence}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Recommendation Reasoning */}
          {analysis.recommendation_reasoning && (
            <div className="ai-recommendation-section">
              <h4>Recommendation Reasoning</h4>
              <p>{analysis.recommendation_reasoning}</p>
            </div>
          )}

          {/* Data Sources */}
          {analysis.data_sources && analysis.data_sources.length > 0 && (
            <div className="ai-data-sources">
              <span className="ai-sources-label">Data analyzed:</span>
              {analysis.data_sources.map((source, idx) => (
                <span key={idx} className="ai-source-tag">{source}</span>
              ))}
            </div>
          )}

          {/* Analysis Timestamp */}
          {analysis.analyzed_at && (
            <div className="ai-timestamp">
              Analysis run: {new Date(analysis.analyzed_at).toLocaleString()}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AIAnalysisPanel;
