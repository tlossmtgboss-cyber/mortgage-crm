import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { loansAPI, activitiesAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import './LeadDetail.css';

function LoanDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [loan, setLoan] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(true);
  const [formData, setFormData] = useState({});
  const [activeTab, setActiveTab] = useState('personal');
  const [borrowers, setBorrowers] = useState([]);
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [saveTimeout, setSaveTimeout] = useState(null);

  useEffect(() => {
    loadLoanData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadLoanData = async () => {
    try {
      setLoading(true);
      const loanData = await loansAPI.getById(id);
      setLoan(loanData);
      setFormData(loanData);

      // Initialize borrowers array
      const borrowersList = [
        {
          id: 0,
          name: loanData.borrower_name || 'Primary Borrower',
          type: 'primary',
          data: {
            name: loanData.borrower_name,
            email: loanData.borrower_email,
            phone: loanData.borrower_phone,
          }
        }
      ];

      // Add co-borrower if exists
      if (loanData.coborrower_name) {
        borrowersList.push({
          id: 1,
          name: loanData.coborrower_name,
          type: 'co-borrower',
          data: {
            name: loanData.coborrower_name,
          }
        });
      }

      setBorrowers(borrowersList);
    } catch (error) {
      console.error('Failed to load loan data:', error);
      alert('Failed to load loan details');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      await loansAPI.update(id, formData);
      setLoan(formData);
      setEditing(false);
      alert('Loan updated successfully!');
    } catch (error) {
      console.error('Failed to save loan:', error);
      alert('Failed to save changes');
    }
  };

  const handleCancel = () => {
    setFormData(loan);
  };

  const handleFieldChange = (field, value) => {
    const updatedData = { ...formData, [field]: value };
    setFormData(updatedData);

    // Auto-save after 1 second of no typing
    if (saveTimeout) clearTimeout(saveTimeout);
    setSaveTimeout(setTimeout(async () => {
      try {
        await loansAPI.update(id, { [field]: value });
      } catch (error) {
        console.error('Auto-save failed:', error);
      }
    }, 1000));
  };

  const handleSwitchBorrower = (borrowerIndex) => {
    setActiveBorrower(borrowerIndex);
    const borrower = borrowers[borrowerIndex];
    if (borrower && borrower.data) {
      setFormData({...formData, ...borrower.data});
    }
  };

  if (loading) {
    return (
      <div className="lead-detail-page">
        <div className="loading">Loading loan details...</div>
      </div>
    );
  }

  if (!loan) {
    return (
      <div className="lead-detail-page">
        <div className="error">Loan not found</div>
      </div>
    );
  }

  const currentBorrower = borrowers[activeBorrower] || borrowers[0];

  return (
    <div className="lead-detail-page">
      {/* Header */}
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/loans')}>
          ← Back to Loans
        </button>
        <div className="header-actions">
          {editing ? (
            <>
              <button className="btn-save" onClick={handleSave}>Save</button>
              <button className="btn-cancel" onClick={handleCancel}>Cancel</button>
            </>
          ) : (
            <button className="btn-edit-header" onClick={() => setEditing(true)}>
              ✏️ Edit
            </button>
          )}
        </div>
      </div>

      {/* Loan Information Toolbar */}
      <div className="loan-toolbar">
        <div className="toolbar-header">
          <h3>Loan Details</h3>
        </div>
        <div className="loan-fields-grid">
          <div className="loan-field">
            <label>Loan Amount</label>
            <input
              type="number"
              value={formData.amount || ''}
              onChange={(e) => handleFieldChange('amount', parseFloat(e.target.value))}
              placeholder="$"
            />
          </div>

          <div className="loan-field">
            <label>Interest Rate</label>
            <input
              type="number"
              step="0.001"
              value={formData.interest_rate || ''}
              onChange={(e) => handleFieldChange('interest_rate', parseFloat(e.target.value))}
              placeholder="%"
            />
          </div>

          <div className="loan-field">
            <label>Loan Term</label>
            <input
              type="number"
              value={formData.term || ''}
              onChange={(e) => handleFieldChange('term', parseInt(e.target.value))}
              placeholder="months"
            />
          </div>

          <div className="loan-field">
            <label>Loan Type</label>
            <input
              type="text"
              value={formData.product_type || ''}
              onChange={(e) => handleFieldChange('product_type', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Lock Date</label>
            <input
              type="date"
              value={formData.lock_date ? formData.lock_date.split('T')[0] : ''}
              onChange={(e) => handleFieldChange('lock_date', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Lock Expiration</label>
            <input
              type="date"
              value={formData.lock_expiration ? formData.lock_expiration.split('T')[0] : ''}
              onChange={(e) => handleFieldChange('lock_expiration', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>APR</label>
            <input
              type="number"
              step="0.001"
              value={formData.apr || ''}
              onChange={(e) => handleFieldChange('apr', parseFloat(e.target.value))}
              placeholder="%"
            />
          </div>

          <div className="loan-field">
            <label>Points</label>
            <input
              type="number"
              step="0.125"
              value={formData.points || ''}
              onChange={(e) => handleFieldChange('points', parseFloat(e.target.value))}
            />
          </div>

          <div className="loan-field">
            <label>Lender</label>
            <input
              type="text"
              value={formData.lender || ''}
              onChange={(e) => handleFieldChange('lender', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Loan Officer</label>
            <input
              type="text"
              value={formData.loan_officer_name || ''}
              onChange={(e) => handleFieldChange('loan_officer_name', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Processor</label>
            <input
              type="text"
              value={formData.processor || ''}
              onChange={(e) => handleFieldChange('processor', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Underwriter</label>
            <input
              type="text"
              value={formData.underwriter || ''}
              onChange={(e) => handleFieldChange('underwriter', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Closing Date</label>
            <input
              type="date"
              value={formData.closing_date ? formData.closing_date.split('T')[0] : ''}
              onChange={(e) => handleFieldChange('closing_date', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Appraisal Value</label>
            <input
              type="number"
              value={formData.appraisal_value || ''}
              onChange={(e) => handleFieldChange('appraisal_value', parseFloat(e.target.value))}
              placeholder="$"
            />
          </div>

          <div className="loan-field">
            <label>LTV %</label>
            <input
              type="number"
              step="0.01"
              value={formData.ltv || ''}
              onChange={(e) => handleFieldChange('ltv', parseFloat(e.target.value))}
              placeholder="%"
            />
          </div>

          <div className="loan-field">
            <label>DTI %</label>
            <input
              type="number"
              step="0.01"
              value={formData.dti || ''}
              onChange={(e) => handleFieldChange('dti', parseFloat(e.target.value))}
              placeholder="%"
            />
          </div>
        </div>
      </div>

      {/* Borrower Selector */}
      <div className="borrower-selector">
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

      {/* Tab Navigation */}
      <div className="profile-tabs">
        <button
          className={`tab-btn ${activeTab === 'personal' ? 'active' : ''}`}
          onClick={() => setActiveTab('personal')}
        >
          Personal
        </button>
        <button
          className={`tab-btn ${activeTab === 'employment' ? 'active' : ''}`}
          onClick={() => setActiveTab('employment')}
        >
          Employment
        </button>
        <button
          className={`tab-btn ${activeTab === 'loan' ? 'active' : ''}`}
          onClick={() => setActiveTab('loan')}
        >
          Loan
        </button>
        <button
          className={`tab-btn ${activeTab === 'conversation' ? 'active' : ''}`}
          onClick={() => setActiveTab('conversation')}
        >
          Conversation Log
        </button>
        <button
          className={`tab-btn ${activeTab === 'checklist' ? 'active' : ''}`}
          onClick={() => setActiveTab('checklist')}
        >
          Checklist
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content-container">
        {/* Personal Information Tab */}
        {activeTab === 'personal' && (
          <div className="tab-content">
            <h2>Personal Information</h2>
            <div className="form-section">
              <div className="form-row">
                <div className="form-group">
                  <label>First Name</label>
                  <input
                    type="text"
                    value={currentBorrower.data.name?.split(' ')[0] || ''}
                    disabled
                  />
                </div>
                <div className="form-group">
                  <label>Last Name</label>
                  <input
                    type="text"
                    value={currentBorrower.data.name?.split(' ').slice(1).join(' ') || ''}
                    disabled
                  />
                </div>
                <div className="form-group">
                  <label>Email</label>
                  {currentBorrower.data.email ? (
                    <ClickableEmail email={currentBorrower.data.email} />
                  ) : (
                    <input type="email" value="" placeholder="No email provided" disabled />
                  )}
                </div>
                <div className="form-group">
                  <label>Phone</label>
                  {currentBorrower.data.phone ? (
                    <ClickablePhone phone={currentBorrower.data.phone} />
                  ) : (
                    <input type="tel" value="" placeholder="No phone provided" disabled />
                  )}
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Loan Number</label>
                  <input
                    type="text"
                    value={formData.loan_number || ''}
                    onChange={(e) => handleFieldChange('loan_number', e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Employment Tab */}
        {activeTab === 'employment' && (
          <div className="tab-content">
            <h2>Employment Information</h2>
            <div className="form-section">
              <p className="info-text">Employment information coming soon</p>
            </div>
          </div>
        )}

        {/* Loan Tab */}
        {activeTab === 'loan' && (
          <div className="tab-content">
            <h2>Property & Loan Details</h2>
            <div className="form-section">
              <div className="form-row">
                <div className="form-group">
                  <label>Property Address</label>
                  <input
                    type="text"
                    value={formData.property_address || ''}
                    onChange={(e) => handleFieldChange('property_address', e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Property City</label>
                  <input
                    type="text"
                    value={formData.property_city || ''}
                    onChange={(e) => handleFieldChange('property_city', e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Property State</label>
                  <input
                    type="text"
                    value={formData.property_state || ''}
                    onChange={(e) => handleFieldChange('property_state', e.target.value)}
                    maxLength="2"
                  />
                </div>
                <div className="form-group">
                  <label>Property ZIP</label>
                  <input
                    type="text"
                    value={formData.property_zip || ''}
                    onChange={(e) => handleFieldChange('property_zip', e.target.value)}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group" style={{gridColumn: 'span 4'}}>
                  <label>Notes</label>
                  <textarea
                    rows="4"
                    value={formData.notes || ''}
                    onChange={(e) => handleFieldChange('notes', e.target.value)}
                    placeholder="Add notes about this loan..."
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Conversation Log Tab */}
        {activeTab === 'conversation' && (
          <div className="tab-content">
            <h2>Conversation Log</h2>
            <div className="activity-feed">
              {activities.length === 0 ? (
                <p className="no-activities">No conversation history yet</p>
              ) : (
                activities.map((activity) => (
                  <div key={activity.id} className="activity-item">
                    <div className="activity-icon">{activity.type}</div>
                    <div className="activity-details">
                      <div className="activity-header">
                        <strong>{activity.title}</strong>
                        <span className="activity-time">
                          {new Date(activity.created_at).toLocaleString()}
                        </span>
                      </div>
                      <p>{activity.description}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* Checklist Tab */}
        {activeTab === 'checklist' && (
          <div className="tab-content">
            <h2>Loan Checklist</h2>
            <div className="form-section">
              <p className="info-text">Loan checklist coming soon</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default LoanDetail;
