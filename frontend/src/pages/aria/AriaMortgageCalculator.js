import React, { useState, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import MobileBottomNav from '../../components/mobile/MobileBottomNav';
import './AriaMortgageCalculator.css';

const LOAN_TYPES = [
  { value: 'conventional', label: 'Conventional' },
  { value: 'fha', label: 'FHA' },
  { value: 'va', label: 'VA' },
  { value: 'usda', label: 'USDA' },
  { value: 'jumbo', label: 'Jumbo' },
];

const LOAN_TYPE_INFO = {
  conventional: 'Standard loan not insured by the government. Typically requires 3-20% down and good credit (620+).',
  fha: 'Government-insured loan with low down payment (3.5%) and flexible credit requirements (580+).',
  va: 'Available to veterans and active military. No down payment required and no PMI.',
  usda: 'For rural and suburban homebuyers. No down payment required. Income limits apply.',
  jumbo: 'For loan amounts exceeding conforming loan limits ($766,550 in most areas). Higher credit/down payment requirements.',
};

const formatCurrency = (val) => {
  if (val === '' || val === null || val === undefined) return '';
  const n = typeof val === 'string' ? parseFloat(val.replace(/[^0-9.]/g, '')) : val;
  if (isNaN(n)) return '';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(n);
};

const formatNumber = (val) => {
  if (val === '' || val === null) return '';
  const n = typeof val === 'string' ? parseFloat(val.replace(/[^0-9.]/g, '')) : val;
  if (isNaN(n)) return '';
  return new Intl.NumberFormat('en-US').format(n);
};

const parseCurrencyInput = (str) => {
  const clean = str.replace(/[^0-9]/g, '');
  return clean ? parseInt(clean, 10) : 0;
};

const calculateMonthlyPayment = (principal, annualRate, years) => {
  const r = annualRate / 100 / 12;
  const n = years * 12;
  if (r === 0) return n > 0 ? principal / n : 0;
  return principal * (r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
};

const calculatePMI = (loanAmount, homeValue, creditScore, loanType) => {
  if (loanType === 'va') return 0;
  const ltv = (loanAmount / homeValue) * 100;
  if (loanType === 'conventional' && ltv <= 80) return 0;
  let rate = 0.005;
  if (ltv > 95) rate = 0.01;
  else if (ltv > 90) rate = 0.008;
  else if (ltv > 85) rate = 0.006;
  if (creditScore < 680) rate += 0.002;
  else if (creditScore >= 760) rate -= 0.001;
  if (loanType === 'fha') rate = 0.0055; // MIP
  return (loanAmount * rate) / 12;
};

export default function AriaMortgageCalculator() {
  const navigate = useNavigate();
  const [loanPurpose, setLoanPurpose] = useState('purchase');
  const [loanType, setLoanType] = useState('conventional');
  const [showLoanInfo, setShowLoanInfo] = useState(false);
  const [homePrice, setHomePrice] = useState(400000);
  const [downPayment, setDownPayment] = useState(80000);
  const [interestRate, setInterestRate] = useState(6.5);
  const [loanTerm, setLoanTerm] = useState(30);
  const [creditScore, setCreditScore] = useState(720);
  const [propertyTax, setPropertyTax] = useState(1.1);
  const [homeInsurance, setHomeInsurance] = useState(1500);
  const [showResults, setShowResults] = useState(false);
  const resultsRef = useRef(null);

  const downPaymentPct = homePrice > 0 ? ((downPayment / homePrice) * 100).toFixed(1) : '0.0';
  const loanAmount = Math.max(0, homePrice - downPayment);

  const results = useMemo(() => {
    if (loanAmount <= 0) return null;
    const safeRate = typeof interestRate === 'number' ? interestRate : parseFloat(interestRate) || 0;
    const pi = calculateMonthlyPayment(loanAmount, safeRate, loanTerm);
    const tax = (homePrice * (propertyTax / 100)) / 12;
    const insurance = homeInsurance / 12;
    const pmi = calculatePMI(loanAmount, homePrice, creditScore, loanType);
    const total = pi + tax + insurance + pmi;
    return { pi, tax, insurance, pmi, total, loanAmount };
  }, [loanAmount, homePrice, interestRate, loanTerm, propertyTax, homeInsurance, creditScore, loanType]);

  const handleHomePriceChange = (val) => {
    const num = parseCurrencyInput(val);
    setHomePrice(num);
    // Adjust down payment to maintain percentage
    const pct = homePrice > 0 ? downPayment / homePrice : 0.2;
    setDownPayment(Math.round(num * pct));
  };

  const handleDownPaymentChange = (val) => {
    const num = parseCurrencyInput(val);
    setDownPayment(Math.min(num, homePrice));
  };

  return (
    <div className="aria-calc-page">
      {/* Header */}
      <div className="aria-calc-header">
        <button className="aria-calc-back" onClick={() => navigate(-1)} aria-label="Go back">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#111827" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
      </div>

      <div className="aria-calc-content">
        <h1 className="aria-calc-title">Mortgage inputs</h1>
        <p className="aria-calc-subtitle">Let's figure out what your monthly payments would be.</p>

        {/* Loan + Home section */}
        <div className="aria-calc-section">
          <div className="aria-calc-section-header">
            <span className="aria-calc-section-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#111827" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z" />
                <polyline points="9 22 9 12 15 12 15 22" />
              </svg>
            </span>
            <span className="aria-calc-section-label">Loan + home</span>
          </div>

          {/* Loan purpose */}
          <div className="aria-calc-field">
            <label className="aria-calc-label">Loan purpose</label>
            <div className="aria-calc-toggle-group">
              <button className={`aria-calc-toggle ${loanPurpose === 'purchase' ? 'aria-calc-toggle--active' : ''}`} onClick={() => setLoanPurpose('purchase')}>
                <span className={`aria-calc-toggle__radio ${loanPurpose === 'purchase' ? 'aria-calc-toggle__radio--checked' : ''}`} />
                Purchase
              </button>
              <button className={`aria-calc-toggle ${loanPurpose === 'refinance' ? 'aria-calc-toggle--active' : ''}`} onClick={() => setLoanPurpose('refinance')}>
                <span className={`aria-calc-toggle__radio ${loanPurpose === 'refinance' ? 'aria-calc-toggle__radio--checked' : ''}`} />
                Refinance
              </button>
            </div>
          </div>

          {/* Loan type */}
          <div className="aria-calc-field">
            <label className="aria-calc-label">Loan type</label>
            <div className="aria-calc-select-wrap">
              <select className="aria-calc-select" value={loanType} onChange={(e) => setLoanType(e.target.value)}>
                {LOAN_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              <span className="aria-calc-select-arrow">&#9662;</span>
            </div>
            <button className="aria-calc-info-link" onClick={() => setShowLoanInfo(!showLoanInfo)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
              Learn about loan types
            </button>
            {showLoanInfo && (
              <div className="aria-calc-info-box">
                <strong>{LOAN_TYPES.find(t => t.value === loanType)?.label}</strong>
                <p>{LOAN_TYPE_INFO[loanType]}</p>
              </div>
            )}
          </div>

          {/* Home price */}
          <div className="aria-calc-field">
            <label className="aria-calc-label">Home price</label>
            <div className="aria-calc-currency-input">
              <span className="aria-calc-currency-prefix">$</span>
              <input
                type="text"
                inputMode="numeric"
                className="aria-calc-input"
                value={formatNumber(homePrice)}
                onChange={(e) => handleHomePriceChange(e.target.value)}
              />
            </div>
            <input
              type="range"
              className="aria-calc-slider"
              min="50000"
              max="2000000"
              step="5000"
              value={homePrice}
              onChange={(e) => { setHomePrice(parseInt(e.target.value)); setDownPayment(Math.round(parseInt(e.target.value) * (downPayment / (homePrice || 1)))); }}
            />
            <div className="aria-calc-slider-labels">
              <span>$50K</span>
              <span>$2M</span>
            </div>
          </div>

          {/* Down payment */}
          <div className="aria-calc-field">
            <label className="aria-calc-label">Down payment <span className="aria-calc-label-hint">({downPaymentPct}%)</span></label>
            <div className="aria-calc-currency-input">
              <span className="aria-calc-currency-prefix">$</span>
              <input
                type="text"
                inputMode="numeric"
                className="aria-calc-input"
                value={formatNumber(downPayment)}
                onChange={(e) => handleDownPaymentChange(e.target.value)}
              />
            </div>
            <input
              type="range"
              className="aria-calc-slider"
              min="0"
              max={homePrice}
              step="1000"
              value={downPayment}
              onChange={(e) => setDownPayment(parseInt(e.target.value))}
            />
          </div>

          {/* Interest rate */}
          <div className="aria-calc-field">
            <label className="aria-calc-label">Interest rate</label>
            <div className="aria-calc-currency-input">
              <input
                type="text"
                inputMode="decimal"
                className="aria-calc-input aria-calc-input--rate"
                value={interestRate}
                onChange={(e) => {
                  const raw = e.target.value;
                  if (raw === '' || raw === '.') {
                    setInterestRate(raw);
                    return;
                  }
                  const v = parseFloat(raw);
                  if (!isNaN(v) && v >= 0 && v <= 20) setInterestRate(v);
                }}
              />
              <span className="aria-calc-currency-suffix">%</span>
            </div>
          </div>

          {/* Loan term */}
          <div className="aria-calc-field">
            <label className="aria-calc-label">Loan term</label>
            <div className="aria-calc-toggle-group">
              {[15, 20, 30].map((t) => (
                <button key={t} className={`aria-calc-toggle ${loanTerm === t ? 'aria-calc-toggle--active' : ''}`} onClick={() => setLoanTerm(t)}>
                  {t} yr
                </button>
              ))}
            </div>
          </div>

          {/* Credit score */}
          <div className="aria-calc-field">
            <label className="aria-calc-label">Credit score</label>
            <input
              type="range"
              className="aria-calc-slider"
              min="300"
              max="850"
              step="10"
              value={creditScore}
              onChange={(e) => setCreditScore(parseInt(e.target.value))}
            />
            <div className="aria-calc-slider-labels">
              <span>300</span>
              <span className="aria-calc-slider-value">{creditScore}</span>
              <span>850</span>
            </div>
          </div>
        </div>

        {/* Calculate button */}
        <button className="aria-calc-submit" onClick={() => {
          setShowResults(true);
          setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
        }}>
          Calculate Payment
        </button>

        {/* Results */}
        {showResults && results && (
          <div className="aria-calc-results" ref={resultsRef}>
            <div className="aria-calc-results__total">
              <span className="aria-calc-results__total-label">Estimated monthly payment</span>
              <span className="aria-calc-results__total-value">{formatCurrency(results.total)}</span>
            </div>
            <div className="aria-calc-results__breakdown">
              <div className="aria-calc-results__row">
                <span>Principal & Interest</span>
                <span>{formatCurrency(results.pi)}</span>
              </div>
              <div className="aria-calc-results__row">
                <span>Property Tax</span>
                <span>{formatCurrency(results.tax)}</span>
              </div>
              <div className="aria-calc-results__row">
                <span>Home Insurance</span>
                <span>{formatCurrency(results.insurance)}</span>
              </div>
              {results.pmi > 0 && (
                <div className="aria-calc-results__row">
                  <span>{loanType === 'fha' ? 'Mortgage Insurance (MIP)' : 'PMI'}</span>
                  <span>{formatCurrency(results.pmi)}</span>
                </div>
              )}
              <div className="aria-calc-results__divider" />
              <div className="aria-calc-results__row aria-calc-results__row--loan">
                <span>Loan amount</span>
                <span>{formatCurrency(results.loanAmount)}</span>
              </div>
            </div>
          </div>
        )}
      </div>

      <MobileBottomNav />
    </div>
  );
}
