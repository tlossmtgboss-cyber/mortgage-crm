import React from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';

const StressTestView = ({ data }) => {
  const getStatusColor = (survivable) => survivable ? '#22c55e' : '#ef4444';

  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Life Happens Stress Test</h2>
        <p className="detail-subtitle">Can you survive financial surprises?</p>
      </div>

      <div className="stress-baseline">
        <h3>Your Baseline</h3>
        <div className="baseline-stats">
          <div className="baseline-stat">
            <span>Monthly Payment</span>
            <span>{formatCurrency(data.baseline.piti)}</span>
          </div>
          <div className="baseline-stat">
            <span>Current DTI</span>
            <span>{data.baseline.dti.toFixed(1)}%</span>
          </div>
          <div className="baseline-stat">
            <span>Monthly Income</span>
            <span>{formatCurrency(data.monthlyIncome)}</span>
          </div>
        </div>
      </div>

      <div className="stress-scenarios">
        <h3>Stress Scenarios</h3>
        <div className="stress-table">
          <div className="stress-header">
            <span>Scenario</span>
            <span>New Payment</span>
            <span>New DTI</span>
            <span>Status</span>
          </div>
          {data.scenarios.map((scenario, idx) => (
            <div key={idx} className="stress-row">
              <div className="stress-scenario">
                <span className="scenario-name">{scenario.name}</span>
                <span className="scenario-trigger">{scenario.trigger}</span>
              </div>
              <span className="stress-payment">
                {formatCurrency(scenario.newPayment)}
                {scenario.impact > 0 && <span className="payment-change">+{formatCurrency(scenario.impact)}</span>}
              </span>
              <span className="stress-dti">{scenario.newDti.toFixed(1)}%</span>
              <span className="stress-status" style={{ color: getStatusColor(scenario.survivable) }}>
                {scenario.survivable ? 'PASS' : 'FAIL'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="stress-score">
        <div className="score-circle" style={{
          background: `conic-gradient(${data.resilienceScore >= 80 ? '#22c55e' : data.resilienceScore >= 60 ? '#f59e0b' : '#ef4444'} ${data.resilienceScore * 3.6}deg, #e2e8f0 0deg)`
        }}>
          <div className="score-inner">
            <span className="score-value">{data.passCount}/{data.totalScenarios}</span>
            <span className="score-label">Tests Passed</span>
          </div>
        </div>
        <div className="score-assessment">
          <h4>Resilience Score: {data.resilienceScore.toFixed(0)}%</h4>
          <p>
            {data.resilienceScore >= 80 && 'Excellent! Your finances can handle most life surprises.'}
            {data.resilienceScore >= 60 && data.resilienceScore < 80 && 'Good resilience, but some scenarios are tight.'}
            {data.resilienceScore < 60 && 'Consider building more financial cushion before buying.'}
          </p>
        </div>
      </div>
    </div>
  );
};

export default StressTestView;
