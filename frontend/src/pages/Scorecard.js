import React, { useState, useEffect } from 'react';
import { analyticsAPI } from '../services/api';
import { fetchStats as fetchCIEStats } from '../client-file/cie-api';
import './Scorecard.css';

function Scorecard() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [period, setPeriod] = useState({ start_date: null, end_date: null });
  const [cieStats, setCieStats] = useState(null);

  useEffect(() => {
    loadScorecard();
    loadCIEStats();
    const interval = setInterval(() => { loadScorecard(); loadCIEStats(); }, 60000);
    return () => clearInterval(interval);
  }, []);

  const loadCIEStats = async () => {
    try {
      const stats = await fetchCIEStats();
      setCieStats(stats);
    } catch (e) {
      // CIE stats are optional — don't block the scorecard
    }
  };

  const loadScorecard = async () => {
    try {
      setLoading(true);
      setError(null);
      // Fetch real data from API
      const apiData = await analyticsAPI.getScorecard();
      setData(apiData);
      if (apiData.period) {
        setPeriod(apiData.period);
      }
      setLoading(false);
    } catch (error) {
      console.error('Failed to load scorecard:', error);
      setError(error.response?.data?.detail || error.message || 'Failed to load scorecard');
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    if (status === 'good') return '#4caf50';
    if (status === 'warning') return '#ff9800';
    if (status === 'critical') return '#f44336';
    return '#9e9e9e';
  };

  const formatCurrency = (amount) => {
    if (!amount) return '$0.00';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  };

  const formatNumber = (num) => {
    if (!num) return '0';
    return new Intl.NumberFormat('en-US').format(num);
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
  };

  if (loading) {
    return (
      <div className="scorecard-page">
        <div className="loading">Loading scorecard...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="scorecard-page">
        <div className="error-container" style={{ padding: '40px', textAlign: 'center' }}>
          <h2 style={{ color: '#f44336' }}>Failed to Load Scorecard</h2>
          <p style={{ marginBottom: '20px' }}>{error}</p>
          <button
            onClick={loadScorecard}
            className="btn-primary"
            style={{ padding: '10px 20px', cursor: 'pointer' }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="scorecard-page">
        <div className="loading">No data available</div>
      </div>
    );
  }

  return (
    <div className="scorecard-page">
      <div className="scorecard-header-main">
        <h1>Loan Scorecard Report</h1>
        <div className="scorecard-subtitle">
          {period.start_date ? formatDate(period.start_date) : 'Loading...'} | LO Scorecard
        </div>
      </div>

      {/* LOAN STARTS VS. ACTIVITY TOTALS */}
      <section className="scorecard-section green-section">
        <div className="section-header green-header">
          <span className="indicator"></span>
          Loan Starts vs. Activity Totals
        </div>
        <div className="section-subheader">
          Counts: {period.start_date || 'N/A'} - {period.end_date || 'N/A'}
        </div>

        <div className="metrics-table-container">
          <table className="scorecard-table">
            <thead>
              <tr>
                <th>Counts</th>
                <th></th>
                <th></th>
                <th>MoT%</th>
                <th>Progress</th>
                <th>Goal%</th>
              </tr>
            </thead>
            <tbody>
              {data.conversion_metrics && data.conversion_metrics.map((metric, index) => (
                <tr key={index}>
                  <td className="metric-name">{metric.metric}</td>
                  <td className="metric-count">{metric.total}</td>
                  <td className="metric-count">{metric.current}</td>
                  <td className="metric-pct">{metric.mot_pct}%</td>
                  <td className="progress-cell">
                    <div className="progress-bar-container">
                      <div
                        className="progress-bar-fill"
                        style={{
                          width: `${Math.min((metric.mot_pct / metric.goal_pct) * 100, 100)}%`,
                          backgroundColor: getStatusColor(metric.status),
                        }}
                      />
                    </div>
                  </td>
                  <td className="metric-pct goal-pct">{metric.goal_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* CONVERSION UPSWING */}
      {data.conversion_upswing && (
      <section className="scorecard-section pink-section">
        <div className="section-header pink-header">
          <span className="indicator"></span>
          Conversion Upswing:
        </div>

        <div className="upswing-grid">
          <div className="upswing-table">
            <h4>10% in Starts</h4>
            <table>
              <tbody>
                <tr>
                  <td>Starts</td>
                  <td className="value">{formatNumber(data.conversion_upswing.current_starts)}</td>
                  <td className="target">Current</td>
                </tr>
                <tr>
                  <td>Starts to Funded Pull-thru</td>
                  <td className="value">{data.conversion_upswing.current_pull_thru_pct}%</td>
                  <td className="target">{data.conversion_upswing.target_pull_thru_pct}%</td>
                </tr>
                <tr>
                  <td>Avg loan amount</td>
                  <td className="value">{formatCurrency(data.conversion_upswing.current_avg_amount)}</td>
                  <td className="target">{formatCurrency(data.conversion_upswing.target_avg_amount)}</td>
                </tr>
                <tr>
                  <td>Increase in volume</td>
                  <td className="value">{formatCurrency(data.conversion_upswing.current_volume)}</td>
                  <td className="target">{formatCurrency(data.conversion_upswing.volume_increase)}</td>
                </tr>
                <tr>
                  <td>Current Avg bps</td>
                  <td className="value">{data.conversion_upswing.current_bps}</td>
                  <td className="target">{data.conversion_upswing.target_bps}</td>
                </tr>
                <tr>
                  <td>Additional compensation</td>
                  <td className="value">{formatCurrency(data.conversion_upswing.current_compensation)}</td>
                  <td className="target highlight">{formatCurrency(data.conversion_upswing.additional_compensation)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
      )}

      {/* CALL INTELLIGENCE SCORES */}
      <section className="scorecard-section blue-section">
        <div className="section-header blue-header">
          <span className="indicator"></span>
          Call Intelligence Scores
        </div>

        <div className="call-scores-content">
          <div className="call-scores-summary">
            <div className="call-score-stat">
              <span className="call-score-stat__value">{cieStats?.total_calls ?? 0}</span>
              <span className="call-score-stat__label">Total Calls</span>
            </div>
            <div className="call-score-stat">
              <span className="call-score-stat__value">{cieStats?.analyzed ?? 0}</span>
              <span className="call-score-stat__label">Analyzed</span>
            </div>
            <div className="call-score-stat">
              <span className="call-score-stat__value call-score-stat__value--accent">
                {cieStats?.avg_cis != null ? (cieStats.avg_cis / 10).toFixed(1) : '—'}
              </span>
              <span className="call-score-stat__label">Avg Score (/ 10)</span>
            </div>
            <div className="call-score-stat">
              <span className="call-score-stat__value">
                {cieStats?.avg_conversion != null ? `${(cieStats.avg_conversion * 100).toFixed(0)}%` : '—'}
              </span>
              <span className="call-score-stat__label">Avg Conversion</span>
            </div>
            <div className="call-score-stat">
              <span className="call-score-stat__value">{cieStats?.pending ?? 0}</span>
              <span className="call-score-stat__label">Pending</span>
            </div>
          </div>

          {cieStats && cieStats.analyzed > 0 && cieStats.avg_cis != null && (
            <div className="call-score-gauge-row">
              <div className="call-score-gauge">
                <div className="call-score-gauge__label">Call Quality Score</div>
                <div className="call-score-gauge__bar-container">
                  <div
                    className="call-score-gauge__bar-fill"
                    style={{
                      width: `${Math.min(cieStats.avg_cis, 100)}%`,
                      backgroundColor: cieStats.avg_cis >= 80 ? '#4caf50' : cieStats.avg_cis >= 60 ? '#ff9800' : '#f44336',
                    }}
                  />
                </div>
                <div className="call-score-gauge__number">
                  {(cieStats.avg_cis / 10).toFixed(1)} / 10
                </div>
              </div>
            </div>
          )}

          {(!cieStats || cieStats.total_calls === 0) && (
            <div className="call-scores-empty">
              No calls analyzed yet. Call scores will appear here once calls are processed by the Call Intelligence Engine.
            </div>
          )}

          <div className="call-scores-dimensions">
            <h4>Score Dimensions</h4>
            <table className="scorecard-table">
              <thead>
                <tr>
                  <th>Dimension</th>
                  <th>Target</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="metric-name">Engagement</td>
                  <td className="metric-pct goal-pct">80%+</td>
                  <td>Active listening, questions asked, rapport building</td>
                </tr>
                <tr>
                  <td className="metric-name">Information Quality</td>
                  <td className="metric-pct goal-pct">80%+</td>
                  <td>Accuracy, thoroughness, clarity of explanations</td>
                </tr>
                <tr>
                  <td className="metric-name">Objection Handling</td>
                  <td className="metric-pct goal-pct">75%+</td>
                  <td>Addressing concerns, overcoming resistance</td>
                </tr>
                <tr>
                  <td className="metric-name">Compliance</td>
                  <td className="metric-pct goal-pct">90%+</td>
                  <td>TRID, fair lending, consent disclosures</td>
                </tr>
                <tr>
                  <td className="metric-name">Rapport</td>
                  <td className="metric-pct goal-pct">80%+</td>
                  <td>Trust building, empathy, personal connection</td>
                </tr>
                <tr>
                  <td className="metric-name">Closing Effectiveness</td>
                  <td className="metric-pct goal-pct">75%+</td>
                  <td>Next steps, commitment, call-to-action clarity</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* FUNDING TOTALS */}
      {data.funding_totals && (
      <section className="scorecard-section yellow-section">
        <div className="section-header yellow-header">
          <span className="indicator"></span>
          Funding Totals
        </div>

        <div className="funding-grid">
          {/* Funded Loans Summary */}
          <div className="funding-table-container">
            <table className="funding-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Units</th>
                  <th>Volume</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="label">Funded Loans</td>
                  <td>{data.funding_totals.total_units}</td>
                  <td className="volume">{formatCurrency(data.funding_totals.total_volume)}</td>
                </tr>
                <tr>
                  <td className="label">Avg Loan Amount</td>
                  <td colSpan="2">{formatCurrency(data.funding_totals.avg_loan_amount)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Loan Type Breakdown */}
          <div className="funding-table-container">
            <table className="funding-table">
              <thead>
                <tr>
                  <th>Loan Type</th>
                  <th>Units</th>
                  <th>Volume</th>
                  <th>%</th>
                </tr>
              </thead>
              <tbody>
                {data.funding_totals.loan_types && data.funding_totals.loan_types.map((type, index) => (
                  <tr key={index}>
                    <td>{type.type}</td>
                    <td>{type.units}</td>
                    <td className="volume">{formatCurrency(type.volume)}</td>
                    <td>{type.percentage.toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Referral Source Breakdown */}
          <div className="funding-table-container">
            <table className="funding-table">
              <thead>
                <tr>
                  <th>Referral Source</th>
                  <th>Referrals</th>
                  <th>Closed Volume</th>
                </tr>
              </thead>
              <tbody>
                {data.funding_totals.referral_sources && data.funding_totals.referral_sources.map((source, index) => (
                  <tr key={index}>
                    <td>{source.source}</td>
                    <td>{source.referrals}</td>
                    <td className="volume">{formatCurrency(source.closed_volume)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
      )}

      <div className="scorecard-footer">
        <small>Last updated: {new Date(data.generated_at).toLocaleString()}</small>
        <small>Auto-refreshes every 60 seconds</small>
      </div>
    </div>
  );
}

export default Scorecard;
