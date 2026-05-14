import React from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';
import ScenarioSelector from '../ScenarioSelector';

const JobMobilityView = ({ data, property, market, onUpdate }) => {
  return (
    <div className="calculator-detail with-selector">
      <div className="detail-header">
        <h2>Job Mobility Impact</h2>
        <p className="detail-subtitle">What if you need to relocate?</p>
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

      <div className="mobility-summary">
        <div className="mobility-stat">
          <span className="stat-label">Minimum Stay to Break Even</span>
          <span className="stat-value">{data.breakEvenYear} years</span>
        </div>
        <div className="mobility-stat">
          <span className="stat-label">Initial Investment</span>
          <span className="stat-value">{formatCurrency(data.initialInvestment)}</span>
        </div>
        <div className="mobility-stat">
          <span className="stat-label">Flexibility Score</span>
          <span className="stat-value" style={{
            color: data.flexibilityScore === 'good' ? '#22c55e' :
                   data.flexibilityScore === 'moderate' ? '#f59e0b' : '#ef4444'
          }}>
            {data.flexibilityScore.toUpperCase()}
          </span>
        </div>
      </div>

      <div className="mobility-scenarios">
        <h3>Relocation Scenarios</h3>
        <div className="mobility-table">
          <div className="mob-header">
            <span>If You Move In</span>
            <span>Home Value</span>
            <span>Net Proceeds</span>
            <span>Total Cost</span>
            <span>vs Renting</span>
          </div>
          {data.scenarios.map((s) => (
            <div key={s.year} className={`mob-row ${s.betterThanRenting ? 'better' : 'worse'}`}>
              <span>Year {s.year}</span>
              <span>{formatCurrency(s.homeValue)}</span>
              <span style={{ color: s.netProceeds > data.initialInvestment ? '#22c55e' : '#ef4444' }}>
                {formatCurrency(s.netProceeds)}
              </span>
              <span>{formatCurrency(s.totalBuyingCost)}</span>
              <span style={{ color: s.betterThanRenting ? '#22c55e' : '#ef4444' }}>
                {s.betterThanRenting ? 'Better' : 'Worse'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mobility-breakdown">
        <h3>Cost Breakdown (If Selling in Year 3)</h3>
        {data.scenarios[2] && (
          <div className="breakdown-items">
            <div className="breakdown-item">
              <span>Down Payment + Closing</span>
              <span>{formatCurrency(data.initialInvestment)}</span>
            </div>
            <div className="breakdown-item">
              <span>3 Years of Payments</span>
              <span>{formatCurrency(data.scenarios[2].totalPiti)}</span>
            </div>
            <div className="breakdown-item">
              <span>Selling Costs (8%)</span>
              <span>-{formatCurrency(data.scenarios[2].sellingCosts)}</span>
            </div>
            <div className="breakdown-item">
              <span>Net Proceeds from Sale</span>
              <span>{formatCurrency(data.scenarios[2].netProceeds)}</span>
            </div>
            <div className="breakdown-item total">
              <span>Total Housing Cost</span>
              <span>{formatCurrency(data.scenarios[2].totalBuyingCost)}</span>
            </div>
            <div className="breakdown-item comparison">
              <span>3 Years Rent Would Cost</span>
              <span>{formatCurrency(data.scenarios[2].rentEquivalent)}</span>
            </div>
          </div>
        )}
      </div>

      <div className="mobility-advice">
        <h4>Recommendation</h4>
        <p>
          {data.flexibilityScore === 'good' && 'Your situation allows for reasonable mobility. Even a 2-year stay could work out financially.'}
          {data.flexibilityScore === 'moderate' && 'Plan to stay at least 3 years to avoid losing money on the transaction.'}
          {data.flexibilityScore === 'poor' && 'Consider renting if you might need to relocate within 3-5 years.'}
        </p>
      </div>
    </div>
  );
};

export default JobMobilityView;
