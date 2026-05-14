import React, { useState } from 'react';
import { formatCurrency, formatCurrencyFull } from '../../../services/calculator/CalculatorService';

const ProgramOptionsView = ({ data }) => {
  const { programs, bestMatch, profile: borrowerProfile, homePrice } = data;
  const [expandedProgram, setExpandedProgram] = useState(bestMatch?.id || 'conventional-5');
  const [activeTab, setActiveTab] = useState('recommendation');

  const tabs = [
    { id: 'recommendation', label: 'AI Recommendation', step: 1 },
    { id: 'programs', label: 'Browse Programs', step: 2 },
    { id: 'details', label: 'Program Details', step: 3 },
    { id: 'compare', label: 'Compare', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view">
      <div className="detail-header">
        <h2>Program Options</h2>
        <p className="detail-subtitle">
          Loan programs available for your <strong>{formatCurrency(homePrice)}</strong> home purchase
        </p>
      </div>

      {/* Process Tabs */}
      <div className="process-tabs">
        {tabs.map((tab, idx) => (
          <button
            key={tab.id}
            className={`process-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-step">{tab.step}</span>
            <span className="tab-label">{tab.label}</span>
            {idx < tabs.length - 1 && <span className="tab-arrow">{'→'}</span>}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'recommendation' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>AI Underwriter Recommendation</h3>
              <p>Our intelligent analysis of the best program for you</p>
            </div>
            <div className="ai-recommendation-banner">
              <div className="ai-header">
                <div className="ai-badge">AI UNDERWRITER ANALYSIS</div>
                <div className="ai-title">Recommended for You: {bestMatch?.name}</div>
              </div>
              <div className="ai-content">
                <p>{bestMatch?.aiInsight}</p>
              </div>
              <div className="ai-factors">
                <div className="factor-chip">Credit Score: {borrowerProfile.creditScore}</div>
                <div className="factor-chip">Savings: {formatCurrency(borrowerProfile.savings)}</div>
                <div className="factor-chip">First-Time Buyer</div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('programs')}>Browse All Programs {'→'}</button>
          </div>
        )}

        {activeTab === 'programs' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Available Programs</h3>
              <p>Click on a program to select it, then view details in the next tab</p>
            </div>
            <div className="program-summary-grid">
              {programs.filter(p => !p.requiresEligibility).map(program => (
                <div key={program.id}
                  className={`program-summary-card ${program.id === bestMatch?.id ? 'recommended' : ''} ${program.id === expandedProgram ? 'selected' : ''}`}
                  onClick={() => setExpandedProgram(program.id)}>
                  {program.id === bestMatch?.id && <div className="best-match-tag">Best Match</div>}
                  <div className="program-summary-name">{program.name}</div>
                  <div className="program-summary-payment">{formatCurrencyFull(program.monthlyPayment)}<span>/mo</span></div>
                  <div className="program-summary-down">{program.downPaymentPct}% down ({formatCurrency(program.downPayment)})</div>
                  <div className="program-summary-score">
                    <div className="score-bar"><div className="score-fill" style={{ width: `${program.suitabilityScore}%` }} /></div>
                    <span className="score-value">{program.suitabilityScore}/100</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="eligibility-programs">
              <h4>Programs Requiring Eligibility</h4>
              <p className="eligibility-note">These programs offer excellent terms if you qualify</p>
              <div className="eligibility-cards">
                {programs.filter(p => p.requiresEligibility).map(program => (
                  <div key={program.id}
                    className={`eligibility-card ${program.id === expandedProgram ? 'selected' : ''}`}
                    onClick={() => setExpandedProgram(program.id)}>
                    <div className="eligibility-header">
                      <div className="eligibility-name">{program.name}</div>
                      <div className="eligibility-tag">Check Eligibility</div>
                    </div>
                    <div className="eligibility-highlight">
                      <span className="highlight-label">Down Payment:</span>
                      <span className="highlight-value">{program.downPaymentPct}%</span>
                    </div>
                    <div className="eligibility-note-small">{program.eligibilityNote}</div>
                  </div>
                ))}
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('details')}>View Program Details {'→'}</button>
          </div>
        )}

        {activeTab === 'details' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Program Details</h3>
              <p>Detailed information about the selected program</p>
            </div>
            {programs.filter(p => p.id === expandedProgram).map(program => (
              <div key={program.id} className="program-detail-expanded">
                <div className="program-detail-header">
                  <div className="program-detail-title">
                    <h3>{program.name}</h3>
                    <div className="program-lender">{program.lender}</div>
                  </div>
                  <div className={`program-category-badge ${program.category}`}>
                    {program.category === 'government' ? 'Government-Backed' : 'Conventional'}
                  </div>
                </div>
                <div className="program-ai-insight">
                  <div className="insight-label">AI Underwriter Insight</div>
                  <p>{program.aiInsight}</p>
                </div>
                <div className="program-numbers-grid">
                  <div className="number-card"><div className="number-label">Down Payment</div><div className="number-value">{formatCurrency(program.downPayment)}</div><div className="number-detail">{program.downPaymentPct}% of home price</div></div>
                  <div className="number-card"><div className="number-label">Monthly Payment</div><div className="number-value">{formatCurrencyFull(program.monthlyPayment)}</div><div className="number-detail">Principal, interest, taxes, insurance</div></div>
                  <div className="number-card"><div className="number-label">Interest Rate</div><div className="number-value">{program.interestRate}%</div><div className="number-detail">30-year fixed</div></div>
                  <div className="number-card"><div className="number-label">Cash to Close</div><div className="number-value">{formatCurrency(program.totalCashNeeded)}</div><div className="number-detail">Down payment + closing costs</div></div>
                </div>
                <div className="program-insurance-section">
                  <h4>Mortgage Insurance</h4>
                  <div className="insurance-details">
                    <div className="insurance-row"><span>Monthly MI/MIP</span><span>{program.pmi > 0 ? formatCurrencyFull(program.pmi) : 'None'}</span></div>
                    {program.mipUpfront && (<div className="insurance-row"><span>Upfront MIP (added to loan)</span><span>{formatCurrency(program.mipUpfront)}</span></div>)}
                    {program.fundingFee && (<div className="insurance-row"><span>VA Funding Fee</span><span>{formatCurrency(program.fundingFee)}</span></div>)}
                    {program.guaranteeFee && (<div className="insurance-row"><span>USDA Guarantee Fee</span><span>{formatCurrency(program.guaranteeFee)}</span></div>)}
                    <div className="insurance-row"><span>Removable?</span><span className={program.pmiRemovable ? 'positive' : program.pmiRemovable === false ? 'negative' : ''}>{program.pmiRemovable === true ? 'Yes, at 20% equity' : program.pmiRemovable === false ? 'No, for life of loan' : 'N/A - No MI'}</span></div>
                  </div>
                </div>
                <div className="program-requirements">
                  <h4>Requirements</h4>
                  <div className="requirements-grid">
                    <div className="requirement-item"><div className="requirement-label">Min. Credit Score</div><div className={`requirement-value ${borrowerProfile.creditScore >= program.creditScoreMin ? 'met' : 'not-met'}`}>{program.creditScoreMin}<span className="your-value">(Yours: {borrowerProfile.creditScore})</span></div></div>
                    <div className="requirement-item"><div className="requirement-label">Max DTI</div><div className="requirement-value">{program.dtiMax}%</div></div>
                  </div>
                </div>
                <div className="program-pros-cons">
                  <div className="pros-section"><h4>Advantages</h4><ul className="pros-list">{program.pros.map((pro, i) => (<li key={i}>{pro}</li>))}</ul></div>
                  <div className="cons-section"><h4>Considerations</h4><ul className="cons-list">{program.cons.map((con, i) => (<li key={i}>{con}</li>))}</ul></div>
                </div>
                <div className="program-best-for"><strong>Best For:</strong> {program.bestFor}</div>
              </div>
            ))}
            <button className="next-step-btn" onClick={() => setActiveTab('compare')}>Compare All Programs {'→'}</button>
          </div>
        )}

        {activeTab === 'compare' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Side-by-Side Comparison</h3>
              <p>Compare all available programs at a glance</p>
            </div>
            <div className="program-comparison-table">
              <div className="comparison-table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Feature</th>
                      {programs.filter(p => !p.requiresEligibility).map(p => (
                        <th key={p.id} className={p.id === bestMatch?.id ? 'recommended' : ''}>{p.name.replace(' Down', '')}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr><td>Down Payment</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{formatCurrency(p.downPayment)}</td>))}</tr>
                    <tr><td>Monthly Payment</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{formatCurrencyFull(p.monthlyPayment)}</td>))}</tr>
                    <tr><td>Interest Rate</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{p.interestRate}%</td>))}</tr>
                    <tr><td>Monthly MI</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{p.pmi > 0 ? formatCurrencyFull(p.pmi) : '-'}</td>))}</tr>
                    <tr><td>MI Removable?</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id} className={p.pmiRemovable ? 'positive' : 'negative'}>{p.pmiRemovable ? 'Yes' : 'No'}</td>))}</tr>
                    <tr><td>Cash to Close</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{formatCurrency(p.totalCashNeeded)}</td>))}</tr>
                    <tr><td>Min. Credit</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{p.creditScoreMin}</td>))}</tr>
                    <tr className="suitability-row"><td>Fit Score</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id} className={p.id === bestMatch?.id ? 'best' : ''}>{p.suitabilityScore}/100</td>))}</tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ProgramOptionsView;
