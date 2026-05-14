import React from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';

const PaymentShockView = ({ data }) => {
  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Payment Shock Forecast</h2>
        <p className="detail-subtitle">How your payment may change over time</p>
      </div>

      <div className="shock-current">
        <h3>Current Payment Breakdown</h3>
        <div className="payment-breakdown">
          <div className="breakdown-item">
            <span>Principal & Interest</span>
            <span>{formatCurrency(data.current.principalInterest)}</span>
          </div>
          <div className="breakdown-item">
            <span>Property Tax</span>
            <span>{formatCurrency(data.current.propertyTax)}</span>
          </div>
          <div className="breakdown-item">
            <span>Insurance</span>
            <span>{formatCurrency(data.current.insurance)}</span>
          </div>
          {data.current.pmi > 0 && (
            <div className="breakdown-item">
              <span>PMI</span>
              <span>{formatCurrency(data.current.pmi)}</span>
            </div>
          )}
          <div className="breakdown-item total">
            <span>Total PITI</span>
            <span>{formatCurrency(data.current.total)}</span>
          </div>
        </div>
      </div>

      <div className="shock-timeline">
        <h3>10-Year Projection</h3>
        <div className="timeline-table">
          <div className="timeline-header">
            <span>Year</span>
            <span>P&I</span>
            <span>Tax</span>
            <span>Insurance</span>
            <span>PMI</span>
            <span>Total</span>
            <span>Increase</span>
          </div>
          {data.projections.map((p) => (
            <div key={p.year} className="timeline-row">
              <span className="year-col">Year {p.year}</span>
              <span>{formatCurrency(p.principalInterest)}</span>
              <span>{formatCurrency(p.propertyTax)}</span>
              <span>{formatCurrency(p.insurance)}</span>
              <span>{formatCurrency(p.pmi)}</span>
              <span className="total-col">{formatCurrency(p.total)}</span>
              <span className="increase-col" style={{ color: p.increase > 0 ? '#ef4444' : '#22c55e' }}>
                {p.increase > 0 ? '+' : ''}{formatCurrency(p.increase)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="shock-summary">
        <div className="summary-stat">
          <span className="stat-label">Peak Payment (Year {data.peakYear})</span>
          <span className="stat-value">{formatCurrency(data.maxPayment)}</span>
        </div>
        <div className="summary-stat">
          <span className="stat-label">Payment Shock Index</span>
          <span className="stat-value" style={{ color: data.shockIndex > 15 ? '#ef4444' : '#f59e0b' }}>
            +{data.shockIndex.toFixed(1)}%
          </span>
        </div>
        <p className="shock-note">
          Note: Property taxes typically increase 3% annually, insurance 4%, and HOA fees 5%.
          PMI is removed around year 7 when you reach 78% LTV.
        </p>
      </div>
    </div>
  );
};

export default PaymentShockView;
