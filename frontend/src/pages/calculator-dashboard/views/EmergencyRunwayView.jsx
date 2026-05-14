import React from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';

const EmergencyRunwayView = ({ data }) => {
  const getStatusColor = (status) => {
    if (status === 'safe') return '#22c55e';
    if (status === 'caution') return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Emergency Runway</h2>
        <p className="detail-subtitle">How long can you survive financially after closing?</p>
      </div>

      <div className="runway-overview">
        <div className="runway-stat-grid">
          <div className="runway-stat">
            <span className="stat-label">Current Savings</span>
            <span className="stat-value">{formatCurrency(data.savings)}</span>
          </div>
          <div className="runway-stat">
            <span className="stat-label">Down Payment</span>
            <span className="stat-value negative">-{formatCurrency(data.downPayment)}</span>
          </div>
          <div className="runway-stat">
            <span className="stat-label">Closing Costs</span>
            <span className="stat-value negative">-{formatCurrency(data.closingCosts)}</span>
          </div>
          <div className="runway-stat highlight">
            <span className="stat-label">Post-Close Savings</span>
            <span className="stat-value" style={{ color: data.postCloseSavings > 0 ? '#22c55e' : '#ef4444' }}>
              {formatCurrency(data.postCloseSavings)}
            </span>
          </div>
        </div>
      </div>

      <div className="runway-scenarios">
        <h3>Survival Scenarios</h3>
        <div className="scenario-cards">
          {data.scenarios.map((scenario, idx) => (
            <div key={idx} className="scenario-card" style={{ borderLeftColor: getStatusColor(scenario.status) }}>
              <div className="scenario-header">
                <span className="scenario-name">{scenario.name}</span>
                <span className="scenario-status" style={{ color: getStatusColor(scenario.status) }}>
                  {scenario.status.toUpperCase()}
                </span>
              </div>
              <div className="scenario-body">
                <div className="scenario-months">
                  <span className="months-value">
                    {scenario.months === Infinity ? '∞' : isNaN(scenario.months) ? '0' : scenario.months.toFixed(1)}
                  </span>
                  <span className="months-label">months</span>
                </div>
                <div className="scenario-burn">
                  Monthly burn: {formatCurrency(scenario.monthlyBurn)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="runway-recommendation">
        <div className="rec-header">
          <span className="rec-icon">{data.riskLevel === 'low' ? '✅' : data.riskLevel === 'moderate' ? '⚠️' : '🚨'}</span>
          <span className="rec-level">Risk Level: {data.riskLevel.toUpperCase()}</span>
        </div>
        <p>
          {data.riskLevel === 'low' && 'Great! You have solid reserves after closing.'}
          {data.riskLevel === 'moderate' && 'Caution: Your reserves are tight. Consider a smaller down payment.'}
          {data.riskLevel === 'high' && 'Warning: Very low reserves. Consider waiting to save more.'}
        </p>
        <div className="rec-target">
          Recommended Reserve: {formatCurrency(data.recommendedReserve)} (6 months expenses)
        </div>
      </div>
    </div>
  );
};

export default EmergencyRunwayView;
