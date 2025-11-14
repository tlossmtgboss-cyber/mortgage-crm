import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { loansAPI, activitiesAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import './LeadDetail.css';

// Mock loans data (same as Loans.js)
const generateMockLoans = () => {
  const currentDate = new Date();
  const currentMonth = currentDate.getMonth();
  const currentYear = currentDate.getFullYear();

  return [
    { id: 1, borrower_name: 'John Anderson', borrower: 'John Anderson', amount: 425000, property_address: '123 Oak St, Austin TX', stage: 'Funded This Month', days_in_process: 28, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 5).toISOString(), funded_date: new Date(currentYear, currentMonth, 5).toISOString() },
    { id: 2, borrower_name: 'Maria Garcia', borrower: 'Maria Garcia', amount: 380000, property_address: '456 Pine Ave, Dallas TX', stage: 'Funded This Month', days_in_process: 32, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 8).toISOString(), funded_date: new Date(currentYear, currentMonth, 8).toISOString() },
    { id: 3, borrower_name: 'Robert Kim', borrower: 'Robert Kim', amount: 520000, property_address: '789 Elm Dr, Houston TX', stage: 'Funded This Month', days_in_process: 25, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 12).toISOString(), funded_date: new Date(currentYear, currentMonth, 12).toISOString() },
    { id: 4, borrower_name: 'Lisa Chen', borrower: 'Lisa Chen', amount: 295000, property_address: '321 Maple Rd, San Antonio TX', stage: 'Funded This Month', days_in_process: 30, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 15).toISOString(), funded_date: new Date(currentYear, currentMonth, 15).toISOString() },
    { id: 5, borrower_name: 'David Martinez', borrower: 'David Martinez', amount: 615000, property_address: '654 Cedar Ln, Fort Worth TX', stage: 'Funded This Month', days_in_process: 27, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 18).toISOString(), funded_date: new Date(currentYear, currentMonth, 18).toISOString() },
    { id: 6, borrower_name: 'Amy Wilson', borrower: 'Amy Wilson', amount: 340000, property_address: '987 Birch St, Arlington TX', stage: 'Funded This Month', days_in_process: 29, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 20).toISOString(), funded_date: new Date(currentYear, currentMonth, 20).toISOString() },
    { id: 7, borrower_name: 'James Brown', borrower: 'James Brown', amount: 450000, property_address: '147 Spruce Ave, Plano TX', stage: 'Funded This Month', days_in_process: 31, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 22).toISOString(), funded_date: new Date(currentYear, currentMonth, 22).toISOString() },
    { id: 8, borrower_name: 'Jennifer Lee', borrower: 'Jennifer Lee', amount: 385000, property_address: '258 Walnut Dr, Irving TX', stage: 'Funded This Month', days_in_process: 26, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 25).toISOString(), funded_date: new Date(currentYear, currentMonth, 25).toISOString() },
    { id: 9, borrower_name: 'Michael Davis', borrower: 'Michael Davis', amount: 495000, property_address: '369 Ash Rd, Frisco TX', stage: 'Funded This Month', days_in_process: 28, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 27).toISOString(), funded_date: new Date(currentYear, currentMonth, 27).toISOString() },
    { id: 10, borrower_name: 'Thomas White', borrower: 'Thomas White', amount: 410000, property_address: '741 Cherry Ln, McKinney TX', stage: 'Funded Prior Month', days_in_process: 30, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth - 1, 5).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 5).toISOString() },
    { id: 11, borrower_name: 'Susan Taylor', borrower: 'Susan Taylor', amount: 375000, property_address: '852 Poplar St, Denton TX', stage: 'Funded Prior Month', days_in_process: 29, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth - 1, 10).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 10).toISOString() },
    { id: 12, borrower_name: 'Daniel Moore', borrower: 'Daniel Moore', amount: 530000, property_address: '963 Hickory Ave, Allen TX', stage: 'Funded Prior Month', days_in_process: 32, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth - 1, 12).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 12).toISOString() },
    { id: 13, borrower_name: 'Patricia Johnson', borrower: 'Patricia Johnson', amount: 325000, property_address: '159 Willow Dr, Carrollton TX', stage: 'Funded Prior Month', days_in_process: 27, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth - 1, 15).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 15).toISOString() },
    { id: 14, borrower_name: 'Kevin Anderson', borrower: 'Kevin Anderson', amount: 445000, property_address: '357 Magnolia Rd, Richardson TX', stage: 'Funded Prior Month', days_in_process: 28, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth - 1, 18).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 18).toISOString() },
    { id: 15, borrower_name: 'Nancy Thomas', borrower: 'Nancy Thomas', amount: 365000, property_address: '486 Sycamore Ln, Lewisville TX', stage: 'Funded Prior Month', days_in_process: 31, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth - 1, 20).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 20).toISOString() },
    { id: 16, borrower_name: 'Emily Davis', borrower: 'Emily Davis', amount: 520000, property_address: '890 Second St, Houston TX', stage: 'In Processing', days_in_process: 12, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 18).toISOString() },
    { id: 17, borrower_name: 'Rachel Martinez', borrower: 'Rachel Martinez', amount: 345000, property_address: '234 Oak Lane, Austin TX', stage: 'In Processing', days_in_process: 8, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 22).toISOString() },
    { id: 18, borrower_name: 'Tom Wilson', borrower: 'Tom Wilson', amount: 295000, property_address: '123 Third Dr, San Antonio TX', stage: 'In Underwriting', days_in_process: 18, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 12).toISOString() },
    { id: 19, borrower_name: 'Carlos Rodriguez', borrower: 'Carlos Rodriguez', amount: 475000, property_address: '567 Elm Street, Dallas TX', stage: 'In Underwriting', days_in_process: 15, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 15).toISOString() },
    { id: 20, borrower_name: 'Jessica Parker', borrower: 'Jessica Parker', amount: 525000, property_address: '789 Maple Ave, Plano TX', stage: 'Approved', days_in_process: 20, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 10).toISOString() },
    { id: 21, borrower_name: 'Mark Stevens', borrower: 'Mark Stevens', amount: 395000, property_address: '321 Pine Dr, Fort Worth TX', stage: 'Approved', days_in_process: 19, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 11).toISOString() },
    { id: 22, borrower_name: 'Lisa Brown', borrower: 'Lisa Brown', amount: 615000, property_address: '456 Fourth Rd, Fort Worth TX', stage: 'Clear to Close', days_in_process: 22, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 8).toISOString() },
    { id: 23, borrower_name: 'Anna Thompson', borrower: 'Anna Thompson', amount: 410000, property_address: '654 Cedar Blvd, Irving TX', stage: 'Clear to Close', days_in_process: 24, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 6).toISOString() },
    { id: 24, borrower_name: 'Brian Foster', borrower: 'Brian Foster', amount: 285000, property_address: '987 Birch Ct, Arlington TX', stage: 'Suspended', days_in_process: 45, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth - 1, 25).toISOString() },
    { id: 25, borrower_name: 'Michelle Cooper', borrower: 'Michelle Cooper', amount: 330000, property_address: '147 Willow Way, Richardson TX', stage: 'Suspended', days_in_process: 38, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth - 1, 28).toISOString() },
  ];
};

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
      let loanData = null;

      try {
        // Try to fetch from API first
        loanData = await loansAPI.getById(id);
      } catch (apiError) {
        console.log('API failed, using mock data:', apiError);
        // Fallback to mock data
        const mockLoans = generateMockLoans();
        loanData = mockLoans.find(loan => loan.id === parseInt(id));

        if (!loanData) {
          alert('Loan not found');
          navigate('/loans');
          return;
        }
      }

      setLoan(loanData);
      setFormData(loanData);

      // Initialize borrowers array
      const borrowersList = [
        {
          id: 0,
          name: loanData.borrower_name || loanData.borrower || 'Primary Borrower',
          type: 'primary',
          data: {
            name: loanData.borrower_name || loanData.borrower,
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
      navigate('/loans');
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
              value={formData.rate || ''}
              onChange={(e) => handleFieldChange('rate', parseFloat(e.target.value))}
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
              value={formData.program || formData.loan_type || ''}
              onChange={(e) => handleFieldChange('program', e.target.value)}
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
          className={`tab-btn ${activeTab === 'team' ? 'active' : ''}`}
          onClick={() => setActiveTab('team')}
        >
          Team Members
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
        <button
          className={`tab-btn ${activeTab === 'important-dates' ? 'active' : ''}`}
          onClick={() => setActiveTab('important-dates')}
        >
          Important Dates
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

        {/* Team Members Tab */}
        {activeTab === 'team' && (
          <div className="tab-content">
            <h2>Team Members</h2>
            <div className="team-description">
              <p>Assign internal team members who are working on this loan.</p>
            </div>
            <div className="form-section">
              <div className="form-row">
                <div className="form-group">
                  <label>Loan Officer</label>
                  <input
                    type="text"
                    value={formData.loan_officer_name || formData.loan_officer || ''}
                    onChange={(e) => handleFieldChange('loan_officer_name', e.target.value)}
                    placeholder="Enter loan officer name"
                  />
                </div>
                <div className="form-group">
                  <label>Loan Officer Email</label>
                  <input
                    type="email"
                    value={formData.loan_officer_email || ''}
                    onChange={(e) => handleFieldChange('loan_officer_email', e.target.value)}
                    placeholder="email@example.com"
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Processor</label>
                  <input
                    type="text"
                    value={formData.processor || ''}
                    onChange={(e) => handleFieldChange('processor', e.target.value)}
                    placeholder="Enter processor name"
                  />
                </div>
                <div className="form-group">
                  <label>Processor Email</label>
                  <input
                    type="email"
                    value={formData.processor_email || ''}
                    onChange={(e) => handleFieldChange('processor_email', e.target.value)}
                    placeholder="email@example.com"
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Underwriter</label>
                  <input
                    type="text"
                    value={formData.underwriter || ''}
                    onChange={(e) => handleFieldChange('underwriter', e.target.value)}
                    placeholder="Enter underwriter name"
                  />
                </div>
                <div className="form-group">
                  <label>Underwriter Email</label>
                  <input
                    type="email"
                    value={formData.underwriter_email || ''}
                    onChange={(e) => handleFieldChange('underwriter_email', e.target.value)}
                    placeholder="email@example.com"
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Closer</label>
                  <input
                    type="text"
                    value={formData.closer || ''}
                    onChange={(e) => handleFieldChange('closer', e.target.value)}
                    placeholder="Enter closer name"
                  />
                </div>
                <div className="form-group">
                  <label>Closer Email</label>
                  <input
                    type="email"
                    value={formData.closer_email || ''}
                    onChange={(e) => handleFieldChange('closer_email', e.target.value)}
                    placeholder="email@example.com"
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

        {/* Important Dates Tab */}
        {activeTab === 'important-dates' && (
          <div className="tab-content">
            <h2>Contract-to-Close Milestone Dates</h2>
            <p className="section-subtitle">Track key milestone dates to manage the file, chase conditions, and prevent last-minute emergencies</p>

            {/* Contract & Property Dates */}
            <div className="dates-section">
              <h3 className="dates-section-title">Contract & Property Dates</h3>
              <div className="dates-grid">
                <div className="date-field">
                  <label>Contract Received Date</label>
                  <input
                    type="date"
                    value={formData.contract_received_date || ''}
                    onChange={(e) => handleFieldChange('contract_received_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Appraisal Ordered Date</label>
                  <input
                    type="date"
                    value={formData.appraisal_ordered_date || ''}
                    onChange={(e) => handleFieldChange('appraisal_ordered_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Appraisal Scheduled Date</label>
                  <input
                    type="date"
                    value={formData.appraisal_scheduled_date || ''}
                    onChange={(e) => handleFieldChange('appraisal_scheduled_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Appraisal Completed Date</label>
                  <input
                    type="date"
                    value={formData.appraisal_completed_date || ''}
                    onChange={(e) => handleFieldChange('appraisal_completed_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Appraisal Received Date</label>
                  <input
                    type="date"
                    value={formData.appraisal_received_date || ''}
                    onChange={(e) => handleFieldChange('appraisal_received_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Title Ordered Date</label>
                  <input
                    type="date"
                    value={formData.title_ordered_date || ''}
                    onChange={(e) => handleFieldChange('title_ordered_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Title Received Date</label>
                  <input
                    type="date"
                    value={formData.title_received_date || ''}
                    onChange={(e) => handleFieldChange('title_received_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Insurance Ordered Date</label>
                  <input
                    type="date"
                    value={formData.insurance_ordered_date || ''}
                    onChange={(e) => handleFieldChange('insurance_ordered_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Insurance Received Date</label>
                  <input
                    type="date"
                    value={formData.insurance_received_date || ''}
                    onChange={(e) => handleFieldChange('insurance_received_date', e.target.value)}
                  />
                </div>
              </div>
            </div>

            {/* Loan Processing Milestones */}
            <div className="dates-section">
              <h3 className="dates-section-title">Loan Processing Milestones</h3>
              <div className="dates-grid">
                <div className="date-field">
                  <label>Initial Disclosures Sent Date</label>
                  <input
                    type="date"
                    value={formData.initial_disclosures_sent_date || ''}
                    onChange={(e) => handleFieldChange('initial_disclosures_sent_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Initial Disclosures Signed Date</label>
                  <input
                    type="date"
                    value={formData.initial_disclosures_signed_date || ''}
                    onChange={(e) => handleFieldChange('initial_disclosures_signed_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Processor Submission Date</label>
                  <input
                    type="date"
                    value={formData.processor_submission_date || ''}
                    onChange={(e) => handleFieldChange('processor_submission_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Underwriting Submission Date</label>
                  <input
                    type="date"
                    value={formData.underwriting_submission_date || ''}
                    onChange={(e) => handleFieldChange('underwriting_submission_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Conditional Approval Date</label>
                  <input
                    type="date"
                    value={formData.conditional_approval_date || ''}
                    onChange={(e) => handleFieldChange('conditional_approval_date', e.target.value)}
                  />
                  <small className="field-hint">UW Decision Date</small>
                </div>

                <div className="date-field">
                  <label>Conditions Sent to Borrower</label>
                  <input
                    type="date"
                    value={formData.conditions_sent_date || ''}
                    onChange={(e) => handleFieldChange('conditions_sent_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Conditions Received from Borrower</label>
                  <input
                    type="date"
                    value={formData.conditions_received_date || ''}
                    onChange={(e) => handleFieldChange('conditions_received_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Resubmission to Underwriting Date</label>
                  <input
                    type="date"
                    value={formData.resubmission_date || ''}
                    onChange={(e) => handleFieldChange('resubmission_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Final Approval / Clear-to-Close Date</label>
                  <input
                    type="date"
                    value={formData.clear_to_close_date || ''}
                    onChange={(e) => handleFieldChange('clear_to_close_date', e.target.value)}
                  />
                </div>
              </div>
            </div>

            {/* Rate Lock Dates */}
            <div className="dates-section">
              <h3 className="dates-section-title">Rate Lock Dates</h3>
              <div className="dates-grid">
                <div className="date-field">
                  <label>Rate Lock Date</label>
                  <input
                    type="date"
                    value={formData.rate_lock_date || ''}
                    onChange={(e) => handleFieldChange('rate_lock_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Rate Lock Expiration Date</label>
                  <input
                    type="date"
                    value={formData.rate_lock_expiration_date || ''}
                    onChange={(e) => handleFieldChange('rate_lock_expiration_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Rate Lock Extension Date</label>
                  <input
                    type="date"
                    value={formData.rate_lock_extension_date || ''}
                    onChange={(e) => handleFieldChange('rate_lock_extension_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Float-down Trigger Date</label>
                  <input
                    type="date"
                    value={formData.float_down_trigger_date || ''}
                    onChange={(e) => handleFieldChange('float_down_trigger_date', e.target.value)}
                  />
                  <small className="field-hint">If applicable</small>
                </div>
              </div>
            </div>

            {/* Closing Process Dates */}
            <div className="dates-section">
              <h3 className="dates-section-title">Closing Process Dates</h3>
              <div className="dates-grid">
                <div className="date-field">
                  <label>Closing Disclosure Sent Date</label>
                  <input
                    type="date"
                    value={formData.closing_disclosure_sent_date || ''}
                    onChange={(e) => handleFieldChange('closing_disclosure_sent_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>CD Received/Signed Date</label>
                  <input
                    type="date"
                    value={formData.cd_received_signed_date || ''}
                    onChange={(e) => handleFieldChange('cd_received_signed_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>CD Delivered Date</label>
                  <input
                    type="date"
                    value={formData.cd_delivered_date || ''}
                    onChange={(e) => handleFieldChange('cd_delivered_date', e.target.value)}
                  />
                  <small className="field-hint">3-day timing rule</small>
                </div>

                <div className="date-field">
                  <label>Final CD Issue Date</label>
                  <input
                    type="date"
                    value={formData.final_cd_issue_date || ''}
                    onChange={(e) => handleFieldChange('final_cd_issue_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Final Closing Package Sent Date</label>
                  <input
                    type="date"
                    value={formData.final_closing_package_sent_date || ''}
                    onChange={(e) => handleFieldChange('final_closing_package_sent_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Closing Scheduled Date</label>
                  <input
                    type="date"
                    value={formData.closing_scheduled_date || ''}
                    onChange={(e) => handleFieldChange('closing_scheduled_date', e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label>Funding Date</label>
                  <input
                    type="date"
                    value={formData.funding_date || ''}
                    onChange={(e) => handleFieldChange('funding_date', e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default LoanDetail;
