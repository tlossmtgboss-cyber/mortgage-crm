import React from 'react';
import AddressAutocomplete from '../../components/AddressAutocomplete';
import MortgageStatementUpload from '../../components/MortgageStatementUpload';
import { Icon } from '../application-shared';

/**
 * PropertyStage - Refinance-specific: current home details.
 * Shows mortgage statement upload, address, home value, balance, rate,
 * payment breakdown, and second lien info.
 */
export default function PropertyStage({
  propertyData,
  setPropertyData,
  statementParsed,
  setStatementParsed,
  handleMortgageStatementData,
  API_URL,
  goToPrevStage,
  goToNextStage,
}) {
  return (
    <div className="stage-content">
      <div className="stage-header">
        <h2>Your Current Home</h2>
        <p>Tell us about the property you want to refinance</p>
      </div>

      {/* Mortgage Statement Upload - only show if form not already filled */}
      {!statementParsed && !propertyData.mortgageBalance && (
        <MortgageStatementUpload
          onDataExtracted={handleMortgageStatementData}
          apiUrl={API_URL}
        />
      )}

      {/* Show success message if statement was parsed */}
      {statementParsed && (
        <div className="statement-parsed-notice">
          <span className="notice-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </span>
          <span>Information imported from your mortgage statement. Please review and update if needed.</span>
        </div>
      )}

      <div className="form-card">
        <div className="form-group">
          <AddressAutocomplete
            value={propertyData.address || ''}
            onChange={(value) => setPropertyData(prev => ({ ...prev, address: value }))}
            onAddressSelect={(addressData) => {
              setPropertyData(prev => ({
                ...prev,
                address: addressData.formatted,
                street: addressData.street,
                city: addressData.city,
                state: addressData.state_code,
                zip: addressData.zip,
                county: addressData.county,
              }));
            }}
            label="Property Address"
            placeholder="Enter your home address..."
            className="fun-input-wrapper"
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Estimated Home Value</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={propertyData.homeValue || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, homeValue: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
            <span className="input-hint"><Icon name="home" size={14} /> Based on recent comparable sales</span>
          </div>
          <div className="form-group">
            <label>Current Mortgage Balance</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={propertyData.mortgageBalance || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, mortgageBalance: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
        </div>

        {/* Equity Calculator */}
        {propertyData.homeValue && propertyData.mortgageBalance && (
          <div className="equity-display">
            <div className="equity-item">
              <span className="equity-label">Your Equity</span>
              <strong className="equity-value">
                ${(parseFloat(propertyData.homeValue) - parseFloat(propertyData.mortgageBalance)).toLocaleString()}
              </strong>
            </div>
            <div className="equity-item">
              <span className="equity-label">Loan-to-Value (LTV)</span>
              <strong className="equity-value">
                {((parseFloat(propertyData.mortgageBalance) / parseFloat(propertyData.homeValue)) * 100).toFixed(1)}%
              </strong>
            </div>
          </div>
        )}

        <div className="form-row">
          <div className="form-group">
            <label>Current Monthly Payment</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={propertyData.monthlyPayment || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, monthlyPayment: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
          <div className="form-group">
            <label>Current Interest Rate</label>
            <div className="input-with-prefix">
              <input type="number" step="0.125" value={propertyData.currentRate || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, currentRate: e.target.value }))} className="fun-input" placeholder="0.000" />
              <span className="input-suffix">%</span>
            </div>
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Original Loan Date</label>
            <input type="month" value={propertyData.loanDate || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, loanDate: e.target.value }))} className="fun-input" />
          </div>
          <div className="form-group">
            <label>Current Loan Term</label>
            <select value={propertyData.currentTerm || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, currentTerm: e.target.value }))} className="fun-input">
              <option value="">Select...</option>
              <option value="30">30 Year</option>
              <option value="25">25 Year</option>
              <option value="20">20 Year</option>
              <option value="15">15 Year</option>
              <option value="10">10 Year</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label>Current Lender</label>
          <input type="text" value={propertyData.lenderName || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, lenderName: e.target.value }))} className="fun-input" placeholder="e.g., Wells Fargo, Chase, Rocket Mortgage" />
        </div>

        {/* Payment Breakdown - show if we have parsed data */}
        {(statementParsed && (propertyData.principalAndInterest || propertyData.propertyTaxes || propertyData.insurance)) && (
          <div className="payment-breakdown-section">
            <h4><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg> Payment Breakdown</h4>
            <p className="section-hint">Imported from your mortgage statement</p>
            <div className="form-row">
              <div className="form-group">
                <label>Principal & Interest</label>
                <div className="input-with-prefix"><span className="input-prefix">$</span>
                  <input type="number" value={propertyData.principalAndInterest || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, principalAndInterest: e.target.value }))} className="fun-input" placeholder="0" />
                </div>
              </div>
              <div className="form-group">
                <label>Property Taxes</label>
                <div className="input-with-prefix"><span className="input-prefix">$</span>
                  <input type="number" value={propertyData.propertyTaxes || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, propertyTaxes: e.target.value }))} className="fun-input" placeholder="0" />
                </div>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Homeowner's Insurance</label>
                <div className="input-with-prefix"><span className="input-prefix">$</span>
                  <input type="number" value={propertyData.insurance || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, insurance: e.target.value }))} className="fun-input" placeholder="0" />
                </div>
              </div>
              <div className="form-group">
                <label>PMI / HOA</label>
                <div className="input-with-prefix"><span className="input-prefix">$</span>
                  <input type="number" value={(parseFloat(propertyData.pmi || 0) + parseFloat(propertyData.hoa || 0)) || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, pmi: e.target.value, hoa: '' }))} className="fun-input" placeholder="0" />
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="form-group">
          <label>Is there a second mortgage or HELOC?</label>
          <div className="income-cards" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div className={`income-card ${propertyData.hasSecondLien === 'yes' ? 'selected' : ''}`} onClick={() => setPropertyData(prev => ({ ...prev, hasSecondLien: 'yes' }))}>
              <span className="card-icon"><Icon name="clipboard" size={24} /></span>
              <span className="card-label">Yes</span>
            </div>
            <div className={`income-card ${propertyData.hasSecondLien === 'no' ? 'selected' : ''}`} onClick={() => setPropertyData(prev => ({ ...prev, hasSecondLien: 'no' }))}>
              <span className="card-icon"><Icon name="check" size={24} /></span>
              <span className="card-label">No</span>
            </div>
          </div>
        </div>

        {propertyData.hasSecondLien === 'yes' && (
          <div className="form-group">
            <label>Second Mortgage/HELOC Balance</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={propertyData.secondLienBalance || ''} onChange={(e) => setPropertyData(prev => ({ ...prev, secondLienBalance: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
        )}
      </div>

      <div className="stage-navigation">
        <button className="btn-back" onClick={goToPrevStage}>{'←'} Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue {'→'}</button>
      </div>
    </div>
  );
}
