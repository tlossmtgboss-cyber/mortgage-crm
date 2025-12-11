/**
 * PaymentCalculator Component
 *
 * Calculates and displays estimated monthly mortgage payments including:
 * - Principal & Interest
 * - Property Taxes (county-level estimates)
 * - Homeowners Insurance (state-level estimates)
 * - PMI (if applicable)
 * - HOA fees
 */

import React, { useState, useMemo, useEffect } from 'react';
import { statesList, getCountyByFips, getCountyByName, getDefaultEffectiveRate, getCountiesForState } from '../lib/propertyTax/countyData';
import { estimatePropertyTax, calculateMonthlyPayment, estimatePMI, formatCurrency } from '../lib/propertyTax/calculator';
import { estimateInsuranceSimple } from '../lib/insurance/calculator';

const PaymentCalculator = ({
  // Pre-filled values from application
  initialHomeValue = 0,
  initialDownPayment = 0,
  initialState = '',
  initialCounty = '',
  initialPropertyUse = 'primaryResidence',
  // Callbacks
  onCalculationComplete,
  // Display options
  showAdvancedOptions = false,
  compact = false,
}) => {
  // Form state
  const [homeValue, setHomeValue] = useState(initialHomeValue);
  const [downPaymentPercent, setDownPaymentPercent] = useState(
    initialHomeValue > 0 && initialDownPayment > 0
      ? Math.round((initialDownPayment / initialHomeValue) * 100)
      : 20
  );
  const [interestRate, setInterestRate] = useState(7.0);
  const [loanTermYears, setLoanTermYears] = useState(30);
  const [selectedState, setSelectedState] = useState(initialState);
  const [selectedCountyFips, setSelectedCountyFips] = useState('');
  const [propertyUse, setPropertyUse] = useState(initialPropertyUse);
  const [hoaMonthly, setHoaMonthly] = useState(0);
  const [showDetails, setShowDetails] = useState(false);

  // Get available counties for selected state
  const availableCounties = useMemo(() => {
    if (!selectedState) return [];
    const stateInfo = statesList.find(s => s.code === selectedState);
    return stateInfo?.counties || [];
  }, [selectedState]);

  // Set county when state changes or initial county is provided
  useEffect(() => {
    if (initialCounty && selectedState) {
      // Try to find county by name
      const county = availableCounties.find(
        c => c.name.toLowerCase().includes(initialCounty.toLowerCase())
      );
      if (county) {
        setSelectedCountyFips(county.fips);
      } else if (availableCounties.length > 0) {
        setSelectedCountyFips(availableCounties[0].fips);
      }
    } else if (availableCounties.length > 0 && !selectedCountyFips) {
      setSelectedCountyFips(availableCounties[0].fips);
    }
  }, [selectedState, initialCounty, availableCounties]);

  // Update values when initial props change
  useEffect(() => {
    if (initialHomeValue > 0) setHomeValue(initialHomeValue);
  }, [initialHomeValue]);

  useEffect(() => {
    if (initialDownPayment > 0 && initialHomeValue > 0) {
      setDownPaymentPercent(Math.round((initialDownPayment / initialHomeValue) * 100));
    }
  }, [initialDownPayment, initialHomeValue]);

  useEffect(() => {
    if (initialState) setSelectedState(initialState);
  }, [initialState]);

  // Calculate all payment components
  const calculation = useMemo(() => {
    if (!homeValue || homeValue <= 0) return null;

    const downPaymentAmount = homeValue * (downPaymentPercent / 100);
    const loanAmount = homeValue - downPaymentAmount;
    const loanTermMonths = loanTermYears * 12;

    // Get county config for tax calculation
    let countyConfig = selectedCountyFips
      ? getCountyByFips(selectedCountyFips)
      : null;

    // Fallback to state default if no county
    if (!countyConfig && selectedState) {
      countyConfig = {
        state: selectedState,
        countyName: 'Default',
        fips: 'default',
        effectiveRate: getDefaultEffectiveRate(selectedState),
      };
    }

    // Property tax estimate
    const taxEstimate = countyConfig
      ? estimatePropertyTax({
          countyConfig,
          propertyUse,
          marketValue: homeValue,
        })
      : { annualTax: homeValue * 0.0107, monthlyTax: Math.round((homeValue * 0.0107) / 12), method: 'effectiveRate' };

    // Insurance estimate
    const insuranceEstimate = estimateInsuranceSimple({
      homeValue,
      stateCode: selectedState || 'US',
      deductible: 1000,
    });

    // PMI estimate
    const pmiMonthly = estimatePMI(loanAmount, homeValue);

    // Full payment calculation
    const payment = calculateMonthlyPayment({
      loanAmount,
      interestRate: interestRate / 100,
      loanTermMonths,
      propertyTaxMonthly: taxEstimate.monthlyTax,
      homeownersInsuranceMonthly: insuranceEstimate.monthlyPremium,
      hoaMonthly,
      pmiMonthly,
    });

    return {
      homeValue,
      downPaymentAmount,
      downPaymentPercent,
      loanAmount,
      interestRate,
      loanTermYears,
      taxEstimate,
      insuranceEstimate,
      pmiMonthly,
      payment,
      ltv: ((loanAmount / homeValue) * 100).toFixed(1),
    };
  }, [homeValue, downPaymentPercent, interestRate, loanTermYears, selectedState, selectedCountyFips, propertyUse, hoaMonthly]);

  // Notify parent of calculation
  useEffect(() => {
    if (calculation && onCalculationComplete) {
      onCalculationComplete(calculation);
    }
  }, [calculation, onCalculationComplete]);

  if (compact) {
    return (
      <div className="payment-calculator-compact">
        {calculation && (
          <div className="compact-result">
            <div className="compact-total">
              <span className="label">Est. Monthly Payment</span>
              <span className="amount">{formatCurrency(calculation.payment.totalMonthly)}</span>
            </div>
            <button
              className="details-toggle"
              onClick={() => setShowDetails(!showDetails)}
            >
              {showDetails ? 'Hide Details' : 'Show Details'}
            </button>
            {showDetails && (
              <div className="compact-breakdown">
                <div className="breakdown-item">
                  <span>Principal & Interest</span>
                  <span>{formatCurrency(calculation.payment.principalAndInterest)}</span>
                </div>
                <div className="breakdown-item">
                  <span>Property Tax</span>
                  <span>{formatCurrency(calculation.payment.propertyTax)}</span>
                </div>
                <div className="breakdown-item">
                  <span>Insurance</span>
                  <span>{formatCurrency(calculation.payment.homeownersInsurance)}</span>
                </div>
                {calculation.payment.pmi > 0 && (
                  <div className="breakdown-item">
                    <span>PMI</span>
                    <span>{formatCurrency(calculation.payment.pmi)}</span>
                  </div>
                )}
                {calculation.payment.hoa > 0 && (
                  <div className="breakdown-item">
                    <span>HOA</span>
                    <span>{formatCurrency(calculation.payment.hoa)}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="payment-calculator">
      <div className="calculator-header">
        <h3>Monthly Payment Calculator</h3>
        <p>See your estimated monthly mortgage payment</p>
      </div>

      <div className="calculator-inputs">
        {/* Home Value */}
        <div className="input-group">
          <label>Home Value</label>
          <div className="input-with-prefix">
            <span className="prefix">$</span>
            <input
              type="number"
              value={homeValue || ''}
              onChange={(e) => setHomeValue(Number(e.target.value))}
              placeholder="450,000"
            />
          </div>
        </div>

        {/* Down Payment Slider */}
        <div className="input-group slider-group">
          <label>
            Down Payment: {downPaymentPercent}%
            <span className="calculated">
              ({formatCurrency(homeValue * (downPaymentPercent / 100))})
            </span>
          </label>
          <input
            type="range"
            min="3"
            max="50"
            step="1"
            value={downPaymentPercent}
            onChange={(e) => setDownPaymentPercent(Number(e.target.value))}
            className="slider"
          />
          <div className="slider-labels">
            <span>3%</span>
            <span>20%</span>
            <span>50%</span>
          </div>
          {downPaymentPercent < 20 && (
            <span className="pmi-warning">PMI required below 20% down</span>
          )}
        </div>

        {/* Interest Rate & Term */}
        <div className="input-row">
          <div className="input-group half">
            <label>Interest Rate (%)</label>
            <input
              type="number"
              min="0"
              max="20"
              step="0.125"
              value={interestRate}
              onChange={(e) => setInterestRate(Number(e.target.value))}
            />
          </div>
          <div className="input-group half">
            <label>Loan Term</label>
            <select
              value={loanTermYears}
              onChange={(e) => setLoanTermYears(Number(e.target.value))}
            >
              <option value={15}>15 years</option>
              <option value={20}>20 years</option>
              <option value={30}>30 years</option>
            </select>
          </div>
        </div>

        {/* Location (for tax/insurance estimates) */}
        <div className="input-row">
          <div className="input-group half">
            <label>State</label>
            <select
              value={selectedState}
              onChange={(e) => {
                setSelectedState(e.target.value);
                setSelectedCountyFips('');
              }}
            >
              <option value="">Select State</option>
              {statesList.map((state) => (
                <option key={state.code} value={state.code}>{state.name}</option>
              ))}
            </select>
          </div>
          {availableCounties.length > 0 && (
            <div className="input-group half">
              <label>County</label>
              <select
                value={selectedCountyFips}
                onChange={(e) => setSelectedCountyFips(e.target.value)}
              >
                {availableCounties.map((county) => (
                  <option key={county.fips} value={county.fips}>{county.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {showAdvancedOptions && (
          <>
            {/* Property Use */}
            <div className="input-group">
              <label>Property Use</label>
              <select
                value={propertyUse}
                onChange={(e) => setPropertyUse(e.target.value)}
              >
                <option value="primaryResidence">Primary Residence</option>
                <option value="secondHome">Second Home</option>
                <option value="rental">Investment/Rental</option>
              </select>
            </div>

            {/* HOA */}
            <div className="input-group">
              <label>HOA Fees (Monthly)</label>
              <div className="input-with-prefix">
                <span className="prefix">$</span>
                <input
                  type="number"
                  min="0"
                  value={hoaMonthly || ''}
                  onChange={(e) => setHoaMonthly(Number(e.target.value))}
                  placeholder="0"
                />
              </div>
            </div>
          </>
        )}
      </div>

      {/* Results */}
      {calculation && (
        <div className="calculator-results">
          <div className="total-payment">
            <span className="label">Estimated Monthly Payment</span>
            <span className="amount">{formatCurrency(calculation.payment.totalMonthly)}</span>
          </div>

          <div className="payment-breakdown">
            <div className="breakdown-header">
              <span>Payment Breakdown</span>
            </div>

            <div className="breakdown-item primary">
              <span className="item-label">Principal & Interest</span>
              <span className="item-amount">{formatCurrency(calculation.payment.principalAndInterest)}</span>
            </div>

            <div className="breakdown-item">
              <span className="item-label">Property Tax</span>
              <span className="item-amount">{formatCurrency(calculation.payment.propertyTax)}</span>
              <span className="item-note">
                {formatCurrency(calculation.taxEstimate.annualTax)}/year
              </span>
            </div>

            <div className="breakdown-item">
              <span className="item-label">Homeowners Insurance</span>
              <span className="item-amount">{formatCurrency(calculation.payment.homeownersInsurance)}</span>
              <span className="item-note">
                {formatCurrency(calculation.insuranceEstimate.annualPremium)}/year
              </span>
            </div>

            {calculation.payment.pmi > 0 && (
              <div className="breakdown-item warning">
                <span className="item-label">PMI</span>
                <span className="item-amount">{formatCurrency(calculation.payment.pmi)}</span>
                <span className="item-note">Removed at 80% LTV</span>
              </div>
            )}

            {calculation.payment.hoa > 0 && (
              <div className="breakdown-item">
                <span className="item-label">HOA Fees</span>
                <span className="item-amount">{formatCurrency(calculation.payment.hoa)}</span>
              </div>
            )}
          </div>

          <div className="loan-summary">
            <div className="summary-item">
              <span>Loan Amount</span>
              <span>{formatCurrency(calculation.loanAmount)}</span>
            </div>
            <div className="summary-item">
              <span>Loan-to-Value (LTV)</span>
              <span>{calculation.ltv}%</span>
            </div>
          </div>

          <p className="disclaimer">
            * Estimates based on county/state averages. Actual amounts may vary.
            Contact a loan officer for precise figures.
          </p>
        </div>
      )}

      <style jsx>{`
        .payment-calculator {
          background: white;
          border-radius: 12px;
          padding: 24px;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        }

        .calculator-header {
          margin-bottom: 20px;
        }

        .calculator-header h3 {
          font-size: 20px;
          font-weight: 600;
          color: #1a1a2e;
          margin: 0 0 4px 0;
        }

        .calculator-header p {
          color: #666;
          margin: 0;
          font-size: 14px;
        }

        .calculator-inputs {
          display: flex;
          flex-direction: column;
          gap: 16px;
          margin-bottom: 24px;
        }

        .input-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .input-group label {
          font-size: 14px;
          font-weight: 500;
          color: #444;
        }

        .input-group label .calculated {
          font-weight: 400;
          color: #666;
          margin-left: 8px;
        }

        .input-row {
          display: flex;
          gap: 16px;
        }

        .input-group.half {
          flex: 1;
        }

        .input-with-prefix {
          display: flex;
          align-items: center;
          background: #f5f5f7;
          border-radius: 8px;
          overflow: hidden;
        }

        .input-with-prefix .prefix {
          padding: 12px;
          background: #e5e5e7;
          color: #666;
          font-weight: 500;
        }

        .input-with-prefix input {
          flex: 1;
          border: none;
          background: transparent;
          padding: 12px;
          font-size: 16px;
        }

        input[type="number"],
        select {
          padding: 12px;
          border: 1px solid #e0e0e0;
          border-radius: 8px;
          font-size: 16px;
          background: #f5f5f7;
        }

        input[type="number"]:focus,
        select:focus {
          outline: none;
          border-color: #4A90A4;
          background: white;
        }

        .slider-group {
          padding: 8px 0;
        }

        .slider {
          width: 100%;
          height: 8px;
          border-radius: 4px;
          background: linear-gradient(to right, #4A90A4 0%, #4A90A4 var(--value), #e0e0e0 var(--value), #e0e0e0 100%);
          appearance: none;
          cursor: pointer;
        }

        .slider::-webkit-slider-thumb {
          appearance: none;
          width: 24px;
          height: 24px;
          border-radius: 50%;
          background: #4A90A4;
          border: 3px solid white;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
          cursor: pointer;
        }

        .slider-labels {
          display: flex;
          justify-content: space-between;
          font-size: 12px;
          color: #888;
          margin-top: 4px;
        }

        .pmi-warning {
          font-size: 12px;
          color: #f59e0b;
          margin-top: 4px;
        }

        .calculator-results {
          background: linear-gradient(135deg, #4A90A4 0%, #357285 100%);
          border-radius: 12px;
          padding: 24px;
          color: white;
        }

        .total-payment {
          text-align: center;
          margin-bottom: 20px;
          padding-bottom: 20px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        }

        .total-payment .label {
          display: block;
          font-size: 14px;
          opacity: 0.9;
          margin-bottom: 8px;
        }

        .total-payment .amount {
          font-size: 48px;
          font-weight: 700;
        }

        .payment-breakdown {
          margin-bottom: 20px;
        }

        .breakdown-header {
          font-size: 14px;
          font-weight: 600;
          margin-bottom: 12px;
          opacity: 0.9;
        }

        .breakdown-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 10px 0;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          flex-wrap: wrap;
        }

        .breakdown-item.primary {
          font-weight: 600;
        }

        .breakdown-item.warning .item-label {
          color: #fbbf24;
        }

        .item-label {
          flex: 1;
        }

        .item-amount {
          font-weight: 600;
        }

        .item-note {
          width: 100%;
          font-size: 12px;
          opacity: 0.7;
          margin-top: 4px;
        }

        .loan-summary {
          background: rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          padding: 12px;
          margin-bottom: 16px;
        }

        .summary-item {
          display: flex;
          justify-content: space-between;
          font-size: 14px;
          padding: 4px 0;
        }

        .disclaimer {
          font-size: 11px;
          opacity: 0.7;
          margin: 0;
          text-align: center;
        }

        /* Compact styles */
        .payment-calculator-compact {
          background: white;
          border-radius: 8px;
          padding: 16px;
          border: 1px solid #e0e0e0;
        }

        .compact-result .compact-total {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }

        .compact-result .compact-total .label {
          font-size: 14px;
          color: #666;
        }

        .compact-result .compact-total .amount {
          font-size: 24px;
          font-weight: 700;
          color: #4A90A4;
        }

        .details-toggle {
          width: 100%;
          padding: 8px;
          background: #f5f5f7;
          border: none;
          border-radius: 6px;
          font-size: 13px;
          color: #666;
          cursor: pointer;
          margin-bottom: 12px;
        }

        .details-toggle:hover {
          background: #e5e5e7;
        }

        .compact-breakdown .breakdown-item {
          display: flex;
          justify-content: space-between;
          font-size: 13px;
          padding: 6px 0;
          border-bottom: 1px solid #f0f0f0;
          color: #444;
        }
      `}</style>
    </div>
  );
};

export default PaymentCalculator;
