import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { loansAPI } from '../services/api';
import './Loans.css';

// Map pipeline stage IDs to filter names
const stageIdToFilter = {
  'new': 'New Leads',
  'preapproved': 'Pre-Approved',
  'le_pending': 'LE Pending',
  'processing': 'In Processing',
  'underwriting': 'In Underwriting',
  'ctc': 'Clear to Close',
  'funded': 'Funded This Month'
};

// Generate mock loans data based on 30 test scenarios
const generateMockLoans = () => {
  return [
    // ========== ACTIVE PIPELINE LOANS (from 30 scenarios) ==========

    // In Processing (7 loans)
    { id: 3, borrower_name: 'Sandra & Robert Chen', borrower: 'Sandra & Robert Chen', amount: 650000, property_address: '4521 Preston Hollow Ln, Dallas TX 75225', stage: 'In Processing', days_in_process: 15, loan_officer: 'Timothy Loss', rate_locked: false, lock_guidance: 'Float Cautious', lock_confidence: 72, loan_number: 'TST-0003', program: 'Conventional 30yr Fixed' },
    { id: 4, borrower_name: 'Angela Martinez', borrower: 'Angela Martinez', amount: 380000, property_address: '789 Freedom Dr, Fort Worth TX 76109', stage: 'In Processing', days_in_process: 20, loan_officer: 'Timothy Loss', rate_locked: true, loan_number: 'TST-0004', program: 'VA 30yr Fixed' },
    { id: 13, borrower_name: 'Brian & Stephanie Cooper', borrower: 'Brian & Stephanie Cooper', amount: 950000, property_address: '12345 Highland Park Blvd, Dallas TX 75205', stage: 'In Processing', days_in_process: 10, loan_officer: 'Timothy Loss', rate_locked: false, lock_guidance: 'Lock Now', lock_confidence: 88, loan_number: 'TST-0013', program: 'Jumbo 30yr ARM' },
    { id: 17, borrower_name: 'Elizabeth & Anthony Cruz', borrower: 'Elizabeth & Anthony Cruz', amount: 265000, property_address: '2468 Commerce St, Garland TX 75040', stage: 'In Processing', days_in_process: 8, loan_officer: 'Timothy Loss', rate_locked: false, lock_guidance: 'Float Cautious', lock_confidence: 68, loan_number: 'TST-0017', program: 'FHA 30yr Fixed' },
    { id: 21, borrower_name: 'Daniel Kim', borrower: 'Daniel Kim', amount: 375000, property_address: '7654 Preston Rd, Dallas TX 75230', stage: 'In Processing', days_in_process: 14, loan_officer: 'Timothy Loss', rate_locked: true, loan_number: 'TST-0021', program: 'Conventional 30yr Fixed' },
    { id: 25, borrower_name: 'Victoria & Jason Wright', borrower: 'Victoria & Jason Wright', amount: 425000, property_address: '1357 Forest Lane, Coppell TX 75019', stage: 'In Processing', days_in_process: 7, loan_officer: 'Timothy Loss', rate_locked: false, lock_guidance: 'Lock Soon', lock_confidence: 78, loan_number: 'TST-0025', program: 'Conventional 30yr Fixed' },

    // Conditional Approval / Approved (5 loans)
    { id: 5, borrower_name: 'David & Patricia Thompson', borrower: 'David & Patricia Thompson', amount: 425000, property_address: '2345 Mockingbird Ln, Richardson TX 75080', stage: 'Approved', days_in_process: 25, loan_officer: 'Timothy Loss', rate_locked: true, loan_number: 'TST-0005', program: 'Conventional 15yr Fixed', underwriter: 'Danielle Brooks' },
    { id: 6, borrower_name: "Michael O'Brien", borrower: "Michael O'Brien", amount: 320000, property_address: '567 Oak Ridge Blvd, Plano TX 75024', stage: 'Approved', days_in_process: 28, loan_officer: 'Timothy Loss', rate_locked: true, loan_number: 'TST-0006', program: 'Conventional 30yr Fixed', underwriter: 'Samuel Price' },
    { id: 14, borrower_name: 'Kevin & Laura Mitchell', borrower: 'Kevin & Laura Mitchell', amount: 290000, property_address: '4567 Cedar Springs, Lewisville TX 75067', stage: 'Approved', days_in_process: 22, loan_officer: 'Timothy Loss', rate_locked: true, loan_number: 'TST-0014', program: 'Conventional 30yr Fixed', underwriter: 'Helen Rogers' },
    { id: 19, borrower_name: 'Catherine & Paul Newman', borrower: 'Catherine & Paul Newman', amount: 565000, property_address: '9012 Stonebriar Pkwy, Frisco TX 75035', stage: 'Approved', days_in_process: 30, loan_officer: 'Timothy Loss', rate_locked: true, loan_number: 'TST-0019', program: 'Conventional 30yr Fixed', underwriter: 'Patricia Donovan' },
    { id: 29, borrower_name: 'Samantha & Eric Clark', borrower: 'Samantha & Eric Clark', amount: 355000, property_address: '6543 Lakewood Blvd, Dallas TX 75214', stage: 'Approved', days_in_process: 18, loan_officer: 'Timothy Loss', rate_locked: true, loan_number: 'TST-0029', program: 'Conventional 30yr Fixed', underwriter: 'Danielle Brooks' },

    // Clear to Close (3 loans)
    { id: 7, borrower_name: 'Jennifer & William Park', borrower: 'Jennifer & William Park', amount: 515000, property_address: '8901 Legacy Dr, Frisco TX 75034', stage: 'Clear to Close', days_in_process: 35, loan_officer: 'Timothy Loss', rate_locked: true, loan_number: 'TST-0007', program: 'Conventional 30yr Fixed', underwriter: 'Helen Rogers' },
    { id: 8, borrower_name: 'Christopher & Maria Santos', borrower: 'Christopher & Maria Santos', amount: 295000, property_address: '1234 Bluebonnet Way, Arlington TX 76011', stage: 'Clear to Close', days_in_process: 32, loan_officer: 'Timothy Loss', rate_locked: true, loan_number: 'TST-0008', program: 'FHA 30yr Fixed', underwriter: 'Kelvin Abdul' },
    { id: 22, borrower_name: 'Jessica & Andrew Moore', borrower: 'Jessica & Andrew Moore', amount: 435000, property_address: '5432 Turtle Creek Blvd, Dallas TX 75219', stage: 'Clear to Close', days_in_process: 38, loan_officer: 'Timothy Loss', rate_locked: true, loan_number: 'TST-0022', program: 'Conventional 30yr Fixed', underwriter: 'Samuel Price' },

    // Suspended (2 loans)
    { id: 9, borrower_name: 'Rachel Green', borrower: 'Rachel Green', amount: 445000, property_address: '5678 Park Lane, McKinney TX 75070', stage: 'Suspended', days_in_process: 45, loan_officer: 'Timothy Loss', rate_locked: false, lock_guidance: 'Lock Now', lock_confidence: 85, loan_number: 'TST-0009', program: 'Conventional 30yr Fixed', underwriter: 'Patricia Donovan' },
    { id: 26, borrower_name: 'Nathan & Olivia Hall', borrower: 'Nathan & Olivia Hall', amount: 395000, property_address: '2468 Hillcrest Ave, University Park TX 75205', stage: 'Suspended', days_in_process: 40, loan_officer: 'Timothy Loss', rate_locked: true, loan_number: 'TST-0026', program: 'Conventional 30yr Fixed', underwriter: 'Kelvin Abdul' },

    // ========== FUNDED LOANS (MUM Clients) ==========
    { id: 10, borrower_name: 'James & Linda Foster', borrower: 'James & Linda Foster', amount: 385000, property_address: '3456 Maple Ave, Carrollton TX 75007', stage: 'Funded This Month', days_in_process: 28, loan_officer: 'Timothy Loss', rate_locked: true, funded_date: '2025-02-28', loan_number: 'TST-0010', program: 'Conventional 30yr Fixed' },
    { id: 11, borrower_name: 'Steven & Amanda Rodriguez', borrower: 'Steven & Amanda Rodriguez', amount: 520000, property_address: '7890 Veterans Pkwy, Irving TX 75039', stage: 'Funded Prior Month', days_in_process: 30, loan_officer: 'Timothy Loss', rate_locked: true, funded_date: '2025-02-05', loan_number: 'TST-0011', program: 'VA 30yr Fixed' },
    { id: 16, borrower_name: 'Robert & Michelle Turner', borrower: 'Robert & Michelle Turner', amount: 475000, property_address: '6789 Southlake Blvd, Southlake TX 76092', stage: 'Funded Prior Month', days_in_process: 32, loan_officer: 'Timothy Loss', rate_locked: true, funded_date: '2025-01-10', loan_number: 'TST-0016', program: 'Conventional 30yr Fixed' },
    { id: 20, borrower_name: 'Timothy & Rebecca Adams', borrower: 'Timothy & Rebecca Adams', amount: 340000, property_address: '3579 Meadowbrook Dr, Colleyville TX 76034', stage: 'Funded Prior Month', days_in_process: 27, loan_officer: 'Timothy Loss', rate_locked: true, funded_date: '2024-12-05', loan_number: 'TST-0020', program: 'Conventional 15yr Fixed' },
    { id: 24, borrower_name: 'Mark & Christine Evans', borrower: 'Mark & Christine Evans', amount: 285000, property_address: '8765 Westover Hills, Fort Worth TX 76116', stage: 'Funded Prior Month', days_in_process: 29, loan_officer: 'Timothy Loss', rate_locked: true, funded_date: '2024-10-28', loan_number: 'TST-0024', program: 'FHA 30yr Fixed' },
    { id: 28, borrower_name: 'Richard & Emily Scott', borrower: 'Richard & Emily Scott', amount: 875000, property_address: '4321 Westlake Dr, Westlake TX 76262', stage: 'Funded Prior Month', days_in_process: 35, loan_officer: 'Timothy Loss', rate_locked: true, funded_date: '2024-10-15', loan_number: 'TST-0028', program: 'Jumbo 30yr Fixed' },
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
    'LE Pending',
    'In Processing',
    'In Underwriting',
    'Approved',
    'Clear to Close',
    'Suspended',
    'Funded',
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
      // Use API data if it has items, otherwise use mock data
      if (Array.isArray(data) && data.length > 0) {
        setLoans(data);
      } else {
        console.log('API returned empty/invalid data, using mock loans');
        setLoans(generateMockLoans());
      }
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

  // Filter by stage - exclude funded loans from "All" since they're closed
  const fundedStages = ['Funded This Month', 'Funded Prior Month'];
  let filteredLoans;

  if (activeFilter === 'All') {
    // Show only active (non-funded) loans
    filteredLoans = safeLoans.filter(loan => !fundedStages.includes(loan.stage));
  } else if (activeFilter === 'Funded') {
    // Show all funded loans (this month and prior)
    filteredLoans = safeLoans.filter(loan => fundedStages.includes(loan.stage));
  } else {
    filteredLoans = safeLoans.filter(loan => loan.stage === activeFilter);
  }

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
          <p>{safeLoans.filter(loan => !fundedStages.includes(loan.stage)).length} active loans</p>
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
              <th>Rate Lock</th>
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
                <td>
                  {loan.rate_locked ? (
                    <span className="rate-lock-badge locked">Locked</span>
                  ) : loan.lock_guidance ? (
                    <span className={`rate-lock-badge guidance ${loan.lock_guidance.toLowerCase().replace(' ', '-')}`}>
                      {loan.lock_guidance} <span className="confidence">{loan.lock_confidence}%</span>
                    </span>
                  ) : (
                    <span className="rate-lock-badge floating">Floating</span>
                  )}
                </td>
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
    'LE Pending': 'le_pending',
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
