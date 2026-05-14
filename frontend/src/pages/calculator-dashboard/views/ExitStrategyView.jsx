import React, { useState } from 'react';
import { formatCurrency, formatCurrencyFull, formatPercent } from '../../../services/calculator/CalculatorService';

const ExitStrategyView = ({ data }) => {
  const { equityTimeline, refinanceScenarios, rentalScenario, homePrice, currentPayment } = data;
  const [activeTab, setActiveTab] = useState('equity');

  const tabs = [
    { id: 'equity', label: 'Equity Timeline', step: 1 },
    { id: 'refinance', label: 'Refinance Options', step: 2 },
    { id: 'rental', label: 'Rental Potential', step: 3 },
    { id: 'summary', label: 'Summary', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view">
      <div className="detail-header">
        <h2>Exit Strategy</h2>
        <p className="detail-subtitle">
          Understanding your options: sell, refinance, or rent
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
        {activeTab === 'equity' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Equity Position Over Time</h3>
              <p>When can you sell profitably? (Assumes 3% annual appreciation)</p>
            </div>
            <div className="equity-timeline">
              <div className="timeline-header">
                <div>Year</div>
                <div>Home Value</div>
                <div>Equity</div>
                <div>Net if Sold</div>
                <div>ROI</div>
              </div>
              {equityTimeline.map((year) => (
                <div key={year.year} className={`timeline-row ${year.canSellProfitably ? 'profitable' : 'underwater'}`}>
                  <div className="year-cell">Year {year.year}</div>
                  <div>{formatCurrency(year.homeValue)}</div>
                  <div>
                    <span className="equity-amount">{formatCurrency(year.equity)}</span>
                    <span className="equity-pct">({formatPercent(year.equityPercent)})</span>
                  </div>
                  <div className={year.netProceeds > 0 ? 'positive' : 'negative'}>
                    {formatCurrency(year.netProceeds)}
                  </div>
                  <div className={year.roi > 0 ? 'positive' : 'negative'}>
                    {year.roi > 0 ? '+' : ''}{formatPercent(year.roi)}
                  </div>
                </div>
              ))}
            </div>
            <div className="timeline-note">
              * Net if Sold accounts for 7% selling costs (realtor fees + closing)
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('refinance')}>
              Explore Refinance Options {'→'}
            </button>
          </div>
        )}

        {activeTab === 'refinance' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Refinance Opportunities</h3>
              <p>If interest rates drop, here's what you could save</p>
            </div>
            <div className="refi-cards">
              {refinanceScenarios.map((scenario) => (
                <div key={scenario.name} className={`refi-card ${scenario.worthIt ? 'worth-it' : ''}`}>
                  <div className="refi-header">
                    <div className="refi-name">{scenario.name}</div>
                    <div className={`refi-badge ${scenario.worthIt ? 'yes' : 'maybe'}`}>
                      {scenario.worthIt ? 'Worth It' : 'Maybe'}
                    </div>
                  </div>
                  <div className="refi-rates">
                    <span>{data.interestRate}%</span>
                    <span className="arrow">{'→'}</span>
                    <span className="new-rate">{scenario.newRate}%</span>
                  </div>
                  <div className="refi-details">
                    <div className="refi-row"><span>New Payment</span><span>{formatCurrencyFull(scenario.newPayment)}</span></div>
                    <div className="refi-row highlight"><span>Monthly Savings</span><span className="positive">{formatCurrencyFull(scenario.monthlySavings)}</span></div>
                    <div className="refi-row"><span>Refi Costs (~2%)</span><span>{formatCurrency(scenario.refinanceCosts)}</span></div>
                    <div className="refi-row"><span>Break-Even</span><span>{scenario.breakEvenMonths} months</span></div>
                  </div>
                </div>
              ))}
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('rental')}>
              See Rental Potential {'→'}
            </button>
          </div>
        )}

        {activeTab === 'rental' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Convert to Rental Property</h3>
              <p>What if you keep it and rent it out?</p>
            </div>
            <div className="rental-card">
              <div className="rental-calc">
                <div className="rental-row">
                  <span>Estimated Monthly Rent</span>
                  <span className="positive">{formatCurrencyFull(rentalScenario.estimatedRent)}</span>
                </div>
                <div className="rental-row">
                  <span>Monthly Mortgage (PITI)</span>
                  <span className="negative">-{formatCurrencyFull(rentalScenario.monthlyMortgage)}</span>
                </div>
                <div className={`rental-row total ${rentalScenario.isPositive ? 'positive' : 'negative'}`}>
                  <span>Monthly Cash Flow</span>
                  <span>{rentalScenario.cashFlow >= 0 ? '+' : ''}{formatCurrencyFull(rentalScenario.cashFlow)}</span>
                </div>
              </div>
              <div className="rental-metrics">
                <div className="metric">
                  <div className="metric-label">Cap Rate</div>
                  <div className="metric-value">{formatPercent(rentalScenario.capRate)}</div>
                </div>
                <div className="metric">
                  <div className="metric-label">Cash Flow Status</div>
                  <div className={`metric-value ${rentalScenario.isPositive ? 'positive' : 'negative'}`}>
                    {rentalScenario.isPositive ? 'Positive' : 'Negative'}
                  </div>
                </div>
              </div>
              <div className="rental-note">
                {rentalScenario.isPositive ? (
                  <>This property could generate passive income if you move and rent it out</>
                ) : (
                  <>You'd need to cover {formatCurrencyFull(Math.abs(rentalScenario.cashFlow))}/month if renting it out</>
                )}
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('summary')}>
              View Summary {'→'}
            </button>
          </div>
        )}

        {activeTab === 'summary' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Flexibility Summary</h3>
              <p>Your exit options at a glance</p>
            </div>
            <div className="exit-summary-grid">
              <div className="exit-option-card">
                <div className="option-icon">{'\u{1F3E0}'}</div>
                <h4>Sell</h4>
                <p>You'll have positive equity by Year 2, making selling viable.</p>
                <div className="option-status positive">Available after Year 2</div>
              </div>
              <div className="exit-option-card">
                <div className="option-icon">{'\u{1F4C9}'}</div>
                <h4>Refinance</h4>
                <p>If rates drop 1%+, refinancing makes sense.</p>
                <div className="option-status">Monitor rate environment</div>
              </div>
              <div className="exit-option-card">
                <div className="option-icon">{'\u{1F3D8}️'}</div>
                <h4>Rent Out</h4>
                <p>The property {rentalScenario.isPositive ? 'could generate income' : 'would need subsidy'}.</p>
                <div className={`option-status ${rentalScenario.isPositive ? 'positive' : 'warning'}`}>
                  {rentalScenario.isPositive ? 'Cash flow positive' : 'Needs monthly subsidy'}
                </div>
              </div>
            </div>
            <div className="key-insight">
              <strong>Bottom Line:</strong> You have multiple exit options. This property provides financial flexibility
              whether you need to sell, refinance for better terms, or convert to an investment property.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ExitStrategyView;
