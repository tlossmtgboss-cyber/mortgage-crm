import React, { useState } from 'react';
import { formatCurrency, formatCurrencyFull, formatPercent } from '../../../services/calculator/CalculatorService';

const CashReservesView = ({ data }) => {
  const { scenarios, tailoredOption, emergencyFundTarget, comfortFundTarget, bestStandard } = data;
  const [activeTab, setActiveTab] = useState('profile');

  const tabs = [
    { id: 'profile', label: 'Your Profile', step: 1 },
    { id: 'tailored', label: 'Tailored Fit', step: 2 },
    { id: 'compare', label: 'Compare Options', step: 3 },
    { id: 'recommendation', label: 'Recommendation', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view">
      <div className="detail-header">
        <h2>Suitability Analysis</h2>
        <p className="detail-subtitle">Finding your <strong>tailored fit</strong> — not just any suit, but one made for you</p>
      </div>

      <div className="process-tabs">
        {tabs.map((tab, idx) => (
          <button key={tab.id} className={`process-tab ${activeTab === tab.id ? 'active' : ''}`} onClick={() => setActiveTab(tab.id)}>
            <span className="tab-step">{tab.step}</span>
            <span className="tab-label">{tab.label}</span>
            {idx < tabs.length - 1 && <span className="tab-arrow">{'→'}</span>}
          </button>
        ))}
      </div>

      <div className="tab-content">
        {activeTab === 'profile' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>Your Financial Measurements</h3><p>Understanding your current financial position</p></div>
            <div className="suitability-intro">
              <div className="suit-analogy">
                <div className="analogy-side"><div className="analogy-title">Off-the-Rack</div><div className="analogy-desc">Standard 3%, 5%, 10% options work for most people</div></div>
                <div className="analogy-vs">vs</div>
                <div className="analogy-side highlighted"><div className="analogy-title">Custom Tailored</div><div className="analogy-desc">A down payment sized exactly for your situation</div></div>
              </div>
            </div>
            <div className="financial-profile">
              <div className="profile-grid">
                <div className="profile-item"><div className="profile-label">Available Savings</div><div className="profile-value">{formatCurrency(data.savings)}</div></div>
                <div className="profile-item"><div className="profile-label">Monthly Expenses</div><div className="profile-value">{formatCurrency(data.monthlyExpenses)}</div></div>
                <div className="profile-item"><div className="profile-label">Minimum Reserve (3 mo)</div><div className="profile-value">{formatCurrency(emergencyFundTarget)}</div></div>
                <div className="profile-item"><div className="profile-label">Ideal Reserve (6 mo)</div><div className="profile-value">{formatCurrency(comfortFundTarget)}</div></div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('tailored')}>See Your Tailored Fit {'→'}</button>
          </div>
        )}

        {activeTab === 'tailored' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>Your Perfect Fit Down Payment</h3><p>Custom calculated for your specific situation</p></div>
            <div className="tailored-recommendation">
              <div className="tailored-header"><div className="tailored-badge">CUSTOM TAILORED FOR ALEX</div></div>
              <div className="tailored-content">
                <div className="tailored-main">
                  <div className="tailored-amount">
                    <div className="amount-label">Optimal Down Payment</div>
                    <div className="amount-value">{formatCurrency(tailoredOption.downPayment)}</div>
                    <div className="amount-pct">{formatPercent(tailoredOption.pct * 100)} down</div>
                  </div>
                  <div className="tailored-result">
                    <div className="result-row"><span>Closing Costs</span><span>{formatCurrency(tailoredOption.closingCosts)}</span></div>
                    <div className="result-row highlight"><span>Cash Remaining</span><span>{formatCurrency(tailoredOption.cashRemaining)}</span></div>
                    <div className="result-row"><span>Emergency Reserve</span><span>{tailoredOption.monthsReserve.toFixed(1)} months</span></div>
                    <div className="result-row"><span>Monthly Payment</span><span>{formatCurrencyFull(tailoredOption.piti.total)}</span></div>
                  </div>
                </div>
                <div className="tailored-why">
                  <strong>Why this amount?</strong> This leaves you with exactly 3 months of expenses
                  ({formatCurrency(emergencyFundTarget)}) in reserve — the recommended minimum emergency fund for new homeowners.
                </div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('compare')}>Compare Standard Options {'→'}</button>
          </div>
        )}

        {activeTab === 'compare' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>How Standard Options Compare</h3><p>See how preset down payment options stack up for you</p></div>
            <div className="suitability-cards">
              {scenarios.map((s) => (
                <div key={s.label} className={`suitability-card ${s.fitLevel}`}>
                  <div className="suit-card-header">
                    <div className="suit-card-title">{s.label}</div>
                    <div className={`fit-badge ${s.fitLevel}`}>{s.fitDescription}</div>
                  </div>
                  <div className="suit-score-ring">
                    <svg viewBox="0 0 100 100" className="score-svg">
                      <circle cx="50" cy="50" r="45" className="score-bg" />
                      <circle cx="50" cy="50" r="45" className={`score-fill ${s.fitLevel}`} strokeDasharray={`${s.suitabilityScore * 2.83} 283`} transform="rotate(-90 50 50)" />
                    </svg>
                    <div className="score-value">{s.suitabilityScore}</div>
                    <div className="score-label">Fit Score</div>
                  </div>
                  <div className="suit-card-details">
                    <div className="suit-detail"><span>Down Payment</span><span>{formatCurrency(s.downPayment)}</span></div>
                    <div className="suit-detail"><span>Cash Left</span><span className={s.cashRemaining < 0 ? 'negative' : ''}>{formatCurrency(s.cashRemaining)}</span></div>
                    <div className="suit-detail"><span>Reserve</span><span>{s.monthsReserve.toFixed(1)} months</span></div>
                  </div>
                  <div className="suit-factors">
                    {s.factors.map((f) => (
                      <div key={f.name} className={`factor-row ${f.status}`}>
                        <div className="factor-name">{f.name}</div>
                        <div className="factor-bar"><div className="factor-fill" style={{ width: `${(f.score / f.max) * 100}%` }} /></div>
                        <div className="factor-score">{f.score}/{f.max}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('recommendation')}>See Final Recommendation {'→'}</button>
          </div>
        )}

        {activeTab === 'recommendation' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>Suitability Recommendation</h3><p>Our final analysis for your situation</p></div>
            <div className="suitability-verdict">
              <div className="verdict-content">
                <div className="verdict-title">Your Best Options</div>
                <div className="rec-options">
                  <div className="rec-option primary">
                    <div className="rec-badge">Custom Tailored</div>
                    <h4>{formatPercent(tailoredOption.pct * 100)} Down ({formatCurrency(tailoredOption.downPayment)})</h4>
                    <p>Leaves you with exactly 3 months of reserves — the recommended minimum for new homeowners.</p>
                  </div>
                  <div className="rec-option secondary">
                    <div className="rec-badge">Best Standard Option</div>
                    <h4>{bestStandard.label}</h4>
                    <p>Scores {bestStandard.suitabilityScore}/100, leaving {formatCurrency(bestStandard.cashRemaining)} ({bestStandard.monthsReserve.toFixed(1)} months) in reserve.</p>
                  </div>
                </div>
                <div className="rec-summary">
                  Based on your savings of <strong>{formatCurrency(data.savings)}</strong> and monthly expenses of
                  <strong> {formatCurrency(data.monthlyExpenses)}</strong>, either option provides adequate reserves
                  while maximizing your purchasing power.
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default CashReservesView;
