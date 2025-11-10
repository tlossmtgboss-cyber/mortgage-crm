import React, { useState, useEffect } from 'react';
import { analyticsAPI } from '../services/api';
import './Scorecard.css';

function Scorecard() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState({ start: null, end: null });

  useEffect(() => {
    loadScorecard();
    // Auto-refresh every 60 seconds for real-time updates
    const interval = setInterval(loadScorecard, 60000);
    return () => clearInterval(interval);
  }, []);

  const loadScorecard = async () => {
    try {
      setLoading(true);
      // Fetch real data from API
      const apiData = await analyticsAPI.getScorecard();
      setData(apiData);
      if (apiData.period) {
        setPeriod(apiData.period);
      }
      setLoading(false);
    } catch (error) {
      console.error('Failed to load scorecard:', error);
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

  if (loading || !data) {
    return (
      <div className="scorecard-page">
        <div className="loading">Loading scorecard...</div>
      </div>
    );
  }

  return (
    <div className="scorecard-page">
      <div className="scorecard-header-main">
        <h1>Loan Scorecard Report</h1>
        <div className="scorecard-subtitle">
          {formatDate(period.start_date)} | LO Scorecard
        </div>
      </div>

      {/* LOAN STARTS VS. ACTIVITY TOTALS */}
      <section className="scorecard-section green-section">
        <div className="section-header green-header">
          <span className="indicator"></span>
          Loan Starts vs. Activity Totals
        </div>
        <div className="section-subheader">
          Counts: {period.start_date} - {period.end_date}
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
              {data.conversion_metrics.map((metric, index) => (
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

      {/* FUNDING TOTALS */}
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
                {data.funding_totals.loan_types.map((type, index) => (
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
                {data.funding_totals.referral_sources.map((source, index) => (
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

      <div className="scorecard-footer">
        <small>Last updated: {new Date(data.generated_at).toLocaleString()}</small>
        <small>Auto-refreshes every 60 seconds</small>
      </div>
    </div>
  );
}

export default Scorecard;
