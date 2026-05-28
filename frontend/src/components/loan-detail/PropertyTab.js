import React, { useState } from 'react';
import CurrencyInput from '../common/CurrencyInput';
import AddressAutocomplete from '../AddressAutocomplete';
import { formatPhoneNumber } from '../../utils/phoneUtils';

/**
 * Property tab — sub-tabs for property details, insurance, and legal.
 */
function PropertyTab({ formData, handleFieldChange }) {
  const [propertySubTab, setPropertySubTab] = useState('property');

  return (
    <div className="info-section">
      {/* Sub-tabs for Property, Insurance, and Legal */}
      <div style={{ display: 'flex', gap: '0', marginBottom: '1.5rem', borderBottom: '1px solid #e0e0e0' }}>
        {[
          ['property', 'Property'],
          ['insurance', 'Insurance'],
          ['legal', 'Legal'],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setPropertySubTab(key)}
            style={{
              padding: '10px 20px',
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: propertySubTab === key ? '600' : '400',
              color: propertySubTab === key ? '#1a73e8' : '#5f6368',
              borderBottom: propertySubTab === key ? '2px solid #1a73e8' : '2px solid transparent',
              marginBottom: '-1px'
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Property Sub-tab Content */}
      {propertySubTab === 'property' && (
        <PropertyContent formData={formData} handleFieldChange={handleFieldChange} />
      )}

      {/* Insurance Sub-tab Content */}
      {propertySubTab === 'insurance' && (
        <InsuranceContent formData={formData} handleFieldChange={handleFieldChange} />
      )}

      {/* Legal Sub-tab Content */}
      {propertySubTab === 'legal' && (
        <LegalContent formData={formData} handleFieldChange={handleFieldChange} />
      )}
    </div>
  );
}

/**
 * Property details sub-content — address, property type, value, Salesforce-synced fields, ratios.
 */
function PropertyContent({ formData, handleFieldChange }) {
  return (
    <>
      <h2 style={{ margin: '0 0 1rem 0' }}>Property</h2>
      <div className="info-grid compact">
        <div className="info-field">
          <label>Property Address</label>
          <input
            type="text"
            value={formData.property_address || formData.address || ''}
            onChange={(e) => handleFieldChange('property_address', e.target.value)}
          />
        </div>
        <div className="info-field">
          <label>City</label>
          <input
            type="text"
            value={formData.property_city || formData.city || ''}
            onChange={(e) => handleFieldChange('property_city', e.target.value)}
          />
        </div>
        <div className="info-field">
          <label>State</label>
          <input
            type="text"
            value={formData.property_state || formData.state || ''}
            onChange={(e) => handleFieldChange('property_state', e.target.value)}
          />
        </div>
        <div className="info-field">
          <label>Zip Code</label>
          <input
            type="text"
            value={formData.property_zip || formData.zip_code || ''}
            onChange={(e) => handleFieldChange('property_zip', e.target.value)}
          />
        </div>
        <div className="info-field">
          <label>Property Type</label>
          <select
            value={formData.property_type || ''}
            onChange={(e) => handleFieldChange('property_type', e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          >
            <option value="">Select Type</option>
            <option value="Single Family">Single Family</option>
            <option value="Condo">Condo</option>
            <option value="Townhouse">Townhouse</option>
            <option value="Multi-Family">Multi-Family</option>
            <option value="Manufactured">Manufactured</option>
            <option value="PUD">PUD</option>
          </select>
        </div>
        <div className="info-field">
          <label>Property Value</label>
          <CurrencyInput
            value={formData.property_value || ''}
            onChange={(value) => handleFieldChange('property_value', value)}
            placeholder="$0"
          />
        </div>
        <div className="info-field">
          <label>Down Payment</label>
          <CurrencyInput
            value={formData.down_payment || ''}
            onChange={(value) => handleFieldChange('down_payment', value)}
            placeholder="$0"
          />
        </div>
        <div className="info-field">
          <label>Credit Score</label>
          <input
            type="number"
            value={formData.credit_score || ''}
            onChange={(e) => handleFieldChange('credit_score', parseInt(e.target.value))}
          />
        </div>
      </div>

      {/* Property Details Section - Salesforce Sync Fields */}
      <h3 style={{ margin: '2rem 0 1rem 0', fontSize: '16px', fontWeight: '600', color: '#333', borderTop: '1px solid #e0e0e0', paddingTop: '1.5rem' }}>
        Property Details
        <span style={{ fontSize: '12px', fontWeight: '400', color: '#666', marginLeft: '8px' }}>(Synced from Salesforce)</span>
      </h3>
      <div className="info-grid compact">
        <div className="info-field">
          <label>Occupancy Type</label>
          <select
            value={formData.occupancy_type || ''}
            onChange={(e) => handleFieldChange('occupancy_type', e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          >
            <option value="">Select Occupancy</option>
            <option value="Primary Residence">Primary Residence</option>
            <option value="Second Home">Second Home</option>
            <option value="Investment">Investment</option>
          </select>
        </div>
        <div className="info-field">
          <label>Property County</label>
          <input
            type="text"
            value={formData.property_county || ''}
            onChange={(e) => handleFieldChange('property_county', e.target.value)}
          />
        </div>
        <div className="info-field">
          <label>Ownership Type</label>
          <select
            value={formData.property_ownership_type || ''}
            onChange={(e) => handleFieldChange('property_ownership_type', e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          >
            <option value="">Select Ownership</option>
            <option value="Fee Simple">Fee Simple</option>
            <option value="Leasehold">Leasehold</option>
          </select>
        </div>
        <div className="info-field">
          <label>Number of Units</label>
          <input
            type="number"
            min="1"
            max="4"
            value={formData.property_units || ''}
            onChange={(e) => handleFieldChange('property_units', parseInt(e.target.value))}
          />
        </div>
        <div className="info-field">
          <label>Appraised Value</label>
          <CurrencyInput
            value={formData.appraisal_value || ''}
            onChange={(value) => handleFieldChange('appraisal_value', value)}
            placeholder="$0"
          />
        </div>
        <div className="info-field">
          <label>Purchase Price</label>
          <CurrencyInput
            value={formData.purchase_price || ''}
            onChange={(value) => handleFieldChange('purchase_price', value)}
            placeholder="$0"
          />
        </div>
      </div>

      {/* LTV/CLTV Section */}
      <h3 style={{ margin: '2rem 0 1rem 0', fontSize: '16px', fontWeight: '600', color: '#333', borderTop: '1px solid #e0e0e0', paddingTop: '1.5rem' }}>
        Loan Ratios
      </h3>
      <div className="info-grid compact">
        <div className="info-field">
          <label>LTV (%)</label>
          <input
            type="number"
            step="0.01"
            value={formData.ltv || ''}
            onChange={(e) => handleFieldChange('ltv', parseFloat(e.target.value))}
            placeholder="0.00"
          />
        </div>
        <div className="info-field">
          <label>CLTV (%)</label>
          <input
            type="number"
            step="0.01"
            value={formData.cltv || ''}
            onChange={(e) => handleFieldChange('cltv', parseFloat(e.target.value))}
            placeholder="0.00"
          />
        </div>
        <div className="info-field">
          <label>Loan Purpose</label>
          <select
            value={formData.loan_purpose || ''}
            onChange={(e) => handleFieldChange('loan_purpose', e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          >
            <option value="">Select Purpose</option>
            <option value="Purchase">Purchase</option>
            <option value="Refinance">Refinance</option>
            <option value="Cash-Out Refinance">Cash-Out Refinance</option>
            <option value="Construction">Construction</option>
            <option value="Home Equity">Home Equity</option>
          </select>
        </div>
        <div className="info-field">
          <label>File State</label>
          <input
            type="text"
            value={formData.file_state || ''}
            onChange={(e) => handleFieldChange('file_state', e.target.value)}
            readOnly
            style={{ backgroundColor: '#f5f5f5' }}
          />
        </div>
      </div>
    </>
  );
}

/**
 * Insurance sub-content — homeowner's and flood insurance details.
 */
function InsuranceContent({ formData, handleFieldChange }) {
  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>Insurance</h2>
      </div>

      {/* Homeowner's Insurance Section */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Homeowner's Insurance</h3>
        <div className="info-grid compact">
          <div className="info-field">
            <label>Insurance Company</label>
            <AddressAutocomplete
              value={formData.homeowner_insurance_company || ''}
              onChange={(value) => handleFieldChange('homeowner_insurance_company', value)}
              onAddressSelect={(place) => {
                handleFieldChange('homeowner_insurance_company', place.formatted || place.name || '');
              }}
              placeholder="Company name"
              types={['establishment']}
            />
          </div>
          <div className="info-field">
            <label>Agent Name</label>
            <input
              type="text"
              value={formData.homeowner_insurance_agent || ''}
              onChange={(e) => handleFieldChange('homeowner_insurance_agent', e.target.value)}
              placeholder="Agent name"
            />
          </div>
          <div className="info-field">
            <label>Agent Phone</label>
            <input
              type="tel"
              value={formData.homeowner_insurance_phone || ''}
              onChange={(e) => handleFieldChange('homeowner_insurance_phone', formatPhoneNumber(e.target.value))}
              placeholder="(555) 555-5555"
            />
          </div>
          <div className="info-field">
            <label>Agent Email</label>
            <input
              type="email"
              value={formData.homeowner_insurance_email || ''}
              onChange={(e) => handleFieldChange('homeowner_insurance_email', e.target.value)}
              placeholder="agent@insurance.com"
            />
          </div>
          <div className="info-field">
            <label>Policy Number</label>
            <input
              type="text"
              value={formData.homeowner_insurance_policy || ''}
              onChange={(e) => handleFieldChange('homeowner_insurance_policy', e.target.value)}
              placeholder="Policy number"
            />
          </div>
          <div className="info-field">
            <label>Annual Premium</label>
            <input
              type="text"
              value={formData.homeowner_insurance_premium || ''}
              onChange={(e) => handleFieldChange('homeowner_insurance_premium', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Coverage Amount</label>
            <input
              type="text"
              value={formData.homeowner_insurance_coverage || ''}
              onChange={(e) => handleFieldChange('homeowner_insurance_coverage', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Effective Date</label>
            <input
              type="date"
              value={formData.homeowner_insurance_effective_date || ''}
              onChange={(e) => handleFieldChange('homeowner_insurance_effective_date', e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Flood Insurance Section */}
      <div style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ fontSize: '16px', fontWeight: '600', margin: 0, color: '#333' }}>Flood Insurance</h3>
          {!formData.has_flood_insurance && (
            <button
              onClick={() => handleFieldChange('has_flood_insurance', true)}
              style={{
                background: '#1a73e8',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                padding: '8px 16px',
                fontSize: '13px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              + Add Flood Insurance
            </button>
          )}
        </div>

        {formData.has_flood_insurance ? (
          <div className="info-grid compact">
            <div className="info-field">
              <label>Insurance Company</label>
              <AddressAutocomplete
                value={formData.flood_insurance_company || ''}
                onChange={(value) => handleFieldChange('flood_insurance_company', value)}
                onAddressSelect={(place) => {
                  handleFieldChange('flood_insurance_company', place.formatted || place.name || '');
                }}
                placeholder="Company name"
                types={['establishment']}
              />
            </div>
            <div className="info-field">
              <label>Agent Name</label>
              <input
                type="text"
                value={formData.flood_insurance_agent || ''}
                onChange={(e) => handleFieldChange('flood_insurance_agent', e.target.value)}
                placeholder="Agent name"
              />
            </div>
            <div className="info-field">
              <label>Agent Phone</label>
              <input
                type="tel"
                value={formData.flood_insurance_phone || ''}
                onChange={(e) => handleFieldChange('flood_insurance_phone', formatPhoneNumber(e.target.value))}
                placeholder="(555) 555-5555"
              />
            </div>
            <div className="info-field">
              <label>Agent Email</label>
              <input
                type="email"
                value={formData.flood_insurance_email || ''}
                onChange={(e) => handleFieldChange('flood_insurance_email', e.target.value)}
                placeholder="agent@insurance.com"
              />
            </div>
            <div className="info-field">
              <label>Policy Number</label>
              <input
                type="text"
                value={formData.flood_insurance_policy || ''}
                onChange={(e) => handleFieldChange('flood_insurance_policy', e.target.value)}
                placeholder="Policy number"
              />
            </div>
            <div className="info-field">
              <label>Annual Premium</label>
              <input
                type="text"
                value={formData.flood_insurance_premium || ''}
                onChange={(e) => handleFieldChange('flood_insurance_premium', e.target.value)}
                placeholder="$0.00"
              />
            </div>
            <div className="info-field">
              <label>Coverage Amount</label>
              <input
                type="text"
                value={formData.flood_insurance_coverage || ''}
                onChange={(e) => handleFieldChange('flood_insurance_coverage', e.target.value)}
                placeholder="$0.00"
              />
            </div>
            <div className="info-field">
              <label>Flood Zone</label>
              <select
                value={formData.flood_zone || ''}
                onChange={(e) => handleFieldChange('flood_zone', e.target.value)}
                style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ddd', fontSize: '14px' }}
              >
                <option value="">-- Select Zone --</option>
                <option value="A">Zone A (High Risk)</option>
                <option value="AE">Zone AE (High Risk)</option>
                <option value="AH">Zone AH (High Risk)</option>
                <option value="AO">Zone AO (High Risk)</option>
                <option value="V">Zone V (Coastal High Risk)</option>
                <option value="VE">Zone VE (Coastal High Risk)</option>
                <option value="X">Zone X (Moderate/Low Risk)</option>
                <option value="B">Zone B (Moderate Risk)</option>
                <option value="C">Zone C (Low Risk)</option>
              </select>
            </div>
            <div className="info-field" style={{ gridColumn: 'span 2' }}>
              <button
                onClick={() => handleFieldChange('has_flood_insurance', false)}
                style={{
                  background: 'none',
                  color: '#dc3545',
                  border: '1px solid #dc3545',
                  borderRadius: '6px',
                  padding: '8px 16px',
                  fontSize: '13px',
                  cursor: 'pointer',
                  marginTop: '8px'
                }}
              >
                Remove Flood Insurance
              </button>
            </div>
          </div>
        ) : (
          <div style={{
            background: '#f8f9fa',
            padding: '1.5rem',
            borderRadius: '8px',
            textAlign: 'center',
            color: '#666'
          }}>
            <p style={{ margin: 0 }}>No flood insurance added. Click "Add Flood Insurance" if required.</p>
          </div>
        )}
      </div>
    </>
  );
}

/**
 * Legal sub-content — title company / closing attorney, address, title & closing details.
 */
function LegalContent({ formData, handleFieldChange }) {
  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>Legal</h2>
      </div>

      {/* Title Company / Closing Attorney Section */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Title Company / Closing Attorney</h3>
        <div className="info-grid compact">
          <div className="info-field">
            <label>Company/Firm Type</label>
            <select
              value={formData.closing_entity_type || ''}
              onChange={(e) => handleFieldChange('closing_entity_type', e.target.value)}
              style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ddd', fontSize: '14px' }}
            >
              <option value="">-- Select Type --</option>
              <option value="title_company">Title Company</option>
              <option value="closing_attorney">Closing Attorney</option>
            </select>
          </div>
          <div className="info-field">
            <label>Company/Firm Name</label>
            <input
              type="text"
              value={formData.closing_company_name || ''}
              onChange={(e) => handleFieldChange('closing_company_name', e.target.value)}
              placeholder="Company or firm name"
            />
          </div>
          <div className="info-field">
            <label>Contact Name</label>
            <input
              type="text"
              value={formData.closing_contact_name || ''}
              onChange={(e) => handleFieldChange('closing_contact_name', e.target.value)}
              placeholder="Primary contact name"
            />
          </div>
          <div className="info-field">
            <label>Phone</label>
            <input
              type="tel"
              value={formData.closing_phone || ''}
              onChange={(e) => handleFieldChange('closing_phone', formatPhoneNumber(e.target.value))}
              placeholder="(555) 555-5555"
            />
          </div>
          <div className="info-field">
            <label>Email</label>
            <input
              type="email"
              value={formData.closing_email || ''}
              onChange={(e) => handleFieldChange('closing_email', e.target.value)}
              placeholder="contact@company.com"
            />
          </div>
          <div className="info-field">
            <label>Fax</label>
            <input
              type="tel"
              value={formData.closing_fax || ''}
              onChange={(e) => handleFieldChange('closing_fax', formatPhoneNumber(e.target.value))}
              placeholder="(555) 555-5555"
            />
          </div>
        </div>
      </div>

      {/* Address Section */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Address</h3>
        <div className="info-grid compact">
          <div className="info-field" style={{ gridColumn: 'span 2' }}>
            <label>Street Address</label>
            <AddressAutocomplete
              value={formData.closing_address || ''}
              onChange={(value) => handleFieldChange('closing_address', value)}
              onAddressSelect={(addressData) => {
                handleFieldChange('closing_address', addressData.street || addressData.formatted || '');
                if (addressData.city) handleFieldChange('closing_city', addressData.city);
                if (addressData.state_code) handleFieldChange('closing_state', addressData.state_code);
                if (addressData.zip) handleFieldChange('closing_zip', addressData.zip);
              }}
              placeholder="Street address"
              types={['address']}
            />
          </div>
          <div className="info-field">
            <label>City</label>
            <input
              type="text"
              value={formData.closing_city || ''}
              onChange={(e) => handleFieldChange('closing_city', e.target.value)}
              placeholder="City"
            />
          </div>
          <div className="info-field">
            <label>State</label>
            <input
              type="text"
              value={formData.closing_state || ''}
              onChange={(e) => handleFieldChange('closing_state', e.target.value)}
              placeholder="State"
            />
          </div>
          <div className="info-field">
            <label>Zip Code</label>
            <input
              type="text"
              value={formData.closing_zip || ''}
              onChange={(e) => handleFieldChange('closing_zip', e.target.value)}
              placeholder="Zip code"
            />
          </div>
        </div>
      </div>

      {/* Title/Closing Details Section */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Title & Closing Details</h3>
        <div className="info-grid compact">
          <div className="info-field">
            <label>Title Order Number</label>
            <input
              type="text"
              value={formData.title_order_number || ''}
              onChange={(e) => handleFieldChange('title_order_number', e.target.value)}
              placeholder="Order number"
            />
          </div>
          <div className="info-field">
            <label>Title Order Date</label>
            <input
              type="date"
              value={formData.title_order_date || ''}
              onChange={(e) => handleFieldChange('title_order_date', e.target.value)}
            />
          </div>
          <div className="info-field">
            <label>Preliminary Title Received</label>
            <input
              type="date"
              value={formData.preliminary_title_date || ''}
              onChange={(e) => handleFieldChange('preliminary_title_date', e.target.value)}
            />
          </div>
          <div className="info-field">
            <label>Closing Scheduled</label>
            <input
              type="datetime-local"
              value={formData.closing_scheduled || ''}
              onChange={(e) => handleFieldChange('closing_scheduled', e.target.value)}
            />
          </div>
          <div className="info-field" style={{ gridColumn: 'span 2' }}>
            <label>Notes</label>
            <textarea
              value={formData.closing_notes || ''}
              onChange={(e) => handleFieldChange('closing_notes', e.target.value)}
              placeholder="Additional notes about title or closing..."
              style={{
                padding: '10px',
                borderRadius: '6px',
                border: '1px solid #ddd',
                fontSize: '14px',
                minHeight: '80px',
                resize: 'vertical'
              }}
            />
          </div>
        </div>
      </div>
    </>
  );
}

export default PropertyTab;
