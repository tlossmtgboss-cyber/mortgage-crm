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
import { estimatePropertyTax, calculateMonthlyPayment, formatCurrency } from '../lib/propertyTax/calculator';
import { estimateInsuranceSimple } from '../lib/insurance/calculator';
import { calculateMortgageInsurance, LOAN_TYPES } from '../lib/mortgageInsurance';

const PaymentCalculator = ({
  // Pre-filled values from application
  initialHomeValue = 0,
  initialDownPayment = 0,
  initialState = '',
  initialCounty = '',
  initialPropertyUse = 'primaryResidence',
  initialCreditScore = 720,
  initialLoanType = 'conventional',
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
  const [interestRate, setInterestRate] = useState(6.5);
  const [loanTermYears, setLoanTermYears] = useState(30);
  const [selectedState, setSelectedState] = useState(initialState);
  const [selectedCountyFips, setSelectedCountyFips] = useState('');
  const [propertyUse, setPropertyUse] = useState(initialPropertyUse);
  const [hoaMonthly, setHoaMonthly] = useState(0);
  const [showDetails, setShowDetails] = useState(false);
  const [creditScore, setCreditScore] = useState(initialCreditScore);
  const [loanType, setLoanType] = useState(initialLoanType);
  const [showMIDetails, setShowMIDetails] = useState(false);
  const [showValidation, setShowValidation] = useState(true); // Show validation from start

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

  useEffect(() => {
    if (initialCreditScore > 0) setCreditScore(initialCreditScore);
  }, [initialCreditScore]);

  useEffect(() => {
    if (initialLoanType) setLoanType(initialLoanType);
  }, [initialLoanType]);

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

    // Mortgage Insurance estimate (PMI, MIP, VA Funding Fee, or USDA Guarantee Fee)
    const mortgageInsurance = calculateMortgageInsurance({
      loanType,
      loanAmount,
      homeValue,
      creditScore,
      loanTermYears,
    });

    // Full payment calculation
    const payment = calculateMonthlyPayment({
      loanAmount,
      interestRate: interestRate / 100,
      loanTermMonths,
      propertyTaxMonthly: taxEstimate.monthlyTax,
      homeownersInsuranceMonthly: insuranceEstimate.monthlyPremium,
      hoaMonthly,
      pmiMonthly: mortgageInsurance.monthlyPremium,
    });

    return {
      homeValue,
      downPaymentAmount,
      downPaymentPercent,
      loanAmount,
      interestRate,
      loanTermYears,
      loanType,
      creditScore,
      taxEstimate,
      insuranceEstimate,
      mortgageInsurance,
      pmiMonthly: mortgageInsurance.monthlyPremium,
      payment,
      ltv: ((loanAmount / homeValue) * 100).toFixed(1),
    };
  }, [homeValue, downPaymentPercent, interestRate, loanTermYears, selectedState, selectedCountyFips, propertyUse, hoaMonthly, creditScore, loanType]);

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

      <div className="calculator-layout">
      <div className="calculator-inputs">
        {/* Home Value */}
        <div className="input-group">
          <label>Home Value <span className="required-star">*</span></label>
          <div className={`input-with-prefix ${showValidation && homeValue <= 0 ? 'required-field' : ''}`}>
            <span className="prefix">$</span>
            <input
              type="number"
              value={homeValue > 0 ? homeValue : ''}
              onChange={(e) => {
                const val = e.target.value;
                // Handle empty input
                if (val === '' || val === null || val === undefined) {
                  setHomeValue(0);
                } else {
                  const num = parseFloat(val.replace(/,/g, ''));
                  setHomeValue(isNaN(num) ? 0 : num);
                }
              }}
              placeholder="Enter home value (e.g. 450000)"
            />
          </div>
        </div>

        {/* Down Payment Slider */}
        <div className="input-group slider-group">
          <label>
            Down Payment: {downPaymentPercent}%
            {homeValue > 0 && (
              <span className="calculated">
                ({formatCurrency(homeValue * (downPaymentPercent / 100))})
              </span>
            )}
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

        {/* Loan Type & Credit Score */}
        <div className="input-row">
          <div className="input-group half">
            <label>Loan Type</label>
            <select
              value={loanType}
              onChange={(e) => setLoanType(e.target.value)}
            >
              <option value="conventional">Conventional</option>
              <option value="fha">FHA</option>
              <option value="va">VA</option>
              <option value="usda">USDA</option>
            </select>
          </div>
          <div className="input-group half">
            <label>Credit Score</label>
            <input
              type="number"
              min="500"
              max="850"
              step="1"
              value={creditScore}
              onChange={(e) => setCreditScore(Number(e.target.value))}
              placeholder="720"
            />
          </div>
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
            <label>State <span className="required-star">*</span></label>
            <select
              value={selectedState}
              onChange={(e) => {
                setSelectedState(e.target.value);
                setSelectedCountyFips('');
              }}
              className={showValidation && !selectedState ? 'required-field' : ''}
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
              <label>Property Use <span className="required-star">*</span></label>
              <select
                value={propertyUse}
                onChange={(e) => setPropertyUse(e.target.value)}
                className={showValidation && !propertyUse ? 'required-field' : ''}
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

      {/* Results Column */}
      <div className="calculator-results-column">
      {/* Message when no home value */}
      {!calculation && homeValue <= 0 && (
        <div className="calculator-prompt">
          <p>Enter a home value to see your estimated monthly payment breakdown.</p>
        </div>
      )}

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

            {calculation.mortgageInsurance?.required && (
              <div className="breakdown-item warning mi-section">
                <div className="mi-header">
                  <span className="item-label">{calculation.mortgageInsurance.type}</span>
                  <span className="item-amount">{formatCurrency(calculation.payment.pmi)}</span>
                </div>
                {calculation.mortgageInsurance.upfrontPremium > 0 && (
                  <span className="item-note upfront">
                    + {formatCurrency(calculation.mortgageInsurance.upfrontPremium)} upfront (can be financed)
                  </span>
                )}
                <span className="item-note">
                  {calculation.mortgageInsurance.cancellation?.canCancel
                    ? `Can be removed at ${calculation.mortgageInsurance.cancellation.requestLTV || 80}% LTV`
                    : calculation.mortgageInsurance.cancellation?.method === 'refinance_only'
                    ? 'Required for life of loan (refinance to remove)'
                    : calculation.mortgageInsurance.type === 'VA Funding Fee'
                    ? 'One-time fee (no monthly MI)'
                    : ''}
                </span>
                <button
                  className="mi-details-toggle"
                  onClick={() => setShowMIDetails(!showMIDetails)}
                >
                  {showMIDetails ? 'Hide Details' : 'View Details'}
                </button>
                {showMIDetails && (
                  <div className="mi-details">
                    <div className="mi-detail-row">
                      <span>Annual Rate:</span>
                      <span>{((calculation.mortgageInsurance.annualRate || 0) * 100).toFixed(2)}%</span>
                    </div>
                    {calculation.mortgageInsurance.creditTier && (
                      <div className="mi-detail-row">
                        <span>Credit Tier:</span>
                        <span style={{textTransform: 'capitalize'}}>{calculation.mortgageInsurance.creditTier}</span>
                      </div>
                    )}
                    {calculation.mortgageInsurance.cancellation?.estimatedMonths && (
                      <div className="mi-detail-row">
                        <span>Est. Time to Remove:</span>
                        <span>~{Math.floor(calculation.mortgageInsurance.cancellation.estimatedMonths / 12)} years</span>
                      </div>
                    )}
                    {calculation.mortgageInsurance.notes && (
                      <p className="mi-notes">{calculation.mortgageInsurance.notes}</p>
                    )}
                  </div>
                )}
              </div>
            )}

            {!calculation.mortgageInsurance?.required && downPaymentPercent >= 20 && (
              <div className="breakdown-item success">
                <span className="item-label">Mortgage Insurance</span>
                <span className="item-amount success-text">Not Required</span>
                <span className="item-note">20%+ down payment eliminates MI</span>
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
      </div>
      </div>

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

        .calculator-layout {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 32px;
          align-items: start;
        }

        @media (max-width: 900px) {
          .calculator-layout {
            grid-template-columns: 1fr;
          }
        }

        .calculator-inputs {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .calculator-results-column {
          position: sticky;
          top: 24px;
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

        .required-star {
          color: #dc2626;
          font-weight: 600;
        }

        .required-field {
          border: 2px solid #dc2626 !important;
          border-radius: 8px;
          animation: pulse-border 2s ease-in-out infinite;
        }

        @keyframes pulse-border {
          0%, 100% { border-color: #dc2626; }
          50% { border-color: #ef4444; }
        }

        .input-with-prefix.required-field {
          border: 2px solid #dc2626;
        }

        select.required-field {
          border: 2px solid #dc2626;
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
          height: fit-content;
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
          font-size: 42px;
          font-weight: 700;
        }

        @media (max-width: 900px) {
          .total-payment .amount {
            font-size: 48px;
          }
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

        .breakdown-item.success .item-label {
          color: #2D7A52;
        }

        .success-text {
          color: #2D7A52;
        }

        /* Mortgage Insurance Section Styles */
        .mi-section {
          flex-direction: column;
          align-items: flex-start;
        }

        .mi-header {
          display: flex;
          justify-content: space-between;
          width: 100%;
          align-items: center;
        }

        .item-note.upfront {
          color: #fbbf24;
          font-weight: 500;
        }

        .mi-details-toggle {
          background: rgba(255, 255, 255, 0.15);
          border: none;
          color: white;
          padding: 6px 12px;
          border-radius: 4px;
          font-size: 12px;
          cursor: pointer;
          margin-top: 8px;
          transition: background 0.2s;
        }

        .mi-details-toggle:hover {
          background: rgba(255, 255, 255, 0.25);
        }

        .mi-details {
          width: 100%;
          background: rgba(0, 0, 0, 0.15);
          border-radius: 6px;
          padding: 12px;
          margin-top: 8px;
        }

        .mi-detail-row {
          display: flex;
          justify-content: space-between;
          font-size: 13px;
          padding: 4px 0;
        }

        .mi-notes {
          font-size: 12px;
          opacity: 0.85;
          margin: 8px 0 0 0;
          line-height: 1.4;
          border-top: 1px solid rgba(255, 255, 255, 0.1);
          padding-top: 8px;
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

        .calculator-prompt {
          background: linear-gradient(135deg, #f5f7fa 0%, #e4e9f0 100%);
          border-radius: 12px;
          padding: 40px 24px;
          text-align: center;
          border: 2px dashed #ccd5e0;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 200px;
        }

        .calculator-prompt p {
          margin: 0;
          color: #666;
          font-size: 15px;
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
