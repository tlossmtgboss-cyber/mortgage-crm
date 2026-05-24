import React from 'react';
import { Icon } from '../application-shared';

/**
 * ReviewStage - Refinance summary before submission.
 * Shows personal info, income, property details, and refinance goals.
 */
export default function ReviewStage({
  profileData,
  incomeData,
  propertyData,
  goalsData,
  setCurrentStage,
  goToPrevStage,
  goToNextStage,
}) {
  const homeValue = parseFloat(propertyData.homeValue) || 0;
  const currentBalance = parseFloat(propertyData.mortgageBalance) || 0;
  const equity = homeValue - currentBalance;
  const newLoanAmount = goalsData.refiType === 'cash_out'
    ? currentBalance + (parseFloat(goalsData.cashOutAmount) || 0)
    : currentBalance;

  return (
    <div className="stage-content review-stage">
      <div className="stage-header">
        <h2>Review Your Application</h2>
        <p>Almost there! Review your information below and make any edits needed.</p>
      </div>

      {/* Summary Hero Card */}
      <div className="review-hero-card">
        <div className="hero-icon-wrapper"><Icon name="check" size={32} /></div>
        <div className="hero-content">
          <h3>Your Refinance Summary</h3>
          <div className="hero-stats">
            <div className="hero-stat">
              <span className="stat-label">Home Value</span>
              <span className="stat-value">${homeValue.toLocaleString()}</span>
            </div>
            <div className="hero-stat-divider"></div>
            <div className="hero-stat">
              <span className="stat-label">Current Balance</span>
              <span className="stat-value">${currentBalance.toLocaleString()}</span>
            </div>
            <div className="hero-stat-divider"></div>
            <div className="hero-stat">
              <span className="stat-label">Your Equity</span>
              <span className="stat-value highlight">${equity.toLocaleString()}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="review-grid">
        {/* Profile Card */}
        <div className="review-card">
          <div className="card-header">
            <div className="card-icon profile-icon"><Icon name="profile" size={24} /></div>
            <div className="card-title"><h4>Personal Information</h4><span className="card-subtitle">Your contact details</span></div>
            <button className="edit-btn-modern" onClick={() => setCurrentStage('profile')}><Icon name="edit" size={16} /><span>Edit</span></button>
          </div>
          <div className="card-body">
            <div className="info-row"><Icon name="profile" size={16} /><span className="info-label">Full Name</span><span className="info-value">{profileData.firstName} {profileData.lastName}</span></div>
            <div className="info-row"><Icon name="email" size={16} /><span className="info-label">Email</span><span className="info-value">{profileData.email}</span></div>
            <div className="info-row"><Icon name="phone" size={16} /><span className="info-label">Phone</span><span className="info-value">{profileData.phone}</span></div>
          </div>
        </div>

        {/* Income Card */}
        <div className="review-card">
          <div className="card-header">
            <div className="card-icon income-icon"><Icon name="briefcase" size={24} /></div>
            <div className="card-title"><h4>Employment & Income</h4><span className="card-subtitle">Your income sources</span></div>
            <button className="edit-btn-modern" onClick={() => setCurrentStage('income')}><Icon name="edit" size={16} /><span>Edit</span></button>
          </div>
          <div className="card-body">
            <div className="info-row"><Icon name="briefcase" size={16} /><span className="info-label">Employment Type</span><span className="info-value capitalize">{incomeData.primaryType?.replace('_', ' ') || 'Not specified'}</span></div>
            {incomeData.employerName && (
              <div className="info-row"><Icon name="building" size={16} /><span className="info-label">Employer</span><span className="info-value">{incomeData.employerName}</span></div>
            )}
            {incomeData.annualSalary && (
              <div className="info-row highlight-row"><Icon name="dollarSign" size={16} /><span className="info-label">Annual Income</span><span className="info-value">${parseFloat(incomeData.annualSalary).toLocaleString()}</span></div>
            )}
          </div>
        </div>

        {/* Property Card */}
        <div className="review-card">
          <div className="card-header">
            <div className="card-icon property-icon"><Icon name="home" size={24} /></div>
            <div className="card-title"><h4>Current Property</h4><span className="card-subtitle">Property being refinanced</span></div>
            <button className="edit-btn-modern" onClick={() => setCurrentStage('property')}><Icon name="edit" size={16} /><span>Edit</span></button>
          </div>
          <div className="card-body">
            <div className="info-row"><Icon name="mapPin" size={16} /><span className="info-label">Address</span><span className="info-value">{propertyData.address || 'Not specified'}</span></div>
            <div className="info-row"><Icon name="home" size={16} /><span className="info-label">Home Value</span><span className="info-value">${homeValue.toLocaleString()}</span></div>
            <div className="info-row"><Icon name="dollarSign" size={16} /><span className="info-label">Current Balance</span><span className="info-value">${currentBalance.toLocaleString()}</span></div>
            <div className="info-row"><Icon name="trendDown" size={16} /><span className="info-label">Current Rate</span><span className="info-value">{propertyData.currentRate || '0'}%</span></div>
            {propertyData.lenderName && (
              <div className="info-row"><Icon name="building" size={16} /><span className="info-label">Current Lender</span><span className="info-value">{propertyData.lenderName}</span></div>
            )}
          </div>
        </div>

        {/* Refinance Goals Card */}
        <div className="review-card">
          <div className="card-header">
            <div className="card-icon goals-icon"><Icon name="target" size={24} /></div>
            <div className="card-title"><h4>Refinance Goals</h4><span className="card-subtitle">Your refinance objectives</span></div>
            <button className="edit-btn-modern" onClick={() => setCurrentStage('goals')}><Icon name="edit" size={16} /><span>Edit</span></button>
          </div>
          <div className="card-body">
            <div className="info-row"><Icon name="document" size={16} /><span className="info-label">Refinance Type</span><span className="info-value capitalize">{goalsData.refiType === 'cash_out' ? 'Cash-Out Refinance' : goalsData.refiType?.replace('_', ' ') || 'Rate & Term'}</span></div>
            {goalsData.refiType === 'cash_out' && goalsData.cashOutAmount && (
              <div className="info-row highlight-row"><Icon name="money" size={16} /><span className="info-label">Cash Out Amount</span><span className="info-value">${parseFloat(goalsData.cashOutAmount).toLocaleString()}</span></div>
            )}
            <div className="info-row"><Icon name="dollarSign" size={16} /><span className="info-label">New Loan Amount</span><span className="info-value">${newLoanAmount.toLocaleString()}</span></div>
          </div>
        </div>
      </div>

      <div className="stage-navigation">
        <button className="btn-back" onClick={goToPrevStage}>{'←'} Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue {'→'}</button>
      </div>
    </div>
  );
}
