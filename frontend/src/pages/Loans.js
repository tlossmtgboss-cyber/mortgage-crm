import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { loansAPI } from '../services/api';
import './Loans.css';

// Map pipeline stage IDs to filter names
const stageIdToFilter = {
  'new': 'New Leads',
  'preapproved': 'Pre-Approved',
  'processing': 'In Processing',
  'underwriting': 'In Underwriting',
  'ctc': 'Clear to Close',
  'funded': 'Funded This Month'
};

// Generate mock loans data
const generateMockLoans = () => {
  const currentDate = new Date();
  const currentMonth = currentDate.getMonth();
  const currentYear = currentDate.getFullYear();

  return [
    // Current month funded loans
    { id: 1, borrower_name: 'John Anderson', borrower: 'John Anderson', amount: 425000, property_address: '123 Oak St, Austin TX', stage: 'Funded This Month', days_in_process: 28, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 5).toISOString(), funded_date: new Date(currentYear, currentMonth, 5).toISOString() },
    { id: 2, borrower_name: 'Maria Garcia', borrower: 'Maria Garcia', amount: 380000, property_address: '456 Pine Ave, Dallas TX', stage: 'Funded This Month', days_in_process: 32, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 8).toISOString(), funded_date: new Date(currentYear, currentMonth, 8).toISOString() },
    { id: 3, borrower_name: 'Robert Kim', borrower: 'Robert Kim', amount: 520000, property_address: '789 Elm Dr, Houston TX', stage: 'Funded This Month', days_in_process: 25, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 12).toISOString(), funded_date: new Date(currentYear, currentMonth, 12).toISOString() },
    { id: 4, borrower_name: 'Lisa Chen', borrower: 'Lisa Chen', amount: 295000, property_address: '321 Maple Rd, San Antonio TX', stage: 'Funded This Month', days_in_process: 30, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 15).toISOString(), funded_date: new Date(currentYear, currentMonth, 15).toISOString() },
    { id: 5, borrower_name: 'David Martinez', borrower: 'David Martinez', amount: 615000, property_address: '654 Cedar Ln, Fort Worth TX', stage: 'Funded This Month', days_in_process: 27, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 18).toISOString(), funded_date: new Date(currentYear, currentMonth, 18).toISOString() },
    { id: 6, borrower_name: 'Amy Wilson', borrower: 'Amy Wilson', amount: 340000, property_address: '987 Birch St, Arlington TX', stage: 'Funded This Month', days_in_process: 29, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 20).toISOString(), funded_date: new Date(currentYear, currentMonth, 20).toISOString() },
    { id: 7, borrower_name: 'James Brown', borrower: 'James Brown', amount: 450000, property_address: '147 Spruce Ave, Plano TX', stage: 'Funded This Month', days_in_process: 31, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth, 22).toISOString(), funded_date: new Date(currentYear, currentMonth, 22).toISOString() },
    { id: 8, borrower_name: 'Jennifer Lee', borrower: 'Jennifer Lee', amount: 385000, property_address: '258 Walnut Dr, Irving TX', stage: 'Funded This Month', days_in_process: 26, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth, 25).toISOString(), funded_date: new Date(currentYear, currentMonth, 25).toISOString() },
    { id: 9, borrower_name: 'Michael Davis', borrower: 'Michael Davis', amount: 495000, property_address: '369 Ash Rd, Frisco TX', stage: 'Funded This Month', days_in_process: 28, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth, 27).toISOString(), funded_date: new Date(currentYear, currentMonth, 27).toISOString() },

    // Prior months funded loans
    { id: 10, borrower_name: 'Thomas White', borrower: 'Thomas White', amount: 410000, property_address: '741 Cherry Ln, McKinney TX', stage: 'Funded Prior Month', days_in_process: 30, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth - 1, 5).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 5).toISOString() },
    { id: 11, borrower_name: 'Susan Taylor', borrower: 'Susan Taylor', amount: 375000, property_address: '852 Poplar St, Denton TX', stage: 'Funded Prior Month', days_in_process: 29, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth - 1, 10).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 10).toISOString() },
    { id: 12, borrower_name: 'Daniel Moore', borrower: 'Daniel Moore', amount: 530000, property_address: '963 Hickory Ave, Allen TX', stage: 'Funded Prior Month', days_in_process: 32, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth - 1, 12).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 12).toISOString() },
    { id: 13, borrower_name: 'Patricia Johnson', borrower: 'Patricia Johnson', amount: 325000, property_address: '159 Willow Dr, Carrollton TX', stage: 'Funded Prior Month', days_in_process: 27, loan_officer: 'Sarah Johnson', created_at: new Date(currentYear, currentMonth - 1, 15).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 15).toISOString() },
    { id: 14, borrower_name: 'Kevin Anderson', borrower: 'Kevin Anderson', amount: 445000, property_address: '357 Magnolia Rd, Richardson TX', stage: 'Funded Prior Month', days_in_process: 28, loan_officer: 'Mike Chen', created_at: new Date(currentYear, currentMonth - 1, 18).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 18).toISOString() },
    { id: 15, borrower_name: 'Nancy Thomas', borrower: 'Nancy Thomas', amount: 365000, property_address: '486 Sycamore Ln, Lewisville TX', stage: 'Funded Prior Month', days_in_process: 31, loan_officer: 'Emily Davis', created_at: new Date(currentYear, currentMonth - 1, 20).toISOString(), funded_date: new Date(currentYear, currentMonth - 1, 20).toISOString() },

    // Active pipeline loans
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

function Loans() {
  const [searchParams] = useSearchParams();
  const stageParam = searchParams.get('stage');
  const initialFilter = stageParam ? stageIdToFilter[stageParam] || 'All' : 'All';

  const [loans, setLoans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [activeFilter, setActiveFilter] = useState(initialFilter);
  const [formData, setFormData] = useState({
    loan_number: '',
    borrower_name: '',
    amount: '',
    program: '',
    rate: '',
    closing_date: '',
  });

  const filters = [
    'All',
    'In Processing',
    'In Underwriting',
    'Approved',
    'Clear to Close',
    'Suspended',
  ];

  useEffect(() => {
    loadLoans();
  }, []);

  useEffect(() => {
    // Update filter when URL parameter changes
    if (stageParam && stageIdToFilter[stageParam]) {
      setActiveFilter(stageIdToFilter[stageParam]);
    }
  }, [stageParam]);

  const loadLoans = async () => {
    try {
      const data = await loansAPI.getAll();
      setLoans(data);
    } catch (err) {
      console.error('Failed to load loans:', err);
      // Use mock data on error
      setLoans(generateMockLoans());
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      // Convert date to datetime format for backend
      const submitData = { ...formData };
      if (submitData.closing_date) {
        submitData.closing_date = `${submitData.closing_date}T00:00:00`;
      }

      console.log('Submitting loan data:', submitData);
      console.log('Auth token exists:', !!localStorage.getItem('token'));

      await loansAPI.create(submitData);
      setShowModal(false);
      resetForm();
      loadLoans();
    } catch (err) {
      console.error('Failed to create loan:', err);
      console.error('Error response:', err.response);
      console.error('Error config:', err.config);
      console.error('Error message:', err.message);

      let errorMessage = 'Failed to create loan';

      if (err.message === 'Network Error') {
        const hasToken = !!localStorage.getItem('token');
        errorMessage = `Cannot connect to server. Auth token present: ${hasToken}. Please try logging out and back in.`;
      } else if (err.response?.status === 401) {
        errorMessage = 'Your session has expired. Please log out and log back in.';
      } else if (err.response?.data?.detail) {
        // Handle both string and object detail
        if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail;
        } else {
          errorMessage = JSON.stringify(err.response.data.detail);
        }
      } else if (err.response?.data) {
        errorMessage = JSON.stringify(err.response.data);
      } else if (err.message) {
        errorMessage = err.message;
      }

      alert(`Failed to create loan: ${errorMessage}`);
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm('Are you sure you want to delete this loan?')) {
      try {
        await loansAPI.delete(id);
        loadLoans();
      } catch (err) {
        alert('Failed to delete loan');
      }
    }
  };

  const resetForm = () => {
    setFormData({
      loan_number: '',
      borrower_name: '',
      amount: '',
      program: '',
      rate: '',
      closing_date: '',
    });
  };

  const handleExport = () => {
    alert('Export functionality coming soon');
  };

  const filteredLoans = activeFilter === 'All'
    ? loans
    : loans.filter(loan => loan.stage === activeFilter);

  if (loading) return <div className="loading">Loading loans...</div>;

  return (
    <div className="loans-page">
      <div className="page-header">
        <div>
          <h1>Active Loans</h1>
          <p>{loans.length} active loans</p>
        </div>
        <div className="header-actions">
          <button className="btn-secondary" onClick={handleExport}>
            Export
          </button>
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            + New Loan
          </button>
        </div>
      </div>

      <div className="filter-tabs">
        {filters.map((filter) => (
          <button
            key={filter}
            className={`filter-tab ${activeFilter === filter ? 'active' : ''}`}
            onClick={() => setActiveFilter(filter)}
          >
            {filter}
          </button>
        ))}
      </div>

      <div className="table-container">
        <table className="loans-table">
          <thead>
            <tr>
              <th>Borrower</th>
              <th>Loan Amount</th>
              <th>Property Address</th>
              <th>Status</th>
              <th>Days in Process</th>
              <th>Loan Officer</th>
            </tr>
          </thead>
          <tbody>
            {filteredLoans.map((loan) => (
              <tr key={loan.id}>
                <td className="borrower-name">{loan.borrower || loan.borrower_name}</td>
                <td className="loan-amount">${(loan.amount || 0).toLocaleString()}</td>
                <td>{loan.property_address || 'N/A'}</td>
                <td>
                  <span className={`status-badge status-${getStatusClass(loan.stage)}`}>
                    {loan.stage}
                  </span>
                </td>
                <td>{loan.days_in_process || calculateDays(loan.created_at)}</td>
                <td>{loan.loan_officer || 'Unassigned'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filteredLoans.length === 0 && (
        <div className="empty-state">
          <h3>No loans found</h3>
          <p>Try adjusting your filters or add a new loan</p>
        </div>
      )}

      {/* Prior Months Closings - shown when viewing Funded This Month */}
      {activeFilter === 'Funded This Month' && (
        <div className="prior-months-section">
          <div className="section-header">
            <h2>Prior Months Closings</h2>
            <p>Historical funded loans from previous months</p>
          </div>

          <div className="table-container">
            <table className="loans-table">
              <thead>
                <tr>
                  <th>Borrower</th>
                  <th>Loan Amount</th>
                  <th>Property Address</th>
                  <th>Funded Date</th>
                  <th>Days in Process</th>
                  <th>Loan Officer</th>
                </tr>
              </thead>
              <tbody>
                {loans
                  .filter(loan => loan.stage === 'Funded Prior Month')
                  .map((loan) => (
                    <tr key={loan.id}>
                      <td className="borrower-name">{loan.borrower || loan.borrower_name}</td>
                      <td className="loan-amount">${(loan.amount || 0).toLocaleString()}</td>
                      <td>{loan.property_address || 'N/A'}</td>
                      <td>
                        {loan.funded_date
                          ? new Date(loan.funded_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                          : 'N/A'}
                      </td>
                      <td>{loan.days_in_process || calculateDays(loan.created_at)}</td>
                      <td>{loan.loan_officer || 'Unassigned'}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>

          {loans.filter(loan => loan.stage === 'Funded Prior Month').length === 0 && (
            <div className="empty-state">
              <h3>No prior month closings found</h3>
              <p>There are no funded loans from previous months</p>
            </div>
          )}
        </div>
      )}

      <div className="legacy-loans-grid" style={{ display: 'none' }}>
        <div className="loans-grid">
          {loans.map((loan) => (
            <div key={loan.id} className="loan-card">
            <div className="loan-header">
              <div>
                <h3>{loan.borrower_name}</h3>
                <span className="loan-number">{loan.loan_number}</span>
              </div>
              <span className={`status-badge status-${loan.sla_status}`}>
                {loan.stage}
              </span>
            </div>

            <div className="loan-details">
              <div className="detail-row">
                <span>Amount:</span>
                <strong>${loan.amount.toLocaleString()}</strong>
              </div>
              {loan.program && (
                <div className="detail-row">
                  <span>Program:</span>
                  <span>{loan.program}</span>
                </div>
              )}
              {loan.rate && (
                <div className="detail-row">
                  <span>Rate:</span>
                  <span>{loan.rate}%</span>
                </div>
              )}
              <div className="detail-row">
                <span>Days in Stage:</span>
                <span>{loan.days_in_stage}</span>
              </div>
              {loan.closing_date && (
                <div className="detail-row">
                  <span>Closing:</span>
                  <span>{new Date(loan.closing_date).toLocaleDateString()}</span>
                </div>
              )}
            </div>

            <div className="loan-actions">
              <button className="btn-delete" onClick={() => handleDelete(loan.id)}>
                Delete
              </button>
            </div>
            </div>
          ))}
        </div>
      </div>

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>New Loan</h2>
              <button className="close-btn" onClick={() => setShowModal(false)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>Loan Number *</label>
                <input
                  type="text"
                  value={formData.loan_number}
                  onChange={(e) => setFormData({ ...formData, loan_number: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label>Borrower Name *</label>
                <input
                  type="text"
                  value={formData.borrower_name}
                  onChange={(e) => setFormData({ ...formData, borrower_name: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label>Loan Amount *</label>
                <input
                  type="number"
                  value={formData.amount}
                  onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                  required
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Program</label>
                  <select
                    value={formData.program}
                    onChange={(e) => setFormData({ ...formData, program: e.target.value })}
                  >
                    <option value="">Select...</option>
                    <option value="Conventional">Conventional</option>
                    <option value="FHA">FHA</option>
                    <option value="VA">VA</option>
                    <option value="USDA">USDA</option>
                    <option value="Jumbo">Jumbo</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Interest Rate %</label>
                  <input
                    type="number"
                    step="0.001"
                    value={formData.rate}
                    onChange={(e) => setFormData({ ...formData, rate: e.target.value })}
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Closing Date</label>
                <input
                  type="date"
                  value={formData.closing_date}
                  onChange={(e) => setFormData({ ...formData, closing_date: e.target.value })}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">Create Loan</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function getStatusClass(status) {
  const statusMap = {
    'Contract Received': 'received',
    'In Processing': 'processing',
    'Approved': 'approved',
    'Suspended': 'suspended',
    'Denied': 'denied',
    'Withdrawn': 'withdrawn',
  };
  return statusMap[status] || 'default';
}

function calculateDays(createdAt) {
  if (!createdAt) return 0;
  const created = new Date(createdAt);
  const today = new Date();
  const diff = Math.floor((today - created) / (1000 * 60 * 60 * 24));
  return diff;
}

export default Loans;
