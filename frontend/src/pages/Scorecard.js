import React, { useState, useEffect } from 'react';
import { analyticsAPI } from '../services/api';
import './Scorecard.css';

function Scorecard() {
  const [loading, setLoading] = useState(true);
  const [conversionMetrics, setConversionMetrics] = useState({
    startsToApps: 0,
    appsToFunded: 0,
    pullThru: 0,
    creditPullConversion: 0,
  });
  const [volumeRevenue, setVolumeRevenue] = useState({
    fundedLoans: 0,
    totalVolume: 0,
    avgLoanAmount: 0,
    basisPoints: 0,
  });
  const [loanTypes, setLoanTypes] = useState([]);
  const [referralSources, setReferralSources] = useState([]);
  const [processTimeline, setProcessTimeline] = useState({
    startsToApp: 0,
    appToUnderwriting: 0,
    lockFunding: 0,
  });

  useEffect(() => {
    loadScorecard();
  }, []);

  const loadScorecard = async () => {
    try {
      setLoading(true);
      const data = await analyticsAPI.getScorecard();

      setConversionMetrics({
        startsToApps: data.conversion_metrics.starts_to_apps || 0,
        appsToFunded: data.conversion_metrics.apps_to_funded || 0,
        pullThru: data.conversion_metrics.pull_thru || 0,
        creditPullConversion: data.conversion_metrics.credit_pull_conversion || 0,
      });

      setVolumeRevenue({
        fundedLoans: data.volume_revenue.funded_loans || 0,
        totalVolume: data.volume_revenue.total_volume || 0,
        avgLoanAmount: data.volume_revenue.avg_loan_amount || 0,
        basisPoints: data.volume_revenue.basis_points || 0,
      });

      setLoanTypes(data.loan_type_distribution || []);
      setReferralSources(data.referral_sources || []);
      setProcessTimeline({
        startsToApp: data.process_timeline.starts_to_app || 0,
        appToUnderwriting: data.process_timeline.app_to_underwriting || 0,
        lockFunding: data.process_timeline.lock_funding || 0,
      });
    } catch (error) {
      console.error('Failed to load scorecard:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="scorecard-page">
        <div className="loading">Loading scorecard...</div>
      </div>
    );
  }

  return (
    <div className="scorecard-page">
      <div className="page-header">
        <h1>Scorecard - Business Metrics</h1>
        <p>Performance analytics and key metrics</p>
      </div>

      <div className="metrics-section">
        <h2>Conversion Metrics</h2>
        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-value">{conversionMetrics.startsToApps}%</div>
            <div className="metric-label">Starts to Apps</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">{conversionMetrics.appsToFunded}%</div>
            <div className="metric-label">Apps to Funded</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">{conversionMetrics.pullThru}%</div>
            <div className="metric-label">Pull-thru Rate</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">{conversionMetrics.creditPullConversion}%</div>
            <div className="metric-label">Credit Pull Conversion</div>
          </div>
        </div>
      </div>

      <div className="metrics-section">
        <h2>Volume & Revenue</h2>
        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-value">{volumeRevenue.fundedLoans}</div>
            <div className="metric-label">Funded Loans</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">${(volumeRevenue.totalVolume / 1000000).toFixed(1)}M</div>
            <div className="metric-label">Total Volume</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">${(volumeRevenue.avgLoanAmount / 1000).toFixed(0)}k</div>
            <div className="metric-label">Avg Loan Amount</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">{volumeRevenue.basisPoints}</div>
            <div className="metric-label">Basis Points</div>
          </div>
        </div>
      </div>

      <div className="metrics-section">
        <h2>Loan Type Distribution</h2>
        <div className="table-container">
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Loan Type</th>
                <th>Volume</th>
                <th>Percentage</th>
              </tr>
            </thead>
            <tbody>
              {loanTypes.map((item) => (
                <tr key={item.type}>
                  <td className="type-label">{item.type}</td>
                  <td className="volume-amount">${item.volume.toLocaleString()}</td>
                  <td>
                    <div className="percentage-bar">
                      <div
                        className="percentage-fill"
                        style={{ width: `${item.percentage}%` }}
                      />
                      <span className="percentage-text">{item.percentage}%</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="metrics-section">
        <h2>Referral Source Performance</h2>
        <div className="referral-cards">
          {referralSources.map((item) => (
            <div key={item.source} className="referral-card">
              <div className="referral-label">{item.source}</div>
              <div className="referral-value">${(item.volume / 1000000).toFixed(1)}M</div>
            </div>
          ))}
        </div>
      </div>

      <div className="metrics-section">
        <h2>Process Timeline</h2>
        <div className="timeline-metrics">
          <div className="timeline-item">
            <div className="timeline-value">{processTimeline.startsToApp} days</div>
            <div className="timeline-label">Starts to App</div>
          </div>
          <div className="timeline-arrow">→</div>
          <div className="timeline-item">
            <div className="timeline-value">{processTimeline.appToUnderwriting} days</div>
            <div className="timeline-label">App to Underwriting</div>
          </div>
          <div className="timeline-arrow">→</div>
          <div className="timeline-item">
            <div className="timeline-value">{processTimeline.lockFunding}%</div>
            <div className="timeline-label">Lock Funding Rate</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Scorecard;
