import React, { useState, useEffect } from 'react';
import { analyticsAPI } from '../services/api';
import './Scorecard.css';

function Scorecard() {
  const [loading, setLoading] = useState(true);
  const [drillDownModal, setDrillDownModal] = useState(null);

  // Sample data - replace with API call
  const [data, setData] = useState({
    conversionMetrics: [
      {
        id: 'starts-to-apps',
        title: 'Starts to Apps (LE)',
        value: 77,
        goal: 75,
        current: 73,
        total: 95,
        isPercentage: true,
      },
      {
        id: 'apps-to-funded',
        title: 'Apps (LE) to Funded',
        value: 62,
        goal: 80,
        current: 45,
        total: 73,
        isPercentage: true,
      },
      {
        id: 'starts-to-funded',
        title: 'Starts to Funded Pull-thru',
        value: 47,
        goal: 50,
        current: 45,
        total: 95,
        isPercentage: true,
      },
      {
        id: 'credit-to-funded',
        title: 'Credit Pull to Funded',
        value: 40,
        goal: 70,
        current: 45,
        total: 112,
        isPercentage: true,
      },
    ],
    volumeRevenue: [
      {
        id: 'funded-loans',
        title: 'Funded Loans',
        value: 60,
        subtitle: 'Avg Monthly: 12.0',
      },
      {
        id: 'total-volume',
        title: 'Total Volume',
        value: '$21.3M',
        subtitle: 'Avg Monthly: $4.26M',
      },
      {
        id: 'avg-loan',
        title: 'Avg Loan Amount',
        value: '$355k',
        subtitle: 'Current Period',
      },
      {
        id: 'avg-bps',
        title: 'Current Avg BPS',
        value: 100,
        subtitle: 'Basis Points',
      },
    ],
    loanTypes: [
      { type: 'Conventional', units: 54, volume: 19244653, percentage: 90.29 },
      { type: 'FHA', units: 2, volume: 841649, percentage: 3.95 },
      { type: 'JUMBO', units: 1, volume: 692000, percentage: 3.25 },
      { type: 'Seconds/HELOC', units: 3, volume: 535211, percentage: 2.51 },
    ],
    referralSources: [
      { source: 'Client', referrals: 50, closedVolume: 17514870 },
      { source: 'Realtor', referrals: 10, closedVolume: 3098843 },
      { source: 'Social Media/Network', referrals: 0, closedVolume: 0 },
      { source: 'Website', referrals: 0, closedVolume: 0 },
    ],
    processTimeline: [
      {
        id: 'starts-to-app',
        title: 'Avg Starts to App (LE)',
        value: '10 Days',
        subtitle: 'Loan Officer Average',
      },
      {
        id: 'app-to-uw',
        title: 'Avg App (LE) to UW',
        value: '5 Days',
        subtitle: 'Loan Officer Average',
      },
      {
        id: 'lock-to-funded',
        title: 'Initial Lock to Funded',
        value: 68,
        goal: 90,
        current: 45,
        total: 66,
        isPercentage: true,
      },
      {
        id: 'lock-extensions',
        title: 'Lock Extensions',
        value: 5,
        goal: 10,
        current: 3,
        total: 66,
        isPercentage: true,
        isLowerBetter: true,
      },
    ],
  });

  useEffect(() => {
    loadScorecard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadScorecard = async () => {
    try {
      setLoading(false);
      // TODO: Fetch real data from API
      // const data = await analyticsAPI.getScorecard();
      // setData(data);
    } catch (error) {
      console.error('Failed to load scorecard:', error);
      setLoading(false);
    }
  };

  const handleMetricClick = (metric, type) => {
    setDrillDownModal({ metric, type });
  };

  const handleExportReport = () => {
    alert('Export Report functionality coming soon!');
  };

  const renderProgressBar = (value, goal) => {
    const percentage = (value / goal) * 100;
    const isOverGoal = percentage >= 100;
    return (
      <div className="progress-bar">
        <div
          className={`progress-fill ${isOverGoal ? 'over-goal' : ''}`}
          style={{ width: `${Math.min(percentage, 100)}%` }}
        />
      </div>
    );
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
      <div className="scorecard-header">
        <div>
          <h1>Scorecard - Business Metrics</h1>
        </div>
        <button className="btn-export" onClick={handleExportReport}>
          Export Report
        </button>
      </div>

      {/* Conversion Metrics */}
      <section className="metrics-section">
        <h2>Conversion Metrics</h2>
        <div className="conversion-grid">
          {data.conversionMetrics.map((metric) => (
            <div
              key={metric.id}
              className="conversion-card clickable"
              onClick={() => handleMetricClick(metric, 'conversion')}
            >
              <div className="metric-title">{metric.title}</div>
              <div className="metric-value-large">{metric.value}%</div>
              <div className="metric-goal">
                Goal: {metric.goal}% | {metric.current} of {metric.total}
              </div>
              {renderProgressBar(metric.value, metric.goal)}
            </div>
          ))}
        </div>
      </section>

      {/* Volume & Revenue */}
      <section className="metrics-section">
        <h2>Volume & Revenue</h2>
        <div className="volume-grid">
          {data.volumeRevenue.map((metric) => (
            <div
              key={metric.id}
              className="volume-card clickable"
              onClick={() => handleMetricClick(metric, 'volume')}
            >
              <div className="metric-title">{metric.title}</div>
              <div className="metric-value-large">{metric.value}</div>
              <div className="metric-subtitle">{metric.subtitle}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Loan Type Distribution */}
      <section className="metrics-section">
        <h2>Loan Type Distribution</h2>
        <div className="table-container">
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Loan Type</th>
                <th>Units</th>
                <th>Volume</th>
                <th>% of Total</th>
              </tr>
            </thead>
            <tbody>
              {data.loanTypes.map((item) => (
                <tr
                  key={item.type}
                  className="clickable-row"
                  onClick={() => handleMetricClick(item, 'loanType')}
                >
                  <td className="type-label">{item.type}</td>
                  <td>{item.units}</td>
                  <td className="volume-amount">${item.volume.toLocaleString()}</td>
                  <td>{item.percentage}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Referral Source Performance */}
      <section className="metrics-section">
        <h2>Referral Source Performance</h2>
        <div className="table-container">
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Referral Source</th>
                <th>Referrals</th>
                <th>Closed Volume</th>
              </tr>
            </thead>
            <tbody>
              {data.referralSources.map((item) => (
                <tr
                  key={item.source}
                  className="clickable-row"
                  onClick={() => handleMetricClick(item, 'referralSource')}
                >
                  <td className="type-label">{item.source}</td>
                  <td>{item.referrals}</td>
                  <td className="volume-amount">${item.closedVolume.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Process Timeline */}
      <section className="metrics-section">
        <h2>Process Timeline</h2>
        <div className="timeline-grid">
          {data.processTimeline.map((metric) => (
            <div
              key={metric.id}
              className="timeline-card clickable"
              onClick={() => handleMetricClick(metric, 'timeline')}
            >
              <div className="metric-title">{metric.title}</div>
              <div className="metric-value-large">
                {metric.isPercentage ? `${metric.value}%` : metric.value}
              </div>
              {metric.goal ? (
                <>
                  <div className="metric-goal">
                    Goal: {metric.isLowerBetter ? '<' : ''}{metric.goal}
                    {metric.isPercentage ? '%' : ''} | {metric.current} of {metric.total}
                  </div>
                  {renderProgressBar(
                    metric.isLowerBetter ? metric.goal - metric.value + metric.goal : metric.value,
                    metric.goal
                  )}
                </>
              ) : (
                <div className="metric-subtitle">{metric.subtitle}</div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Drill-Down Modal */}
      {drillDownModal && (
        <div className="modal-overlay" onClick={() => setDrillDownModal(null)}>
          <div className="drill-down-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>
                {drillDownModal.metric.title || drillDownModal.metric.type || drillDownModal.metric.source}
              </h2>
              <button className="close-btn" onClick={() => setDrillDownModal(null)}>
                ×
              </button>
            </div>
            <div className="modal-content">
              <div className="drill-down-summary">
                <h3>Detailed Breakdown</h3>
                <p>Click on any data point below to see individual records:</p>
              </div>

              {drillDownModal.type === 'conversion' && (
                <div className="drill-down-stats">
                  <div className="stat-row">
                    <span className="stat-label">Current Performance:</span>
                    <span className="stat-value">
                      {drillDownModal.metric.value}% ({drillDownModal.metric.current} of{' '}
                      {drillDownModal.metric.total})
                    </span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Goal:</span>
                    <span className="stat-value">{drillDownModal.metric.goal}%</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Gap to Goal:</span>
                    <span
                      className={`stat-value ${
                        drillDownModal.metric.value >= drillDownModal.metric.goal ? 'positive' : 'negative'
                      }`}
                    >
                      {drillDownModal.metric.value >= drillDownModal.metric.goal ? '+' : ''}
                      {drillDownModal.metric.value - drillDownModal.metric.goal}%
                    </span>
                  </div>
                </div>
              )}

              {drillDownModal.type === 'volume' && (
                <div className="drill-down-stats">
                  <div className="stat-row">
                    <span className="stat-label">Current Period:</span>
                    <span className="stat-value">{drillDownModal.metric.value}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Average:</span>
                    <span className="stat-value">{drillDownModal.metric.subtitle}</span>
                  </div>
                </div>
              )}

              {drillDownModal.type === 'loanType' && (
                <div className="drill-down-stats">
                  <div className="stat-row">
                    <span className="stat-label">Units:</span>
                    <span className="stat-value">{drillDownModal.metric.units}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Total Volume:</span>
                    <span className="stat-value">${drillDownModal.metric.volume.toLocaleString()}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Average Loan Size:</span>
                    <span className="stat-value">
                      ${(drillDownModal.metric.volume / drillDownModal.metric.units).toLocaleString(undefined, {
                        maximumFractionDigits: 0,
                      })}
                    </span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Percentage of Portfolio:</span>
                    <span className="stat-value">{drillDownModal.metric.percentage}%</span>
                  </div>
                </div>
              )}

              {drillDownModal.type === 'referralSource' && (
                <div className="drill-down-stats">
                  <div className="stat-row">
                    <span className="stat-label">Total Referrals:</span>
                    <span className="stat-value">{drillDownModal.metric.referrals}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Closed Volume:</span>
                    <span className="stat-value">${drillDownModal.metric.closedVolume.toLocaleString()}</span>
                  </div>
                  {drillDownModal.metric.referrals > 0 && (
                    <div className="stat-row">
                      <span className="stat-label">Avg Volume per Referral:</span>
                      <span className="stat-value">
                        ${(drillDownModal.metric.closedVolume / drillDownModal.metric.referrals).toLocaleString(
                          undefined,
                          { maximumFractionDigits: 0 }
                        )}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {drillDownModal.type === 'timeline' && (
                <div className="drill-down-stats">
                  <div className="stat-row">
                    <span className="stat-label">Current Performance:</span>
                    <span className="stat-value">
                      {drillDownModal.metric.isPercentage
                        ? `${drillDownModal.metric.value}%`
                        : drillDownModal.metric.value}
                    </span>
                  </div>
                  {drillDownModal.metric.goal && (
                    <>
                      <div className="stat-row">
                        <span className="stat-label">Goal:</span>
                        <span className="stat-value">
                          {drillDownModal.metric.isLowerBetter ? '<' : ''}
                          {drillDownModal.metric.goal}
                          {drillDownModal.metric.isPercentage ? '%' : ''}
                        </span>
                      </div>
                      <div className="stat-row">
                        <span className="stat-label">Sample Size:</span>
                        <span className="stat-value">
                          {drillDownModal.metric.current} of {drillDownModal.metric.total}
                        </span>
                      </div>
                    </>
                  )}
                </div>
              )}

              <div className="modal-actions">
                <button className="btn-primary" onClick={() => setDrillDownModal(null)}>
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Scorecard;
