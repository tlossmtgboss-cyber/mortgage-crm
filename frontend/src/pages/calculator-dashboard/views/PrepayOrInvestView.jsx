import React, { useState, useMemo } from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';

const PrepayOrInvestView = ({ data }) => {
  const {
    loanAmount: initialLoanAmount,
    interestRate: initialRate,
    termYears: initialTerm,
    monthlyExtraCash: initialExtra,
    estimatedMarketReturn: initialReturn,
    currentEquity,
    homePrice,
  } = data;

  // Local state for interactive inputs
  const [mortgageBalance, setMortgageBalance] = useState(initialLoanAmount);
  const [mortgageRate, setMortgageRate] = useState(initialRate);
  const [remainingYears, setRemainingYears] = useState(initialTerm);
  const [monthlyExtra, setMonthlyExtra] = useState(initialExtra);
  const [marketReturn, setMarketReturn] = useState(initialReturn);
  const [showAnalysis, setShowAnalysis] = useState(false);

  // Calculate both strategies
  const results = useMemo(() => {
    const monthlyRate = mortgageRate / 100 / 12;
    const totalMonths = remainingYears * 12;

    // Calculate standard monthly payment
    const standardPayment = (mortgageBalance * monthlyRate * Math.pow(1 + monthlyRate, totalMonths)) /
      (Math.pow(1 + monthlyRate, totalMonths) - 1);

    // Strategy 1: Prepay mortgage
    let prepayBalance = mortgageBalance;
    let prepayMonths = 0;
    let prepayTotalInterest = 0;
    let prepayCash = 0;

    while (prepayBalance > 0 && prepayMonths < 360) {
      const interestPayment = prepayBalance * monthlyRate;
      const principalPayment = Math.min(standardPayment - interestPayment + monthlyExtra, prepayBalance);
      prepayTotalInterest += interestPayment;
      prepayBalance -= principalPayment;
      prepayMonths++;

      // Once mortgage is paid off, invest the full amount
      if (prepayBalance <= 0) {
        const remainingMonths = totalMonths - prepayMonths;
        const monthlyInvestment = standardPayment + monthlyExtra;
        // Future value of monthly investments
        const monthlyMarketRate = marketReturn / 100 / 12;
        prepayCash = monthlyInvestment * ((Math.pow(1 + monthlyMarketRate, remainingMonths) - 1) / monthlyMarketRate);
      }
    }

    // Strategy 2: Invest extra in market
    let investBalance = mortgageBalance;
    let investTotalInterest = 0;
    let investmentValue = 0;
    const monthlyMarketRate = marketReturn / 100 / 12;

    for (let m = 0; m < totalMonths && investBalance > 0; m++) {
      const interestPayment = investBalance * monthlyMarketRate;
      const principalPayment = Math.min(standardPayment - investBalance * monthlyRate, investBalance);
      investTotalInterest += investBalance * monthlyRate;
      investBalance = Math.max(0, investBalance - principalPayment);

      // Monthly investment grows
      investmentValue = (investmentValue + monthlyExtra) * (1 + monthlyMarketRate);
    }

    // Calculate final positions at end of original term
    const prepayEquity = homePrice; // Own home outright
    const prepayTotalWealth = prepayEquity + prepayCash;
    const prepayMortgageFreeDate = prepayMonths;

    const investEquity = homePrice - investBalance; // May still have mortgage
    const investTotalWealth = investEquity + investmentValue;
    const investMortgageFreeDate = totalMonths;

    // Determine winner
    const investingWinsBy = investTotalWealth - prepayTotalWealth;
    const winner = investingWinsBy > 0 ? 'invest' : 'prepay';

    // Interest saved by prepaying
    const standardTotalInterest = (standardPayment * totalMonths) - mortgageBalance;
    const interestSaved = standardTotalInterest - prepayTotalInterest;

    // Year-by-year breakdown for chart
    const yearlyBreakdown = [];
    let pBalance = mortgageBalance;
    let pCash = 0;
    let iBalance = mortgageBalance;
    let iCash = 0;
    let pPaidOff = false;

    for (let year = 1; year <= remainingYears; year++) {
      for (let m = 0; m < 12; m++) {
        // Prepay strategy
        if (pBalance > 0) {
          const pInterest = pBalance * monthlyRate;
          const pPrincipal = Math.min(standardPayment - pInterest + monthlyExtra, pBalance);
          pBalance = Math.max(0, pBalance - pPrincipal);
        } else {
          pCash = (pCash + standardPayment + monthlyExtra) * (1 + monthlyMarketRate);
          pPaidOff = true;
        }

        // Invest strategy
        if (iBalance > 0) {
          const iInterest = iBalance * monthlyRate;
          const iPrincipal = standardPayment - iInterest;
          iBalance = Math.max(0, iBalance - iPrincipal);
        }
        iCash = (iCash + monthlyExtra) * (1 + monthlyMarketRate);
      }

      yearlyBreakdown.push({
        year,
        prepay: {
          equity: homePrice - pBalance,
          cash: pCash,
          total: (homePrice - pBalance) + pCash,
          mortgagePaidOff: pPaidOff,
        },
        invest: {
          equity: homePrice - iBalance,
          cash: iCash,
          total: (homePrice - iBalance) + iCash,
          mortgagePaidOff: iBalance <= 0,
        },
      });
    }

    return {
      standardPayment,
      prepay: {
        monthsToPayoff: prepayMonths,
        yearsToPayoff: (prepayMonths / 12).toFixed(1),
        totalInterest: prepayTotalInterest,
        interestSaved,
        finalCash: prepayCash,
        finalEquity: prepayEquity,
        totalWealth: prepayTotalWealth,
      },
      invest: {
        monthsToPayoff: totalMonths,
        yearsToPayoff: remainingYears,
        totalInterest: investTotalInterest,
        finalCash: investmentValue,
        finalEquity: investEquity,
        totalWealth: investTotalWealth,
      },
      winner,
      difference: Math.abs(investingWinsBy),
      investingWinsBy,
      yearlyBreakdown,
    };
  }, [mortgageBalance, mortgageRate, remainingYears, monthlyExtra, marketReturn, homePrice]);

  const [activeTab, setActiveTab] = useState('settings');

  const tabs = [
    { id: 'settings', label: 'Settings', step: 1 },
    { id: 'compare', label: 'Compare Strategies', step: 2 },
    { id: 'timeline', label: 'Timeline', step: 3 },
    { id: 'analysis', label: 'Analysis', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view prepay-invest-view">
      <div className="detail-header">
        <h2>Prepay or Invest?</h2>
        <p className="detail-subtitle">
          Compare guaranteed debt reduction vs. potential market growth
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
        {activeTab === 'settings' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Configure Your Scenario</h3>
              <p>Adjust your mortgage and investment assumptions</p>
            </div>
            <div className="prepay-inputs">
              <div className="inputs-row">
                <div className="input-group">
                  <label>Mortgage Balance</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input type="number" value={mortgageBalance} onChange={(e) => setMortgageBalance(parseFloat(e.target.value) || 0)} />
                  </div>
                </div>
                <div className="input-group">
                  <label>Mortgage Rate</label>
                  <div className="input-with-suffix">
                    <input type="number" step="0.125" value={mortgageRate} onChange={(e) => setMortgageRate(parseFloat(e.target.value) || 0)} />
                    <span className="suffix">%</span>
                  </div>
                </div>
                <div className="input-group">
                  <label>Remaining Years</label>
                  <div className="input-with-suffix">
                    <input type="number" value={remainingYears} onChange={(e) => setRemainingYears(parseInt(e.target.value) || 1)} />
                    <span className="suffix">yrs</span>
                  </div>
                </div>
              </div>
              <div className="inputs-row">
                <div className="input-group">
                  <label>Monthly Extra Cash</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input type="number" value={monthlyExtra} onChange={(e) => setMonthlyExtra(parseFloat(e.target.value) || 0)} />
                  </div>
                </div>
                <div className="input-group">
                  <label>Estimated After-Tax Return</label>
                  <div className="input-with-suffix">
                    <input type="number" step="0.5" value={marketReturn} onChange={(e) => setMarketReturn(parseFloat(e.target.value) || 0)} />
                    <span className="suffix">%</span>
                  </div>
                </div>
              </div>
            </div>
            <div className={`winner-banner ${results.winner}`}>
              <div className="winner-label">{results.winner === 'invest' ? 'Investing Wins By' : 'Prepaying Wins By'}</div>
              <div className="winner-amount">{results.investingWinsBy >= 0 ? '+' : ''}{formatCurrency(results.difference)}</div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('compare')}>Compare Strategies {'→'}</button>
          </div>
        )}

        {activeTab === 'compare' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Strategy Comparison</h3>
              <p>Compare prepaying mortgage vs investing in the market</p>
            </div>
            <div className="strategy-comparison">
              <div className={`strategy-card ${results.winner === 'prepay' ? 'winner' : ''}`}>
                <div className="strategy-header">
                  <span className="strategy-name">Prepay Strategy</span>
                  {results.winner === 'prepay' && <span className="winner-badge">Winner</span>}
                </div>
                <div className="strategy-subtitle">Put extra toward mortgage</div>
                <div className="strategy-metrics">
                  <div className="metric"><span className="metric-label">Mortgage-Free In</span><span className="metric-value highlight">{results.prepay.yearsToPayoff} years</span></div>
                  <div className="metric"><span className="metric-label">Interest Saved</span><span className="metric-value positive">{formatCurrency(results.prepay.interestSaved)}</span></div>
                  <div className="metric"><span className="metric-label">Final Home Equity</span><span className="metric-value">{formatCurrency(results.prepay.finalEquity)}</span></div>
                  <div className="metric"><span className="metric-label">Cash/Investments</span><span className="metric-value">{formatCurrency(results.prepay.finalCash)}</span></div>
                  <div className="metric total"><span className="metric-label">Total Wealth</span><span className="metric-value">{formatCurrency(results.prepay.totalWealth)}</span></div>
                </div>
              </div>
              <div className={`strategy-card ${results.winner === 'invest' ? 'winner' : ''}`}>
                <div className="strategy-header">
                  <span className="strategy-name">Invest Strategy</span>
                  {results.winner === 'invest' && <span className="winner-badge">Winner</span>}
                </div>
                <div className="strategy-subtitle">Invest extra in the market</div>
                <div className="strategy-metrics">
                  <div className="metric"><span className="metric-label">Mortgage-Free In</span><span className="metric-value">{results.invest.yearsToPayoff} years</span></div>
                  <div className="metric"><span className="metric-label">Investment Growth</span><span className="metric-value positive">{formatCurrency(results.invest.finalCash)}</span></div>
                  <div className="metric"><span className="metric-label">Final Home Equity</span><span className="metric-value">{formatCurrency(results.invest.finalEquity)}</span></div>
                  <div className="metric"><span className="metric-label">Cash/Investments</span><span className="metric-value">{formatCurrency(results.invest.finalCash)}</span></div>
                  <div className="metric total"><span className="metric-label">Total Wealth</span><span className="metric-value">{formatCurrency(results.invest.totalWealth)}</span></div>
                </div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('timeline')}>See Timeline {'→'}</button>
          </div>
        )}

        {activeTab === 'timeline' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Wealth Accumulation Timeline</h3>
              <p>Track how your wealth grows over time with each strategy</p>
            </div>
            <div className="yearly-breakdown">
              <div className="breakdown-table-wrapper">
                <table className="breakdown-table">
                  <thead>
                    <tr><th>Year</th><th>Prepay Total</th><th>Invest Total</th><th>Difference</th></tr>
                  </thead>
                  <tbody>
                    {results.yearlyBreakdown.filter((_, i) => i % 5 === 4 || i === 0 || i === results.yearlyBreakdown.length - 1).map(row => (
                      <tr key={row.year}>
                        <td>Year {row.year}</td>
                        <td>{formatCurrency(row.prepay.total)}{row.prepay.mortgagePaidOff && <span className="paid-off-badge">Paid Off</span>}</td>
                        <td>{formatCurrency(row.invest.total)}</td>
                        <td className={row.invest.total > row.prepay.total ? 'positive' : 'negative'}>
                          {row.invest.total > row.prepay.total ? '+' : ''}{formatCurrency(row.invest.total - row.prepay.total)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('analysis')}>See Analysis {'→'}</button>
          </div>
        )}

        {activeTab === 'analysis' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>AI Underwriter Analysis</h3>
              <p>Detailed analysis and recommendation</p>
            </div>
            <div className="ai-analysis-content">
              <div className="analysis-body">
                <p>
                  <strong>Summary:</strong> With a {mortgageRate}% mortgage rate and {marketReturn}% expected market return,
                  {results.winner === 'invest'
                    ? ` investing wins by ${formatCurrency(results.difference)} over the life of the loan.`
                    : ` prepaying wins by ${formatCurrency(results.difference)} over the life of the loan.`
                  }
                </p>
                <p>
                  <strong>The Math:</strong> Your mortgage interest rate of {mortgageRate}% represents a guaranteed
                  "return" when you prepay. When your mortgage rate is {mortgageRate < marketReturn ? 'lower' : 'higher'} than expected market returns,
                  {mortgageRate < marketReturn ? ' mathematically, investing tends to come out ahead.' : ' mathematically, prepaying tends to be the better choice.'}
                </p>
                <div className="risk-considerations">
                  <h5>Risk Considerations:</h5>
                  <ul>
                    <li>Prepaying provides a <em>guaranteed</em> return equal to your mortgage rate</li>
                    <li>Market returns are <em>variable</em> and could be higher or lower than {marketReturn}%</li>
                    <li>Prepaying builds equity faster, providing financial security</li>
                    <li>Investing maintains liquidity (you can access the funds if needed)</li>
                  </ul>
                </div>
                <p>
                  <strong>Recommendation:</strong>
                  {results.winner === 'invest' && results.difference > 50000
                    ? ' Given the significant difference, investing likely makes sense if you can handle market volatility.'
                    : results.winner === 'prepay' && results.difference > 50000
                    ? ' Given the significant difference, prepaying your mortgage is likely the better choice.'
                    : ' The strategies are relatively close. Consider your risk tolerance and whether you value the peace of mind of being debt-free.'
                  }
                </p>
              </div>
            </div>
            <div className="prepay-verdict">
              <strong>Key Insight:</strong> The breakeven point is when your mortgage rate equals your after-tax investment return.
              At {mortgageRate}% mortgage rate and {marketReturn}% expected return,
              {mortgageRate < marketReturn
                ? ` the ${(marketReturn - mortgageRate).toFixed(2)}% spread favors investing.`
                : mortgageRate > marketReturn
                ? ` the ${(mortgageRate - marketReturn).toFixed(2)}% spread favors prepaying.`
                : ' the rates are equal — choose based on your preference for guaranteed vs. potential returns.'
              }
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default PrepayOrInvestView;
