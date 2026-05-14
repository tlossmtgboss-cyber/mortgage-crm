import React from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';
import ScenarioSelector from '../ScenarioSelector';

const EquityVelocityView = ({ data, property, market, onUpdate }) => {
  return (
    <div className="calculator-detail with-selector">
      <div className="detail-header">
        <h2>Equity Velocity</h2>
        <p className="detail-subtitle">How fast will your wealth grow?</p>
      </div>

      {onUpdate && (
        <ScenarioSelector
          homePrice={property?.homePrice || 285000}
          downPaymentPct={property?.downPaymentPct || 5}
          interestRate={market?.interestRate || 6.875}
          termYears={market?.termYears || 30}
          points={market?.points || 0}
          onUpdate={onUpdate}
        />
      )}

      <div className="velocity-highlights">
        <div className="velocity-stat">
          <span className="stat-label">Year 5 Equity</span>
          <span className="stat-value green">{formatCurrency(data.year5Equity)}</span>
        </div>
        <div className="velocity-stat">
          <span className="stat-label">Year 10 Equity</span>
          <span className="stat-value green">{formatCurrency(data.year10Equity)}</span>
        </div>
        <div className="velocity-stat">
          <span className="stat-label">Peak Velocity Year</span>
          <span className="stat-value">Year {data.peakVelocityYear}</span>
        </div>
      </div>

      <div className="velocity-timeline">
        <h3>Equity Growth Timeline</h3>
        <div className="velocity-table">
          <div className="v-header">
            <span>Year</span>
            <span>Home Value</span>
            <span>Loan Balance</span>
            <span>Total Equity</span>
            <span>Yearly Gain</span>
            <span>ROI</span>
          </div>
          {data.timeline.slice(0, 10).map((t) => (
            <div key={t.year} className="v-row">
              <span>Year {t.year}</span>
              <span>{formatCurrency(t.homeValue)}</span>
              <span>{formatCurrency(t.loanBalance)}</span>
              <span className="equity-col">{formatCurrency(t.totalEquity)}</span>
              <span style={{ color: '#22c55e' }}>+{formatCurrency(t.velocityThisYear)}</span>
              <span>{t.roi.toFixed(0)}%</span>
            </div>
          ))}
        </div>
      </div>

      <div className="velocity-breakdown">
        <h3>Equity Sources (Year 10)</h3>
        <div className="source-bars">
          <div className="source-bar">
            <span className="source-label">Down Payment</span>
            <div className="bar-fill" style={{ width: `${(data.initialEquity / data.year10Equity) * 100}%`, background: '#3b82f6' }} />
            <span className="source-value">{formatCurrency(data.initialEquity)}</span>
          </div>
          <div className="source-bar">
            <span className="source-label">Principal Paid</span>
            <div className="bar-fill" style={{ width: `${(data.timeline[9].equityFromPrincipal / data.year10Equity) * 100}%`, background: '#22c55e' }} />
            <span className="source-value">{formatCurrency(data.timeline[9].equityFromPrincipal)}</span>
          </div>
          <div className="source-bar">
            <span className="source-label">Appreciation</span>
            <div className="bar-fill" style={{ width: `${(data.timeline[9].equityFromAppreciation / data.year10Equity) * 100}%`, background: '#f59e0b' }} />
            <span className="source-value">{formatCurrency(data.timeline[9].equityFromAppreciation)}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EquityVelocityView;
