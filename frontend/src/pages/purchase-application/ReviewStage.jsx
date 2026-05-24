import React from 'react';
import { Icon } from '../application-shared';

/**
 * ReviewStage - Summary of all application data before submission.
 */
export default function ReviewStage({
  profileData,
  incomeData,
  assetData,
  propertyData,
  declarations,
  coBorrowerData,
  ssnDisplay,
  coBorrowerSsnDisplay,
  paymentEstimate,
  hasMultipleBorrowers,
  setCurrentStage,
  goToPrevStage,
  goToNextStage,
}) {
  const totalAssets = (parseFloat(assetData.checking) || 0) +
    (parseFloat(assetData.savings) || 0) +
    (parseFloat(assetData.investments) || 0) +
    (parseFloat(assetData.giftAmount) || 0);
  const purchasePrice = paymentEstimate?.homeValue || parseFloat(propertyData.purchasePrice || 0);
  const downPaymentAmount = paymentEstimate?.downPaymentAmount || parseFloat(propertyData.downPayment || 0);
  const loanAmount = paymentEstimate?.loanAmount || (purchasePrice - downPaymentAmount);
  const downPaymentPercent = paymentEstimate?.downPaymentPercent || (purchasePrice > 0 ? ((downPaymentAmount / purchasePrice) * 100).toFixed(1) : 0);

  const borrowerNames = [profileData.firstName];
  if (hasMultipleBorrowers && coBorrowerData.firstName) {
    borrowerNames.push(coBorrowerData.firstName);
  }
  const welcomeMessage = `Welcome ${borrowerNames.join(' and ')}`;

  return (
    <div className="stage-content review-stage">
      <div className="stage-header">
        <h2>{welcomeMessage}</h2>
        <p>Almost there! Review your information below and make any edits needed.</p>
      </div>

      <div className="review-hero-card">
        <div className="hero-icon-wrapper"><Icon name="check" size={32} /></div>
        <div className="hero-content">
          <h3>Your Loan Summary</h3>
          <div className="hero-stats">
            <div className="hero-stat"><span className="stat-label">Purchase Price</span><span className="stat-value">${purchasePrice.toLocaleString()}</span></div>
            <div className="hero-stat-divider"></div>
            <div className="hero-stat"><span className="stat-label">Down Payment</span><span className="stat-value">${downPaymentAmount.toLocaleString()} <small>({downPaymentPercent}%)</small></span></div>
            <div className="hero-stat-divider"></div>
            <div className="hero-stat"><span className="stat-label">Loan Amount</span><span className="stat-value highlight">${loanAmount.toLocaleString()}</span></div>
          </div>
        </div>
      </div>

      <div className="review-grid">
        {/* Borrower Card */}
        <div className="review-card borrower-card">
          <div className="card-header">
            <div className="card-icon borrower-icon"><Icon name="user" size={24} /></div>
            <div className="card-title"><h4>Borrower Information</h4><span className="card-subtitle">Primary applicant details</span></div>
            <button className="edit-btn-modern" onClick={() => setCurrentStage('profile')}><Icon name="edit" size={16} /><span>Edit</span></button>
          </div>
          <div className="card-body">
            <div className="info-row"><Icon name="profile" size={16} /><span className="info-label">Full Name</span><span className="info-value">{profileData.firstName} {profileData.lastName}</span></div>
            <div className="info-row"><Icon name="email" size={16} /><span className="info-label">Email</span><span className="info-value">{profileData.email}</span></div>
            <div className="info-row"><Icon name="phone" size={16} /><span className="info-label">Phone</span><span className="info-value">{profileData.phone}</span></div>
            {ssnDisplay && (<div className="info-row"><Icon name="lock" size={16} /><span className="info-label">SSN</span><span className="info-value masked">{ssnDisplay}</span></div>)}
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
            {incomeData.employerName && (<div className="info-row"><Icon name="building" size={16} /><span className="info-label">Employer</span><span className="info-value">{incomeData.employerName}</span></div>)}
            {incomeData.annualSalary && (<div className="info-row highlight-row"><Icon name="dollarSign" size={16} /><span className="info-label">Annual Income</span><span className="info-value">${parseFloat(incomeData.annualSalary).toLocaleString()}</span></div>)}
          </div>
        </div>

        {/* Assets Card */}
        <div className="review-card">
          <div className="card-header">
            <div className="card-icon assets-icon"><Icon name="dollarSign" size={24} /></div>
            <div className="card-title"><h4>Assets & Down Payment</h4><span className="card-subtitle">Your available funds</span></div>
            <button className="edit-btn-modern" onClick={() => setCurrentStage('assets')}><Icon name="edit" size={16} /><span>Edit</span></button>
          </div>
          <div className="card-body">
            {parseFloat(assetData.checking) > 0 && (<div className="info-row"><Icon name="creditCard" size={16} /><span className="info-label">Checking</span><span className="info-value">${parseFloat(assetData.checking).toLocaleString()}</span></div>)}
            {parseFloat(assetData.savings) > 0 && (<div className="info-row"><Icon name="piggyBank" size={16} /><span className="info-label">Savings</span><span className="info-value">${parseFloat(assetData.savings).toLocaleString()}</span></div>)}
            {parseFloat(assetData.investments) > 0 && (<div className="info-row"><Icon name="chart" size={16} /><span className="info-label">Investments</span><span className="info-value">${parseFloat(assetData.investments).toLocaleString()}</span></div>)}
            {declarations.gift_funds === 'yes' && parseFloat(assetData.giftAmount) > 0 && (<div className="info-row"><Icon name="gift" size={16} /><span className="info-label">Gift Funds</span><span className="info-value">${parseFloat(assetData.giftAmount).toLocaleString()}</span></div>)}
            <div className="info-row total-row"><Icon name="wallet" size={16} /><span className="info-label">Total Available</span><span className="info-value">${totalAssets.toLocaleString()}</span></div>
          </div>
        </div>

        {/* Property Card */}
        <div className="review-card">
          <div className="card-header">
            <div className="card-icon property-icon"><Icon name="home" size={24} /></div>
            <div className="card-title"><h4>Property Details</h4><span className="card-subtitle">Your new home</span></div>
            <button className="edit-btn-modern" onClick={() => setCurrentStage('property')}><Icon name="edit" size={16} /><span>Edit</span></button>
          </div>
          <div className="card-body">
            <div className="info-row"><Icon name="home" size={16} /><span className="info-label">Property Type</span><span className="info-value capitalize">{propertyData.propertyType?.replace('_', ' ') || 'Not specified'}</span></div>
            <div className="info-row"><Icon name="mapPin" size={16} /><span className="info-label">Location</span><span className="info-value">{propertyData.state || 'Not specified'}{propertyData.county ? `, ${propertyData.county}` : ''}</span></div>
            <div className="info-row"><Icon name="document" size={16} /><span className="info-label">Loan Program</span><span className="info-value uppercase">{propertyData.program || 'Conventional'}</span></div>
            <div className="info-row"><Icon name="calendar" size={16} /><span className="info-label">Occupancy</span><span className="info-value capitalize">{propertyData.occupancy?.replace('_', ' ') || 'Primary Residence'}</span></div>
          </div>
        </div>
      </div>

      {hasMultipleBorrowers && coBorrowerData.firstName && (
        <div className="review-card coborrower-card">
          <div className="card-header">
            <div className="card-icon coborrower-icon"><Icon name="users" size={24} /></div>
            <div className="card-title"><h4>Co-Borrower Information</h4><span className="card-subtitle">Second applicant details</span></div>
            <button className="edit-btn-modern" onClick={() => setCurrentStage('profile')}><Icon name="edit" size={16} /><span>Edit</span></button>
          </div>
          <div className="card-body">
            <div className="info-row"><Icon name="profile" size={16} /><span className="info-label">Full Name</span><span className="info-value">{coBorrowerData.firstName} {coBorrowerData.lastName}</span></div>
            <div className="info-row"><Icon name="email" size={16} /><span className="info-label">Email</span><span className="info-value">{coBorrowerData.email}</span></div>
            <div className="info-row"><Icon name="phone" size={16} /><span className="info-label">Phone</span><span className="info-value">{coBorrowerData.phone}</span></div>
            {coBorrowerSsnDisplay && (<div className="info-row"><Icon name="lock" size={16} /><span className="info-label">SSN</span><span className="info-value masked">{coBorrowerSsnDisplay}</span></div>)}
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
