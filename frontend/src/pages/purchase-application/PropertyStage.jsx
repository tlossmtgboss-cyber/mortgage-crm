import React from 'react';
import AddressAutocomplete from '../../components/AddressAutocomplete';
import PaymentCalculator from '../../components/PaymentCalculator';
import { Icon } from '../application-shared';

/**
 * PropertyStage - Property type, occupancy, price, and loan details.
 * Multi-step: 1) Type, 2) Occupancy, 3) Price/Down Payment/Loan Program.
 */
export default function PropertyStage({
  declarations,
  propertyData,
  setPropertyData,
  propertyStep,
  setPropertyStep,
  paymentEstimate,
  setPaymentEstimate,
  setCurrentStage,
  goToPrevStage,
  goToNextStage,
}) {
  const isVeteran = declarations.veteran === 'yes' || declarations.veteran === 'active';
  const isFirstTimeBuyer = declarations.first_time_buyer === 'yes';

  // Step 1: Property Type
  if (propertyStep === 1) {
    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Property Type</h2>
          <p>What type of property are you looking for?</p>
        </div>
        <div className="form-card">
          <div className="property-type-selector">
            <div className="income-cards">
              {[
                { type: 'Single Family', icon: 'home', desc: 'Detached home' },
                { type: 'Condo', icon: 'building', desc: 'Condominium unit' },
                { type: 'Townhouse', icon: 'layers', desc: 'Attached home' },
                { type: 'Multi-Family', icon: 'users', desc: '2-4 units' },
              ].map(({ type, icon, desc }) => (
                <div key={type} className={`income-card ${propertyData.propertyType === type ? 'selected' : ''}`} onClick={() => setPropertyData(prev => ({ ...prev, propertyType: type }))}>
                  <span className="card-icon"><Icon name={icon} size={28} /></span>
                  <span className="card-label">{type}</span>
                  <span className="card-desc">{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>{'←'} Back</button>
          <button className="btn-continue" onClick={() => setPropertyStep(2)} disabled={!propertyData.propertyType}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  // Step 2: Occupancy
  if (propertyStep === 2) {
    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>How Will You Use This Home?</h2>
          <p>This affects your loan options and rates</p>
        </div>
        <div className="form-card">
          <div className="occupancy-selector">
            <div className="income-cards">
              {[
                { value: 'primary', icon: 'home', label: 'Primary Home', desc: "I'll live here" },
                { value: 'second', icon: 'beach', label: 'Second Home', desc: 'Vacation property' },
                { value: 'investment', icon: 'trendUp', label: 'Investment', desc: 'Rental income' },
              ].map(({ value, icon, label, desc }) => (
                <div key={value} className={`income-card ${propertyData.occupancy === value ? 'selected' : ''}`} onClick={() => setPropertyData(prev => ({ ...prev, occupancy: value }))}>
                  <span className="card-icon"><Icon name={icon} size={28} /></span>
                  <span className="card-label">{label}</span>
                  <span className="card-desc">{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setPropertyStep(1)}>{'←'} Back</button>
          <button className="btn-continue" onClick={() => setPropertyStep(3)} disabled={!propertyData.occupancy}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  // Step 3: Price, Down Payment, Loan Program
  const prefilledPrice = paymentEstimate?.homeValue || propertyData.purchasePrice;
  const prefilledDownPayment = paymentEstimate?.downPaymentAmount || propertyData.downPayment;

  return (
    <div className="stage-content">
      <div className="stage-header">
        <h2>Estimated Budget & Loan Details</h2>
        <p>Review your preliminary numbers below</p>
      </div>

      <div className="preliminary-disclaimer" style={{
        background: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)',
        border: '1px solid #f59e0b',
        borderRadius: '12px',
        padding: '16px 20px',
        marginBottom: '24px',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '12px'
      }}>
        <Icon name="info" size={20} style={{ color: '#d97706', flexShrink: 0, marginTop: '2px' }} />
        <div>
          <p style={{ margin: 0, color: '#92400e', fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>Preliminary Estimates</p>
          <p style={{ margin: 0, color: '#78350f', fontSize: '13px', lineHeight: '1.5' }}>
            The numbers shown below are estimates based on the information you've provided. Your loan officer will review these details with you and make any necessary adjustments based on current rates, your specific situation, and available loan programs.
          </p>
        </div>
      </div>

      {paymentEstimate && (
        <div className="form-card budget-summary-card">
          <div className="budget-summary-header">
            <Icon name="calculator" size={24} />
            <h3>Your Budget Summary</h3>
            <button className="edit-button" onClick={() => setCurrentStage('goals')} style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', background: 'transparent', border: '1px solid #e5e7eb', borderRadius: '8px', fontSize: '14px', color: '#374151', cursor: 'pointer', transition: 'all 0.2s' }} onMouseEnter={(e) => { e.target.style.background = '#f3f4f6'; }} onMouseLeave={(e) => { e.target.style.background = 'transparent'; }}>
              <Icon name="edit" size={16} /> Edit
            </button>
          </div>
          <div className="budget-summary-grid">
            <div className="budget-item"><span className="budget-label">Home Value</span><span className="budget-value">${paymentEstimate.homeValue?.toLocaleString()}</span></div>
            <div className="budget-item"><span className="budget-label">Down Payment</span><span className="budget-value">${paymentEstimate.downPaymentAmount?.toLocaleString()} ({paymentEstimate.downPaymentPercent}%)</span></div>
            <div className="budget-item"><span className="budget-label">Loan Amount</span><span className="budget-value">${paymentEstimate.loanAmount?.toLocaleString()}</span></div>
            <div className="budget-item highlight"><span className="budget-label">Est. Monthly Payment</span><span className="budget-value">${paymentEstimate.payment?.totalMonthly?.toLocaleString()}</span></div>
          </div>
          <div className="budget-breakdown">
            <div className="breakdown-row"><span>Principal & Interest</span><span>${paymentEstimate.payment?.principalAndInterest?.toLocaleString()}</span></div>
            <div className="breakdown-row"><span>Property Tax</span><span>${paymentEstimate.payment?.propertyTax?.toLocaleString()}/mo</span></div>
            <div className="breakdown-row"><span>Insurance</span><span>${paymentEstimate.payment?.homeownersInsurance?.toLocaleString()}/mo</span></div>
            {paymentEstimate.payment?.pmi > 0 && (<div className="breakdown-row"><span>Mortgage Insurance</span><span>${paymentEstimate.payment?.pmi?.toLocaleString()}/mo</span></div>)}
          </div>
        </div>
      )}

      {(declarations.found_property === 'yes' || !paymentEstimate) && (
        <div className="form-card">
          {declarations.found_property === 'yes' && (
            <AddressAutocomplete
              value={propertyData.address || ''}
              onChange={(value) => setPropertyData(prev => ({ ...prev, address: value }))}
              onAddressSelect={(addressData) => {
                setPropertyData(prev => ({ ...prev, address: addressData.formatted, street: addressData.street, city: addressData.city, state: addressData.state_code, zip: addressData.zip, county: addressData.county }));
              }}
              label="Property Address"
              placeholder="Enter property address..."
              className="fun-input-wrapper"
            />
          )}
          {!paymentEstimate && (
            <div className="form-row">
              <div className="form-group">
                <label>{declarations.found_property === 'yes' ? 'Purchase Price' : 'Target Price Range'}</label>
                <div className="input-with-prefix"><span className="input-prefix">$</span>
                  <input type="number" value={propertyData.purchasePrice || prefilledPrice || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, purchasePrice: e.target.value }))} className="fun-input" placeholder="0" />
                </div>
              </div>
              <div className="form-group">
                <label>Down Payment</label>
                <div className="input-with-prefix"><span className="input-prefix">$</span>
                  <input type="number" value={propertyData.downPayment || prefilledDownPayment || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, downPayment: e.target.value }))} className="fun-input" placeholder="0" />
                </div>
                {(propertyData.purchasePrice || prefilledPrice) && (propertyData.downPayment || prefilledDownPayment) && (
                  <span className="calculated-hint">{(((propertyData.downPayment || prefilledDownPayment) / (propertyData.purchasePrice || prefilledPrice)) * 100).toFixed(1)}% down</span>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {!paymentEstimate && (propertyData.purchasePrice || prefilledPrice) && parseFloat(propertyData.purchasePrice || prefilledPrice) > 0 && (
        <div className="form-card payment-calculator-section">
          <PaymentCalculator
            initialHomeValue={parseFloat(propertyData.purchasePrice || prefilledPrice) || 0}
            initialDownPayment={parseFloat(propertyData.downPayment || prefilledDownPayment) || 0}
            initialState={propertyData.state || ''}
            initialCounty={propertyData.county || ''}
            initialPropertyUse={propertyData.occupancy === 'primary' ? 'primaryResidence' : propertyData.occupancy === 'second' ? 'secondHome' : propertyData.occupancy === 'investment' ? 'rental' : 'primaryResidence'}
            showAdvancedOptions={false}
            onCalculationComplete={(calculation) => setPaymentEstimate(calculation)}
          />
        </div>
      )}

      <div className="stage-navigation">
        <button className="btn-back" onClick={() => setPropertyStep(2)}>{'←'} Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue {'→'}</button>
      </div>
    </div>
  );
}
