import React from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';

const LifestyleFitView = ({ data }) => {
  const getFitColor = (level) => {
    if (level === 'comfortable') return '#22c55e';
    if (level === 'adequate') return '#3b82f6';
    if (level === 'tight') return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Lifestyle Fit Index</h2>
        <p className="detail-subtitle">Will homeownership change your quality of life?</p>
      </div>

      <div className="lifestyle-score">
        <div className="fit-gauge" style={{ '--fit-color': getFitColor(data.fitLevel) }}>
          <div className="gauge-value">{data.fitScore.toFixed(0)}%</div>
          <div className="gauge-label">Discretionary Income</div>
          <div className="gauge-level" style={{ color: getFitColor(data.fitLevel) }}>
            {data.fitLevel.toUpperCase()}
          </div>
        </div>
      </div>

      <div className="lifestyle-comparison">
        <div className="budget-column renter">
          <h3>As Renter</h3>
          <div className="budget-items">
            <div className="budget-item">
              <span>Housing</span>
              <span>{formatCurrency(data.currentBudget.housing)}</span>
            </div>
            <div className="budget-item">
              <span>Utilities</span>
              <span>{formatCurrency(data.currentBudget.utilities)}</span>
            </div>
            <div className="budget-item">
              <span>Food</span>
              <span>{formatCurrency(data.currentBudget.food)}</span>
            </div>
            <div className="budget-item">
              <span>Transportation</span>
              <span>{formatCurrency(data.currentBudget.transportation)}</span>
            </div>
            <div className="budget-item">
              <span>Entertainment</span>
              <span>{formatCurrency(data.currentBudget.entertainment)}</span>
            </div>
            <div className="budget-item">
              <span>Savings</span>
              <span>{formatCurrency(data.currentBudget.savings)}</span>
            </div>
            <div className="budget-item total">
              <span>Total Expenses</span>
              <span>{formatCurrency(data.currentBudget.total)}</span>
            </div>
          </div>
        </div>

        <div className="budget-arrow">{'→'}</div>

        <div className="budget-column homeowner">
          <h3>As Homeowner</h3>
          <div className="budget-items">
            <div className="budget-item">
              <span>Housing (PITI)</span>
              <span>{formatCurrency(data.homeownerBudget.housing)}</span>
            </div>
            <div className="budget-item">
              <span>Utilities</span>
              <span>{formatCurrency(data.homeownerBudget.utilities)}</span>
            </div>
            <div className="budget-item">
              <span>Maintenance Reserve</span>
              <span>{formatCurrency(data.homeownerBudget.maintenance)}</span>
            </div>
            <div className="budget-item">
              <span>Food</span>
              <span>{formatCurrency(data.homeownerBudget.food)}</span>
            </div>
            <div className="budget-item">
              <span>Entertainment</span>
              <span>{formatCurrency(data.homeownerBudget.entertainment)}</span>
            </div>
            <div className="budget-item">
              <span>Savings</span>
              <span>{formatCurrency(data.homeownerBudget.savings)}</span>
            </div>
            <div className="budget-item total">
              <span>Total Expenses</span>
              <span>{formatCurrency(data.homeownerBudget.total)}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="lifestyle-impact">
        <h3>Monthly Impact</h3>
        <div className="impact-summary">
          <div className="impact-stat">
            <span>Monthly Squeeze</span>
            <span style={{ color: data.monthlySqueeze > 0 ? '#ef4444' : '#22c55e' }}>
              {data.monthlySqueeze > 0 ? '+' : ''}{formatCurrency(data.monthlySqueeze)}
            </span>
          </div>
          <div className="impact-stat">
            <span>Discretionary Left</span>
            <span style={{ color: getFitColor(data.fitLevel) }}>{formatCurrency(data.discretionaryIncome)}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LifestyleFitView;
