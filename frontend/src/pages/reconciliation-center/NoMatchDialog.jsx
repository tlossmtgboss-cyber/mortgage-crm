import React from 'react';
import { ALL_STAGES } from './constants';
import { formatFieldName } from './helpers';

/**
 * NoMatchDialog - Modal shown when no matching borrower is found.
 * Allows creating a new borrower with name, loan number, stage, and referral partner.
 * Includes an embedded Create Referral Partner sub-dialog.
 */
export default function NoMatchDialog({
  noMatchData,
  newBorrowerForm,
  setNewBorrowerForm,
  processingAction,
  handleCreateBorrower,
  handleCancelNoMatch,
  // Referral partner props
  referralSearchTerm,
  searchReferralPartners,
  showReferralDropdown,
  setShowReferralDropdown,
  referralSearchResults,
  selectReferralPartner,
  selectedReferralPartner,
  clearReferralPartner,
  // Create referral partner sub-dialog
  showCreateReferralDialog,
  setShowCreateReferralDialog,
  newReferralPartner,
  setNewReferralPartner,
  handleCreateReferralPartner,
}) {
  return (
    <div className="dialog-overlay">
      <div className="dialog-content no-match-dialog">
        <div className="dialog-header">
          <h3>No Matching Borrower Found</h3>
          <button className="dialog-close" onClick={handleCancelNoMatch}>&times;</button>
        </div>
        <div className="dialog-body">
          <p>No existing borrower profile matches this extracted data. Would you like to create a new borrower?</p>

          {noMatchData?.fields && (
            <div className="extracted-summary">
              <h4>Extracted Information:</h4>
              <ul>
                {Object.entries(noMatchData.fields).map(([key, fieldData]) => {
                  const displayValue = typeof fieldData === 'object' ? fieldData.value : fieldData;
                  return displayValue && <li key={key}><strong>{formatFieldName(key)}:</strong> {displayValue}</li>;
                })}
              </ul>
            </div>
          )}

          <div className="new-borrower-form">
            <h4>New Borrower Details:</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
              <div className="form-group">
                <label>First Name *</label>
                <input
                  type="text"
                  value={newBorrowerForm.first_name}
                  onChange={(e) => setNewBorrowerForm(prev => ({ ...prev, first_name: e.target.value }))}
                  placeholder="Enter first name"
                  required
                  style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                />
              </div>
              <div className="form-group">
                <label>Last Name *</label>
                <input
                  type="text"
                  value={newBorrowerForm.last_name}
                  onChange={(e) => setNewBorrowerForm(prev => ({ ...prev, last_name: e.target.value }))}
                  placeholder="Enter last name"
                  required
                  style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                />
              </div>
              <div className="form-group">
                <label>Loan Number</label>
                <input
                  type="text"
                  value={newBorrowerForm.loan_number}
                  onChange={(e) => setNewBorrowerForm(prev => ({ ...prev, loan_number: e.target.value }))}
                  placeholder="Enter loan number"
                  style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                />
              </div>
            </div>

            {/* Stage Selector - All Stages */}
            <div className="form-group" style={{ marginTop: '15px' }}>
              <label style={{ fontWeight: '600', marginBottom: '8px', display: 'block' }}>
                Stage *
              </label>
              <select
                value={newBorrowerForm.loan_stage}
                onChange={(e) => setNewBorrowerForm(prev => ({ ...prev, loan_stage: e.target.value }))}
                style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '14px' }}
              >
                <optgroup label="Lead Stages">
                  {ALL_STAGES.filter(s => s.category === 'Lead').map(stage => (
                    <option key={stage.value} value={stage.value}>{stage.label}</option>
                  ))}
                </optgroup>
                <optgroup label="Active Loan Stages">
                  {ALL_STAGES.filter(s => s.category === 'Active Loan').map(stage => (
                    <option key={stage.value} value={stage.value}>{stage.label}</option>
                  ))}
                </optgroup>
                <optgroup label="MUM / Portfolio">
                  {ALL_STAGES.filter(s => s.category === 'MUM').map(stage => (
                    <option key={stage.value} value={stage.value}>{stage.label}</option>
                  ))}
                </optgroup>
                <optgroup label="Other">
                  {ALL_STAGES.filter(s => s.category === 'Other').map(stage => (
                    <option key={stage.value} value={stage.value}>{stage.label}</option>
                  ))}
                </optgroup>
              </select>
            </div>

            {/* Searchable Referral Partner */}
            <div className="form-group" style={{ marginTop: '15px', position: 'relative' }}>
              <label style={{ fontWeight: '600', marginBottom: '8px', display: 'block' }}>
                Referral Partner
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  value={referralSearchTerm}
                  onChange={(e) => searchReferralPartners(e.target.value)}
                  onFocus={() => referralSearchTerm && setShowReferralDropdown(true)}
                  placeholder="Type to search referral partners..."
                  style={{
                    width: '100%',
                    padding: '10px',
                    paddingRight: selectedReferralPartner ? '35px' : '10px',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px',
                    fontSize: '14px'
                  }}
                />
                {selectedReferralPartner && (
                  <button
                    onClick={clearReferralPartner}
                    style={{
                      position: 'absolute',
                      right: '10px',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      fontSize: '16px',
                      color: '#6b7280'
                    }}
                  >
                    &#10005;
                  </button>
                )}
              </div>

              {/* Search Results Dropdown */}
              {showReferralDropdown && (
                <div style={{
                  position: 'absolute',
                  top: '100%',
                  left: 0,
                  right: 0,
                  background: 'white',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  maxHeight: '200px',
                  overflowY: 'auto',
                  zIndex: 1000,
                  boxShadow: '0 4px 6px rgba(0,0,0,0.1)'
                }}>
                  {referralSearchResults.length > 0 ? (
                    referralSearchResults.map(partner => (
                      <div
                        key={partner.id}
                        onClick={() => selectReferralPartner(partner)}
                        style={{
                          padding: '10px 15px',
                          cursor: 'pointer',
                          borderBottom: '1px solid #f3f4f6',
                          transition: 'background 0.2s'
                        }}
                        onMouseEnter={(e) => e.target.style.background = '#f3f4f6'}
                        onMouseLeave={(e) => e.target.style.background = 'white'}
                      >
                        <div style={{ fontWeight: '500' }}>{partner.name}</div>
                        {(partner.company || partner.company_name) && (
                          <div style={{ fontSize: '12px', color: '#6b7280' }}>{partner.company || partner.company_name}</div>
                        )}
                        {partner.type && (
                          <span style={{
                            fontSize: '11px',
                            background: '#e5e7eb',
                            padding: '2px 8px',
                            borderRadius: '9999px',
                            marginTop: '4px',
                            display: 'inline-block'
                          }}>
                            {partner.type}
                          </span>
                        )}
                      </div>
                    ))
                  ) : (
                    <div style={{ padding: '15px', textAlign: 'center' }}>
                      <p style={{ color: '#6b7280', margin: '0 0 10px 0' }}>
                        No matching partners found
                      </p>
                      <button
                        onClick={() => {
                          setNewReferralPartner(prev => ({ ...prev, name: referralSearchTerm }));
                          setShowCreateReferralDialog(true);
                          setShowReferralDropdown(false);
                        }}
                        style={{
                          background: '#3b82f6',
                          color: 'white',
                          border: 'none',
                          padding: '8px 16px',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          fontSize: '13px'
                        }}
                      >
                        + Add "{referralSearchTerm}" as new partner
                      </button>
                    </div>
                  )}
                </div>
              )}

              {selectedReferralPartner && (
                <div style={{
                  marginTop: '8px',
                  padding: '8px 12px',
                  background: '#ecfdf5',
                  borderRadius: '6px',
                  fontSize: '13px',
                  color: '#2D7A52'
                }}>
                  Selected: {selectedReferralPartner.name}
                  {(selectedReferralPartner.company || selectedReferralPartner.company_name) && ` (${selectedReferralPartner.company || selectedReferralPartner.company_name})`}
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="dialog-footer">
          <button className="btn btn-secondary" onClick={handleCancelNoMatch}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleCreateBorrower}
            disabled={processingAction || !newBorrowerForm.first_name || !newBorrowerForm.last_name}
          >
            {processingAction ? 'Creating...' : 'Create Borrower & Approve'}
          </button>
        </div>
      </div>

      {/* Create New Referral Partner Dialog */}
      {showCreateReferralDialog && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 2000
        }}>
          <div style={{
            background: 'white',
            borderRadius: '12px',
            width: '450px',
            maxWidth: '90%',
            boxShadow: '0 25px 50px rgba(0,0,0,0.25)'
          }}>
            <div style={{
              padding: '20px',
              borderBottom: '1px solid #e5e7eb',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <h3 style={{ margin: 0, fontSize: '18px' }}>Add New Referral Partner</h3>
              <button
                onClick={() => setShowCreateReferralDialog(false)}
                style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: '#6b7280' }}
              >
                &times;
              </button>
            </div>
            <div style={{ padding: '20px' }}>
              <div className="form-group" style={{ marginBottom: '15px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Name *</label>
                <input
                  type="text"
                  value={newReferralPartner.name}
                  onChange={(e) => setNewReferralPartner(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="Full name"
                  style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                />
              </div>
              <div className="form-group" style={{ marginBottom: '15px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Company</label>
                <input
                  type="text"
                  value={newReferralPartner.company}
                  onChange={(e) => setNewReferralPartner(prev => ({ ...prev, company: e.target.value }))}
                  placeholder="Company name (optional)"
                  style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '15px' }}>
                <div className="form-group">
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Email</label>
                  <input
                    type="email"
                    value={newReferralPartner.email}
                    onChange={(e) => setNewReferralPartner(prev => ({ ...prev, email: e.target.value }))}
                    placeholder="Email (optional)"
                    style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                  />
                </div>
                <div className="form-group">
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Phone</label>
                  <input
                    type="tel"
                    value={newReferralPartner.phone}
                    onChange={(e) => setNewReferralPartner(prev => ({ ...prev, phone: e.target.value }))}
                    placeholder="Phone (optional)"
                    style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                  />
                </div>
              </div>
              <div className="form-group">
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Type</label>
                <select
                  value={newReferralPartner.type}
                  onChange={(e) => setNewReferralPartner(prev => ({ ...prev, type: e.target.value }))}
                  style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
                >
                  <option value="realtor">Realtor</option>
                  <option value="builder">Builder</option>
                  <option value="financial_advisor">Financial Advisor</option>
                  <option value="attorney">Attorney</option>
                  <option value="cpa">CPA</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </div>
            <div style={{
              padding: '15px 20px',
              borderTop: '1px solid #e5e7eb',
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '10px'
            }}>
              <button
                onClick={() => setShowCreateReferralDialog(false)}
                style={{
                  padding: '10px 20px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  background: 'white',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleCreateReferralPartner}
                disabled={!newReferralPartner.name.trim()}
                style={{
                  padding: '10px 20px',
                  border: 'none',
                  borderRadius: '6px',
                  background: newReferralPartner.name.trim() ? '#3b82f6' : '#9ca3af',
                  color: 'white',
                  cursor: newReferralPartner.name.trim() ? 'pointer' : 'not-allowed'
                }}
              >
                Create Partner
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
