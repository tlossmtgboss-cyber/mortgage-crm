import React, { useState } from 'react';
import { formatCurrency, formatCurrencyFull } from '../../../services/calculator/CalculatorService';

const RentVsBuyView = ({ data }) => {
  const { taxBenefits, netWorthProjection } = data;
  const year5Renter = netWorthProjection.renterPath[4];
  const year5Buyer = netWorthProjection.buyerPath[4];
  const wealthDifference = year5Buyer.netWorth - year5Renter.netWorth;
  const [activeTab, setActiveTab] = useState('overview');

  const tabs = [
    { id: 'overview', label: 'Monthly Costs', step: 1 },
    { id: 'taxes', label: 'Tax Benefits', step: 2 },
    { id: 'networth', label: 'Net Worth', step: 3 },
    { id: 'timeline', label: 'Timeline', step: 4 },
    { id: 'verdict', label: 'Verdict', step: 5 },
  ];

  return (
    <div className="calculator-detail tabbed-view">
      <div className="detail-header">
        <h2>Rent vs. Buy: True Cost Analysis</h2>
        <p className="detail-subtitle">Including tax benefits, net worth building, and true cost of ownership</p>
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
        {activeTab === 'overview' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>Monthly Payment Comparison</h3><p>See the true cost of renting vs. buying</p></div>
            <div className="cost-comparison-grid">
              <div className="cost-column rent">
                <div className="cost-column-header">Renting</div>
                <div className="cost-row main"><span>Monthly Rent</span><span>{formatCurrencyFull(data.currentRent)}</span></div>
                <div className="cost-row sub"><span>Wealth Building</span><span className="negative">$0</span></div>
                <div className="cost-row sub"><span>Tax Benefits</span><span>$0</span></div>
                <div className="cost-row total"><span>True Monthly Cost</span><span className="negative">{formatCurrencyFull(data.currentRent)}</span></div>
              </div>
              <div className="cost-column buy">
                <div className="cost-column-header">Buying</div>
                <div className="cost-row main"><span>PITI Payment</span><span>{formatCurrencyFull(data.mortgagePayment)}</span></div>
                <div className="cost-row sub positive-row"><span>Principal (Savings)</span><span className="positive">-{formatCurrencyFull(data.principalBuildup)}</span></div>
                <div className="cost-row sub positive-row"><span>Tax Savings</span><span className="positive">-{formatCurrencyFull(taxBenefits.monthlyTaxSavings)}</span></div>
                <div className="cost-row total"><span>True Monthly Cost</span><span className="highlight">{formatCurrencyFull(data.trueMonthlyCost)}</span></div>
              </div>
            </div>
            <div className="true-cost-insight">
              <strong>True Cost Difference:</strong> After accounting for equity building and tax benefits,
              your effective housing cost is only <strong>{formatCurrencyFull(data.trueMonthlyCost - data.currentRent)}</strong> more per month!
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('taxes')}>See Tax Benefits {'→'}</button>
          </div>
        )}

        {activeTab === 'taxes' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>Tax Benefits Breakdown (Year 1)</h3><p>How homeownership reduces your tax burden</p></div>
            <div className="tax-grid">
              <div className="tax-item"><div className="tax-label">Mortgage Interest</div><div className="tax-value">{formatCurrency(taxBenefits.annualInterest)}</div></div>
              <div className="tax-item"><div className="tax-label">Property Tax</div><div className="tax-value">{formatCurrency(taxBenefits.annualPropertyTax)}</div></div>
              <div className="tax-item"><div className="tax-label">Total Deductions</div><div className="tax-value">{formatCurrency(taxBenefits.totalDeductions)}</div></div>
              <div className="tax-item highlight"><div className="tax-label">Annual Tax Savings</div><div className="tax-value positive">{formatCurrency(taxBenefits.annualTaxSavings)}</div></div>
            </div>
            <div className="tax-note">
              {taxBenefits.itemizingMakesSense ? (
                <>Itemizing deductions saves you <strong>{formatCurrency(taxBenefits.annualTaxSavings)}/year</strong> over standard deduction</>
              ) : (
                <>Note: Standard deduction ({formatCurrency(taxBenefits.standardDeduction)}) may be better — consult a tax professional</>
              )}
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('networth')}>See Net Worth Impact {'→'}</button>
          </div>
        )}

        {activeTab === 'networth' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>5-Year Net Worth Projection</h3><p>Compare your wealth building potential</p></div>
            <div className="net-worth-comparison">
              <div className="net-worth-card renter">
                <div className="nw-header">If You Continue Renting</div>
                <div className="nw-amount">{formatCurrency(year5Renter.netWorth)}</div>
                <div className="nw-breakdown">
                  <div className="nw-item"><span>Starting savings invested</span><span>+{formatCurrency(data.downPayment + 9000)}</span></div>
                  <div className="nw-item negative"><span>Rent paid (gone forever)</span><span>-{formatCurrency(data.fiveYearRent)}</span></div>
                </div>
              </div>
              <div className="net-worth-card buyer highlighted">
                <div className="nw-header">If You Buy</div>
                <div className="nw-amount">{formatCurrency(year5Buyer.netWorth)}</div>
                <div className="nw-breakdown">
                  <div className="nw-item"><span>Home Value (Year 5)</span><span>{formatCurrency(year5Buyer.homeValue)}</span></div>
                  <div className="nw-item"><span>Remaining Mortgage</span><span>-{formatCurrency(year5Buyer.remainingLoan)}</span></div>
                  <div className="nw-item positive"><span>Home Equity Built</span><span className="positive">{formatCurrency(year5Buyer.homeEquity)}</span></div>
                </div>
              </div>
            </div>
            <div className="wealth-difference">
              <div className="wealth-diff-content">
                <div className="wealth-diff-label">Wealth Advantage of Buying (5 Years)</div>
                <div className="wealth-diff-amount">+{formatCurrency(wealthDifference)}</div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('timeline')}>See Year-by-Year {'→'}</button>
          </div>
        )}

        {activeTab === 'timeline' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>Year-by-Year Net Worth</h3><p>Track how your wealth grows over time</p></div>
            <div className="year-table">
              <div className="year-table-header"><div>Year</div><div>Renter Net Worth</div><div>Buyer Net Worth</div><div>Buyer Advantage</div></div>
              {netWorthProjection.renterPath.map((renter, idx) => {
                const buyer = netWorthProjection.buyerPath[idx];
                const advantage = buyer.netWorth - renter.netWorth;
                return (
                  <div key={renter.year} className="year-table-row">
                    <div>Year {renter.year}</div>
                    <div>{formatCurrency(renter.netWorth)}</div>
                    <div>{formatCurrency(buyer.netWorth)}</div>
                    <div className={advantage > 0 ? 'positive' : 'negative'}>{advantage > 0 ? '+' : ''}{formatCurrency(advantage)}</div>
                  </div>
                );
              })}
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('verdict')}>See Final Verdict {'→'}</button>
          </div>
        )}

        {activeTab === 'verdict' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>The Verdict</h3><p>Our recommendation based on your analysis</p></div>
            <div className="verdict-box">
              <div className="verdict-content">
                <div className="verdict-title">Verdict: Buying Builds Significantly More Wealth</div>
                <ul className="verdict-reasons">
                  <li>True monthly cost is only {formatCurrencyFull(data.trueMonthlyCost - data.currentRent)} more than rent after tax benefits</li>
                  <li>You'll have <strong>{formatCurrency(wealthDifference)}</strong> more wealth in 5 years</li>
                  <li>Tax deductions save you <strong>{formatCurrency(taxBenefits.annualTaxSavings)}/year</strong></li>
                  <li>Your payment is locked while rent increases 3%+ annually</li>
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RentVsBuyView;
