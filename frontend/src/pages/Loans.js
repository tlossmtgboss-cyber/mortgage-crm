import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { loansAPI, salesforceAPI } from '../services/api';
import CalendarSidebar from '../components/CalendarSidebar';
import PermissionGate from '../components/PermissionGate';
import { usePermissions } from '../contexts/PermissionContext';
import { formatPhoneNumber } from '../utils/phoneUtils';
import './Loans.css';
import { toast } from '../utils/toast';

// Map display names to API enum values (backend uses uppercase)
const stageDisplayToApi = {
  'Application': 'APPLICATION',
  'Disclosed': 'DISCLOSED',
  'Processing': 'PROCESSING',
  'In Processing': 'PROCESSING',
  'Submitted': 'SUBMITTED',
  'Underwriting': 'UNDERWRITING',
  'In Underwriting': 'UNDERWRITING',
  'UW Received': 'UW_RECEIVED',
  'Conditional Approval': 'CONDITIONAL_APPROVAL',
  'Approved': 'APPROVED',
  'Suspended': 'SUSPENDED',
  'CTC': 'CTC',
  'Clear to Close': 'CLEAR_TO_CLOSE',
  'Closing': 'CLOSING',
  'Docs': 'DOCS',
  'Docs Out': 'DOCS_OUT',
  'Funded': 'FUNDED',
  'Cancelled': 'CANCELLED',
  'Denied': 'DENIED',
  'Dead': 'DEAD',
  'Nurture': 'NURTURE',
  'Withdrawn': 'WITHDRAWN',
  'Does Not Qualify': 'DOES_NOT_QUALIFY',
};

// Map API enum values to display names
const stageApiToDisplay = {
  'APPLICATION': 'Application',
  'DISCLOSED': 'Disclosed',
  'PROCESSING': 'Processing',
  'SUBMITTED': 'Submitted',
  'UNDERWRITING': 'Underwriting',
  'UW_RECEIVED': 'UW Received',
  'CONDITIONAL_APPROVAL': 'Conditional Approval',
  'APPROVED': 'Approved',
  'SUSPENDED': 'Suspended',
  'CTC': 'CTC',
  'CLEAR_TO_CLOSE': 'Clear to Close',
  'CLOSING': 'Closing',
  'DOCS': 'Docs',
  'DOCS_OUT': 'Docs Out',
  'FUNDED': 'Funded',
  'CANCELLED': 'Cancelled',
  'DENIED': 'Denied',
  'DEAD': 'Dead',
  'NURTURE': 'Nurture',
  'WITHDRAWN': 'Withdrawn',
  'DOES_NOT_QUALIFY': 'Does Not Qualify',
};

// Get display name for a stage value (handles both title case and uppercase)
const getStageDisplay = (stage) => {
  if (!stage) return '';
  return stageApiToDisplay[stage] || stageApiToDisplay[stage.toUpperCase()] || stage;
};

// Map pipeline stage IDs to filter names
const stageIdToFilter = {
  'new': 'New Leads',
  'preapproved': 'Pre-Approved',
  'application': 'Application',
  'disclosed': 'Disclosed',
  'processing': 'In Processing',
  'underwriting': 'In Underwriting',
  'approved': 'Approved',
  'ctc': 'Clear to Close',
  'closing': 'Closing',
  'suspended': 'Suspended',
  'funded': 'Funded',
  'inactive': 'Inactive',
};

function Loans() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const stageParam = searchParams.get('stage');
  const initialFilter = stageParam ? stageIdToFilter[stageParam] || 'All' : 'All';

  // Permission check - require loans access
  // Use isAdmin from context which has robust admin detection (checks permission_role, is_admin flag, legacy role)
  const canAccessLoans = isAdmin || hasAnyPermission(['loans.view', 'loans.view_all', 'loans.manage']) || userRole === 'sales' || userRole === 'management' || userRole === 'admin';

  const [loans, setLoans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [activeFilter, setActiveFilter] = useState(initialFilter);
  const [activeBorrower, setActiveBorrower] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusDropdown, setStatusDropdown] = useState({ show: false, loanId: null, position: { top: 0, left: 0 } });
  const [duplicateMap, setDuplicateMap] = useState({});
  const [duplicateTasksCreated, setDuplicateTasksCreated] = useState(false);
  const [selectedLoans, setSelectedLoans] = useState([]);
  const [syncingFromSalesforce, setSyncingFromSalesforce] = useState(false);
  const [syncResult, setSyncResult] = useState(null);

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
    'Application',
    'Disclosed',
    'In Processing',
    'In Underwriting',
    'Approved',
    'Clear to Close',
    'Suspended',
    'Inactive',
  ];

  // Status options — all stages across Lead, Active Loan, and MUM
  const loanStatusOptions = [
    // Lead stages
    { label: 'Lead Stages', isHeader: true },
    'New',
    'Attempted Contact',
    'Prospect',
    'Pre-Qualified',
    'Pre-Approved',
    'Long-Term Nurture',
    // Active Loan stages
    { label: 'Active Loan Stages', isHeader: true },
    'Application',
    'Disclosed',
    'Processing',
    'Submitted',
    'Underwriting',
    'UW Received',
    'Conditional Approval',
    'Approved',
    'Suspended',
    'CTC',
    'Clear to Close',
    'Closing',
    'Docs',
    'Docs Out',
    'Cancelled',
    'Denied',
    'Dead',
    'Nurture',
    'Withdrawn',
    'Does Not Qualify',
    // MUM (Funded)
    { label: 'MUM / Closed', isHeader: true },
    'Funded',
  ];

  // Map filter display names to actual API stage values (supports both legacy title case and new uppercase)
  const filterToStage = {
    'Application': ['Application', 'APPLICATION'],
    'Disclosed': ['Disclosed', 'DISCLOSED'],
    'In Processing': ['Processing', 'Submitted', 'PROCESSING', 'SUBMITTED'],
    'In Underwriting': ['UW Received', 'Underwriting', 'UW_RECEIVED', 'UNDERWRITING'],
    'Approved': ['Approved', 'APPROVED', 'Conditional Approval', 'CONDITIONAL_APPROVAL'],
    'Clear to Close': ['CTC', 'Clear to Close', 'CLEAR_TO_CLOSE', 'CTC'],
    'Suspended': ['Suspended', 'SUSPENDED'],
    'Inactive': ['Cancelled', 'CANCELLED', 'Denied', 'DENIED', 'Dead', 'DEAD', 'Nurture', 'NURTURE', 'Withdrawn', 'WITHDRAWN', 'Does Not Qualify', 'DOES_NOT_QUALIFY'],
  };

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
      // Use API data if available
      if (Array.isArray(data)) {
        setLoans(data);
        // Only detect duplicates among active pipeline loans (exclude funded/closed/etc.)
        const inactiveStages = ['FUNDED', 'Funded', 'CANCELLED', 'Cancelled', 'DENIED', 'Denied', 'DEAD', 'Dead', 'NURTURE', 'Nurture', 'WITHDRAWN', 'Withdrawn', 'DOES_NOT_QUALIFY', 'Does Not Qualify'];
        const activeLoans = data.filter(loan => {
          const stage = loan.stage || '';
          return !inactiveStages.includes(stage) && !stage.toLowerCase().includes('funded');
        });
        detectDuplicates(activeLoans);
      } else {
        setLoans([]);
      }
    } catch (err) {
      console.error('Failed to load loans:', err);
      setLoans([]);
    } finally {
      setLoading(false);
    }
  };

  // Sync all loans from Salesforce
  const handleSalesforceSync = async () => {
    setSyncingFromSalesforce(true);
    setSyncResult(null);
    try {
      const result = await salesforceAPI.syncAllLoans();
      setSyncResult({
        success: true,
        message: result.message || `Synced: ${result.linked || 0} linked, ${result.created || 0} created, ${result.updated || 0} updated`,
        details: result
      });
      // Reload loans after sync
      await loadLoans();
    } catch (err) {
      console.error('Salesforce sync failed:', err);
      const errorMsg = err.response?.data?.detail || err.response?.data?.error || err.message || 'Sync failed';
      setSyncResult({
        success: false,
        message: typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg)
      });
    } finally {
      setSyncingFromSalesforce(false);
      // Clear result after 10 seconds
      setTimeout(() => setSyncResult(null), 10000);
    }
  };

  // Detect duplicates based on borrower email
  const detectDuplicates = (loansList) => {
    const emailGroups = {};
    loansList.forEach(loan => {
      if (loan.borrower_email) {
        const email = loan.borrower_email.toLowerCase();
        if (!emailGroups[email]) {
          emailGroups[email] = [];
        }
        emailGroups[email].push({
          id: loan.id,
          loan_number: loan.loan_number,
          borrower_name: loan.borrower_name,
          stage: loan.stage,
        });
      }
    });

    // Only keep entries with duplicates
    const duplicates = {};
    Object.entries(emailGroups).forEach(([email, loans]) => {
      if (loans.length > 1) {
        loans.forEach(loan => {
          duplicates[loan.id] = {
            email,
            count: loans.length,
            otherLoans: loans.filter(l => l.id !== loan.id),
          };
        });
      }
    });
    setDuplicateMap(duplicates);
  };

  // Check if loan has duplicates
  const hasDuplicate = (loanId) => duplicateMap[loanId] !== undefined;
  const getDuplicateInfo = (loanId) => duplicateMap[loanId];
  const getTotalDuplicates = () => {
    const uniqueEmails = new Set(Object.values(duplicateMap).map(d => d.email));
    return uniqueEmails.size;
  };

  // Create tasks for duplicates
  const handleCreateDuplicateTasks = async () => {
    try {
      const token = localStorage.getItem('token');
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE = isProduction
        ? 'https://api.perenniaai.com'
        : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
      const response = await fetch(`${API_BASE}/api/v1/duplicates/create-tasks`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const data = await response.json();
        setDuplicateTasksCreated(true);
        toast.success(`Created ${data.tasks_created} tasks to review duplicate records.`);
      } else {
        const error = await response.json();
        toast.error(`Error: ${error.detail || 'Failed to create tasks'}`);
      }
    } catch (err) {
      console.error('Error creating duplicate tasks:', err);
      toast.error('Failed to create duplicate tasks');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    // Combine primary borrower data with property and loan data
    const primaryBorrower = borrowers[0];

    // Validate required fields
    const fullName = `${primaryBorrower.first_name || ''} ${primaryBorrower.last_name || ''}`.trim();
    if (!fullName) {
      toast.error('Please enter borrower first name and last name');
      return;
    }

    if (!loanData.loan_number) {
      toast.error('Please enter a loan number');
      return;
    }

    if (!loanData.amount) {
      toast.error('Please enter a loan amount');
      return;
    }

    // Build submit data matching backend LoanCreate model
    // Defined outside try block so it's accessible in catch block for retry
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

    try {
      await loansAPI.create(submitData);
      setShowModal(false);
      resetForm();
      loadLoans();
    } catch (err) {
      console.error('Failed to create loan:', err);
      console.error('Error response:', err.response);
      console.error('Error config:', err.config);
      console.error('Error message:', err.message);

      // Handle duplicate borrower detection (409 Conflict)
      if (err.response?.status === 409 && err.response?.data?.detail?.error === 'duplicate_borrower') {
        const detail = err.response.data.detail;
        const existingLoan = detail.existing_loan;

        const confirmCreate = window.confirm(
          `⚠️ Duplicate Borrower Detected\n\n` +
          `A loan for "${existingLoan.borrower_name}" already exists:\n` +
          `• Loan #: ${existingLoan.loan_number}\n` +
          `• Status: ${getStageDisplay(existingLoan.stage)}\n` +
          `• Amount: $${existingLoan.amount?.toLocaleString()}\n\n` +
          `Do you want to create a new loan anyway?`
        );

        if (confirmCreate) {
          try {
            // Retry with skip_duplicate_check=true
            await loansAPI.create(submitData, true);
            setShowModal(false);
            resetForm();
            loadLoans();
          } catch (retryErr) {
            console.error('Failed to create loan (retry):', retryErr);
            toast.error(`Failed to create loan: ${retryErr.response?.data?.detail || retryErr.message}`);
          }
        }
        return;
      }

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

      toast.error(`Failed to create loan: ${errorMessage}`);
    }
  };

  const handleDelete = async (id) => {
    try {
      await loansAPI.delete(id);
      loadLoans();
    } catch (err) {
      toast.error('Failed to delete loan');
    }
  };

  // Bulk selection and delete handlers
  const handleSelectLoan = (loanId, e) => {
    e.stopPropagation(); // Prevent row click navigation
    setSelectedLoans(prev =>
      prev.includes(loanId)
        ? prev.filter(id => id !== loanId)
        : [...prev, loanId]
    );
  };

  const handleSelectAll = (e) => {
    e.stopPropagation();
    if (selectedLoans.length === filteredLoans.length) {
      setSelectedLoans([]);
    } else {
      setSelectedLoans(filteredLoans.map(loan => loan.id));
    }
  };

  const handleBulkDelete = async () => {
    if (selectedLoans.length === 0) {
      toast.error('No loans selected');
      return;
    }

    const confirmDelete = window.confirm(
      `Are you sure you want to delete ${selectedLoans.length} loan${selectedLoans.length > 1 ? 's' : ''}?\n\nThis action cannot be undone.`
    );

    if (!confirmDelete) return;

    try {
      const result = await loansAPI.bulkDelete(selectedLoans);
      toast.success(`Successfully deleted ${result.deleted_count} loans${result.errors?.length > 0 ? ` with ${result.errors.length} errors` : ''}`);
      setSelectedLoans([]);
      loadLoans();
    } catch (err) {
      console.error('Failed to bulk delete loans:', err);
      const errorDetail = err.response?.data?.detail;
      const errorMessage = typeof errorDetail === 'string'
        ? errorDetail
        : (errorDetail?.message || err.message || 'Unknown error');
      toast.error('Failed to delete loans: ' + errorMessage);
    }
  };

  // Status dropdown handlers
  const handleStatusClick = (e, loanId) => {
    e.stopPropagation(); // Prevent row click navigation
    const rect = e.target.getBoundingClientRect();
    setStatusDropdown({
      show: true,
      loanId,
      position: {
        top: rect.bottom + window.scrollY + 5,
        left: rect.left + window.scrollX,
      },
    });
  };

  const handleStatusChange = async (newStatus) => {
    const loanId = statusDropdown.loanId;
    setStatusDropdown({ show: false, loanId: null, position: { top: 0, left: 0 } });

    // Convert display name to API enum value
    const apiStage = stageDisplayToApi[newStatus] || newStatus.toUpperCase().replace(/ /g, '_');

    try {
      await loansAPI.update(loanId, { stage: apiStage });
      // Update local state with the API value (will be displayed via getStageDisplay)
      setLoans(loans.map(loan =>
        loan.id === loanId ? { ...loan, stage: apiStage } : loan
      ));
    } catch (err) {
      console.error('Failed to update loan status:', err);
      const errorMsg = err.response?.data?.detail || err.response?.data?.error || err.message || 'Failed to update loan status';
      toast.error(errorMsg);
    }
  };

  const closeStatusDropdown = () => {
    setStatusDropdown({ show: false, loanId: null, position: { top: 0, left: 0 } });
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
    toast.info('Export functionality coming soon');
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
    if (borrowers.length > 1) {
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

  // Filter by stage - exclude funded loans from "All" since they belong in Portfolio
  // Include all variations of "Funded" status
  // Inactive stages that don't appear in the "All" active pipeline view
  const inactiveStages = ['FUNDED', 'Funded', 'CANCELLED', 'Cancelled', 'DENIED', 'Denied', 'DEAD', 'Dead', 'NURTURE', 'Nurture', 'WITHDRAWN', 'Withdrawn', 'DOES_NOT_QUALIFY', 'Does Not Qualify'];

  const isInactiveLoan = (loan) => {
    const stage = loan.stage || '';
    return inactiveStages.includes(stage) || stage.toLowerCase().includes('funded');
  };

  let filteredLoans;

  if (activeFilter === 'All') {
    // Show only active (non-funded/inactive) loans
    filteredLoans = safeLoans.filter(loan => !isInactiveLoan(loan));
  } else {
    // Use the mapping to match filter name to actual API stage values
    const stageValues = filterToStage[activeFilter] || [activeFilter];
    filteredLoans = safeLoans.filter(loan => stageValues.includes(loan.stage));
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

  // Access denied if user doesn't have loans permissions
  if (!canAccessLoans) {
    return (
      <div className="loans-page-wrapper">
        <div className="loans-page">
          <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
            <h2>Access Denied</h2>
            <p>You don't have permission to view loans.</p>
            <button className="btn-primary" onClick={() => navigate('/dashboard')}>
              Return to Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (loading) return <div className="loading">Loading loans...</div>;

  return (
    <div className="loans-page-wrapper">
      <div className="loans-page">
        <div className="page-header">
          <div>
            <h1>Active Loans</h1>
          <p>{safeLoans.filter(loan => !isInactiveLoan(loan)).length} active loans</p>
        </div>
        <div className="header-actions">
          {selectedLoans.length > 0 && (
            <PermissionGate permission="loans.delete" isWriteOperation showDisabled>
              <button className="btn-danger" onClick={handleBulkDelete}>
                Delete Selected ({selectedLoans.length})
              </button>
            </PermissionGate>
          )}
        </div>
        {syncResult && (
          <div className={`sync-result ${syncResult.success ? 'success' : 'error'}`}>
            {syncResult.message}
          </div>
        )}
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

      {/* Duplicate Warning Banner */}
      {getTotalDuplicates() > 0 && (
        <div className="duplicate-warning-banner">
          <div className="duplicate-warning-content">
            <span className="duplicate-icon">⚠️</span>
            <span className="duplicate-text">
              <strong>{getTotalDuplicates()} potential duplicate{getTotalDuplicates() > 1 ? 's' : ''} detected</strong>
              {' '}- Loans with the same borrower email found. Review and merge to avoid confusion.
            </span>
          </div>
          {!duplicateTasksCreated && (
            <button className="create-tasks-btn" onClick={handleCreateDuplicateTasks}>
              Create Merge Tasks
            </button>
          )}
          {duplicateTasksCreated && (
            <span className="tasks-created-badge">✓ Tasks Created</span>
          )}
        </div>
      )}

      <div className="table-container">
        <table className="loans-table">
          <thead>
            <tr>
              <th className="checkbox-column">
                <input
                  type="checkbox"
                  checked={filteredLoans.length > 0 && selectedLoans.length === filteredLoans.length}
                  onChange={handleSelectAll}
                  title="Select all"
                />
              </th>
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
                className={`${hasDuplicate(loan.id) ? 'has-duplicate' : ''} ${selectedLoans.includes(loan.id) ? 'selected' : ''}`}
                onClick={() => navigate(`/loans/${loan.id}`)}
                style={{ cursor: 'pointer' }}
              >
                <td className="checkbox-column" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selectedLoans.includes(loan.id)}
                    onChange={(e) => handleSelectLoan(loan.id, e)}
                  />
                </td>
                <td className="borrower-name">
                  <div className="borrower-info">
                    <span>{(loan.borrower_name && loan.borrower_name !== 'Unknown Borrower') ? loan.borrower_name : loan.borrower || loan.borrower_email || 'Unknown Borrower'}</span>
                    {hasDuplicate(loan.id) && (
                      <span
                        className="duplicate-badge"
                        title={`Duplicate: Same email as ${getDuplicateInfo(loan.id).otherLoans.map(l => l.loan_number || l.borrower_name).join(', ')}`}
                      >
                        DUPLICATE
                      </span>
                    )}
                  </div>
                </td>
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
                  <span
                    className={`status-badge status-${getStatusClass(loan.stage)} status-clickable`}
                    onClick={(e) => handleStatusClick(e, loan.id)}
                    title="Click to change status"
                  >
                    {getStageDisplay(loan.stage)}
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
                {getStageDisplay(loan.stage)}
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
                    onChange={(e) => updateBorrower(activeBorrower, 'phone', formatPhoneNumber(e.target.value))}
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

      {/* Status Dropdown Popup */}
      {statusDropdown.show && (
        <>
          <div className="status-dropdown-overlay" onClick={closeStatusDropdown} />
          <div
            className="status-dropdown-popup"
            style={{
              top: statusDropdown.position.top,
              left: statusDropdown.position.left,
            }}
          >
            <div className="status-dropdown-header">Change Loan Status</div>
            <div className="status-dropdown-options" style={{ maxHeight: '400px', overflowY: 'auto' }}>
              {loanStatusOptions.map((status, idx) => (
                status.isHeader ? (
                  <div key={status.label} className="status-dropdown-section-header" style={{
                    padding: '6px 12px',
                    fontSize: '11px',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    color: '#6b7280',
                    borderTop: idx > 0 ? '1px solid #e5e7eb' : 'none',
                    marginTop: idx > 0 ? '4px' : 0,
                    letterSpacing: '0.05em',
                  }}>
                    {status.label}
                  </div>
                ) : (
                  <button
                    key={status}
                    className={`status-dropdown-option status-${getStatusClass(status)}`}
                    onClick={() => handleStatusChange(status)}
                  >
                    {status}
                  </button>
                )
              ))}
            </div>
          </div>
        </>
      )}
      </div>
      <CalendarSidebar />
    </div>
  );
}

function getStatusClass(status) {
  if (!status) return 'default';
  const statusMap = {
    // Lead stages
    'New': 'new',
    'Attempted Contact': 'attempted-contact',
    'Prospect': 'prospect',
    'Pre-Qualified': 'pre-qualified',
    'Pre-Approved': 'pre-approved',
    'Long-Term Nurture': 'nurture',
    // Application
    'Application': 'application',
    'APPLICATION': 'application',
    'Contract Received': 'application',
    // Disclosed
    'Disclosed': 'disclosed',
    'DISCLOSED': 'disclosed',
    // Processing
    'Processing': 'processing',
    'PROCESSING': 'processing',
    'In Processing': 'processing',
    'Submitted': 'processing',
    'SUBMITTED': 'processing',
    // Underwriting
    'Underwriting': 'underwriting',
    'UNDERWRITING': 'underwriting',
    'In Underwriting': 'underwriting',
    'UW Received': 'underwriting',
    'UW_RECEIVED': 'underwriting',
    // Approved
    'Conditional Approval': 'approved',
    'CONDITIONAL_APPROVAL': 'approved',
    'Approved': 'approved',
    'APPROVED': 'approved',
    // Clear to Close
    'CTC': 'ctc',
    'Clear to Close': 'ctc',
    'CLEAR_TO_CLOSE': 'ctc',
    // Closing / Docs
    'Closing': 'closing',
    'CLOSING': 'closing',
    'Docs': 'closing',
    'DOCS': 'closing',
    'Docs Out': 'closing',
    'DOCS_OUT': 'closing',
    // Suspended
    'Suspended': 'suspended',
    'SUSPENDED': 'suspended',
    // Funded
    'Funded': 'funded',
    'FUNDED': 'funded',
    // Inactive statuses
    'Cancelled': 'cancelled',
    'CANCELLED': 'cancelled',
    'Denied': 'denied',
    'DENIED': 'denied',
    'Dead': 'dead',
    'DEAD': 'dead',
    'Nurture': 'nurture',
    'NURTURE': 'nurture',
    'Withdrawn': 'withdrawn',
    'WITHDRAWN': 'withdrawn',
    'Does Not Qualify': 'not-qualified',
    'DOES_NOT_QUALIFY': 'not-qualified',
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
