import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
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
  const navigate = useNavigate();
  const stageParam = searchParams.get('stage');
  const initialFilter = stageParam ? stageIdToFilter[stageParam] || 'All' : 'All';

  const [loans, setLoans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [activeFilter, setActiveFilter] = useState(initialFilter);
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');

  // Borrowers array - each borrower has their own contact info
  const [borrowers, setBorrowers] = useState([
    {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      credit_score: '',
      employment_status: '',
      annual_income: '',
      monthly_debts: '',
    }
  ]);

  // Shared property data
  const [propertyData, setPropertyData] = useState({
    address: '',
    city: '',
    state: '',
    zip_code: '',
    property_type: '',
    property_value: '',
    down_payment: '',
  });

  // Loan-specific data
  const [loanData, setLoanData] = useState({
    loan_number: '',
    amount: '',
    product_type: '',  // Maps to backend 'program'
    loan_type: '',     // Purchase, Refinance, etc.
    interest_rate: '',
    term: 360,
    closing_date: '',
    lock_date: '',
    processor: '',
    underwriter: '',
    realtor_agent: '',
    title_company: '',
    notes: '',
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
      // Ensure data is an array
      setLoans(Array.isArray(data) ? data : []);
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
      // Combine primary borrower data with property and loan data
      const primaryBorrower = borrowers[0];

      // Validate required fields
      const fullName = `${primaryBorrower.first_name || ''} ${primaryBorrower.last_name || ''}`.trim();
      if (!fullName) {
        alert('Please enter borrower first name and last name');
        return;
      }

      if (!loanData.loan_number) {
        alert('Please enter a loan number');
        return;
      }

      if (!loanData.amount) {
        alert('Please enter a loan amount');
        return;
      }

      // Build submit data matching backend LoanCreate model
      const submitData = {
        loan_number: loanData.loan_number,
        borrower_name: fullName,
        borrower_email: primaryBorrower.email || null,
        borrower_phone: primaryBorrower.phone || null,
        coborrower_name: borrowers.length > 1
          ? `${borrowers[1].first_name || ''} ${borrowers[1].last_name || ''}`.trim() || null
          : null,
        amount: parseFloat(loanData.amount),
        product_type: loanData.product_type || null,
        loan_type: loanData.loan_type || null,
        interest_rate: loanData.interest_rate ? parseFloat(loanData.interest_rate) : null,
        term: loanData.term || 360,
        purchase_price: propertyData.property_value ? parseFloat(propertyData.property_value) : null,
        down_payment: propertyData.down_payment ? parseFloat(propertyData.down_payment) : null,
        property_address: propertyData.address || null,
        property_city: propertyData.city || null,
        property_state: propertyData.state || null,
        property_zip: propertyData.zip_code || null,
        lock_date: loanData.lock_date ? `${loanData.lock_date}T00:00:00` : null,
        closing_date: loanData.closing_date ? `${loanData.closing_date}T00:00:00` : null,
        processor: loanData.processor || null,
        underwriter: loanData.underwriter || null,
        realtor_agent: loanData.realtor_agent || null,
        title_company: loanData.title_company || null,
        notes: loanData.notes || null,
      };

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
    setBorrowers([{
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      credit_score: '',
      employment_status: '',
      annual_income: '',
      monthly_debts: '',
    }]);

    setPropertyData({
      address: '',
      city: '',
      state: '',
      zip_code: '',
      property_type: '',
      property_value: '',
      down_payment: '',
    });

    setLoanData({
      loan_number: '',
      amount: '',
      product_type: '',
      loan_type: '',
      interest_rate: '',
      term: 360,
      closing_date: '',
      lock_date: '',
      processor: '',
      underwriter: '',
      realtor_agent: '',
      title_company: '',
      notes: '',
    });

    setActiveBorrower(0);
  };

  const handleExport = () => {
    alert('Export functionality coming soon');
  };

  // Borrower management functions
  const addBorrower = () => {
    setBorrowers([...borrowers, {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      credit_score: '',
      employment_status: '',
      annual_income: '',
      monthly_debts: '',
    }]);
    setActiveBorrower(borrowers.length);
  };

  const removeBorrower = (index) => {
    if (borrowers.length > 1 && window.confirm('Remove this borrower?')) {
      const newBorrowers = borrowers.filter((_, i) => i !== index);
      setBorrowers(newBorrowers);
      setActiveBorrower(Math.max(0, index - 1));
    }
  };

  const updateBorrower = (index, field, value) => {
    const newBorrowers = [...borrowers];
    newBorrowers[index] = { ...newBorrowers[index], [field]: value };
    setBorrowers(newBorrowers);
  };

  // Get current borrower for the form
  const currentBorrower = borrowers[activeBorrower] || borrowers[0];

  // Ensure loans is always an array before filtering
  const safeLoans = Array.isArray(loans) ? loans : [];

  // Filter by stage
  let filteredLoans = activeFilter === 'All'
    ? safeLoans
    : safeLoans.filter(loan => loan.stage === activeFilter);

  // Filter by search query
  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase();
    filteredLoans = filteredLoans.filter(loan =>
      loan.borrower_name?.toLowerCase().includes(query) ||
      loan.borrower?.toLowerCase().includes(query) ||
      loan.property_address?.toLowerCase().includes(query) ||
      loan.loan_officer?.toLowerCase().includes(query) ||
      loan.amount?.toString().includes(query)
    );
  }

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

      <div className="search-bar-container">
        <input
          type="text"
          className="search-bar"
          placeholder="Search loans by borrower, property address, loan officer, or amount..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <button className="clear-search" onClick={() => setSearchQuery('')}>
            ×
          </button>
        )}
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
              <tr
                key={loan.id}
                onClick={() => navigate(`/loans/${loan.id}`)}
                style={{ cursor: 'pointer' }}
              >
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
                {safeLoans
                  .filter(loan => loan.stage === 'Funded Prior Month')
                  .map((loan) => (
                    <tr
                      key={loan.id}
                      onClick={() => navigate(`/loans/${loan.id}`)}
                      style={{ cursor: 'pointer' }}
                    >
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
          {safeLoans.map((loan) => (
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
              {/* Borrower Tabs */}
              <div className="borrower-tabs">
                <div className="tabs-row">
                  {borrowers.map((borrower, index) => (
                    <div
                      key={index}
                      className={`borrower-tab ${activeBorrower === index ? 'active' : ''}`}
                      onClick={() => setActiveBorrower(index)}
                    >
                      <span>Borrower {index + 1}</span>
                      {index > 0 && (
                        <button
                          type="button"
                          className="remove-borrower-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            removeBorrower(index);
                          }}
                          title="Remove borrower"
                        >
                          ×
                        </button>
                      )}
                    </div>
                  ))}
                  <button
                    type="button"
                    className="add-borrower-btn"
                    onClick={addBorrower}
                    title="Add another borrower"
                  >
                    +
                  </button>
                </div>
              </div>

              {/* Borrower Information */}
              <div className="form-section-title">Borrower {activeBorrower + 1} Information</div>

              <div className="form-row">
                <div className="form-group">
                  <label>First Name *</label>
                  <input
                    type="text"
                    value={currentBorrower.first_name}
                    onChange={(e) => updateBorrower(activeBorrower, 'first_name', e.target.value)}
                    required={activeBorrower === 0}
                  />
                </div>

                <div className="form-group">
                  <label>Last Name *</label>
                  <input
                    type="text"
                    value={currentBorrower.last_name}
                    onChange={(e) => updateBorrower(activeBorrower, 'last_name', e.target.value)}
                    required={activeBorrower === 0}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={currentBorrower.email}
                    onChange={(e) => updateBorrower(activeBorrower, 'email', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={currentBorrower.phone}
                    onChange={(e) => updateBorrower(activeBorrower, 'phone', e.target.value)}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Credit Score</label>
                  <input
                    type="number"
                    value={currentBorrower.credit_score}
                    onChange={(e) => updateBorrower(activeBorrower, 'credit_score', e.target.value)}
                    min="300"
                    max="850"
                  />
                </div>

                <div className="form-group">
                  <label>Employment Status</label>
                  <select
                    value={currentBorrower.employment_status}
                    onChange={(e) => updateBorrower(activeBorrower, 'employment_status', e.target.value)}
                  >
                    <option value="">Select...</option>
                    <option value="Full-Time">Full-Time</option>
                    <option value="Part-Time">Part-Time</option>
                    <option value="Self-Employed">Self-Employed</option>
                    <option value="Retired">Retired</option>
                    <option value="Unemployed">Unemployed</option>
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Annual Income</label>
                  <input
                    type="number"
                    value={currentBorrower.annual_income}
                    onChange={(e) => updateBorrower(activeBorrower, 'annual_income', e.target.value)}
                    placeholder="$"
                  />
                </div>

                <div className="form-group">
                  <label>Monthly Debts</label>
                  <input
                    type="number"
                    value={currentBorrower.monthly_debts}
                    onChange={(e) => updateBorrower(activeBorrower, 'monthly_debts', e.target.value)}
                    placeholder="$"
                  />
                </div>
              </div>

              {/* Property Information */}
              <div className="form-section-title">Property Information</div>

              <div className="form-group">
                <label>Property Address</label>
                <input
                  type="text"
                  value={propertyData.address}
                  onChange={(e) => setPropertyData({ ...propertyData, address: e.target.value })}
                  placeholder="Street address"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>City</label>
                  <input
                    type="text"
                    value={propertyData.city}
                    onChange={(e) => setPropertyData({ ...propertyData, city: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>State</label>
                  <input
                    type="text"
                    value={propertyData.state}
                    onChange={(e) => setPropertyData({ ...propertyData, state: e.target.value })}
                    maxLength="2"
                    placeholder="CA"
                  />
                </div>

                <div className="form-group">
                  <label>ZIP Code</label>
                  <input
                    type="text"
                    value={propertyData.zip_code}
                    onChange={(e) => setPropertyData({ ...propertyData, zip_code: e.target.value })}
                    maxLength="10"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Property Type</label>
                  <select
                    value={propertyData.property_type}
                    onChange={(e) => setPropertyData({ ...propertyData, property_type: e.target.value })}
                  >
                    <option value="">Select...</option>
                    <option value="Single Family">Single Family</option>
                    <option value="Condo">Condo</option>
                    <option value="Townhouse">Townhouse</option>
                    <option value="Multi-Family">Multi-Family</option>
                    <option value="Manufactured">Manufactured</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Property Value</label>
                  <input
                    type="number"
                    value={propertyData.property_value}
                    onChange={(e) => setPropertyData({ ...propertyData, property_value: e.target.value })}
                    placeholder="$"
                  />
                </div>

                <div className="form-group">
                  <label>Down Payment</label>
                  <input
                    type="number"
                    value={propertyData.down_payment}
                    onChange={(e) => setPropertyData({ ...propertyData, down_payment: e.target.value })}
                    placeholder="$"
                  />
                </div>
              </div>

              {/* Loan Details */}
              <div className="form-section-title">Loan Details</div>

              <div className="form-row">
                <div className="form-group">
                  <label>Loan Number *</label>
                  <input
                    type="text"
                    value={loanData.loan_number}
                    onChange={(e) => setLoanData({ ...loanData, loan_number: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label>Loan Amount *</label>
                  <input
                    type="number"
                    value={loanData.amount}
                    onChange={(e) => setLoanData({ ...loanData, amount: e.target.value })}
                    placeholder="$"
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Loan Type</label>
                  <select
                    value={loanData.loan_type}
                    onChange={(e) => setLoanData({ ...loanData, loan_type: e.target.value })}
                  >
                    <option value="">Select...</option>
                    <option value="Purchase">Purchase</option>
                    <option value="Refinance">Refinance</option>
                    <option value="Cash-Out Refi">Cash-Out Refi</option>
                    <option value="HELOC">HELOC</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Program</label>
                  <select
                    value={loanData.product_type}
                    onChange={(e) => setLoanData({ ...loanData, product_type: e.target.value })}
                  >
                    <option value="">Select...</option>
                    <option value="Conventional">Conventional</option>
                    <option value="FHA">FHA</option>
                    <option value="VA">VA</option>
                    <option value="USDA">USDA</option>
                    <option value="Jumbo">Jumbo</option>
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Interest Rate %</label>
                  <input
                    type="number"
                    step="0.001"
                    value={loanData.interest_rate}
                    onChange={(e) => setLoanData({ ...loanData, interest_rate: e.target.value })}
                    placeholder="6.500"
                  />
                </div>

                <div className="form-group">
                  <label>Term (months)</label>
                  <input
                    type="number"
                    value={loanData.term}
                    onChange={(e) => setLoanData({ ...loanData, term: e.target.value })}
                    placeholder="360"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Lock Date</label>
                  <input
                    type="date"
                    value={loanData.lock_date}
                    onChange={(e) => setLoanData({ ...loanData, lock_date: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Closing Date</label>
                  <input
                    type="date"
                    value={loanData.closing_date}
                    onChange={(e) => setLoanData({ ...loanData, closing_date: e.target.value })}
                  />
                </div>
              </div>

              {/* Team Members */}
              <div className="form-section-title">Team Members</div>

              <div className="form-row">
                <div className="form-group">
                  <label>Processor</label>
                  <input
                    type="text"
                    value={loanData.processor}
                    onChange={(e) => setLoanData({ ...loanData, processor: e.target.value })}
                    placeholder="Processor name"
                  />
                </div>

                <div className="form-group">
                  <label>Underwriter</label>
                  <input
                    type="text"
                    value={loanData.underwriter}
                    onChange={(e) => setLoanData({ ...loanData, underwriter: e.target.value })}
                    placeholder="Underwriter name"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Realtor/Agent</label>
                  <input
                    type="text"
                    value={loanData.realtor_agent}
                    onChange={(e) => setLoanData({ ...loanData, realtor_agent: e.target.value })}
                    placeholder="Realtor name"
                  />
                </div>

                <div className="form-group">
                  <label>Title Company</label>
                  <input
                    type="text"
                    value={loanData.title_company}
                    onChange={(e) => setLoanData({ ...loanData, title_company: e.target.value })}
                    placeholder="Title company name"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Notes</label>
                <textarea
                  rows="3"
                  value={loanData.notes}
                  onChange={(e) => setLoanData({ ...loanData, notes: e.target.value })}
                  placeholder="Additional notes..."
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
