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
import './SmartDocs.css';

function SmartDocs() {
  const navigate = useNavigate();
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

  // Fetch all loans and categorize them
  const fetchAllLoans = useCallback(async () => {
    try {
      // Try multiple endpoints
      let loans = [];

      // Use the Smart Docs loans endpoint (shows all active loans without permission filtering)
      const token = localStorage.getItem('token');
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

      let response = await fetch('/api/v1/smart-docs/loans', { headers });

      if (response.ok) {
        const data = await response.json();
        loans = data.loans || [];
      } else {
        // Fallback to main loans endpoint if smart-docs endpoint fails
        response = await fetch('/api/v1/loans/', { headers });
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

  // Initial load - only use fetchAllLoans
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      await fetchAllLoans();
      setLoading(false);
    };
    loadData();
  }, [fetchAllLoans]);

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
                      <th>Name</th>
                      <th>Loan #</th>
                      <th>Amount</th>
                      <th>Program</th>
                      <th>Stage</th>
                      <th>Property</th>
                      <th>Added</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredData.map((applicant) => (
                      <tr
                        key={applicant.loan_id}
                        className={applicant.overdue_count > 0 ? 'has-overdue' : ''}
                        onClick={() => navigate(`/loans/${applicant.loan_id}?tab=documents`)}
                      >
                        <td>
                          <span className="borrower-name">{applicant.borrower_name}</span>
                          {applicant.borrower_email && (
                            <span className="borrower-email">{applicant.borrower_email}</span>
                          )}
                        </td>
                        <td className="loan-number">{applicant.loan_number || `#${applicant.loan_id}`}</td>
                        <td className="loan-amount">{formatCurrency(applicant.loan_amount)}</td>
                        <td>{applicant.program || '-'}</td>
                        <td>
                          <span className={`stage-badge stage-${(applicant.stage || 'processing').toLowerCase().replace(/\s+/g, '-')}`}>
                            {applicant.stage || 'Processing'}
                          </span>
                        </td>
                        <td className="property-cell">{applicant.property_address || '-'}</td>
                        <td className="date-cell">{formatDate(applicant.created_at)}</td>
                        <td>
                          <button className="btn-view-sm" onClick={(e) => { e.stopPropagation(); navigate(`/loans/${applicant.loan_id}?tab=documents`); }}>
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
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
                        onClick={() => navigate(`/loans/${applicant.loan_id}?tab=documents`)}
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
                          <button className="btn-review-sm" onClick={(e) => { e.stopPropagation(); navigate(`/loans/${applicant.loan_id}?tab=documents`); }}>
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
        ) : (
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
                        onClick={() => navigate(`/loans/${applicant.loan_id}?tab=documents`)}
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
                          <button className="btn-view-sm" onClick={(e) => { e.stopPropagation(); navigate(`/loans/${applicant.loan_id}?tab=documents`); }}>
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
        )}
      </div>

      {/* Pagination */}
      {((activeTab === 'documents-uploaded' && pendingReview.total_pages > 1) ||
        (activeTab === 'documents-owed' && outstandingDocs.total_pages > 1) ||
        (activeTab === 'completed' && completedClients.total_pages > 1)) && (
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
                : completedClients.total_pages}
          </span>
          <button
            disabled={
              pagination.page >=
              (activeTab === 'documents-uploaded'
                ? pendingReview.total_pages
                : activeTab === 'documents-owed'
                  ? outstandingDocs.total_pages
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
