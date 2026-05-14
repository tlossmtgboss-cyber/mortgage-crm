import React from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';
import ScenarioSelector from '../ScenarioSelector';

const InflationHedgeView = ({ data, property, market, onUpdate }) => {
  const getColor = (rec) => {
    if (rec === 'strong') return '#22c55e';
    if (rec === 'moderate') return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="calculator-detail with-selector">
      <div className="detail-header">
        <h2>Inflation Hedge Index</h2>
        <p className="detail-subtitle">How homeownership protects you from rising costs</p>
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

      <div className="hedge-score">
        <div className="score-display" style={{ '--hedge-color': getColor(data.recommendation) }}>
          <span className="score-number">{data.hedgeScore.toFixed(0)}</span>
          <span className="score-label">Hedge Score</span>
          <span className="score-recommendation" style={{ color: getColor(data.recommendation) }}>
            {data.recommendation.toUpperCase()} PROTECTION
          </span>
        </div>
      </div>

      <div className="hedge-comparison">
        <h3>Current Costs</h3>
        <div className="cost-compare">
          <div className="cost-item">
            <span>Your Rent Today</span>
            <span>{formatCurrency(data.currentRent)}</span>
          </div>
          <div className="cost-item">
            <span>Mortgage Payment (PITI)</span>
            <span>{formatCurrency(data.currentPiti)}</span>
          </div>
        </div>
      </div>

      <div className="hedge-scenarios">
        <h3>Inflation Scenarios (10-Year Projection)</h3>
        {data.analysis.map((scenario, idx) => (
          <div key={idx} className="scenario-block">
            <div className="scenario-title">
              <span>{scenario.scenario}</span>
              <span className="hedge-value" style={{ color: scenario.totalHedgeValue > 0 ? '#22c55e' : '#ef4444' }}>
                {scenario.totalHedgeValue > 0 ? '+' : ''}{formatCurrency(scenario.totalHedgeValue)} hedge value
              </span>
            </div>
            <div className="scenario-detail">
              <span>Year 10 Rent: {formatCurrency(scenario.year10Rent)}</span>
              <span>Year 10 PITI: {formatCurrency(scenario.year10Piti)}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="hedge-insight">
        <h4>Why This Matters</h4>
        <p>
          With a fixed-rate mortgage, your principal & interest payment never changes.
          While taxes and insurance increase, they're a smaller portion of your payment.
          Meanwhile, rents typically rise 3-5% annually, compounding over time.
        </p>
      </div>
    </div>
  );
};

export default InflationHedgeView;
