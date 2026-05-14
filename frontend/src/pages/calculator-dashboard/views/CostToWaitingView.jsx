import React, { useState, useMemo } from 'react';
import { formatCurrency, formatCurrencyFull } from '../../../services/calculator/CalculatorService';

const CostToWaitingView = ({ data, onUpdateData }) => {
  const { homePrice: initialHomePrice, currentRent, interestRate: initialRate, downPaymentPct, savings, monthlyIncome } = data;

  const [waitMonths, setWaitMonths] = useState(12);
  const [homeAppreciation, setHomeAppreciation] = useState(data.homeAppreciationRate || 4.0);
  const [rateIncrease, setRateIncrease] = useState(data.rateIncreasePerYear || 0.5);
  const [rentIncrease, setRentIncrease] = useState(data.rentIncreaseRate || 3.0);

  function calcEquityBuilt(loan, rate, months) {
    const monthlyRate = (rate / 100) / 12;
    const payment = (loan * monthlyRate * Math.pow(1 + monthlyRate, 360)) / (Math.pow(1 + monthlyRate, 360) - 1);
    let balance = loan;
    let totalPrincipal = 0;
    for (let m = 0; m < months; m++) {
      const interest = balance * monthlyRate;
      const principal = payment - interest;
      totalPrincipal += principal;
      balance -= principal;
    }
    return totalPrincipal;
  }

  const calculations = useMemo(() => {
    const waitYears = waitMonths / 12;
    const futureHomePrice = initialHomePrice * Math.pow(1 + homeAppreciation / 100, waitYears);
    const homePriceIncrease = futureHomePrice - initialHomePrice;
    const futureRate = initialRate + (rateIncrease * waitYears);
    const currentDownPayment = initialHomePrice * (downPaymentPct / 100);
    const futureDownPayment = futureHomePrice * (downPaymentPct / 100);
    const downPaymentIncrease = futureDownPayment - currentDownPayment;
    const currentLoan = initialHomePrice - currentDownPayment;
    const futureLoan = futureHomePrice - futureDownPayment;

    const calcMonthlyPI = (loan, rate, years = 30) => {
      const monthlyRate = (rate / 100) / 12;
      const numPayments = years * 12;
      return (loan * monthlyRate * Math.pow(1 + monthlyRate, numPayments)) / (Math.pow(1 + monthlyRate, numPayments) - 1);
    };

    const currentPayment = calcMonthlyPI(currentLoan, initialRate);
    const futurePayment = calcMonthlyPI(futureLoan, futureRate);
    const monthlyPaymentIncrease = futurePayment - currentPayment;

    let totalRentPaid = 0;
    let monthlyRent = currentRent;
    for (let m = 0; m < waitMonths; m++) {
      totalRentPaid += monthlyRent;
      if (m > 0 && m % 12 === 0) monthlyRent *= (1 + rentIncrease / 100);
    }

    const currentTotalInterest = (currentPayment * 360) - currentLoan;
    const futureTotalInterest = (futurePayment * 360) - futureLoan;
    const interestIncrease = futureTotalInterest - currentTotalInterest;
    const equityBuiltIfBoughtNow = calcEquityBuilt(currentLoan, initialRate, waitMonths);
    const totalCostOfWaiting = downPaymentIncrease + totalRentPaid + interestIncrease;
    const monthlyCostOfWaiting = totalCostOfWaiting / waitMonths;

    return { waitMonths, waitYears, currentHomePrice: initialHomePrice, futureHomePrice, homePriceIncrease, currentRate: initialRate, futureRate, currentDownPayment, futureDownPayment, downPaymentIncrease, currentLoan, futureLoan, currentPayment, futurePayment, monthlyPaymentIncrease, totalRentPaid, currentTotalInterest, futureTotalInterest, interestIncrease, equityBuiltIfBoughtNow, totalCostOfWaiting, monthlyCostOfWaiting };
  }, [waitMonths, homeAppreciation, rateIncrease, rentIncrease, initialHomePrice, initialRate, downPaymentPct, currentRent]);

  const [activeTab, setActiveTab] = useState('settings');
  const tabs = [
    { id: 'settings', label: 'Settings', step: 1 },
    { id: 'compare', label: 'Compare', step: 2 },
    { id: 'breakdown', label: 'Cost Breakdown', step: 3 },
    { id: 'summary', label: 'Summary', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view cost-waiting-view">
      <div className="detail-header"><h2>Cost of Waiting</h2><p className="detail-subtitle">See what delaying your purchase could really cost you</p></div>

      <div className="process-tabs">
        {tabs.map((tab, idx) => (
          <button key={tab.id} className={`process-tab ${activeTab === tab.id ? 'active' : ''}`} onClick={() => setActiveTab(tab.id)}>
            <span className="tab-step">{tab.step}</span><span className="tab-label">{tab.label}</span>
            {idx < tabs.length - 1 && <span className="tab-arrow">{'→'}</span>}
          </button>
        ))}
      </div>

      <div className="tab-content">
        {activeTab === 'settings' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>Configure Your Scenario</h3><p>Adjust the assumptions to see how waiting affects you</p></div>
            <div className="waiting-inputs">
              <div className="input-section">
                <h4>How Long Would You Wait?</h4>
                <div className="wait-time-selector">
                  {[6, 12, 18, 24, 36].map(months => (
                    <button key={months} className={`wait-btn ${waitMonths === months ? 'active' : ''}`} onClick={() => setWaitMonths(months)}>
                      {months < 12 ? `${months} mo` : `${months / 12} yr${months > 12 ? 's' : ''}`}
                    </button>
                  ))}
                </div>
              </div>
              <div className="assumptions-grid">
                <div className="assumption-field"><label>Home Price Growth</label><div className="input-with-suffix small"><input type="number" step="0.5" value={homeAppreciation} onChange={(e) => setHomeAppreciation(parseFloat(e.target.value) || 0)} /><span className="suffix">%/yr</span></div></div>
                <div className="assumption-field"><label>Interest Rate Increase</label><div className="input-with-suffix small"><input type="number" step="0.25" value={rateIncrease} onChange={(e) => setRateIncrease(parseFloat(e.target.value) || 0)} /><span className="suffix">%/yr</span></div></div>
                <div className="assumption-field"><label>Rent Increase</label><div className="input-with-suffix small"><input type="number" step="0.5" value={rentIncrease} onChange={(e) => setRentIncrease(parseFloat(e.target.value) || 0)} /><span className="suffix">%/yr</span></div></div>
              </div>
            </div>
            <div className="cost-impact-hero">
              <div className="impact-label">Total Cost of Waiting {calculations.waitMonths} Months</div>
              <div className="impact-amount">{formatCurrency(calculations.totalCostOfWaiting)}</div>
              <div className="impact-monthly">That's {formatCurrency(calculations.monthlyCostOfWaiting)}/month you're losing</div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('compare')}>Compare Now vs Later {'→'}</button>
          </div>
        )}

        {activeTab === 'compare' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>Buy Now vs. Buy Later</h3><p>See the detailed comparison after {calculations.waitMonths} months</p></div>
            <div className="waiting-comparison">
              <div className="comparison-column buy-now">
                <div className="column-header">Buy Now</div>
                <div className="comparison-items">
                  <div className="comparison-item"><span className="item-label">Home Price</span><span className="item-value">{formatCurrency(calculations.currentHomePrice)}</span></div>
                  <div className="comparison-item"><span className="item-label">Interest Rate</span><span className="item-value">{calculations.currentRate.toFixed(3)}%</span></div>
                  <div className="comparison-item"><span className="item-label">Down Payment ({downPaymentPct}%)</span><span className="item-value">{formatCurrency(calculations.currentDownPayment)}</span></div>
                  <div className="comparison-item"><span className="item-label">Loan Amount</span><span className="item-value">{formatCurrency(calculations.currentLoan)}</span></div>
                  <div className="comparison-item highlight"><span className="item-label">Monthly P&I</span><span className="item-value">{formatCurrencyFull(calculations.currentPayment)}</span></div>
                  <div className="comparison-item"><span className="item-label">Total Interest (30yr)</span><span className="item-value">{formatCurrency(calculations.currentTotalInterest)}</span></div>
                </div>
              </div>
              <div className="comparison-vs"><div className="vs-circle">VS</div><div className="vs-time">After {calculations.waitMonths} months</div></div>
              <div className="comparison-column buy-later">
                <div className="column-header">Buy Later</div>
                <div className="comparison-items">
                  <div className="comparison-item"><span className="item-label">Home Price</span><span className="item-value negative">{formatCurrency(calculations.futureHomePrice)}<span className="change">+{formatCurrency(calculations.homePriceIncrease)}</span></span></div>
                  <div className="comparison-item"><span className="item-label">Interest Rate</span><span className="item-value negative">{calculations.futureRate.toFixed(3)}%<span className="change">+{(calculations.futureRate - calculations.currentRate).toFixed(3)}%</span></span></div>
                  <div className="comparison-item"><span className="item-label">Down Payment ({downPaymentPct}%)</span><span className="item-value negative">{formatCurrency(calculations.futureDownPayment)}<span className="change">+{formatCurrency(calculations.downPaymentIncrease)}</span></span></div>
                  <div className="comparison-item"><span className="item-label">Loan Amount</span><span className="item-value">{formatCurrency(calculations.futureLoan)}</span></div>
                  <div className="comparison-item highlight"><span className="item-label">Monthly P&I</span><span className="item-value negative">{formatCurrencyFull(calculations.futurePayment)}<span className="change">+{formatCurrencyFull(calculations.monthlyPaymentIncrease)}</span></span></div>
                  <div className="comparison-item"><span className="item-label">Total Interest (30yr)</span><span className="item-value negative">{formatCurrency(calculations.futureTotalInterest)}<span className="change">+{formatCurrency(calculations.interestIncrease)}</span></span></div>
                </div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('breakdown')}>See Cost Breakdown {'→'}</button>
          </div>
        )}

        {activeTab === 'breakdown' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>Where the Cost Comes From</h3><p>Breaking down the total cost of waiting</p></div>
            <div className="cost-breakdown">
              <div className="breakdown-bars">
                <div className="breakdown-item">
                  <div className="breakdown-header"><span className="breakdown-label">Extra Down Payment Needed</span><span className="breakdown-value">{formatCurrency(calculations.downPaymentIncrease)}</span></div>
                  <div className="breakdown-bar"><div className="breakdown-fill rent" style={{ width: `${Math.min(100, (calculations.downPaymentIncrease / calculations.totalCostOfWaiting) * 100)}%` }} /></div>
                </div>
                <div className="breakdown-item">
                  <div className="breakdown-header"><span className="breakdown-label">Rent Paid While Waiting</span><span className="breakdown-value">{formatCurrency(calculations.totalRentPaid)}</span></div>
                  <div className="breakdown-bar"><div className="breakdown-fill interest" style={{ width: `${Math.min(100, (calculations.totalRentPaid / calculations.totalCostOfWaiting) * 100)}%` }} /></div>
                </div>
                <div className="breakdown-item">
                  <div className="breakdown-header"><span className="breakdown-label">Additional Lifetime Interest</span><span className="breakdown-value">{formatCurrency(calculations.interestIncrease)}</span></div>
                  <div className="breakdown-bar"><div className="breakdown-fill extra" style={{ width: `${Math.min(100, (calculations.interestIncrease / calculations.totalCostOfWaiting) * 100)}%` }} /></div>
                </div>
              </div>
            </div>
            <div className="lost-opportunity">
              <h4>Plus: Opportunity Cost</h4>
              <p>If you bought today, you'd build <strong>{formatCurrency(calculations.equityBuiltIfBoughtNow)}</strong> in equity over the next {calculations.waitMonths} months through principal payments alone — not counting any home appreciation.</p>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('summary')}>See Summary {'→'}</button>
          </div>
        )}

        {activeTab === 'summary' && (
          <div className="tab-panel">
            <div className="panel-header"><h3>The Bottom Line</h3><p>Summary of what waiting will cost you</p></div>
            <div className="cost-impact-hero">
              <div className="impact-label">Total Cost of Waiting {calculations.waitMonths} Months</div>
              <div className="impact-amount">{formatCurrency(calculations.totalCostOfWaiting)}</div>
              <div className="impact-monthly">That's {formatCurrency(calculations.monthlyCostOfWaiting)}/month you're losing</div>
            </div>
            <div className="waiting-verdict">
              <div className="verdict-title">Key Takeaways</div>
              <ul className="verdict-list">
                <li>Every month you wait costs approximately <strong>{formatCurrency(calculations.monthlyCostOfWaiting)}</strong></li>
                <li>You'll need <strong>{formatCurrency(calculations.downPaymentIncrease)} more</strong> for your down payment</li>
                <li>Your monthly payment will be <strong>{formatCurrencyFull(calculations.monthlyPaymentIncrease)} higher</strong></li>
                <li>You'll pay <strong>{formatCurrency(calculations.interestIncrease)}</strong> more in lifetime interest</li>
              </ul>
              {calculations.totalCostOfWaiting > savings * 0.5 && (
                <div className="verdict-warning">The cost of waiting {calculations.waitMonths} months exceeds 50% of your current savings.</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default CostToWaitingView;
