import React, { useState } from 'react';
import { formatCurrency, formatCurrencyFull, formatPercent } from '../../../services/calculator/CalculatorService';

const RepaymentStrategyView = ({ data }) => {
  const { standard30, extra200, extra500, biweekly, fifteenYear, loanAmount, interestRate } = data;
  const [activeTab, setActiveTab] = useState('overview');

  const tabs = [
    { id: 'overview', label: 'Current Loan', step: 1 },
    { id: 'strategies', label: 'Payoff Strategies', step: 2 },
    { id: 'fifteen', label: '15-Year Option', step: 3 },
    { id: 'recommendation', label: 'Recommendation', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view">
      <div className="detail-header">
        <h2>Repayment Strategy</h2>
        <p className="detail-subtitle">
          How to pay off your mortgage faster and build wealth
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
        {activeTab === 'overview' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Your Current Loan Details</h3>
              <p>Understanding your baseline before exploring strategies</p>
            </div>
            <div className="repay-summary">
              <div className="repay-summary-item">
                <div className="summary-label">Loan Amount</div>
                <div className="summary-value">{formatCurrency(loanAmount)}</div>
              </div>
              <div className="repay-summary-item">
                <div className="summary-label">Interest Rate</div>
                <div className="summary-value">{interestRate}%</div>
              </div>
              <div className="repay-summary-item">
                <div className="summary-label">Standard Payment</div>
                <div className="summary-value">{formatCurrencyFull(standard30.payment)}</div>
              </div>
              <div className="repay-summary-item highlight">
                <div className="summary-label">Total Interest (30yr)</div>
                <div className="summary-value negative">{formatCurrency(standard30.totalInterest)}</div>
              </div>
            </div>
            <div className="panel-insight">
              <strong>Did you know?</strong> Over 30 years, you'll pay {formatCurrency(standard30.totalInterest)} in interest —
              that's {formatPercent((standard30.totalInterest / loanAmount) * 100)} of your original loan amount!
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('strategies')}>
              Explore Payoff Strategies {'→'}
            </button>
          </div>
        )}

        {activeTab === 'strategies' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Accelerated Payoff Strategies</h3>
              <p>Compare different ways to pay off your mortgage faster</p>
            </div>
            <div className="strategy-cards">
              <div className="strategy-card baseline">
                <div className="strategy-header">
                  <div className="strategy-name">Standard 30-Year</div>
                  <div className="strategy-badge baseline">Baseline</div>
                </div>
                <div className="strategy-payment">
                  <span className="payment-amount">{formatCurrencyFull(standard30.payment)}</span>
                  <span className="payment-freq">/month</span>
                </div>
                <div className="strategy-details">
                  <div className="detail-row"><span>Payoff Time</span><span>30 years</span></div>
                  <div className="detail-row"><span>Total Interest</span><span className="negative">{formatCurrency(standard30.totalInterest)}</span></div>
                  <div className="detail-row"><span>Interest Saved</span><span>{'—'}</span></div>
                </div>
              </div>

              <div className="strategy-card">
                <div className="strategy-header">
                  <div className="strategy-name">+$200/month Extra</div>
                  <div className="strategy-badge good">Popular</div>
                </div>
                <div className="strategy-payment">
                  <span className="payment-amount">{formatCurrencyFull(extra200.payment)}</span>
                  <span className="payment-freq">/month</span>
                </div>
                <div className="strategy-details">
                  <div className="detail-row"><span>Payoff Time</span><span className="positive">{extra200.years} years</span></div>
                  <div className="detail-row"><span>Total Interest</span><span>{formatCurrency(extra200.totalInterest)}</span></div>
                  <div className="detail-row highlight"><span>Interest Saved</span><span className="positive">{formatCurrency(extra200.interestSaved)}</span></div>
                </div>
                <div className="strategy-impact">Save {extra200.yearsSaved.toFixed(1)} years & {formatCurrency(extra200.interestSaved)}</div>
              </div>

              <div className="strategy-card recommended">
                <div className="strategy-header">
                  <div className="strategy-name">+$500/month Extra</div>
                  <div className="strategy-badge best">Best Value</div>
                </div>
                <div className="strategy-payment">
                  <span className="payment-amount">{formatCurrencyFull(extra500.payment)}</span>
                  <span className="payment-freq">/month</span>
                </div>
                <div className="strategy-details">
                  <div className="detail-row"><span>Payoff Time</span><span className="positive">{extra500.years} years</span></div>
                  <div className="detail-row"><span>Total Interest</span><span>{formatCurrency(extra500.totalInterest)}</span></div>
                  <div className="detail-row highlight"><span>Interest Saved</span><span className="positive">{formatCurrency(extra500.interestSaved)}</span></div>
                </div>
                <div className="strategy-impact">Save {extra500.yearsSaved.toFixed(1)} years & {formatCurrency(extra500.interestSaved)}</div>
              </div>

              <div className="strategy-card">
                <div className="strategy-header">
                  <div className="strategy-name">Biweekly Payments</div>
                  <div className="strategy-badge">Easy</div>
                </div>
                <div className="strategy-payment">
                  <span className="payment-amount">{formatCurrencyFull(biweekly.payment)}</span>
                  <span className="payment-freq">/2 weeks</span>
                </div>
                <div className="strategy-details">
                  <div className="detail-row"><span>Payoff Time</span><span className="positive">{biweekly.years} years</span></div>
                  <div className="detail-row"><span>Total Interest</span><span>{formatCurrency(biweekly.totalInterest)}</span></div>
                  <div className="detail-row highlight"><span>Interest Saved</span><span className="positive">{formatCurrency(biweekly.interestSaved)}</span></div>
                </div>
                <div className="strategy-impact">Same budget, {biweekly.yearsSaved.toFixed(1)} years faster</div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('fifteen')}>
              See 15-Year Option {'→'}
            </button>
          </div>
        )}

        {activeTab === 'fifteen' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>15-Year Loan Alternative</h3>
              <p>A shorter term means higher payments but massive interest savings</p>
            </div>
            <div className="fifteen-year-card">
              <div className="fifteen-comparison">
                <div className="fifteen-side">
                  <div className="fifteen-label">30-Year Loan</div>
                  <div className="fifteen-payment">{formatCurrencyFull(standard30.payment)}/mo</div>
                  <div className="fifteen-interest">Total Interest: {formatCurrency(standard30.totalInterest)}</div>
                </div>
                <div className="fifteen-vs">vs</div>
                <div className="fifteen-side highlight">
                  <div className="fifteen-label">15-Year Loan ({fifteenYear.rate}%)</div>
                  <div className="fifteen-payment">{formatCurrencyFull(fifteenYear.payment)}/mo</div>
                  <div className="fifteen-interest">Total Interest: {formatCurrency(fifteenYear.totalInterest)}</div>
                </div>
              </div>
              <div className="fifteen-summary">
                <div className="summary-item">
                  <span>Extra Monthly Cost</span>
                  <span>+{formatCurrencyFull(fifteenYear.extraMonthlyNeeded)}</span>
                </div>
                <div className="summary-item highlight">
                  <span>Total Interest Saved</span>
                  <span className="positive">{formatCurrency(fifteenYear.interestSaved)}</span>
                </div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('recommendation')}>
              See Recommendation {'→'}
            </button>
          </div>
        )}

        {activeTab === 'recommendation' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Our Recommendation</h3>
              <p>The best strategy based on your situation</p>
            </div>
            <div className="recommendation-box">
              <div className="rec-badge">Best Strategy</div>
              <h4>Biweekly Payments</h4>
              <p>
                The biweekly payment strategy is the easiest win — same monthly budget but you make
                13 payments per year instead of 12, saving <strong>{formatCurrency(biweekly.interestSaved)}</strong> and
                <strong> {biweekly.yearsSaved.toFixed(1)} years</strong>.
              </p>
              <div className="rec-comparison">
                <div className="rec-item">
                  <span className="rec-label">Interest Saved</span>
                  <span className="rec-value positive">{formatCurrency(biweekly.interestSaved)}</span>
                </div>
                <div className="rec-item">
                  <span className="rec-label">Years Saved</span>
                  <span className="rec-value positive">{biweekly.yearsSaved.toFixed(1)} years</span>
                </div>
                <div className="rec-item">
                  <span className="rec-label">Effort Level</span>
                  <span className="rec-value">Easy - Just switch payment schedule</span>
                </div>
              </div>
            </div>
            <div className="alternative-strategies">
              <h5>If you have extra cash flow:</h5>
              <ul>
                <li>+$200/month saves {formatCurrency(extra200.interestSaved)} and {extra200.yearsSaved.toFixed(1)} years</li>
                <li>+$500/month saves {formatCurrency(extra500.interestSaved)} and {extra500.yearsSaved.toFixed(1)} years</li>
                <li>15-year loan saves {formatCurrency(fifteenYear.interestSaved)} (but requires {formatCurrencyFull(fifteenYear.extraMonthlyNeeded)} more/month)</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RepaymentStrategyView;
