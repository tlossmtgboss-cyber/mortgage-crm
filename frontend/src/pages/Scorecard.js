import React, { useState, useEffect } from 'react';
import { analyticsAPI } from '../services/api';
import GoalTracker from './GoalTracker';
import './Scorecard.css';

function Scorecard() {
  const [activeTab, setActiveTab] = useState('scorecard');
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

      // Ensure all required data structures exist with defaults
      const normalizedData = {
        conversion_metrics: apiData?.conversion_metrics || [],
        conversion_upswing: apiData?.conversion_upswing || {
          current_starts: 0,
          current_pull_thru_pct: 0,
          target_pull_thru_pct: 0,
          current_avg_amount: 0,
          target_avg_amount: 0,
          current_volume: 0,
          volume_increase: 0,
          current_bps: 0,
          target_bps: 0,
          current_compensation: 0,
          additional_compensation: 0
        },
        funding_totals: {
          total_units: apiData?.funding_totals?.total_units || 0,
          total_volume: apiData?.funding_totals?.total_volume || 0,
          avg_loan_amount: apiData?.funding_totals?.avg_loan_amount || 0,
          loan_types: apiData?.funding_totals?.loan_types || [],
          referral_sources: apiData?.funding_totals?.referral_sources || []
        },
        period: apiData?.period || { start_date: '', end_date: '' },
        generated_at: apiData?.generated_at || new Date().toISOString()
      };

      setData(normalizedData);
      if (normalizedData.period) {
        setPeriod(normalizedData.period);
      }
      setLoading(false);
    } catch (error) {
      console.error('Failed to load scorecard:', error);
      // Set empty data structure on error so page doesn't crash
      setData({
        conversion_metrics: [],
        conversion_upswing: {
          current_starts: 0,
          current_pull_thru_pct: 0,
          target_pull_thru_pct: 0,
          current_avg_amount: 0,
          target_avg_amount: 0,
          current_volume: 0,
          volume_increase: 0,
          current_bps: 0,
          target_bps: 0,
          current_compensation: 0,
          additional_compensation: 0
        },
        funding_totals: {
          total_units: 0,
          total_volume: 0,
          avg_loan_amount: 0,
          loan_types: [],
          referral_sources: []
        },
        period: { start_date: new Date().toISOString(), end_date: new Date().toISOString() },
        generated_at: new Date().toISOString()
      });
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

      {/* Tab Navigation */}
      <div className="scorecard-tabs">
        <button
          className={`tab-button ${activeTab === 'scorecard' ? 'active' : ''}`}
          onClick={() => setActiveTab('scorecard')}
        >
          Scorecard Report
        </button>
        <button
          className={`tab-button ${activeTab === 'goal-tracker' ? 'active' : ''}`}
          onClick={() => setActiveTab('goal-tracker')}
        >
          Goal Tracker
        </button>
      </div>

      {/* Conditional Tab Content */}
      {activeTab === 'scorecard' ? (
        <div className="scorecard-content">

      {/* TOP ROW: Loan Starts (left) and Conversion Upswing (right) */}
      <div className="scorecard-top-row">
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
                {data.conversion_metrics && data.conversion_metrics.length > 0 ? (
                  data.conversion_metrics.map((metric, index) => (
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
                  ))
                ) : (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '40px', color: '#666' }}>
                      No conversion metrics available
                    </td>
                  </tr>
                )}
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
          <div className="section-subheader">
            {period.start_date} - {period.end_date}
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
      </div>

      {/* BOTTOM ROW: Funding Totals (full width) */}
      <section className="scorecard-section yellow-section">
        <div className="section-header yellow-header">
          <span className="indicator"></span>
          Funding Totals
        </div>
        <div className="section-subheader">
          {period.start_date} - {period.end_date}
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
                {data.funding_totals.loan_types && data.funding_totals.loan_types.length > 0 ? (
                  data.funding_totals.loan_types.map((type, index) => (
                    <tr key={index}>
                      <td>{type.type}</td>
                      <td>{type.units}</td>
                      <td className="volume">{formatCurrency(type.volume)}</td>
                      <td>{type.percentage.toFixed(2)}%</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="4" style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
                      No loan type data available
                    </td>
                  </tr>
                )}
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
                {data.funding_totals.referral_sources && data.funding_totals.referral_sources.length > 0 ? (
                  data.funding_totals.referral_sources.map((source, index) => (
                    <tr key={index}>
                      <td>{source.source}</td>
                      <td>{source.referrals}</td>
                      <td className="volume">{formatCurrency(source.closed_volume)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="3" style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
                      No referral source data available
                    </td>
                  </tr>
                )}
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
      ) : (
        <GoalTracker />
      )}
    </div>
  );
}

export default Scorecard;
