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
    } catch (error) {
      console.error('Failed to save loan:', error);
      alert('Failed to save changes');
    }
  };

  const handleChange = (field, value) => {
    const updatedData = { ...formData, [field]: value };
    setFormData(updatedData);

    // Auto-save after 1 second of no typing
    if (saveTimeout) clearTimeout(saveTimeout);
    setSaveTimeout(setTimeout(() => handleSave(), 1000));
  };

  if (loading) {
    return <div className="loading">Loading loan details...</div>;
  }

  if (!loan) {
    return <div className="error">Loan not found</div>;
  }

  const currentBorrower = borrowers[activeBorrower] || borrowers[0];

  return (
    <div className="lead-detail">
      <div className="detail-header">
        <button className="back-btn" onClick={() => navigate('/loans')}>
          ← Back to Loans
        </button>
        <h1>{loan.borrower_name}</h1>
      </div>

      <div className="detail-content">
        {/* Borrower Tabs */}
        {borrowers.length > 1 && (
          <div className="borrower-tabs">
            {borrowers.map((borrower, index) => (
              <button
                key={borrower.id}
                className={`borrower-tab ${activeBorrower === index ? 'active' : ''}`}
                onClick={() => setActiveBorrower(index)}
              >
                {borrower.name}
                {borrower.type === 'primary' && <span className="badge primary-badge">PRIMARY</span>}
              </button>
            ))}
          </div>
        )}

        {/* Tabs */}
        <div className="tabs">
          <button
            className={`tab ${activeTab === 'personal' ? 'active' : ''}`}
            onClick={() => setActiveTab('personal')}
          >
            Personal
          </button>
          <button
            className={`tab ${activeTab === 'employment' ? 'active' : ''}`}
            onClick={() => setActiveTab('employment')}
          >
            Employment
          </button>
          <button
            className={`tab ${activeTab === 'loan' ? 'active' : ''}`}
            onClick={() => setActiveTab('loan')}
          >
            Loan
          </button>
          <button
            className={`tab ${activeTab === 'conversation' ? 'active' : ''}`}
            onClick={() => setActiveTab('conversation')}
          >
            Conversation Log
          </button>
          <button
            className={`tab ${activeTab === 'checklist' ? 'active' : ''}`}
            onClick={() => setActiveTab('checklist')}
          >
            Checklist
          </button>
        </div>

        {/* Personal Information Tab */}
        {activeTab === 'personal' && (
          <div className="tab-content">
            <h2>Personal Information</h2>
            <div className="form-section">
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
              <div className="form-group">
                <label>Loan Number</label>
                <input
                  type="text"
                  value={formData.loan_number || ''}
                  disabled
                />
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
            <h2>Loan Details</h2>
            <div className="form-section">
              <div className="form-row">
                <div className="form-group">
                  <label>Loan Amount</label>
                  <input
                    type="text"
                    value={formData.amount ? `$${formData.amount.toLocaleString()}` : ''}
                    onChange={(e) => {
                      const numValue = parseFloat(e.target.value.replace(/[^0-9.]/g, ''));
                      handleChange('amount', numValue);
                    }}
                  />
                </div>
                <div className="form-group">
                  <label>Interest Rate</label>
                  <input
                    type="text"
                    value={formData.interest_rate ? `${formData.interest_rate}%` : ''}
                    onChange={(e) => {
                      const numValue = parseFloat(e.target.value.replace(/[^0-9.]/g, ''));
                      handleChange('interest_rate', numValue);
                    }}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Lender</label>
                  <input
                    type="text"
                    value={formData.lender || ''}
                    onChange={(e) => handleChange('lender', e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Loan Officer</label>
                  <input
                    type="text"
                    value={formData.loan_officer_name || ''}
                    disabled
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Lock Date</label>
                  <input
                    type="date"
                    value={formData.lock_date ? formData.lock_date.split('T')[0] : ''}
                    onChange={(e) => handleChange('lock_date', e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Lock Expiration</label>
                  <input
                    type="date"
                    value={formData.lock_expiration ? formData.lock_expiration.split('T')[0] : ''}
                    onChange={(e) => handleChange('lock_expiration', e.target.value)}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Closing Date</label>
                  <input
                    type="date"
                    value={formData.closing_date ? formData.closing_date.split('T')[0] : ''}
                    onChange={(e) => handleChange('closing_date', e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Appraisal Value</label>
                  <input
                    type="text"
                    value={formData.appraisal_value ? `$${formData.appraisal_value.toLocaleString()}` : ''}
                    onChange={(e) => {
                      const numValue = parseFloat(e.target.value.replace(/[^0-9.]/g, ''));
                      handleChange('appraisal_value', numValue);
                    }}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Property Address</label>
                  <input
                    type="text"
                    value={formData.property_address || ''}
                    onChange={(e) => handleChange('property_address', e.target.value)}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Property City</label>
                  <input
                    type="text"
                    value={formData.property_city || ''}
                    onChange={(e) => handleChange('property_city', e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Property State</label>
                  <input
                    type="text"
                    value={formData.property_state || ''}
                    onChange={(e) => handleChange('property_state', e.target.value)}
                    maxLength="2"
                  />
                </div>
                <div className="form-group">
                  <label>Property ZIP</label>
                  <input
                    type="text"
                    value={formData.property_zip || ''}
                    onChange={(e) => handleChange('property_zip', e.target.value)}
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Notes</label>
                <textarea
                  rows="4"
                  value={formData.notes || ''}
                  onChange={(e) => handleChange('notes', e.target.value)}
                  placeholder="Add notes about this loan..."
                />
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
