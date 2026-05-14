import React, { useState } from 'react';
import CurrencyInput from '../../components/common/CurrencyInput';
import { formatPhoneNumber } from '../../utils/phoneUtils';

/**
 * Property tab — sub-tabs for property details, insurance, and legal.
 */
function PropertyTab({ formData, handleFieldChange }) {
  const [propertySubTab, setPropertySubTab] = useState('property');

  return (
    <div className="info-section">
      {/* Sub-tabs */}
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

      {propertySubTab === 'property' && (
        <PropertyContent formData={formData} handleFieldChange={handleFieldChange} />
      )}

      {propertySubTab === 'insurance' && (
        <InsuranceContent formData={formData} handleFieldChange={handleFieldChange} />
      )}

      {propertySubTab === 'legal' && (
        <LegalContent formData={formData} handleFieldChange={handleFieldChange} />
      )}
    </div>
  );
}

function PropertyContent({ formData, handleFieldChange }) {
  return (
    <>
      <h2 style={{ margin: '0 0 1rem 0' }}>Property</h2>
      <div className="info-grid compact">
        <div className="info-field">
          <label>Property Address</label>
          <input type="text" value={formData.address || ''} onChange={(e) => handleFieldChange('address', e.target.value)} />
        </div>
        <div className="info-field">
          <label>City</label>
          <input type="text" value={formData.city || ''} onChange={(e) => handleFieldChange('city', e.target.value)} />
        </div>
        <div className="info-field">
          <label>State</label>
          <input type="text" value={formData.state || ''} onChange={(e) => handleFieldChange('state', e.target.value)} />
        </div>
        <div className="info-field">
          <label>Zip Code</label>
          <input type="text" value={formData.zip_code || ''} onChange={(e) => handleFieldChange('zip_code', e.target.value)} />
        </div>
        <div className="info-field">
          <label>Property Type</label>
          <input type="text" value={formData.property_type || ''} onChange={(e) => handleFieldChange('property_type', e.target.value)} />
        </div>
        <div className="info-field">
          <label>Property Value</label>
          <CurrencyInput value={formData.property_value || ''} onChange={(value) => handleFieldChange('property_value', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>Down Payment</label>
          <CurrencyInput value={formData.down_payment || ''} onChange={(value) => handleFieldChange('down_payment', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>Credit Score</label>
          <input type="number" value={formData.credit_score || ''} onChange={(e) => handleFieldChange('credit_score', parseInt(e.target.value))} />
        </div>
      </div>
    </>
  );
}

function InsuranceContent({ formData, handleFieldChange }) {
  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>Insurance</h2>
      </div>

      {/* Homeowner's Insurance */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Homeowner's Insurance</h3>
        <div className="info-grid compact">
          {[
            ['Insurance Company', 'homeowner_insurance_company', 'text', 'Company name'],
            ['Agent Name', 'homeowner_insurance_agent', 'text', 'Agent name'],
            ['Agent Phone', 'homeowner_insurance_phone', 'tel', '(555) 555-5555'],
            ['Agent Email', 'homeowner_insurance_email', 'email', 'agent@insurance.com'],
            ['Policy Number', 'homeowner_insurance_policy', 'text', 'Policy number'],
            ['Annual Premium', 'homeowner_insurance_premium', 'text', '$0.00'],
            ['Coverage Amount', 'homeowner_insurance_coverage', 'text', '$0.00'],
            ['Effective Date', 'homeowner_insurance_effective_date', 'date', ''],
          ].map(([label, key, type, placeholder]) => (
            <div className="info-field" key={key}>
              <label>{label}</label>
              <input
                type={type}
                value={formData[key] || ''}
                onChange={(e) => handleFieldChange(key, type === 'tel' ? formatPhoneNumber(e.target.value) : e.target.value)}
                placeholder={placeholder}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Flood Insurance */}
      <div style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ fontSize: '16px', fontWeight: '600', margin: 0, color: '#333' }}>Flood Insurance</h3>
          {!formData.has_flood_insurance && (
            <button
              onClick={() => handleFieldChange('has_flood_insurance', true)}
              style={{
                background: '#1a73e8', color: 'white', border: 'none', borderRadius: '6px',
                padding: '8px 16px', fontSize: '13px', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: '6px'
              }}
            >
              + Add Flood Insurance
            </button>
          )}
        </div>

        {formData.has_flood_insurance ? (
          <div className="info-grid compact">
            {[
              ['Insurance Company', 'flood_insurance_company', 'text', 'Company name'],
              ['Agent Name', 'flood_insurance_agent', 'text', 'Agent name'],
              ['Agent Phone', 'flood_insurance_phone', 'tel', '(555) 555-5555'],
              ['Agent Email', 'flood_insurance_email', 'email', 'agent@insurance.com'],
              ['Policy Number', 'flood_insurance_policy', 'text', 'Policy number'],
              ['Annual Premium', 'flood_insurance_premium', 'text', '$0.00'],
              ['Coverage Amount', 'flood_insurance_coverage', 'text', '$0.00'],
            ].map(([label, key, type, placeholder]) => (
              <div className="info-field" key={key}>
                <label>{label}</label>
                <input
                  type={type}
                  value={formData[key] || ''}
                  onChange={(e) => handleFieldChange(key, type === 'tel' ? formatPhoneNumber(e.target.value) : e.target.value)}
                  placeholder={placeholder}
                />
              </div>
            ))}
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
                  background: 'none', color: '#dc3545', border: '1px solid #dc3545',
                  borderRadius: '6px', padding: '8px 16px', fontSize: '13px', cursor: 'pointer', marginTop: '8px'
                }}
              >
                Remove Flood Insurance
              </button>
            </div>
          </div>
        ) : (
          <div style={{ background: '#f8f9fa', padding: '1.5rem', borderRadius: '8px', textAlign: 'center', color: '#666' }}>
            <p style={{ margin: 0 }}>No flood insurance added. Click "Add Flood Insurance" if required.</p>
          </div>
        )}
      </div>
    </>
  );
}

function LegalContent({ formData, handleFieldChange }) {
  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>Legal</h2>
      </div>

      {/* Title Company / Closing Attorney */}
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
          {[
            ['Company/Firm Name', 'closing_company_name', 'text', 'Company or firm name'],
            ['Contact Name', 'closing_contact_name', 'text', 'Primary contact name'],
            ['Phone', 'closing_phone', 'tel', '(555) 555-5555'],
            ['Email', 'closing_email', 'email', 'contact@company.com'],
            ['Fax', 'closing_fax', 'tel', '(555) 555-5555'],
          ].map(([label, key, type, placeholder]) => (
            <div className="info-field" key={key}>
              <label>{label}</label>
              <input
                type={type}
                value={formData[key] || ''}
                onChange={(e) => handleFieldChange(key, type === 'tel' ? formatPhoneNumber(e.target.value) : e.target.value)}
                placeholder={placeholder}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Address */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Address</h3>
        <div className="info-grid compact">
          <div className="info-field" style={{ gridColumn: 'span 2' }}>
            <label>Street Address</label>
            <input type="text" value={formData.closing_address || ''} onChange={(e) => handleFieldChange('closing_address', e.target.value)} placeholder="Street address" />
          </div>
          <div className="info-field">
            <label>City</label>
            <input type="text" value={formData.closing_city || ''} onChange={(e) => handleFieldChange('closing_city', e.target.value)} placeholder="City" />
          </div>
          <div className="info-field">
            <label>State</label>
            <input type="text" value={formData.closing_state || ''} onChange={(e) => handleFieldChange('closing_state', e.target.value)} placeholder="State" />
          </div>
          <div className="info-field">
            <label>Zip Code</label>
            <input type="text" value={formData.closing_zip || ''} onChange={(e) => handleFieldChange('closing_zip', e.target.value)} placeholder="Zip code" />
          </div>
        </div>
      </div>

      {/* Title & Closing Details */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Title & Closing Details</h3>
        <div className="info-grid compact">
          <div className="info-field">
            <label>Title Order Number</label>
            <input type="text" value={formData.title_order_number || ''} onChange={(e) => handleFieldChange('title_order_number', e.target.value)} placeholder="Order number" />
          </div>
          <div className="info-field">
            <label>Title Order Date</label>
            <input type="date" value={formData.title_order_date || ''} onChange={(e) => handleFieldChange('title_order_date', e.target.value)} />
          </div>
          <div className="info-field">
            <label>Preliminary Title Received</label>
            <input type="date" value={formData.preliminary_title_date || ''} onChange={(e) => handleFieldChange('preliminary_title_date', e.target.value)} />
          </div>
          <div className="info-field">
            <label>Closing Scheduled</label>
            <input type="datetime-local" value={formData.closing_scheduled || ''} onChange={(e) => handleFieldChange('closing_scheduled', e.target.value)} />
          </div>
          <div className="info-field" style={{ gridColumn: 'span 2' }}>
            <label>Notes</label>
            <textarea
              value={formData.closing_notes || ''}
              onChange={(e) => handleFieldChange('closing_notes', e.target.value)}
              placeholder="Additional notes about title or closing..."
              style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ddd', fontSize: '14px', minHeight: '80px', resize: 'vertical' }}
            />
          </div>
        </div>
      </div>
    </>
  );
}

export default PropertyTab;
