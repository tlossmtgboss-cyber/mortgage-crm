import React from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';
import ScenarioSelector from '../ScenarioSelector';

const BreakEvenHorizonView = ({ data, property, market, onUpdate }) => {
  return (
    <div className="calculator-detail with-selector">
      <div className="detail-header">
        <h2>Break-Even Horizon</h2>
        <p className="detail-subtitle">When does buying beat renting?</p>
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

      <div className="breakeven-result">
        <div className="breakeven-highlight">
          <span className="be-label">Break-Even Point</span>
          <span className="be-value">
            Year {data.breakEvenYear}
          </span>
          <span className="be-note">
            {typeof data.breakEvenYear === 'number'
              ? `After ${data.breakEvenYear} years, buying becomes more profitable than renting.`
              : 'Based on assumptions, buying may take longer than 10 years to break even.'}
          </span>
        </div>
      </div>

      <div className="breakeven-timeline">
        <h3>Year-by-Year Comparison</h3>
        <div className="be-table">
          <div className="be-header">
            <span>Year</span>
            <span>Renter Net Worth</span>
            <span>Buyer Net Worth</span>
            <span>Advantage</span>
          </div>
          {data.comparison.map((c) => (
            <div key={c.year} className={`be-row ${c.buyerAdvantage > 0 ? 'buyer-wins' : ''}`}>
              <span>Year {c.year}</span>
              <span>{formatCurrency(c.netRenter)}</span>
              <span>{formatCurrency(c.netBuyer)}</span>
              <span style={{ color: c.buyerAdvantage > 0 ? '#22c55e' : '#ef4444' }}>
                {c.buyerAdvantage > 0 ? '+' : ''}{formatCurrency(c.buyerAdvantage)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="breakeven-assumptions">
        <h4>Assumptions</h4>
        <div className="assumptions-grid">
          <div className="assumption">
            <span>Home Appreciation</span>
            <span>{data.assumptions.homeAppreciation}%/year</span>
          </div>
          <div className="assumption">
            <span>Rent Increase</span>
            <span>{data.assumptions.rentIncrease}%/year</span>
          </div>
          <div className="assumption">
            <span>Investment Return</span>
            <span>{data.assumptions.investmentReturn}%/year</span>
          </div>
          <div className="assumption">
            <span>Maintenance</span>
            <span>{data.assumptions.maintenance}%/year</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BreakEvenHorizonView;
