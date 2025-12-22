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
              filteredData.map((applicant) => (
                <div
                  key={applicant.loan_id}
                  className={`applicant-card ${applicant.overdue_count > 0 ? 'has-overdue' : ''}`}
                  onClick={() => navigate(`/client/loan/${applicant.loan_id}?tab=documents`)}
                >
                  <div className="applicant-header">
                    <div className="applicant-info">
                      <h3>{applicant.borrower_name}</h3>
                      <span className="loan-number">{applicant.loan_number || `Loan #${applicant.loan_id}`}</span>
                    </div>
                    <div className="header-right">
                      <span className={`stage-badge stage-${(applicant.stage || 'processing').toLowerCase().replace(/\s+/g, '-')}`}>
                        {applicant.stage || 'Processing'}
                      </span>
                    </div>
                  </div>

                  <div className="loan-details-grid">
                    <div className="loan-detail">
                      <span className="detail-label">Loan Amount</span>
                      <span className="detail-value">{formatCurrency(applicant.loan_amount)}</span>
                    </div>
                    <div className="loan-detail">
                      <span className="detail-label">Program</span>
                      <span className="detail-value">{applicant.program || 'Not Set'}</span>
                    </div>
                    {applicant.property_address && (
                      <div className="loan-detail address">
                        <span className="detail-label">Property</span>
                        <span className="detail-value">{applicant.property_address}</span>
                      </div>
                    )}
                    {applicant.borrower_email && (
                      <div className="loan-detail">
                        <span className="detail-label">Email</span>
                        <span className="detail-value email">{applicant.borrower_email}</span>
                      </div>
                    )}
                  </div>

                  {(applicant.requests || []).length > 0 && (
                    <div className="requests-preview">
                      {applicant.requests.slice(0, 4).map((req) => {
                        const dueInfo = formatDueDate(req.due_date);
                        return (
                          <div key={req.id} className={`request-chip ${req.is_overdue ? 'overdue' : ''}`}>
                            <span className={`priority-dot ${getPriorityClass(req.priority)}`} />
                            <span className="request-title">{req.title}</span>
                            {req.due_date && (
                              <span className={`due-date ${dueInfo.class}`}>
                                {dueInfo.text}
                              </span>
                            )}
                          </div>
                        );
                      })}
                      {applicant.requests.length > 4 && (
                        <div className="request-chip more">
                          +{applicant.requests.length - 4} more
                        </div>
                      )}
                    </div>
                  )}

                  <div className="card-footer">
                    <span className="created-date">
                      Added {formatDate(applicant.created_at)}
                    </span>
                    <button className="btn-view">View Details →</button>
                  </div>
                </div>
              ))
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
              filteredData.map((applicant) => (
                <div
                  key={applicant.loan_id}
                  className="applicant-card"
                  onClick={() => navigate(`/client/loan/${applicant.loan_id}?tab=documents`)}
                >
                  <div className="applicant-header">
                    <div className="applicant-info">
                      <h3>{applicant.borrower_name}</h3>
                      <span className="loan-info">
                        {applicant.loan_number || `Loan #${applicant.loan_id}`}
                        {applicant.loan_purpose && ` • ${applicant.loan_purpose}`}
                      </span>
                    </div>
                    <div className="pending-badge">
                      {applicant.pending_count} pending
                    </div>
                  </div>
                  <div className="documents-preview">
                    {(applicant.documents || []).slice(0, 3).map((doc) => (
                      <div key={doc.id} className="doc-chip">
                        <span className="doc-type">{doc.doc_type || 'Document'}</span>
                        <span className="doc-date">{formatDate(doc.uploaded_at)}</span>
                      </div>
                    ))}
                    {(applicant.documents || []).length > 3 && (
                      <div className="doc-chip more">
                        +{applicant.documents.length - 3} more
                      </div>
                    )}
                  </div>
                  <div className="card-footer">
                    <span className="oldest-upload">
                      Oldest: {formatDate(applicant.oldest_upload)}
                    </span>
                    <button className="btn-review">Review Documents →</button>
                  </div>
                </div>
              ))
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
              filteredData.map((applicant) => (
                <div
                  key={applicant.loan_id}
                  className="applicant-card completed-card"
                  onClick={() => navigate(`/client/loan/${applicant.loan_id}?tab=documents`)}
                >
                  <div className="applicant-header">
                    <div className="applicant-info">
                      <h3>{applicant.borrower_name}</h3>
                      <span className="loan-info">
                        {applicant.loan_number || `Loan #${applicant.loan_id}`}
                        {applicant.loan_purpose && ` • ${applicant.loan_purpose}`}
                      </span>
                    </div>
                    <div className="completed-badge">
                      ✓ Completed
                    </div>
                  </div>
                  <div className="completed-details">
                    <div className="completed-detail">
                      <span className="detail-label">Loan Amount</span>
                      <span className="detail-value">{formatCurrency(applicant.loan_amount)}</span>
                    </div>
                    <div className="completed-detail">
                      <span className="detail-label">Funded</span>
                      <span className="detail-value">{formatDate(applicant.funded_at)}</span>
                    </div>
                  </div>
                  <div className="card-footer">
                    <span className="loan-complete-status">All documents collected</span>
                    <button className="btn-view">View Archive →</button>
                  </div>
                </div>
              ))
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
