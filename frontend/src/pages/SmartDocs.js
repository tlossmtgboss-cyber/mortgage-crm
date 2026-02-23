/**
 * SmartDocs Page
 *
 * Dashboard for managing document workflows across all applicants.
 * Shows:
 * - Loan search functionality
 * - Clients that owe documents
 * - Clients with uploaded documents pending review
 * - Completed clients (finished financing)
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { smartDocsAPI } from '../services/smartDocsApi';
import { API_BASE_URL } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import { isMasterAdmin } from '../config/roleConfig';
import AdminContracts from '../components/AdminContracts';
import './SmartDocs.css';
import { toast } from '../utils/toast';

function SmartDocs() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin, isPlatformAdmin } = usePermissions();

  // Permission check - require documents/loans access
  // Use isAdmin from context which has robust admin detection (checks permission_role, is_admin flag, legacy role)
  const canAccessSmartDocs = isAdmin || hasAnyPermission(['documents.view', 'documents.manage', 'loans.view', 'loans.manage']) || userRole === 'sales' || userRole === 'management' || userRole === 'admin';

  const [activeTab, setActiveTab] = useState('documents-owed');
  const [summary, setSummary] = useState(null);
  const [pendingReview, setPendingReview] = useState({ applicants: [], total: 0 });
  const [outstandingDocs, setOutstandingDocs] = useState({ applicants: [], total: 0 });
  const [completedClients, setCompletedClients] = useState({ applicants: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pagination, setPagination] = useState({ page: 1, limit: 20 });
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [docTypeFilter, setDocTypeFilter] = useState('all');
  const [duplicateMap, setDuplicateMap] = useState({});  // Map of email -> list of loan IDs
  const [duplicateTasksCreated, setDuplicateTasksCreated] = useState(false);

  // Queue view state
  const [queueData, setQueueData] = useState({ queue: [], total: 0, summary: {} });
  const [queueSummary, setQueueSummary] = useState(null);
  const [slaFilter, setSlaFilter] = useState('all');

  // Fetch all loans and categorize them
  const fetchAllLoans = useCallback(async () => {
    try {
      // Try multiple endpoints
      let loans = [];

      // Use the Smart Docs loans endpoint (shows all active loans without permission filtering)
      const token = localStorage.getItem('token');
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

      let response = await fetch(`${API_BASE_URL}/api/v1/smart-docs/loans`, { headers });

      if (response.ok) {
        const data = await response.json();
        loans = data.loans || [];
      } else {
        // Fallback to main loans endpoint if smart-docs endpoint fails
        response = await fetch(`${API_BASE_URL}/api/v1/loans/`, { headers });
        if (response.ok) {
          const data = await response.json();
          loans = Array.isArray(data) ? data : (data.loans || []);
        }
      }

      // Categorize loans
      const owed = [];
      const uploaded = [];
      const completed = [];

      loans.forEach(loan => {
        const loanData = {
          loan_id: loan.id,
          loan_number: loan.loan_number,
          borrower_name: loan.borrower_name || loan.primary_borrower_name || 'Unknown',
          borrower_email: loan.borrower_email,
          borrower_phone: loan.borrower_phone,
          loan_purpose: loan.loan_purpose || loan.purpose,
          loan_amount: loan.amount || loan.loan_amount || 0,
          program: loan.program || loan.loan_type,
          stage: loan.stage,
          property_address: loan.property_address,
          closing_date: loan.closing_date,
          rate: loan.rate,
          funded_at: loan.funded_at,
          created_at: loan.created_at,
          outstanding_count: loan.outstanding_docs_count || 0,
          overdue_count: loan.overdue_docs_count || 0,
          pending_count: loan.pending_docs_count || 0,
          requests: [],
          documents: [],
        };

        // Categorize based on stage (API returns 'stage' not 'status')
        const stage = (loan.stage || loan.status || '').toLowerCase();
        if (stage === 'funded' || stage === 'closed') {
          completed.push(loanData);
        } else {
          // All non-funded loans go to "owed" (active pipeline)
          owed.push({ ...loanData, outstanding_count: 1 });
        }
      });

      setOutstandingDocs({
        applicants: owed,
        total: owed.length,
        total_pages: Math.ceil(owed.length / pagination.limit) || 1,
      });

      setPendingReview({
        applicants: uploaded,
        total: uploaded.length,
        total_pages: Math.ceil(uploaded.length / pagination.limit) || 1,
      });

      setCompletedClients({
        applicants: completed,
        total: completed.length,
        total_pages: Math.ceil(completed.length / pagination.limit) || 1,
      });

      setSummary({
        outstanding_requests: { applicants: owed.length, overdue: 0 },
        pending_review: { applicants: uploaded.length, documents: 0 },
      });

      // Detect duplicates based on borrower_email
      const emailGroups = {};
      [...owed, ...uploaded, ...completed].forEach(loan => {
        if (loan.borrower_email) {
          const email = loan.borrower_email.toLowerCase();
          if (!emailGroups[email]) {
            emailGroups[email] = [];
          }
          emailGroups[email].push({
            loan_id: loan.loan_id,
            loan_number: loan.loan_number,
            borrower_name: loan.borrower_name,
            stage: loan.stage,
          });
        }
      });

      // Only keep entries with duplicates (more than 1 loan per email)
      const duplicates = {};
      Object.entries(emailGroups).forEach(([email, loanList]) => {
        if (loanList.length > 1) {
          loanList.forEach(loan => {
            duplicates[loan.loan_id] = {
              email,
              count: loanList.length,
              otherLoans: loanList.filter(l => l.loan_id !== loan.loan_id),
            };
          });
        }
      });
      setDuplicateMap(duplicates);

      // Don't show error even if no loans - just show empty state
    } catch (err) {
      console.error('Error fetching loans:', err);
      // Set empty data instead of error so UI still works
      setOutstandingDocs({ applicants: [], total: 0, total_pages: 1 });
      setPendingReview({ applicants: [], total: 0, total_pages: 1 });
      setCompletedClients({ applicants: [], total: 0, total_pages: 1 });
      setSummary({
        outstanding_requests: { applicants: 0, overdue: 0 },
        pending_review: { applicants: 0, documents: 0 },
      });
    }
  }, [pagination.limit]);

  // Fetch dashboard summary
  const fetchSummary = useCallback(async () => {
    try {
      const data = await smartDocsAPI.getDashboardSummary();
      setSummary(data);
    } catch (err) {
      console.error('Error fetching summary:', err);
      // Summary will be set by fetchAllLoans as fallback
    }
  }, []);

  // Fetch pending review applicants
  const fetchPendingReview = useCallback(async () => {
    try {
      const data = await smartDocsAPI.getApplicantsPendingReview(pagination.page, pagination.limit);
      setPendingReview(data);
    } catch (err) {
      console.error('Error fetching pending review:', err);
      // Will use data from fetchAllLoans
    }
  }, [pagination]);

  // Fetch outstanding docs applicants
  const fetchOutstandingDocs = useCallback(async () => {
    try {
      const data = await smartDocsAPI.getApplicantsOutstandingDocs(
        pagination.page,
        pagination.limit,
        overdueOnly
      );
      setOutstandingDocs(data);
    } catch (err) {
      console.error('Error fetching outstanding docs:', err);
      // Will use data from fetchAllLoans
    }
  }, [pagination, overdueOnly]);

  // Fetch completed clients (loans that are funded/closed)
  const fetchCompletedClients = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/loans?status=funded&limit=${pagination.limit}&page=${pagination.page}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        const loans = data.loans || data || [];
        setCompletedClients({
          applicants: loans.map(loan => ({
            loan_id: loan.id,
            loan_number: loan.loan_number,
            borrower_name: loan.borrower_name || loan.primary_borrower_name || 'Unknown',
            loan_purpose: loan.loan_purpose,
            funded_at: loan.funded_at,
            loan_amount: loan.loan_amount,
          })),
          total: loans.length,
          total_pages: Math.ceil(loans.length / pagination.limit) || 1,
        });
      }
    } catch (err) {
      console.error('Error fetching completed clients:', err);
    }
  }, [pagination]);

  // Fetch queue data
  const fetchQueue = useCallback(async () => {
    try {
      const slaStatus = slaFilter !== 'all' ? slaFilter : null;
      const data = await smartDocsAPI.getQueue(
        pagination.page,
        pagination.limit,
        slaStatus,
        searchQuery || null
      );
      setQueueData(data);
    } catch (err) {
      console.error('Error fetching queue:', err);
    }
  }, [pagination, slaFilter, searchQuery]);

  // Fetch queue summary
  const fetchQueueSummary = useCallback(async () => {
    try {
      const data = await smartDocsAPI.getQueueSummary();
      setQueueSummary(data);
    } catch (err) {
      console.error('Error fetching queue summary:', err);
    }
  }, []);

  // Handle sending reminder
  const handleSendReminder = async (loanId) => {
    try {
      const result = await smartDocsAPI.sendReminder(loanId);
      if (result.sent) {
        toast.success(`Reminder sent for ${result.documents_reminded} documents`);
        fetchQueue(); // Refresh queue
      } else {
        toast.error(result.message || 'Could not send reminder');
      }
    } catch (err) {
      console.error('Error sending reminder:', err);
      toast.error('Failed to send reminder');
    }
  };

  // Initial load - fetch all data
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      await Promise.all([
        fetchAllLoans(),
        fetchQueueSummary(),
      ]);
      setLoading(false);
    };
    loadData();
  }, [fetchAllLoans, fetchQueueSummary]);

  // Fetch queue when tab is active
  useEffect(() => {
    if (activeTab === 'queue') {
      fetchQueue();
    }
  }, [activeTab, fetchQueue]);

  // Handle tab change
  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setPagination({ page: 1, limit: 20 });
  };

  // Filter applicants by search query
  const filterBySearch = (applicants) => {
    if (!searchQuery.trim()) return applicants;
    const query = searchQuery.toLowerCase();
    return applicants.filter(applicant =>
      (applicant.borrower_name && applicant.borrower_name.toLowerCase().includes(query)) ||
      (applicant.loan_number && applicant.loan_number.toLowerCase().includes(query)) ||
      (applicant.loan_id && String(applicant.loan_id).includes(query))
    );
  };

  // Get filtered data based on active tab
  const getFilteredData = () => {
    if (activeTab === 'documents-uploaded') {
      return filterBySearch(pendingReview.applicants);
    } else if (activeTab === 'documents-owed') {
      return filterBySearch(outstandingDocs.applicants);
    } else if (activeTab === 'completed') {
      return filterBySearch(completedClients.applicants);
    }
    return [];
  };

  // Format currency
  const formatCurrency = (amount) => {
    if (!amount) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  // Format date
  const formatDate = (dateString) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    const now = new Date();
    const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;

    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  // Format due date with urgency
  const formatDueDate = (dateString) => {
    if (!dateString) return { text: 'No due date', class: '' };
    const date = new Date(dateString);
    const now = new Date();
    const diffDays = Math.ceil((date - now) / (1000 * 60 * 60 * 24));

    if (diffDays < 0) return { text: `${Math.abs(diffDays)} days overdue`, class: 'overdue' };
    if (diffDays === 0) return { text: 'Due today', class: 'urgent' };
    if (diffDays <= 3) return { text: `Due in ${diffDays} days`, class: 'soon' };

    return {
      text: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      class: ''
    };
  };

  // Get priority badge class
  const getPriorityClass = (priority) => {
    switch (priority?.toUpperCase()) {
      case 'CRITICAL': return 'critical';
      case 'HIGH': return 'high';
      case 'NORMAL': return 'normal';
      case 'LOW': return 'low';
      default: return 'normal';
    }
  };

  // Check if a loan has duplicates
  const hasDuplicate = (loanId) => {
    return duplicateMap[loanId] !== undefined;
  };

  // Get duplicate info for a loan
  const getDuplicateInfo = (loanId) => {
    return duplicateMap[loanId];
  };

  // Get total duplicate count
  const getTotalDuplicates = () => {
    const uniqueEmails = new Set(Object.values(duplicateMap).map(d => d.email));
    return uniqueEmails.size;
  };

  // Create tasks for all duplicates
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

  // Platform admin sees contracts dashboard instead of loan documents
  const userEmail = (() => {
    try { return JSON.parse(localStorage.getItem('user'))?.email; } catch { return null; }
  })();
  if (isPlatformAdmin || isMasterAdmin(userEmail)) {
    return <AdminContracts />;
  }

  // Access denied if user doesn't have documents permissions
  if (!canAccessSmartDocs) {
    return (
      <div className="smart-docs-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Smart Docs.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const filteredData = getFilteredData();

  return (
    <div className="smart-docs-page">
      {/* Header */}
      <div className="smart-docs-header">
        <div className="header-content">
          <h1>Smart Docs</h1>
          <p className="subtitle">Track and manage document collection across all clients</p>
        </div>
      </div>

      {/* Duplicate Warning Banner */}
      {getTotalDuplicates() > 0 && (
        <div className="duplicate-warning-banner">
          <div className="duplicate-warning-content">
            <span className="duplicate-icon">⚠️</span>
            <span className="duplicate-text">
              <strong>{getTotalDuplicates()} potential duplicate{getTotalDuplicates() > 1 ? 's' : ''} detected</strong>
              {' '}- Records with the same email address found. Review and merge to avoid confusion.
            </span>
          </div>
          {!duplicateTasksCreated && (
            <button
              className="create-tasks-btn"
              onClick={handleCreateDuplicateTasks}
            >
              Create Merge Tasks
            </button>
          )}
          {duplicateTasksCreated && (
            <span className="tasks-created-badge">✓ Tasks Created</span>
          )}
        </div>
      )}

      {/* Filters Bar */}
      <div className="filters-bar">
        <div className="filter-group">
          <select
            className="filter-select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Status</option>
            <option value="pending">Pending Review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="expired">Expired</option>
          </select>
        </div>

        <div className="filter-group">
          <select
            className="filter-select"
            value={docTypeFilter}
            onChange={(e) => setDocTypeFilter(e.target.value)}
          >
            <option value="all">All Document Types</option>
            <option value="income">Income Documents</option>
            <option value="assets">Asset Documents</option>
            <option value="identity">Identity Documents</option>
            <option value="property">Property Documents</option>
            <option value="credit">Credit Documents</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className="search-input-wrapper">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            className="search-input"
            placeholder="Search by borrower or loan..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              className="search-clear"
              onClick={() => setSearchQuery('')}
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="summary-cards">
          <div
            className={`summary-card outstanding ${activeTab === 'documents-owed' ? 'active' : ''}`}
            onClick={() => handleTabChange('documents-owed')}
          >
            <div className="card-value">{summary.outstanding_requests?.applicants || 0}</div>
            <div className="card-label">Documents Owed</div>
            <div className="card-sub">
              {summary.outstanding_requests?.overdue || 0} overdue
            </div>
          </div>
          <div
            className={`summary-card pending ${activeTab === 'documents-uploaded' ? 'active' : ''}`}
            onClick={() => handleTabChange('documents-uploaded')}
          >
            <div className="card-value">{summary.pending_review?.applicants || 0}</div>
            <div className="card-label">Documents Uploaded</div>
            <div className="card-sub">{summary.pending_review?.documents || 0} documents to review</div>
          </div>
          <div
            className={`summary-card completed ${activeTab === 'completed' ? 'active' : ''}`}
            onClick={() => handleTabChange('completed')}
          >
            <div className="card-value">{completedClients.total || 0}</div>
            <div className="card-label">Completed</div>
            <div className="card-sub">Finished financing</div>
          </div>
        </div>
      )}

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Tabs */}
      <div className="smart-docs-tabs">
        <button
          className={`tab-btn ${activeTab === 'documents-owed' ? 'active' : ''}`}
          onClick={() => handleTabChange('documents-owed')}
        >
          Documents Owed
          {outstandingDocs.total > 0 && (
            <span className="tab-badge outstanding">{outstandingDocs.total}</span>
          )}
        </button>
        <button
          className={`tab-btn ${activeTab === 'documents-uploaded' ? 'active' : ''}`}
          onClick={() => handleTabChange('documents-uploaded')}
        >
          Documents Uploaded
          {pendingReview.total > 0 && (
            <span className="tab-badge pending">{pendingReview.total}</span>
          )}
        </button>
        <button
          className={`tab-btn ${activeTab === 'completed' ? 'active' : ''}`}
          onClick={() => handleTabChange('completed')}
        >
          Completed
          {completedClients.total > 0 && (
            <span className="tab-badge completed">{completedClients.total}</span>
          )}
        </button>
        <button
          className={`tab-btn ${activeTab === 'queue' ? 'active' : ''}`}
          onClick={() => handleTabChange('queue')}
        >
          Queue View
          {queueSummary?.by_sla_status?.breached > 0 && (
            <span className="tab-badge breached">{queueSummary.by_sla_status.breached}</span>
          )}
        </button>
      </div>

      {/* Tab Content */}
      <div className="smart-docs-content">
        {loading ? (
          <div className="loading-state">
            <div className="spinner" />
            <p>Loading...</p>
          </div>
        ) : activeTab === 'documents-owed' ? (
          /* Documents Owed Tab */
          <div className="applicants-list">
            <div className="list-filters">
              <label className="filter-checkbox">
                <input
                  type="checkbox"
                  checked={overdueOnly}
                  onChange={(e) => setOverdueOnly(e.target.checked)}
                />
                Show overdue only
              </label>
            </div>
            {filteredData.length === 0 ? (
              <div className="empty-state">
                <span className="empty-icon">✓</span>
                <h3>{searchQuery ? 'No matching clients' : 'All documents collected!'}</h3>
                <p>{searchQuery ? 'Try a different search term' : 'No outstanding document requests'}</p>
              </div>
            ) : (
              <div className="table-container">
                <table className="smart-docs-table">
                  <thead>
                    <tr>
                      <th>Client</th>
                      <th>Docs Status</th>
                      <th>Stage</th>
                      <th>Docs Progress</th>
                      <th>Status</th>
                      <th>Days Waiting</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredData.map((applicant) => {
                      const docsCollected = applicant.docs_collected || 0;
                      const docsRequired = applicant.docs_required || 8;
                      const completionPct = docsRequired > 0 ? Math.round((docsCollected / docsRequired) * 100) : 0;
                      const daysWaiting = applicant.created_at
                        ? Math.floor((new Date() - new Date(applicant.created_at)) / (1000 * 60 * 60 * 24))
                        : 0;
                      const isOverdue = daysWaiting > 5;
                      const isAtRisk = daysWaiting > 3 && daysWaiting <= 5;

                      return (
                      <tr
                        key={applicant.loan_id}
                        className={`${isOverdue ? 'has-overdue' : ''} ${hasDuplicate(applicant.loan_id) ? 'has-duplicate' : ''}`}
                        onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                      >
                        <td>
                          <div className="borrower-info">
                            <span className="borrower-name">{applicant.borrower_name}</span>
                            {hasDuplicate(applicant.loan_id) && (
                              <span
                                className="duplicate-badge"
                                title={`Duplicate: Same email as ${getDuplicateInfo(applicant.loan_id).otherLoans.map(l => l.loan_number || l.borrower_name).join(', ')}`}
                              >
                                DUPLICATE
                              </span>
                            )}
                          </div>
                          {applicant.borrower_email && (
                            <span className="borrower-email">{applicant.borrower_email}</span>
                          )}
                        </td>
                        <td className="docs-status-cell">
                          <div className="docs-counts">
                            <span className="docs-requested" title="Documents Requested">
                              {applicant.outstanding_count || docsRequired} requested
                            </span>
                            <span className="docs-to-review" title="Documents to Review">
                              {applicant.pending_count || 0} to review
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className={`stage-badge stage-${(applicant.stage || 'processing').toLowerCase().replace(/\s+/g, '-')}`}>
                            {applicant.stage || 'Processing'}
                          </span>
                        </td>
                        <td>
                          <div className="completion-cell">
                            <div className="progress-bar">
                              <div
                                className="progress-fill"
                                style={{ width: `${completionPct}%` }}
                              />
                            </div>
                            <span className="completion-text">
                              {docsCollected}/{docsRequired}
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className={`sla-badge ${isOverdue ? 'sla-breached' : isAtRisk ? 'sla-at_risk' : 'sla-good'}`}>
                            {isOverdue ? 'OVERDUE' : isAtRisk ? 'AT RISK' : 'ON TRACK'}
                          </span>
                        </td>
                        <td className="days-waiting">
                          <span className={daysWaiting > 5 ? 'text-danger' : daysWaiting > 3 ? 'text-warning' : ''}>
                            {daysWaiting} {daysWaiting === 1 ? 'day' : 'days'}
                          </span>
                        </td>
                        <td>
                          <button className="btn-view-sm" onClick={(e) => { e.stopPropagation(); navigate(`/smart-docs/client/${applicant.loan_id}`); }}>
                            View
                          </button>
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : activeTab === 'documents-uploaded' ? (
          /* Documents Uploaded Tab */
          <div className="applicants-list">
            {filteredData.length === 0 ? (
              <div className="empty-state">
                <span className="empty-icon">✓</span>
                <h3>{searchQuery ? 'No matching clients' : 'All caught up!'}</h3>
                <p>{searchQuery ? 'Try a different search term' : 'No documents pending review'}</p>
              </div>
            ) : (
              <div className="table-container">
                <table className="smart-docs-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Loan #</th>
                      <th>Purpose</th>
                      <th>Pending Docs</th>
                      <th>Oldest Upload</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredData.map((applicant) => (
                      <tr
                        key={applicant.loan_id}
                        onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                      >
                        <td>
                          <span className="borrower-name">{applicant.borrower_name}</span>
                        </td>
                        <td className="loan-number">{applicant.loan_number || `#${applicant.loan_id}`}</td>
                        <td>{applicant.loan_purpose || '-'}</td>
                        <td>
                          <span className="pending-badge">{applicant.pending_count} pending</span>
                        </td>
                        <td className="date-cell">{formatDate(applicant.oldest_upload)}</td>
                        <td>
                          <button className="btn-review-sm" onClick={(e) => { e.stopPropagation(); navigate(`/smart-docs/client/${applicant.loan_id}`); }}>
                            Review
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : activeTab === 'completed' ? (
          /* Completed Tab */
          <div className="applicants-list">
            {filteredData.length === 0 ? (
              <div className="empty-state">
                <span className="empty-icon">🎉</span>
                <h3>{searchQuery ? 'No matching clients' : 'No completed loans yet'}</h3>
                <p>{searchQuery ? 'Try a different search term' : 'Funded loans will appear here'}</p>
              </div>
            ) : (
              <div className="table-container">
                <table className="smart-docs-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Loan #</th>
                      <th>Purpose</th>
                      <th>Amount</th>
                      <th>Funded</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredData.map((applicant) => (
                      <tr
                        key={applicant.loan_id}
                        className="completed-row"
                        onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                      >
                        <td>
                          <span className="borrower-name">{applicant.borrower_name}</span>
                        </td>
                        <td className="loan-number">{applicant.loan_number || `#${applicant.loan_id}`}</td>
                        <td>{applicant.loan_purpose || '-'}</td>
                        <td className="loan-amount">{formatCurrency(applicant.loan_amount)}</td>
                        <td className="date-cell">{formatDate(applicant.funded_at)}</td>
                        <td>
                          <span className="completed-badge">Completed</span>
                        </td>
                        <td>
                          <button className="btn-view-sm" onClick={(e) => { e.stopPropagation(); navigate(`/smart-docs/client/${applicant.loan_id}`); }}>
                            Archive
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          /* Queue View Tab */
          <div className="queue-view">
            {/* SLA Filter */}
            <div className="queue-filters">
              <select
                className="filter-select"
                value={slaFilter}
                onChange={(e) => setSlaFilter(e.target.value)}
              >
                <option value="all">All SLA Status</option>
                <option value="BREACHED">Breached</option>
                <option value="AT_RISK">At Risk</option>
                <option value="GOOD">Good</option>
              </select>
            </div>

            {/* Queue Summary Cards */}
            {queueSummary && (
              <div className="queue-summary-cards">
                <div className="queue-summary-card breached">
                  <div className="card-value">{queueSummary.by_sla_status?.breached || 0}</div>
                  <div className="card-label">SLA Breached</div>
                </div>
                <div className="queue-summary-card at-risk">
                  <div className="card-value">{queueSummary.by_sla_status?.at_risk || 0}</div>
                  <div className="card-label">At Risk</div>
                </div>
                <div className="queue-summary-card good">
                  <div className="card-value">{queueSummary.by_sla_status?.good || 0}</div>
                  <div className="card-label">On Track</div>
                </div>
              </div>
            )}

            {/* Queue Table */}
            {queueData.queue.length === 0 ? (
              <div className="empty-state">
                <span className="empty-icon">✓</span>
                <h3>No clients in queue</h3>
                <p>All document requests have been fulfilled</p>
              </div>
            ) : (
              <div className="table-container">
                <table className="smart-docs-table">
                  <thead>
                    <tr>
                      <th>Client</th>
                      <th>Loan #</th>
                      <th>Completion</th>
                      <th>SLA Status</th>
                      <th>Last Activity</th>
                      <th>Reminders</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {queueData.queue.map((item) => (
                      <tr
                        key={item.loan_id}
                        className={`queue-row ${item.has_sla_breach ? 'has-breach' : ''}`}
                        onClick={() => navigate(`/smart-docs/client/${item.loan_id}`)}
                      >
                        <td>
                          <div className="borrower-info">
                            <span className="borrower-name">{item.borrower_name}</span>
                            {item.borrower_email && (
                              <span className="borrower-email">{item.borrower_email}</span>
                            )}
                          </div>
                        </td>
                        <td className="loan-number">{item.loan_number || `#${item.loan_id}`}</td>
                        <td>
                          <div className="completion-cell">
                            <div className="progress-bar">
                              <div
                                className="progress-fill"
                                style={{ width: `${item.completion_percentage}%` }}
                              />
                            </div>
                            <span className="completion-text">
                              {item.received_valid}/{item.total_requested} ({item.completion_percentage}%)
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className={`sla-badge sla-${item.sla_status.toLowerCase()}`}>
                            {item.sla_status}
                            {item.breached_count > 0 && ` (${item.breached_count})`}
                          </span>
                        </td>
                        <td className="date-cell">{formatDate(item.last_activity)}</td>
                        <td>
                          {item.reminders_enabled ? (
                            <span className="reminder-enabled">On</span>
                          ) : (
                            <span className="reminder-disabled">Off</span>
                          )}
                        </td>
                        <td>
                          <button
                            className="btn-send-reminder"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSendReminder(item.loan_id);
                            }}
                          >
                            Send Reminder
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Pagination */}
      {((activeTab === 'documents-uploaded' && pendingReview.total_pages > 1) ||
        (activeTab === 'documents-owed' && outstandingDocs.total_pages > 1) ||
        (activeTab === 'completed' && completedClients.total_pages > 1) ||
        (activeTab === 'queue' && queueData.total_pages > 1)) && (
        <div className="pagination">
          <button
            disabled={pagination.page === 1}
            onClick={() => setPagination((prev) => ({ ...prev, page: prev.page - 1 }))}
          >
            Previous
          </button>
          <span>
            Page {pagination.page} of{' '}
            {activeTab === 'documents-uploaded'
              ? pendingReview.total_pages
              : activeTab === 'documents-owed'
                ? outstandingDocs.total_pages
                : activeTab === 'queue'
                  ? queueData.total_pages
                  : completedClients.total_pages}
          </span>
          <button
            disabled={
              pagination.page >=
              (activeTab === 'documents-uploaded'
                ? pendingReview.total_pages
                : activeTab === 'documents-owed'
                  ? outstandingDocs.total_pages
                  : activeTab === 'queue'
                    ? queueData.total_pages
                    : completedClients.total_pages)
            }
            onClick={() => setPagination((prev) => ({ ...prev, page: prev.page + 1 }))}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

export default SmartDocs;
