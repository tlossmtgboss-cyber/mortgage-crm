import React from 'react';
import { Icon } from '../application-shared';

/**
 * GoalsStage - Refinance-specific: refi type, cash-out amount, purpose.
 * Shows VA streamline / FHA streamline options when applicable.
 */
export default function GoalsStage({
  declarations,
  propertyData,
  goalsData,
  setGoalsData,
  handleGoalsFieldChange,
  goToPrevStage,
  goToNextStage,
}) {
  const isVeteran = declarations.veteran === 'yes' || declarations.veteran === 'active';
  const currentLoanIsVA = declarations.current_loan_type === 'va';
  const currentLoanIsFHA = declarations.current_loan_type === 'fha';

  // Calculate potential cash out
  const equity = (parseFloat(propertyData.homeValue) || 0) - (parseFloat(propertyData.mortgageBalance) || 0);
  const maxCashOut = Math.max(0, equity * 0.8); // Assume 80% LTV max

  return (
    <div className="stage-content">
      <div className="stage-header">
        <h2>Your Refinance Goals</h2>
        <p>Let's find the best option for you</p>
      </div>

      {/* Preliminary Disclaimer */}
      <div className="preliminary-disclaimer" style={{
        background: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)',
        border: '1px solid #f59e0b',
        borderRadius: '12px',
        padding: '16px 20px',
        marginBottom: '24px',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '12px',
      }}>
        <div style={{ color: '#d97706', marginTop: '2px' }}>
          <Icon name="info" size={20} />
        </div>
        <div>
          <p style={{ fontWeight: '600', color: '#92400e', margin: '0 0 4px 0', fontSize: '15px' }}>
            Preliminary Estimates
          </p>
          <p style={{ color: '#92400e', margin: 0, fontSize: '14px', lineHeight: '1.5' }}>
            The numbers shown below are estimates based on current market conditions and the information you've provided.
            Your loan officer will review these details with you and provide personalized, accurate figures based on your specific situation.
          </p>
        </div>
      </div>

      {/* Refinance Type Selection */}
      <div className="form-card">
        <h3>What type of refinance?</h3>
        <div className="income-cards">
          <div className={`income-card ${goalsData.refiType === 'rate_term' ? 'selected' : ''}`} onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'rate_term' }))}>
            <span className="card-icon"><Icon name="trendDown" size={28} /></span>
            <span className="card-label">Rate & Term</span>
            <span className="card-desc">Lower rate or change term</span>
          </div>
          <div className={`income-card ${goalsData.refiType === 'cash_out' ? 'selected' : ''}`} onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'cash_out' }))}>
            <span className="card-icon"><Icon name="money" size={28} /></span>
            <span className="card-label">Cash-Out</span>
            <span className="card-desc">Get cash from equity</span>
          </div>
          {(isVeteran || currentLoanIsVA) && (
            <div className={`income-card ${goalsData.refiType === 'va_irrrl' ? 'selected' : ''}`} onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'va_irrrl' }))}>
              <span className="card-icon"><Icon name="medal" size={28} /></span>
              <span className="card-label">VA Streamline</span>
              <span className="card-desc">Fast, limited docs</span>
            </div>
          )}
          {currentLoanIsFHA && (
            <div className={`income-card ${goalsData.refiType === 'fha_streamline' ? 'selected' : ''}`} onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'fha_streamline' }))}>
              <span className="card-icon"><Icon name="government" size={28} /></span>
              <span className="card-label">FHA Streamline</span>
              <span className="card-desc">No appraisal needed</span>
            </div>
          )}
        </div>
      </div>

      {/* Cash-Out Amount */}
      {goalsData.refiType === 'cash_out' && (
        <div className="form-card">
          <h3><Icon name="dollarSign" size={20} /> Cash-Out Amount</h3>
          <p className="section-hint">
            Based on your equity, you may be able to access up to <strong>${maxCashOut.toLocaleString()}</strong>
          </p>
          <div className="form-group">
            <label>How much cash do you need?</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={goalsData.cashOutAmount || ''} onChange={(e) => handleGoalsFieldChange('cashOutAmount', e.target.value, setGoalsData)} className="fun-input" placeholder="0" max={maxCashOut} />
            </div>
          </div>
          <div className="form-group">
            <label>What will you use the cash for?</label>
            <select value={goalsData.cashOutPurpose || ''} onChange={(e) => handleGoalsFieldChange('cashOutPurpose', e.target.value, setGoalsData)} className="fun-input">
              <option value="">Select...</option>
              <option value="home_improvement">Home Improvements</option>
              <option value="debt_consolidation">Debt Consolidation</option>
              <option value="education">Education</option>
              <option value="investment">Investment</option>
              <option value="emergency_fund">Emergency Fund</option>
              <option value="other">Other</option>
            </select>
          </div>
        </div>
      )}

      <div className="stage-navigation">
        <button className="btn-back" onClick={goToPrevStage}>{'←'} Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue {'→'}</button>
      </div>
    </div>
  );
}
