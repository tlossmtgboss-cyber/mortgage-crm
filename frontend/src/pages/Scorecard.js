import React from 'react';
import './Scorecard.css';

function Scorecard() {
  const conversionMetrics = {
    startsToApps: 77,
    appsToFunded: 62,
    pullThru: 48,
    creditPullConversion: 40,
  };

  const volumeRevenue = {
    fundedLoans: 60,
    totalVolume: 21300000,
    avgLoanAmount: 355000,
    basisPoints: 185,
  };

  const loanTypes = [
    { type: 'Conventional', volume: 19231700, percentage: 90.29 },
    { type: 'FHA', volume: 841350, percentage: 3.95 },
    { type: 'Jumbo', volume: 692250, percentage: 3.25 },
    { type: 'Seconds/HELOC', volume: 534700, percentage: 2.51 },
  ];

  const referralSources = [
    { source: 'Client Referrals', volume: 17300000 },
    { source: 'Realtor Referrals', volume: 4000000 },
  ];

  const processTimeline = {
    startsToApp: 10,
    appToUnderwriting: 5,
    lockFunding: 68,
  };

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
