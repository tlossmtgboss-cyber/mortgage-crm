import React, { useState } from 'react';
import { formatCurrency } from '../../services/calculator/CalculatorService';

const ScenarioSelector = ({
  homePrice,
  downPaymentPct,
  interestRate,
  termYears,
  points,
  loanProgram = 'conventional',
  onUpdate
}) => {
  const DOWN_PAYMENT_OPTIONS = [3, 3.5, 5, 10, 20];
  const TERM_OPTIONS = [30, 20, 15, 10];
  const POINTS_OPTIONS = [0, 0.5, 1, 1.5, 2];

  const LOAN_PROGRAMS = [
    { id: 'conventional', name: 'Conventional', desc: '3-20% down, 620+ credit', minDown: 3 },
    { id: 'fha', name: 'FHA', desc: '3.5% down, 580+ credit', minDown: 3.5 },
    { id: 'va', name: 'VA', desc: '0% down, veterans only', minDown: 0 },
    { id: 'usda', name: 'USDA', desc: '0% down, rural areas', minDown: 0 },
    { id: 'jumbo', name: 'Jumbo', desc: 'Loans over $832,750', minDown: 10 },
    { id: 'allinone', name: 'All In One', desc: 'First-lien HELOC, 680+ credit', minDown: 20, special: true },
  ];

  const RATE_OPTIONS = [
    { rate: 6.25, label: 'Excellent Credit', points: 1.5 },
    { rate: 6.5, label: 'Great Credit', points: 1 },
    { rate: 6.75, label: 'Good Credit', points: 0.5 },
    { rate: 6.875, label: 'Market Rate', points: 0 },
    { rate: 7.0, label: 'Fair Credit', points: 0 },
    { rate: 7.25, label: 'Lower Credit', points: 0 },
  ];

  const [selectedProgram, setSelectedProgram] = useState(loanProgram);
  const [selectedRate, setSelectedRate] = useState(interestRate);
  const [customRate, setCustomRate] = useState(interestRate.toString());

  const downPayment = homePrice * (downPaymentPct / 100);
  const loanAmount = homePrice - downPayment;
  const pointsCost = loanAmount * (points / 100);
  const rateReduction = points * 0.25;

  const handleProgramChange = (programId) => {
    setSelectedProgram(programId);
    const program = LOAN_PROGRAMS.find(p => p.id === programId);
    if (program && downPaymentPct < program.minDown) {
      onUpdate({ downPaymentPct: program.minDown });
    }
  };

  return (
    <div className="scenario-selector">
      {/* Purchase Details */}
      <div className="selector-section">
        <h3>Purchase Details</h3>
        <div className="selector-row">
          <div className="selector-field">
            <label>Home Price</label>
            <div className="input-with-prefix">
              <span className="prefix">$</span>
              <input
                type="number"
                value={homePrice}
                onChange={(e) => onUpdate({ homePrice: Number(e.target.value) || 0 })}
              />
            </div>
          </div>
          <div className="selector-field">
            <label>Down Payment</label>
            <div className="down-payment-input">
              <div className="input-with-suffix">
                <input
                  type="number"
                  value={downPaymentPct}
                  onChange={(e) => onUpdate({ downPaymentPct: Number(e.target.value) || 0 })}
                />
                <span className="suffix">%</span>
              </div>
              <span className="down-amount">{formatCurrency(downPayment)}</span>
            </div>
          </div>
        </div>
        <div className="quick-select-row">
          {DOWN_PAYMENT_OPTIONS.map(pct => (
            <button
              key={pct}
              className={`quick-btn ${downPaymentPct === pct ? 'active' : ''}`}
              onClick={() => onUpdate({ downPaymentPct: pct })}
            >
              {pct}%
            </button>
          ))}
        </div>
        <div className="loan-amount-display">
          <span>Loan Amount:</span>
          <span className="loan-value">{formatCurrency(loanAmount)}</span>
        </div>
      </div>

      {/* Loan Program */}
      <div className="selector-section">
        <h3>Loan Program</h3>
        <div className="program-grid">
          {LOAN_PROGRAMS.map(program => (
            <button
              key={program.id}
              className={`program-btn ${selectedProgram === program.id ? 'active' : ''} ${program.special ? 'special' : ''}`}
              onClick={() => handleProgramChange(program.id)}
            >
              {program.special && <span className="special-badge">HELOC</span>}
              <span className="program-name">{program.name}</span>
              <span className="program-desc">{program.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Interest Rate Options */}
      <div className="selector-section">
        <h3>Interest Rate Options</h3>
        <p className="section-hint">Select rates to compare. Check multiple to see side-by-side analysis.</p>
        <div className="rate-grid">
          {RATE_OPTIONS.map((opt, idx) => (
            <button
              key={idx}
              className={`rate-btn ${selectedRate === opt.rate ? 'active' : ''}`}
              onClick={() => {
                setSelectedRate(opt.rate);
                setCustomRate(opt.rate.toString());
                onUpdate({ interestRate: opt.rate, points: opt.points });
              }}
            >
              <span className="rate-value">{opt.rate}%</span>
              <span className="rate-label">{opt.label}</span>
              {opt.points > 0 && <span className="rate-points">{opt.points} pts</span>}
            </button>
          ))}
        </div>
        <div className="custom-rate-row">
          <span>Or enter custom rate:</span>
          <div className="input-with-suffix small">
            <input
              type="number"
              step="0.125"
              value={customRate}
              onChange={(e) => {
                setCustomRate(e.target.value);
                const rate = parseFloat(e.target.value);
                if (!isNaN(rate) && rate > 0) {
                  setSelectedRate(rate);
                  onUpdate({ interestRate: rate });
                }
              }}
            />
            <span className="suffix">%</span>
          </div>
        </div>
      </div>

      {/* Loan Term */}
      <div className="selector-section">
        <h3>Loan Term</h3>
        <div className="term-grid">
          {TERM_OPTIONS.map(term => (
            <button
              key={term}
              className={`term-btn ${termYears === term ? 'active' : ''}`}
              onClick={() => onUpdate({ termYears: term })}
            >
              <span className="term-value">{term}</span>
              <span className="term-label">years</span>
            </button>
          ))}
        </div>
      </div>

      {/* Discount Points */}
      <div className="selector-section">
        <h3>Discount Points</h3>
        <p className="section-hint">Pay upfront to reduce your rate. Each point costs 1% of loan amount.</p>
        <div className="points-row">
          {POINTS_OPTIONS.map(pt => (
            <button
              key={pt}
              className={`points-btn ${points === pt ? 'active' : ''}`}
              onClick={() => onUpdate({ points: pt })}
            >
              {pt}
            </button>
          ))}
        </div>
        {points > 0 && (
          <div className="points-summary">
            <div className="points-item">
              <span>Upfront Cost</span>
              <span className="cost">{formatCurrency(pointsCost)}</span>
            </div>
            <div className="points-item">
              <span>Rate Reduction</span>
              <span className="reduction">-{rateReduction.toFixed(3)}%</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ScenarioSelector;
