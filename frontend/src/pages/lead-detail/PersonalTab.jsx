import React, { useState } from 'react';
import EmploymentTab from '../../components/EmploymentTab';
import IncomeTab from '../../components/income/IncomeTab';
import { formatPhoneNumber } from '../../utils/phoneUtils';

/**
 * Personal tab — sub-tabs for personal info, employment, income, and assets.
 */
function PersonalTab({
  id,
  lead,
  formData,
  handleFieldChange,
  handleIncomeChange,
  borrowers,
  activeBorrower,
  handleSwitchBorrower,
  handleAddBorrower,
  customFields,
  setCustomFields,
  referralPartners,
}) {
  const [personalSubTab, setPersonalSubTab] = useState('info');
  const [showAddFieldModal, setShowAddFieldModal] = useState(false);
  const [newFieldName, setNewFieldName] = useState('');

  const handleAddCustomField = () => {
    if (!newFieldName.trim()) return;
    const fieldKey = newFieldName.toLowerCase().replace(/\s+/g, '_');
    setCustomFields([...customFields, { key: fieldKey, label: newFieldName }]);
    setNewFieldName('');
    setShowAddFieldModal(false);
  };

  const handleRemoveCustomField = (fieldKey) => {
    setCustomFields(customFields.filter(f => f.key !== fieldKey));
  };

  return (
    <div className="info-section">
      {/* Borrower Selector */}
      <div className="borrower-selector" style={{ marginBottom: '1.5rem' }}>
        <div className="borrower-buttons-group">
          {borrowers.map((borrower, index) => (
            <button
              key={borrower.id}
              className={`borrower-btn ${activeBorrower === index ? 'active' : ''}`}
              onClick={() => handleSwitchBorrower(index)}
            >
              {borrower.name}
              {borrower.type === 'primary' && <span className="borrower-badge">Primary</span>}
            </button>
          ))}
        </div>
        <button className="borrower-add-btn" onClick={handleAddBorrower} title="Add Borrower">
          + Add Person
        </button>
      </div>

      {/* Sub-tabs */}
      <div style={{ display: 'flex', gap: '0', marginBottom: '1.5rem', borderBottom: '1px solid #e0e0e0' }}>
        {['info', 'employment', 'income', 'assets'].map((tab) => (
          <button
            key={tab}
            onClick={() => setPersonalSubTab(tab)}
            style={{
              padding: '10px 20px',
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: personalSubTab === tab ? '600' : '400',
              color: personalSubTab === tab ? '#1a73e8' : '#5f6368',
              borderBottom: personalSubTab === tab ? '2px solid #1a73e8' : '2px solid transparent',
              marginBottom: '-1px'
            }}
          >
            {tab === 'info' ? 'Personal Information' : tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Personal Information Sub-tab */}
      {personalSubTab === 'info' && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ margin: 0 }}>Personal Information</h2>
            <button
              onClick={() => setShowAddFieldModal(true)}
              style={{
                background: '#007bff',
                color: 'white',
                border: 'none',
                borderRadius: '50%',
                width: '32px',
                height: '32px',
                fontSize: '20px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                lineHeight: 1
              }}
              title="Add custom field"
            >
              +
            </button>
          </div>
          <div className="info-grid compact">
            <div className="info-field">
              <label>First Name</label>
              <input
                type="text"
                value={formData.first_name || ''}
                onChange={(e) => handleFieldChange('first_name', e.target.value)}
              />
            </div>
            <div className="info-field">
              <label>Last Name</label>
              <input
                type="text"
                value={formData.last_name || ''}
                onChange={(e) => handleFieldChange('last_name', e.target.value)}
              />
            </div>
            <div className="info-field">
              <label>Email</label>
              <input
                type="email"
                value={formData.email || ''}
                onChange={(e) => handleFieldChange('email', e.target.value)}
              />
            </div>
            <div className="info-field">
              <label>Phone</label>
              <input
                type="tel"
                value={formData.phone || ''}
                onChange={(e) => handleFieldChange('phone', formatPhoneNumber(e.target.value))}
              />
            </div>
            <div className="info-field">
              <label>Preferred Communication</label>
              <select
                value={formData.preferred_communication || ''}
                onChange={(e) => handleFieldChange('preferred_communication', e.target.value)}
                style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ddd', fontSize: '14px' }}
              >
                <option value="">-- Select Preference --</option>
                <option value="email">Email</option>
                <option value="phone">Phone Call</option>
                <option value="text">Text Message</option>
                <option value="voicemail">Voicemail</option>
              </select>
            </div>
            <div className="info-field">
              <label>Referral Partner</label>
              <select
                value={formData.referral_partner_id || ''}
                onChange={(e) => handleFieldChange('referral_partner_id', e.target.value ? parseInt(e.target.value) : null)}
                style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ddd', fontSize: '14px' }}
              >
                <option value="">-- No Partner Assigned --</option>
                {referralPartners.map(partner => (
                  <option key={partner.id} value={partner.id}>
                    {partner.name} {partner.company ? `(${partner.company})` : ''}
                  </option>
                ))}
              </select>
            </div>
            {/* Custom Fields */}
            {customFields.map((field) => (
              <div className="info-field" key={field.key}>
                <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  {field.label}
                  <button
                    onClick={() => handleRemoveCustomField(field.key)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#dc3545',
                      cursor: 'pointer',
                      fontSize: '14px',
                      padding: '0 4px'
                    }}
                    title="Remove field"
                  >
                    x
                  </button>
                </label>
                <input
                  type="text"
                  value={formData[field.key] || ''}
                  onChange={(e) => handleFieldChange(field.key, e.target.value)}
                />
              </div>
            ))}
          </div>

          {/* Add Field Modal */}
          {showAddFieldModal && (
            <div className="modal-overlay" onClick={() => setShowAddFieldModal(false)}>
              <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '400px' }}>
                <div className="modal-header">
                  <h3>Add Custom Field</h3>
                  <button className="modal-close" onClick={() => setShowAddFieldModal(false)}>x</button>
                </div>
                <div className="modal-body">
                  <div className="form-group">
                    <label>Field Name</label>
                    <input
                      type="text"
                      value={newFieldName}
                      onChange={e => setNewFieldName(e.target.value)}
                      className="form-control"
                      placeholder="Enter field name"
                      autoFocus
                    />
                  </div>
                </div>
                <div className="modal-footer">
                  <button className="btn-secondary" onClick={() => setShowAddFieldModal(false)}>Cancel</button>
                  <button
                    className="btn-primary"
                    onClick={handleAddCustomField}
                    disabled={!newFieldName.trim()}
                  >
                    Add Field
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* Employment Sub-tab */}
      {personalSubTab === 'employment' && (
        <EmploymentTab
          leadId={id}
          formData={formData}
          onFieldChange={handleFieldChange}
          entityType="leads"
        />
      )}

      {/* Income Sub-tab */}
      {personalSubTab === 'income' && (
        <IncomeTab
          borrowerId={parseInt(id)}
          loanId={lead?.loan_id || parseInt(id)}
          onIncomeChange={handleIncomeChange}
        />
      )}

      {/* Assets Sub-tab */}
      {personalSubTab === 'assets' && (
        <AssetsContent formData={formData} handleFieldChange={handleFieldChange} />
      )}
    </div>
  );
}

/**
 * Assets sub-tab content — bank accounts, investments, retirement, other, gifts.
 */
function AssetsContent({ formData, handleFieldChange }) {
  const assetFields = [
    'checking_balance', 'savings_balance', 'money_market_balance', 'cd_balance',
    'stocks_bonds_value', 'mutual_funds_value', 'brokerage_value',
    'retirement_401k', 'ira_balance', 'roth_ira_balance', 'pension_value',
    'other_real_estate_value', 'vehicle_value', 'life_insurance_value',
    'other_assets_value', 'gift_amount'
  ];

  const totalAssets = assetFields.reduce((sum, field) => {
    return sum + parseFloat(((formData[field] || '0') + '').replace(/[^0-9.-]/g, ''));
  }, 0);

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>Assets</h2>
      </div>

      {/* Bank Accounts */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Bank Accounts</h3>
        <div className="info-grid compact">
          {[
            ['Checking Account Balance', 'checking_balance'],
            ['Savings Account Balance', 'savings_balance'],
            ['Money Market Balance', 'money_market_balance'],
            ['CD Balance', 'cd_balance'],
          ].map(([label, key]) => (
            <div className="info-field" key={key}>
              <label>{label}</label>
              <input
                type="text"
                value={formData[key] || ''}
                onChange={(e) => handleFieldChange(key, e.target.value)}
                placeholder="$0.00"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Investment Accounts */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Investment Accounts</h3>
        <div className="info-grid compact">
          {[
            ['Stocks/Bonds Value', 'stocks_bonds_value'],
            ['Mutual Funds Value', 'mutual_funds_value'],
            ['Brokerage Account Value', 'brokerage_value'],
          ].map(([label, key]) => (
            <div className="info-field" key={key}>
              <label>{label}</label>
              <input
                type="text"
                value={formData[key] || ''}
                onChange={(e) => handleFieldChange(key, e.target.value)}
                placeholder="$0.00"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Retirement Accounts */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Retirement Accounts</h3>
        <div className="info-grid compact">
          {[
            ['401(k) Balance', 'retirement_401k'],
            ['IRA Balance', 'ira_balance'],
            ['Roth IRA Balance', 'roth_ira_balance'],
            ['Pension Value', 'pension_value'],
          ].map(([label, key]) => (
            <div className="info-field" key={key}>
              <label>{label}</label>
              <input
                type="text"
                value={formData[key] || ''}
                onChange={(e) => handleFieldChange(key, e.target.value)}
                placeholder="$0.00"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Other Assets */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Other Assets</h3>
        <div className="info-grid compact">
          {[
            ['Real Estate (Other Properties)', 'other_real_estate_value'],
            ['Vehicle Value', 'vehicle_value'],
            ['Life Insurance Cash Value', 'life_insurance_value'],
            ['Other Assets', 'other_assets_value'],
          ].map(([label, key]) => (
            <div className="info-field" key={key}>
              <label>{label}</label>
              <input
                type="text"
                value={formData[key] || ''}
                onChange={(e) => handleFieldChange(key, e.target.value)}
                placeholder="$0.00"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Gift Funds */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Gift Funds</h3>
        <div className="info-grid compact">
          <div className="info-field">
            <label>Gift Amount</label>
            <input
              type="text"
              value={formData.gift_amount || ''}
              onChange={(e) => handleFieldChange('gift_amount', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Gift Donor Name</label>
            <input
              type="text"
              value={formData.gift_donor_name || ''}
              onChange={(e) => handleFieldChange('gift_donor_name', e.target.value)}
              placeholder="Donor's full name"
            />
          </div>
          <div className="info-field">
            <label>Gift Donor Relationship</label>
            <select
              value={formData.gift_donor_relationship || ''}
              onChange={(e) => handleFieldChange('gift_donor_relationship', e.target.value)}
              style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ddd', fontSize: '14px' }}
            >
              <option value="">-- Select Relationship --</option>
              <option value="parent">Parent</option>
              <option value="grandparent">Grandparent</option>
              <option value="sibling">Sibling</option>
              <option value="spouse">Spouse</option>
              <option value="other_relative">Other Relative</option>
              <option value="employer">Employer</option>
              <option value="other">Other</option>
            </select>
          </div>
        </div>
      </div>

      {/* Total Assets Summary */}
      <div style={{
        background: '#f8f9fa',
        padding: '1rem',
        borderRadius: '8px',
        marginTop: '1rem',
        border: '1px solid #e0e0e0'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: '600', color: '#333' }}>Total Assets</span>
          <span style={{ fontWeight: '700', fontSize: '18px', color: '#1a73e8' }}>
            ${totalAssets.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>
      </div>
    </>
  );
}

export default PersonalTab;
