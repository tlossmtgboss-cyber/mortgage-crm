import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ClickablePhone } from '../../components/ClickableContact';
import { formatPhoneNumber } from '../../utils/phoneUtils';
import { circleContactTypes, getContactIcon } from './constants';

/**
 * Circle tab — Circle of Cashflow referral opportunities + Circle of Influence contacts.
 */
function CircleTab({
  circleContacts,
  setCircleContacts,
  showCircleModal,
  setShowCircleModal,
  circleForm,
  setCircleForm,
  searchResults,
  setSearchResults,
  showSearchResults,
  setShowSearchResults,
  searchLoading,
  cashflowOpportunities,
  cashflowReferrals,
  cashflowLoading,
  onNameChange,
  onSelectSearchResult,
  onSubmit,
}) {
  const navigate = useNavigate();

  const handleEditCircleContact = (contact) => {
    setCircleForm({
      name: contact.name,
      email: contact.email || '',
      phone: contact.phone || '',
      type: contact.type,
      notes: contact.notes || '',
      editId: contact.id,
      leadId: contact.leadId
    });
    setShowCircleModal(true);
  };

  const handleDeleteCircleContact = (contactId) => {
    setCircleContacts(circleContacts.filter(c => c.id !== contactId));
  };

  return (
    <div className="info-section">
      <h2>Circle</h2>
      <div className="circle-content">
        {/* Circle of Cashflow Section */}
        <div className="cashflow-section" style={{ marginBottom: '30px' }}>
          <h3 style={{ marginBottom: '15px', color: '#2e7d32' }}>Circle of Cashflow - Referral Opportunities</h3>

          {cashflowLoading ? (
            <p>Loading referral data...</p>
          ) : (
            <>
              {cashflowOpportunities.length > 0 ? (
                <div className="circle-grid" style={{ marginBottom: '20px' }}>
                  {cashflowOpportunities.map(opp => (
                    <div key={opp.id} className="circle-card" style={{ borderLeft: '4px solid #ff9800' }}>
                      <div className="circle-header">
                        <h3>💡 {opp.category.replace('_', ' ').toUpperCase()}</h3>
                        <span style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: '12px',
                          backgroundColor: opp.status === 'detected' ? '#fff3e0' : opp.status === 'sent' ? '#e8f5e9' : '#e3f2fd',
                          color: opp.status === 'detected' ? '#e65100' : opp.status === 'sent' ? '#2e7d32' : '#1565c0'
                        }}>
                          {opp.status}
                        </span>
                      </div>
                      <div className="circle-list">
                        <p style={{ fontSize: '14px', color: '#666', margin: '8px 0' }}>{opp.ai_reasoning}</p>
                        <p style={{ fontSize: '12px', color: '#999' }}>Priority: {opp.priority}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#999', fontStyle: 'italic', marginBottom: '20px' }}>
                  No referral opportunities detected. Submit a financial questionnaire to identify opportunities.
                </p>
              )}

              {cashflowReferrals.length > 0 && (
                <div style={{ marginBottom: '20px' }}>
                  <h4 style={{ marginBottom: '10px' }}>Referral History</h4>
                  <div className="circle-grid">
                    {cashflowReferrals.map(ref => (
                      <div key={ref.id} className="circle-card" style={{ borderLeft: '4px solid #4caf50' }}>
                        <div className="circle-header">
                          <h3>📤 {ref.partner_name || 'Partner'}</h3>
                          <span style={{ fontSize: '12px', color: '#666' }}>{ref.status}</span>
                        </div>
                        <div className="circle-list">
                          <p style={{ fontSize: '14px' }}>{ref.category.replace('_', ' ')}</p>
                          <p style={{ fontSize: '12px', color: '#999' }}>{new Date(ref.referral_date).toLocaleDateString()}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Circle of Influence Section */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
          <h3 style={{ margin: 0 }}>Circle of Influence</h3>
          <button
            className="btn-add-circle"
            onClick={() => setShowCircleModal(true)}
            style={{ padding: '8px 16px' }}
          >
            + Add Contact
          </button>
        </div>
        <p className="circle-description">
          Add and manage the borrower's circle of influence - family members, co-borrowers,
          real estate agents, and other key contacts involved in the loan process.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {circleContacts.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', color: '#999', backgroundColor: '#f8f9fa', borderRadius: '8px', border: '1px solid #e9ecef' }}>
              No contacts added yet. Click "+ Add Contact" to add someone to the circle of influence.
            </div>
          ) : (
            circleContacts.map(contact => (
              <div key={contact.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 12px', backgroundColor: '#f8f9fa', borderRadius: '6px', border: '1px solid #e9ecef' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                  <span style={{ fontSize: '18px' }}>{getContactIcon(contact.type)}</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {contact.leadId ? (
                        <span
                          onClick={() => navigate(`/leads/${contact.leadId}`)}
                          style={{ fontWeight: '500', color: '#217f8d', cursor: 'pointer', textDecoration: 'none' }}
                          onMouseEnter={e => e.target.style.textDecoration = 'underline'}
                          onMouseLeave={e => e.target.style.textDecoration = 'none'}
                        >
                          {contact.name}
                        </span>
                      ) : (
                        <span style={{ fontWeight: '500' }}>{contact.name}</span>
                      )}
                      <span style={{ fontSize: '12px', padding: '2px 8px', backgroundColor: '#e0f2f1', color: '#00695c', borderRadius: '12px' }}>{contact.type}</span>
                    </div>
                    <div style={{ fontSize: '13px', color: '#666' }}>
                      {contact.email && <span>{contact.email}</span>}
                      {contact.email && contact.phone && <span> &bull; </span>}
                      {contact.phone && <ClickablePhone phone={contact.phone} />}
                    </div>
                    {contact.notes && <div style={{ fontSize: '12px', color: '#999', fontStyle: 'italic' }}>{contact.notes}</div>}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    onClick={() => handleEditCircleContact(contact)}
                    style={{ background: 'none', border: 'none', color: '#217f8d', cursor: 'pointer', fontSize: '14px', padding: '4px 8px' }}
                    title="Edit contact"
                  >
                    ✏️
                  </button>
                  <button
                    onClick={() => handleDeleteCircleContact(contact.id)}
                    style={{ background: 'none', border: 'none', color: '#dc3545', cursor: 'pointer', fontSize: '16px', padding: '4px 8px' }}
                    title="Remove contact"
                  >
                    x
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Add/Edit Referral Partner Modal */}
        {showCircleModal && (
          <div className="modal-overlay" onClick={() => { setShowCircleModal(false); setShowSearchResults(false); }}>
            <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '500px' }}>
              <div className="modal-header">
                <h3>{circleForm.editId ? 'Edit Referral Partner' : 'Add Referral Partner'}</h3>
                <button className="modal-close" onClick={() => { setShowCircleModal(false); setShowSearchResults(false); setCircleForm({ name: '', email: '', phone: '', type: 'Co-Borrower', notes: '' }); }}>x</button>
              </div>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div className="form-group">
                  <label>Contact Type *</label>
                  <select
                    value={circleForm.type}
                    onChange={e => setCircleForm({...circleForm, type: e.target.value})}
                    className="form-control"
                  >
                    {circleContactTypes.map(type => (
                      <option key={type.value} value={type.value}>{type.value}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group" style={{ position: 'relative' }}>
                  <label>Name *</label>
                  <input
                    type="text"
                    value={circleForm.name}
                    onChange={onNameChange}
                    onFocus={() => circleForm.name.length >= 2 && setShowSearchResults(true)}
                    className="form-control"
                    placeholder="Start typing to search..."
                    autoComplete="off"
                  />
                  {searchLoading && (
                    <div style={{ position: 'absolute', right: '10px', top: '35px', color: '#999', fontSize: '12px' }}>
                      Searching...
                    </div>
                  )}
                  {showSearchResults && searchResults.length > 0 && (
                    <div style={{
                      position: 'absolute', top: '100%', left: 0, right: 0,
                      backgroundColor: 'white', border: '1px solid #ddd', borderRadius: '4px',
                      boxShadow: '0 4px 12px rgba(0,0,0,0.15)', maxHeight: '200px', overflowY: 'auto', zIndex: 1000
                    }}>
                      {searchResults.map(result => (
                        <div
                          key={result.id}
                          onClick={() => onSelectSearchResult(result)}
                          style={{ padding: '10px 12px', cursor: 'pointer', borderBottom: '1px solid #eee', transition: 'background-color 0.15s' }}
                          onMouseEnter={e => e.target.style.backgroundColor = '#f5f5f5'}
                          onMouseLeave={e => e.target.style.backgroundColor = 'white'}
                        >
                          <div style={{ fontWeight: '500' }}>{result.name}</div>
                          <div style={{ fontSize: '12px', color: '#666' }}>
                            {result.email && <span>{result.email}</span>}
                            {result.email && result.phone && <span> &bull; </span>}
                            {result.phone && <ClickablePhone phone={result.phone} />}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="form-group">
                  <label>Email</label>
                  <input type="email" value={circleForm.email} onChange={e => setCircleForm({...circleForm, email: e.target.value})} className="form-control" placeholder="Enter email address" />
                </div>
                <div className="form-group">
                  <label>Phone</label>
                  <input type="tel" value={circleForm.phone} onChange={e => setCircleForm({...circleForm, phone: formatPhoneNumber(e.target.value)})} className="form-control" placeholder="Enter phone number" />
                </div>
                <div className="form-group">
                  <label>Notes</label>
                  <textarea value={circleForm.notes} onChange={e => setCircleForm({...circleForm, notes: e.target.value})} className="form-control" placeholder="Add any notes about this contact" rows={3} />
                </div>
              </div>
              <div className="modal-footer">
                <button className="btn-secondary" onClick={() => setShowCircleModal(false)}>Cancel</button>
                <button className="btn-primary" onClick={onSubmit} disabled={!circleForm.name.trim()}>
                  {circleForm.editId ? 'Save Changes' : 'Add Contact'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default CircleTab;
