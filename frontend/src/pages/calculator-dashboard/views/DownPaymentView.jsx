import React from 'react';
import { formatCurrency, formatCurrencyFull } from '../../../services/calculator/CalculatorService';

const DownPaymentView = ({ data, profile }) => (
  <div className="calculator-detail">
    <div className="detail-header">
      <h2>Down Payment Options</h2>
      <p className="detail-subtitle">
        For a <strong>{formatCurrency(data.homePrice)}</strong> home
      </p>
    </div>

    <div className="savings-display">
      <div className="savings-label">Your Available Savings</div>
      <div className="savings-amount">{formatCurrency(data.savings)}</div>
    </div>

    <div className="scenarios-table">
      <div className="table-header">
        <div>Scenario</div>
        <div>Down Payment</div>
        <div>Monthly Payment</div>
        <div>PMI</div>
        <div>Cash Left</div>
      </div>
      {data.scenarios.map((scenario, idx) => (
        <div
          key={scenario.label}
          className={`table-row ${idx === 0 ? 'recommended' : ''} ${scenario.cashRemaining < 0 ? 'warning' : ''}`}
        >
          <div className="scenario-name">
            {scenario.label}
            {idx === 0 && <span className="rec-badge">Best for You</span>}
          </div>
          <div>{formatCurrency(scenario.downPayment)}</div>
          <div>{formatCurrencyFull(scenario.piti.total)}</div>
          <div>{formatCurrencyFull(scenario.piti.pmi)}/mo</div>
          <div className={scenario.cashRemaining < 0 ? 'negative' : scenario.cashRemaining < 5000 ? 'tight' : 'good'}>
            {formatCurrency(scenario.cashRemaining)}
            {scenario.cashRemaining < 0 && <span className="status-tag danger">SHORT</span>}
            {scenario.cashRemaining >= 0 && scenario.cashRemaining < 5000 && <span className="status-tag warning">TIGHT</span>}
            {scenario.cashRemaining >= 5000 && <span className="status-tag success">OK</span>}
          </div>
        </div>
      ))}
    </div>

    <div className="pmi-info">
      <h4>About PMI (Private Mortgage Insurance)</h4>
      <ul>
        <li>Required when down payment is less than 20%</li>
        <li>Automatically cancels when you reach 78% LTV</li>
        <li>Can request removal at 80% LTV with good payment history</li>
      </ul>
      <div className="pmi-timeline">
        {data.scenarios.filter(s => s.piti.pmi > 0).map((s) => (
          <div key={s.label} className="pmi-item">
            <strong>{s.label}:</strong> PMI of {formatCurrencyFull(s.piti.pmi)}/mo
            for ~{(s.pmiMonths / 12).toFixed(1)} years
          </div>
        ))}
      </div>
    </div>
  </div>
);

export default DownPaymentView;
