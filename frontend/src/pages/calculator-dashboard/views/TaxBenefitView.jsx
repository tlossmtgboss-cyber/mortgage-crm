import React from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';
import ScenarioSelector from '../ScenarioSelector';

const TaxBenefitView = ({ data, property, market, onUpdate }) => {
  return (
    <div className="calculator-detail with-selector">
      <div className="detail-header">
        <h2>Tax Benefit Realization</h2>
        <p className="detail-subtitle">Your actual tax savings from homeownership</p>
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

      <div className="tax-summary">
        <div className="tax-stat">
          <span className="stat-label">Your Tax Bracket</span>
          <span className="stat-value">{(data.marginalTaxRate * 100).toFixed(0)}%</span>
        </div>
        <div className="tax-stat">
          <span className="stat-label">Year 1 Tax Savings</span>
          <span className="stat-value green">{formatCurrency(data.year1Savings)}</span>
        </div>
        <div className="tax-stat">
          <span className="stat-label">Monthly Benefit</span>
          <span className="stat-value green">{formatCurrency(data.year1MonthlyBenefit)}</span>
        </div>
        <div className="tax-stat highlight">
          <span className="stat-label">Effective Monthly Payment</span>
          <span className="stat-value">{formatCurrency(data.effectiveYear1Payment)}</span>
        </div>
      </div>

      <div className="tax-itemizing">
        <div className={`itemizing-status ${data.itemizingBeneficial ? 'beneficial' : 'not-beneficial'}`}>
          {data.itemizingBeneficial ? (
            <>
              <span className="status-icon">✅</span>
              <span>Itemizing your deductions makes sense!</span>
            </>
          ) : (
            <>
              <span className="status-icon">⚠️</span>
              <span>Standard deduction may be better for you.</span>
            </>
          )}
        </div>
        <div className="deduction-comparison">
          <div className="deduction-item">
            <span>Your Itemized Deductions (Year 1)</span>
            <span>{formatCurrency(data.yearlyBenefits[0].totalDeductions)}</span>
          </div>
          <div className="deduction-item">
            <span>Standard Deduction</span>
            <span>{formatCurrency(data.standardDeduction)}</span>
          </div>
        </div>
      </div>

      <div className="tax-timeline">
        <h3>10-Year Tax Benefit Projection</h3>
        <div className="tax-table">
          <div className="tax-header">
            <span>Year</span>
            <span>Mortgage Interest</span>
            <span>Property Tax</span>
            <span>Tax Savings</span>
            <span>Effective Payment</span>
          </div>
          {data.yearlyBenefits.map((y) => (
            <div key={y.year} className="tax-row">
              <span>Year {y.year}</span>
              <span>{formatCurrency(y.mortgageInterest)}</span>
              <span>{formatCurrency(y.propertyTax)}</span>
              <span style={{ color: '#22c55e' }}>{formatCurrency(y.taxSavings)}</span>
              <span>{formatCurrency(y.effectivePayment)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="tax-total">
        <span>Total 10-Year Tax Savings:</span>
        <span className="total-value">{formatCurrency(data.totalTenYearSavings)}</span>
      </div>
    </div>
  );
};

export default TaxBenefitView;
