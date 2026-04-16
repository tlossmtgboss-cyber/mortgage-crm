import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import './PipelineProbability.css';
import { getToken } from '../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || '';

// Utility for API calls
const fetchWithAuth = async (endpoint, options = {}) => {
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'Content-Type': 'application/json',
      ...options.headers
    }
  });
  if (!response.ok) throw new Error('API request failed');
  return response.json();
};

// Format currency
const formatCurrency = (amount) => {
  if (!amount) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(amount);
};

// Risk level badge component
const RiskBadge = ({ level }) => {
  const colors = {
    low: '#10b981',
    medium: '#f59e0b',
    high: '#ef4444',
    critical: '#dc2626'
  };

  return (
    <span
      className={`risk-badge risk-${level}`}
      style={{ backgroundColor: colors[level] || colors.medium }}
    >
      {level?.toUpperCase()}
    </span>
  );
};

// Trend indicator component
const TrendIndicator = ({ trend }) => {
  const icons = {
    improving: '↑',
    stable: '→',
    declining: '↓'
  };

  return (
    <span className={`trend-indicator trend-${trend}`}>
      {icons[trend] || icons.stable}
    </span>
  );
};

// Probability bar component
const ProbabilityBar = ({ value, showLabel = true }) => {
  const getColor = (val) => {
    if (val >= 80) return '#10b981';
    if (val >= 60) return '#3b82f6';
    if (val >= 40) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="probability-bar-container">
      <div className="probability-bar">
        <div
          className="probability-fill"
          style={{
            width: `${Math.min(value, 100)}%`,
            backgroundColor: getColor(value)
          }}
        />
      </div>
      {showLabel && <span className="probability-value">{value}%</span>}
    </div>
  );
};

// Pipeline Probability Dashboard Widget
export const PipelineProbabilityWidget = ({ compact = false }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [atRiskLoans, setAtRiskLoans] = useState([]);
  const [error, setError] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [summaryData, atRiskData] = await Promise.all([
        fetchWithAuth('/api/v1/pipeline-probability/summary'),
        fetchWithAuth('/api/v1/pipeline-probability/at-risk?threshold=50&limit=5')
      ]);

      setSummary(summaryData);
      setAtRiskLoans(atRiskData);
    } catch (err) {
      console.error('Failed to load probability data:', err);
      setError('Failed to load pipeline probability data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div className="pp-widget loading">
        <div className="loading-spinner" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="pp-widget error">
        <p>{error}</p>
        <button onClick={loadData}>Retry</button>
      </div>
    );
  }

  if (compact) {
    return (
      <div className="pp-widget compact" onClick={() => navigate('/pipeline-probability')}>
        <div className="pp-compact-header">
          <h3>Pipeline Health</h3>
          <span className="pp-score">{summary?.weighted_avg_probability || 0}%</span>
        </div>
        <ProbabilityBar value={summary?.weighted_avg_probability || 0} showLabel={false} />
        <div className="pp-compact-stats">
          <span className="pp-stat">
            <span className="stat-value danger">{summary?.critical_risk_count || 0}</span>
            <span className="stat-label">Critical</span>
          </span>
          <span className="pp-stat">
            <span className="stat-value warning">{summary?.high_risk_count || 0}</span>
            <span className="stat-label">High Risk</span>
          </span>
          <span className="pp-stat">
            <span className="stat-value">{formatCurrency(summary?.expected_funded_volume)}</span>
            <span className="stat-label">Expected</span>
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="pp-widget">
      <div className="pp-header">
        <h2>Pipeline Probability</h2>
        <button className="pp-view-all" onClick={() => navigate('/pipeline-probability')}>
          View Details →
        </button>
      </div>

      {/* Summary Stats */}
      <div className="pp-summary-grid">
        <div className="pp-summary-card primary">
          <div className="pp-summary-label">Weighted Probability</div>
          <div className="pp-summary-value">{summary?.weighted_avg_probability || 0}%</div>
          <ProbabilityBar value={summary?.weighted_avg_probability || 0} showLabel={false} />
        </div>

        <div className="pp-summary-card">
          <div className="pp-summary-label">Expected Funded</div>
          <div className="pp-summary-value">{formatCurrency(summary?.expected_funded_volume)}</div>
        </div>

        <div className="pp-summary-card warning">
          <div className="pp-summary-label">At-Risk Volume</div>
          <div className="pp-summary-value">{formatCurrency(summary?.at_risk_volume)}</div>
        </div>

        <div className="pp-summary-card">
          <div className="pp-summary-label">Total Pipeline</div>
          <div className="pp-summary-value">{summary?.total_loans || 0} loans</div>
        </div>
      </div>

      {/* Risk Distribution */}
      <div className="pp-risk-distribution">
        <h4>Risk Distribution</h4>
        <div className="pp-risk-bars">
          <div className="pp-risk-bar">
            <span className="risk-label">Low</span>
            <div className="risk-bar-fill low" style={{ width: `${(summary?.low_risk_count / summary?.total_loans) * 100 || 0}%` }} />
            <span className="risk-count">{summary?.low_risk_count || 0}</span>
          </div>
          <div className="pp-risk-bar">
            <span className="risk-label">Medium</span>
            <div className="risk-bar-fill medium" style={{ width: `${(summary?.medium_risk_count / summary?.total_loans) * 100 || 0}%` }} />
            <span className="risk-count">{summary?.medium_risk_count || 0}</span>
          </div>
          <div className="pp-risk-bar">
            <span className="risk-label">High</span>
            <div className="risk-bar-fill high" style={{ width: `${(summary?.high_risk_count / summary?.total_loans) * 100 || 0}%` }} />
            <span className="risk-count">{summary?.high_risk_count || 0}</span>
          </div>
          <div className="pp-risk-bar">
            <span className="risk-label">Critical</span>
            <div className="risk-bar-fill critical" style={{ width: `${(summary?.critical_risk_count / summary?.total_loans) * 100 || 0}%` }} />
            <span className="risk-count">{summary?.critical_risk_count || 0}</span>
          </div>
        </div>
      </div>

      {/* At-Risk Loans */}
      {atRiskLoans.length > 0 && (
        <div className="pp-at-risk">
          <h4>At-Risk Loans (Below 50%)</h4>
          <div className="pp-at-risk-list">
            {atRiskLoans.slice(0, 5).map((loan) => (
              <div
                key={loan.loan_id}
                className="pp-at-risk-item"
                onClick={() => navigate(`/loans/${loan.loan_id}`)}
              >
                <div className="at-risk-info">
                  <span className="at-risk-borrower">{loan.borrower_name}</span>
                  <span className="at-risk-amount">{formatCurrency(loan.loan_amount)}</span>
                </div>
                <div className="at-risk-metrics">
                  <ProbabilityBar value={loan.close_probability} />
                  <RiskBadge level={loan.risk_level} />
                  <TrendIndicator trend={loan.trend} />
                </div>
                {loan.recommended_actions?.length > 0 && (
                  <div className="at-risk-action">
                    <span className="action-icon">💡</span>
                    <span className="action-text">{loan.recommended_actions[0]?.action}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Trends */}
      <div className="pp-trends">
        <div className="pp-trend-item">
          <span className="trend-icon">↑</span>
          <span className="trend-count">{summary?.improving_count || 0}</span>
          <span className="trend-label">Improving</span>
        </div>
        <div className="pp-trend-item">
          <span className="trend-icon">↓</span>
          <span className="trend-count">{summary?.declining_count || 0}</span>
          <span className="trend-label">Declining</span>
        </div>
      </div>
    </div>
  );
};

// Full Pipeline Probability Page
export const PipelineProbabilityPage = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [loans, setLoans] = useState([]);
  const [distribution, setDistribution] = useState(null);
  const [filters, setFilters] = useState({
    riskLevel: '',
    minProbability: '',
    maxProbability: ''
  });
  const [selectedLoan, setSelectedLoan] = useState(null);
  const [error, setError] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams();
      if (filters.riskLevel) params.append('risk_level', filters.riskLevel);
      if (filters.minProbability) params.append('min_probability', filters.minProbability);
      if (filters.maxProbability) params.append('max_probability', filters.maxProbability);

      const [summaryData, loansData, distData] = await Promise.all([
        fetchWithAuth('/api/v1/pipeline-probability/summary'),
        fetchWithAuth(`/api/v1/pipeline-probability/pipeline?${params.toString()}`),
        fetchWithAuth('/api/v1/pipeline-probability/distribution')
      ]);

      setSummary(summaryData);
      setLoans(loansData);
      setDistribution(distData);
    } catch (err) {
      console.error('Failed to load probability data:', err);
      setError('Failed to load pipeline probability data');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const loadLoanDetails = async (loanId) => {
    try {
      const details = await fetchWithAuth(`/api/v1/pipeline-probability/loan/${loanId}`);
      setSelectedLoan(details);
    } catch (err) {
      console.error('Failed to load loan details:', err);
    }
  };

  if (loading) {
    return (
      <div className="pp-page loading">
        <div className="loading-spinner" />
        <p>Calculating pipeline probabilities...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="pp-page error">
        <h2>Error</h2>
        <p>{error}</p>
        <button onClick={loadData}>Retry</button>
      </div>
    );
  }

  return (
    <div className="pp-page">
      <div className="pp-page-header">
        <div className="pp-page-title">
          <h1>Pipeline Probability Analysis</h1>
          <p>AI-powered closing probability predictions for your pipeline</p>
        </div>
        <button className="pp-refresh-btn" onClick={loadData}>
          <i className="fas fa-sync-alt" /> Refresh Scores
        </button>
      </div>

      {/* Summary Cards */}
      <div className="pp-page-summary">
        <div className="pp-summary-card large">
          <div className="pp-summary-icon">📊</div>
          <div className="pp-summary-content">
            <div className="pp-summary-label">Weighted Avg Probability</div>
            <div className="pp-summary-value large">{summary?.weighted_avg_probability || 0}%</div>
          </div>
        </div>

        <div className="pp-summary-card">
          <div className="pp-summary-icon">💰</div>
          <div className="pp-summary-content">
            <div className="pp-summary-label">Expected Funded Volume</div>
            <div className="pp-summary-value">{formatCurrency(summary?.expected_funded_volume)}</div>
          </div>
        </div>

        <div className="pp-summary-card">
          <div className="pp-summary-icon">📈</div>
          <div className="pp-summary-content">
            <div className="pp-summary-label">Total Pipeline</div>
            <div className="pp-summary-value">{formatCurrency(summary?.total_volume)}</div>
            <div className="pp-summary-subtext">{summary?.total_loans || 0} loans</div>
          </div>
        </div>

        <div className="pp-summary-card warning">
          <div className="pp-summary-icon">⚠️</div>
          <div className="pp-summary-content">
            <div className="pp-summary-label">At-Risk Volume</div>
            <div className="pp-summary-value">{formatCurrency(summary?.at_risk_volume)}</div>
            <div className="pp-summary-subtext">{(summary?.high_risk_count || 0) + (summary?.critical_risk_count || 0)} loans</div>
          </div>
        </div>
      </div>

      {/* Distribution Chart */}
      {distribution && (
        <div className="pp-distribution-section">
          <h3>Probability Distribution</h3>
          <div className="pp-distribution-chart">
            {distribution.buckets?.map((bucket) => (
              <div key={bucket} className="pp-distribution-bar">
                <div className="distribution-bar-fill" style={{
                  height: `${(distribution.distribution[bucket]?.count / distribution.total_loans) * 100 || 0}%`
                }} />
                <div className="distribution-label">{bucket}%</div>
                <div className="distribution-count">{distribution.distribution[bucket]?.count || 0}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top Risk Factors */}
      {summary?.top_risk_factors?.length > 0 && (
        <div className="pp-risk-factors-section">
          <h3>Top Risk Factors Across Pipeline</h3>
          <div className="pp-risk-factors-list">
            {summary.top_risk_factors.map((rf, idx) => (
              <div key={idx} className="pp-risk-factor-item">
                <span className="rf-factor">{rf.factor}</span>
                <span className="rf-count">{rf.count} loans</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="pp-filters">
        <select
          value={filters.riskLevel}
          onChange={(e) => handleFilterChange('riskLevel', e.target.value)}
        >
          <option value="">All Risk Levels</option>
          <option value="low">Low Risk</option>
          <option value="medium">Medium Risk</option>
          <option value="high">High Risk</option>
          <option value="critical">Critical</option>
        </select>

        <input
          type="number"
          placeholder="Min Probability"
          value={filters.minProbability}
          onChange={(e) => handleFilterChange('minProbability', e.target.value)}
        />

        <input
          type="number"
          placeholder="Max Probability"
          value={filters.maxProbability}
          onChange={(e) => handleFilterChange('maxProbability', e.target.value)}
        />
      </div>

      {/* Loans Table */}
      <div className="pp-loans-section">
        <h3>Pipeline Loans ({loans.length})</h3>
        <div className="pp-loans-table">
          <table>
            <thead>
              <tr>
                <th>Borrower</th>
                <th>Loan Amount</th>
                <th>Status</th>
                <th>Probability</th>
                <th>Risk</th>
                <th>Trend</th>
                <th>Days to Close</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loans.map((loan) => (
                <tr
                  key={loan.loan_id}
                  className={`pp-loan-row ${selectedLoan?.loan_id === loan.loan_id ? 'selected' : ''}`}
                  onClick={() => loadLoanDetails(loan.loan_id)}
                >
                  <td>
                    <div className="loan-borrower">
                      <span className="borrower-name">{loan.borrower_name}</span>
                      <span className="loan-number">{loan.loan_number}</span>
                    </div>
                  </td>
                  <td>{formatCurrency(loan.loan_amount)}</td>
                  <td>
                    <span className="loan-status">{loan.current_status}</span>
                  </td>
                  <td>
                    <div className="probability-cell">
                      <ProbabilityBar value={loan.close_probability} />
                    </div>
                  </td>
                  <td><RiskBadge level={loan.risk_level} /></td>
                  <td><TrendIndicator trend={loan.trend} /></td>
                  <td>
                    {loan.expected_close_days} days
                    {loan.lock_expiration_risk && (
                      <span className="lock-warning" title="Lock expiration risk">⚠️</span>
                    )}
                  </td>
                  <td>
                    <button
                      className="pp-view-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/loans/${loan.loan_id}`);
                      }}
                    >
                      View Loan
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Loan Detail Panel */}
      {selectedLoan && (
        <div className="pp-loan-detail-panel">
          <div className="pp-detail-header">
            <h3>{selectedLoan.borrower_name}</h3>
            <button className="pp-close-btn" onClick={() => setSelectedLoan(null)}>×</button>
          </div>

          <div className="pp-detail-content">
            <div className="pp-detail-score">
              <div className="score-circle" style={{
                borderColor: selectedLoan.close_probability >= 70 ? '#10b981' :
                             selectedLoan.close_probability >= 50 ? '#f59e0b' : '#ef4444'
              }}>
                <span className="score-value">{selectedLoan.close_probability}%</span>
                <span className="score-label">Probability</span>
              </div>
              <div className="confidence-level">
                Confidence: {selectedLoan.confidence_level}%
              </div>
            </div>

            {/* Risk Factors */}
            {selectedLoan.risk_factors?.length > 0 && (
              <div className="pp-detail-section">
                <h4>Risk Factors</h4>
                <div className="pp-factors-list">
                  {selectedLoan.risk_factors.map((rf, idx) => (
                    <div key={idx} className="pp-factor-item risk">
                      <div className="factor-header">
                        <span className="factor-name">{rf.factor}</span>
                        <span className="factor-impact">{(rf.impact * 100).toFixed(0)}%</span>
                      </div>
                      <p className="factor-desc">{rf.description}</p>
                      {rf.mitigation && (
                        <p className="factor-mitigation">💡 {rf.mitigation}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Strength Factors */}
            {selectedLoan.strength_factors?.length > 0 && (
              <div className="pp-detail-section">
                <h4>Strength Factors</h4>
                <div className="pp-factors-list">
                  {selectedLoan.strength_factors.map((sf, idx) => (
                    <div key={idx} className="pp-factor-item strength">
                      <div className="factor-header">
                        <span className="factor-name">{sf.factor}</span>
                        <span className="factor-impact success">+{(sf.impact * 100).toFixed(0)}%</span>
                      </div>
                      <p className="factor-desc">{sf.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recommended Actions */}
            {selectedLoan.recommended_actions?.length > 0 && (
              <div className="pp-detail-section">
                <h4>Recommended Actions</h4>
                <div className="pp-actions-list">
                  {selectedLoan.recommended_actions.map((action, idx) => (
                    <div key={idx} className={`pp-action-item priority-${action.priority}`}>
                      <div className="action-header">
                        <span className="action-priority">{action.priority}</span>
                        <span className="action-impact">+{action.expected_impact}% potential</span>
                      </div>
                      <p className="action-text">{action.action}</p>
                      <div className="action-meta">
                        <span className="action-effort">Effort: {action.effort}</span>
                        {action.deadline_days && (
                          <span className="action-deadline">Complete in {action.deadline_days} days</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Comparison */}
            <div className="pp-detail-section comparison">
              <h4>Comparison</h4>
              <div className="comparison-stats">
                {selectedLoan.similar_loans_close_rate && (
                  <div className="comparison-stat">
                    <span className="stat-label">Similar Loans Close Rate</span>
                    <span className="stat-value">{selectedLoan.similar_loans_close_rate}%</span>
                  </div>
                )}
                {selectedLoan.stage_avg_probability && (
                  <div className="comparison-stat">
                    <span className="stat-label">Stage Avg Probability</span>
                    <span className="stat-value">{selectedLoan.stage_avg_probability}%</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default { PipelineProbabilityWidget, PipelineProbabilityPage };
