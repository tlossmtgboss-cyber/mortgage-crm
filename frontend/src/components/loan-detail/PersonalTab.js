import React, { useState } from 'react';
import EmploymentTab from '../EmploymentTab';
import { formatPhoneNumber } from '../../utils/phoneUtils';

/**
 * Personal tab — sub-tabs for personal info, employment, and assets.
 * Includes borrower selector, custom fields, and the Add Field modal.
 */
function PersonalTab({
  id,
  formData,
  handleFieldChange,
  borrowers,
  activeBorrower,
  handleSwitchBorrower,
  handleAddBorrower,
  customFields,
  setCustomFields,
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

      {/* Sub-tabs for Personal Information, Employment, and Assets */}
      <div style={{ display: 'flex', gap: '0', marginBottom: '1.5rem', borderBottom: '1px solid #e0e0e0' }}>
        {[
          ['info', 'Personal Information'],
          ['employment', 'Employment'],
          ['assets', 'Assets'],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setPersonalSubTab(key)}
            style={{
              padding: '10px 20px',
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: personalSubTab === key ? '600' : '400',
              color: personalSubTab === key ? '#1a73e8' : '#5f6368',
              borderBottom: personalSubTab === key ? '2px solid #1a73e8' : '2px solid transparent',
              marginBottom: '-1px'
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Personal Information Sub-tab Content */}
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
                value={formData.borrower_first_name || (formData.borrower_name || '').split(' ')[0] || ''}
                onChange={(e) => handleFieldChange('borrower_first_name', e.target.value)}
              />
            </div>
            <div className="info-field">
              <label>Last Name</label>
              <input
                type="text"
                value={formData.borrower_last_name || (formData.borrower_name || '').split(' ').slice(1).join(' ') || ''}
                onChange={(e) => handleFieldChange('borrower_last_name', e.target.value)}
              />
            </div>
            <div className="info-field">
              <label>Email</label>
              <input
                type="email"
                value={formData.borrower_email || ''}
                onChange={(e) => handleFieldChange('borrower_email', e.target.value)}
              />
            </div>
            <div className="info-field">
              <label>Phone</label>
              <input
                type="tel"
                value={formData.borrower_phone || ''}
                onChange={(e) => handleFieldChange('borrower_phone', formatPhoneNumber(e.target.value))}
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
                    ×
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
                  <button className="modal-close" onClick={() => setShowAddFieldModal(false)}>×</button>
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

      {/* Employment Sub-tab Content */}
      {personalSubTab === 'employment' && (
        <EmploymentTab
          leadId={id}
          formData={formData}
          onFieldChange={handleFieldChange}
          entityType="loans"
        />
      )}

      {/* Assets Sub-tab Content */}
      {personalSubTab === 'assets' && (
        <AssetsContent formData={formData} handleFieldChange={handleFieldChange} />
      )}
    </div>
  );
}

/**
 * Assets sub-tab content — bank accounts, investments, retirement, other assets, gift funds.
 */
function AssetsContent({ formData, handleFieldChange }) {
  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>Assets</h2>
      </div>

      {/* Bank Accounts Section */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Bank Accounts</h3>
        <div className="info-grid compact">
          <div className="info-field">
            <label>Checking Account Balance</label>
            <input
              type="text"
              value={formData.checking_balance || ''}
              onChange={(e) => handleFieldChange('checking_balance', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Savings Account Balance</label>
            <input
              type="text"
              value={formData.savings_balance || ''}
              onChange={(e) => handleFieldChange('savings_balance', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Money Market Balance</label>
            <input
              type="text"
              value={formData.money_market_balance || ''}
              onChange={(e) => handleFieldChange('money_market_balance', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>CD Balance</label>
            <input
              type="text"
              value={formData.cd_balance || ''}
              onChange={(e) => handleFieldChange('cd_balance', e.target.value)}
              placeholder="$0.00"
            />
          </div>
        </div>
      </div>

      {/* Investment Accounts Section */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Investment Accounts</h3>
        <div className="info-grid compact">
          <div className="info-field">
            <label>Stocks/Bonds Value</label>
            <input
              type="text"
              value={formData.stocks_bonds_value || ''}
              onChange={(e) => handleFieldChange('stocks_bonds_value', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Mutual Funds Value</label>
            <input
              type="text"
              value={formData.mutual_funds_value || ''}
              onChange={(e) => handleFieldChange('mutual_funds_value', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Brokerage Account Value</label>
            <input
              type="text"
              value={formData.brokerage_value || ''}
              onChange={(e) => handleFieldChange('brokerage_value', e.target.value)}
              placeholder="$0.00"
            />
          </div>
        </div>
      </div>

      {/* Retirement Accounts Section */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Retirement Accounts</h3>
        <div className="info-grid compact">
          <div className="info-field">
            <label>401(k) Balance</label>
            <input
              type="text"
              value={formData.retirement_401k || ''}
              onChange={(e) => handleFieldChange('retirement_401k', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>IRA Balance</label>
            <input
              type="text"
              value={formData.ira_balance || ''}
              onChange={(e) => handleFieldChange('ira_balance', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Roth IRA Balance</label>
            <input
              type="text"
              value={formData.roth_ira_balance || ''}
              onChange={(e) => handleFieldChange('roth_ira_balance', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Pension Value</label>
            <input
              type="text"
              value={formData.pension_value || ''}
              onChange={(e) => handleFieldChange('pension_value', e.target.value)}
              placeholder="$0.00"
            />
          </div>
        </div>
      </div>

      {/* Other Assets Section */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '1rem', color: '#333' }}>Other Assets</h3>
        <div className="info-grid compact">
          <div className="info-field">
            <label>Real Estate (Other Properties)</label>
            <input
              type="text"
              value={formData.other_real_estate_value || ''}
              onChange={(e) => handleFieldChange('other_real_estate_value', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Vehicle Value</label>
            <input
              type="text"
              value={formData.vehicle_value || ''}
              onChange={(e) => handleFieldChange('vehicle_value', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Life Insurance Cash Value</label>
            <input
              type="text"
              value={formData.life_insurance_value || ''}
              onChange={(e) => handleFieldChange('life_insurance_value', e.target.value)}
              placeholder="$0.00"
            />
          </div>
          <div className="info-field">
            <label>Other Assets</label>
            <input
              type="text"
              value={formData.other_assets_value || ''}
              onChange={(e) => handleFieldChange('other_assets_value', e.target.value)}
              placeholder="$0.00"
            />
          </div>
        </div>
      </div>

      {/* Gift Funds Section */}
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
              <option value="other_relative">Other Relative</option>
              <option value="employer">Employer</option>
              <option value="friend">Friend</option>
            </select>
          </div>
        </div>
      </div>
    </>
  );
}

export default PersonalTab;
