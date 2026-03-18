import React from 'react';
import CurrencyInput from '../../components/common/CurrencyInput';

export default function LoanDetailsTab({ formData, handleFieldChange }) {
  return (
    <div className="info-section">
      <h2>Loan Details</h2>

      {/* Transaction Type Toggle */}
      <div className="transaction-type-toggle" style={{ marginBottom: '1.5rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '600', color: '#374151' }}>Transaction Type</label>
        <div style={{ display: 'flex', gap: '0', borderRadius: '8px', overflow: 'hidden', border: '1px solid #d1d5db', width: 'fit-content' }}>
          <button
            type="button"
            onClick={() => handleFieldChange('loan_purpose', 'Purchase')}
            style={{
              padding: '0.75rem 1.5rem', border: 'none',
              background: (formData.loan_purpose === 'Purchase' || !formData.loan_purpose) ? '#3b82f6' : '#f3f4f6',
              color: (formData.loan_purpose === 'Purchase' || !formData.loan_purpose) ? 'white' : '#374151',
              fontWeight: '600', cursor: 'pointer', transition: 'all 0.2s'
            }}
          >
            Purchase
          </button>
          <button
            type="button"
            onClick={() => handleFieldChange('loan_purpose', 'Refinance')}
            style={{
              padding: '0.75rem 1.5rem', border: 'none', borderLeft: '1px solid #d1d5db',
              background: formData.loan_purpose === 'Refinance' ? '#3b82f6' : '#f3f4f6',
              color: formData.loan_purpose === 'Refinance' ? 'white' : '#374151',
              fontWeight: '600', cursor: 'pointer', transition: 'all 0.2s'
            }}
          >
            Refinance
          </button>
        </div>
      </div>

      <div className="info-grid">
        <div className="info-field">
          <label>Loan Number</label>
          <input type="text" value={formData.loan_number || ''} onChange={(e) => handleFieldChange('loan_number', e.target.value)} placeholder="Enter loan number" />
        </div>

        {(formData.loan_purpose === 'Purchase' || !formData.loan_purpose) && (
          <div className="info-field">
            <label>Purchase Price</label>
            <CurrencyInput value={formData.purchase_price || ''} onChange={(value) => handleFieldChange('purchase_price', value)} placeholder="$0" />
          </div>
        )}

        <div className="info-field">
          <label>Loan Amount</label>
          <CurrencyInput value={formData.loan_amount || ''} onChange={(value) => handleFieldChange('loan_amount', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>Interest Rate</label>
          <input type="number" step="0.001" value={formData.interest_rate || ''} onChange={(e) => handleFieldChange('interest_rate', e.target.value)} placeholder="%" />
        </div>
        <div className="info-field">
          <label>Loan Term</label>
          <input type="number" value={formData.loan_term || ''} onChange={(e) => handleFieldChange('loan_term', e.target.value)} placeholder="Months" />
        </div>
        <div className="info-field">
          <label>Loan Type</label>
          <select value={formData.loan_type || ''} onChange={(e) => handleFieldChange('loan_type', e.target.value)}>
            <option value="">Select...</option>
            <option value="Conventional">Conventional</option>
            <option value="FHA">FHA</option>
            <option value="VA">VA</option>
            <option value="USDA">USDA</option>
            <option value="Jumbo">Jumbo</option>
            <option value="HELOC">HELOC</option>
          </select>
        </div>
        <div className="info-field">
          <label>Lock Date</label>
          <input type="date" value={formData.lock_date || ''} onChange={(e) => handleFieldChange('lock_date', e.target.value)} />
        </div>
        <div className="info-field">
          <label>Lock Expiration</label>
          <input type="date" value={formData.lock_expiration || ''} onChange={(e) => handleFieldChange('lock_expiration', e.target.value)} />
        </div>
        <div className="info-field">
          <label>APR</label>
          <input type="number" step="0.001" value={formData.apr || ''} onChange={(e) => handleFieldChange('apr', e.target.value)} placeholder="%" />
        </div>
        <div className="info-field">
          <label>Points</label>
          <input type="number" step="0.125" value={formData.points || ''} onChange={(e) => handleFieldChange('points', e.target.value)} />
        </div>
        <div className="info-field">
          <label>Closing Date</label>
          <input type="date" value={formData.closing_date || ''} onChange={(e) => handleFieldChange('closing_date', e.target.value)} />
        </div>
        <div className="info-field">
          <label>Appraisal Value</label>
          <CurrencyInput value={formData.appraisal_value || ''} onChange={(value) => handleFieldChange('appraisal_value', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>LTV %</label>
          <input type="number" step="0.01" value={formData.ltv || ''} onChange={(e) => handleFieldChange('ltv', e.target.value)} placeholder="%" />
        </div>
        <div className="info-field">
          <label>DTI %</label>
          <input type="number" step="0.01" value={formData.dti || ''} onChange={(e) => handleFieldChange('dti', e.target.value)} placeholder="%" />
        </div>
        <div className="info-field">
          <label>CLTV %</label>
          <input type="number" step="0.01" value={formData.cltv || ''} onChange={(e) => handleFieldChange('cltv', e.target.value)} placeholder="%" />
        </div>
      </div>

      {/* 1st Loan Financial Details */}
      <h3 style={{ margin: '2rem 0 1rem 0', fontSize: '16px', fontWeight: '600', color: '#333', borderTop: '1px solid #e0e0e0', paddingTop: '1.5rem' }}>
        1st Loan Financial Details
        <span style={{ fontSize: '12px', fontWeight: '400', color: '#666', marginLeft: '8px' }}>(Synced from Salesforce)</span>
      </h3>
      <div className="info-grid">
        <div className="info-field">
          <label>Rate Type</label>
          <select value={formData.rate_type || ''} onChange={(e) => handleFieldChange('rate_type', e.target.value)}>
            <option value="">Select...</option>
            <option value="Fixed">Fixed</option>
            <option value="ARM">ARM</option>
            <option value="5/1 ARM">5/1 ARM</option>
            <option value="7/1 ARM">7/1 ARM</option>
            <option value="10/1 ARM">10/1 ARM</option>
          </select>
        </div>
        <div className="info-field">
          <label>Monthly P&I Payment</label>
          <CurrencyInput value={formData.monthly_payment || ''} onChange={(value) => handleFieldChange('monthly_payment', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>Property Tax (Annual)</label>
          <CurrencyInput value={formData.property_tax || ''} onChange={(value) => handleFieldChange('property_tax', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>Hazard Insurance (Monthly)</label>
          <CurrencyInput value={formData.hazard_insurance || ''} onChange={(value) => handleFieldChange('hazard_insurance', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>Mortgage Insurance (Monthly)</label>
          <CurrencyInput value={formData.mortgage_insurance || ''} onChange={(value) => handleFieldChange('mortgage_insurance', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>HOA (Monthly)</label>
          <CurrencyInput value={formData.hoa_amount || ''} onChange={(value) => handleFieldChange('hoa_amount', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>Origination Fee</label>
          <CurrencyInput value={formData.origination_fee || ''} onChange={(value) => handleFieldChange('origination_fee', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>Est. Prepaid Interest</label>
          <CurrencyInput value={formData.estimated_prepaid_interest || ''} onChange={(value) => handleFieldChange('estimated_prepaid_interest', value)} placeholder="$0" />
        </div>
      </div>

      {/* ARM Details */}
      {formData.rate_type && formData.rate_type.includes('ARM') && (
        <>
          <h4 style={{ margin: '1.5rem 0 1rem 0', fontSize: '14px', fontWeight: '600', color: '#666' }}>ARM Details</h4>
          <div className="info-grid">
            <div className="info-field">
              <label>Index Rate</label>
              <input type="number" step="0.001" value={formData.index_rate || ''} onChange={(e) => handleFieldChange('index_rate', parseFloat(e.target.value))} placeholder="%" />
            </div>
            <div className="info-field">
              <label>Margin</label>
              <input type="number" step="0.001" value={formData.margin || ''} onChange={(e) => handleFieldChange('margin', parseFloat(e.target.value))} placeholder="%" />
            </div>
          </div>
        </>
      )}

      {/* Present vs Proposed */}
      <h3 style={{ margin: '2rem 0 1rem 0', fontSize: '16px', fontWeight: '600', color: '#333', borderTop: '1px solid #e0e0e0', paddingTop: '1.5rem' }}>
        Present vs Proposed Housing
      </h3>
      <div className="info-grid">
        <div className="info-field">
          <label>Present Monthly Payment</label>
          <CurrencyInput value={formData.present_monthly_payment || ''} onChange={(value) => handleFieldChange('present_monthly_payment', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>Proposed Monthly Payment</label>
          <CurrencyInput value={formData.proposed_monthly_payment || ''} onChange={(value) => handleFieldChange('proposed_monthly_payment', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>Present Housing Expense</label>
          <CurrencyInput value={formData.present_housing_expense || ''} onChange={(value) => handleFieldChange('present_housing_expense', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>Proposed Housing Expense</label>
          <CurrencyInput value={formData.proposed_housing_expense || ''} onChange={(value) => handleFieldChange('proposed_housing_expense', value)} placeholder="$0" />
        </div>
      </div>

      {/* 2nd Loan Details */}
      <h3 style={{ margin: '2rem 0 1rem 0', fontSize: '16px', fontWeight: '600', color: '#333', borderTop: '1px solid #e0e0e0', paddingTop: '1.5rem' }}>
        2nd Loan Details
        <span style={{ fontSize: '12px', fontWeight: '400', color: '#666', marginLeft: '8px' }}>(If Applicable)</span>
      </h3>
      <div className="info-grid">
        <div className="info-field">
          <label>2nd Loan Amount</label>
          <CurrencyInput value={formData.second_loan_amount || ''} onChange={(value) => handleFieldChange('second_loan_amount', value)} placeholder="$0" />
        </div>
        <div className="info-field">
          <label>2nd Loan Rate</label>
          <input type="number" step="0.001" value={formData.second_loan_rate || ''} onChange={(e) => handleFieldChange('second_loan_rate', parseFloat(e.target.value))} placeholder="%" />
        </div>
        <div className="info-field">
          <label>2nd Loan Payment</label>
          <CurrencyInput value={formData.second_loan_payment || ''} onChange={(value) => handleFieldChange('second_loan_payment', value)} placeholder="$0" />
        </div>
      </div>
    </div>
  );
}
