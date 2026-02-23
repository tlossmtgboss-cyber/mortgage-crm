/**
 * SmartDocsDashboard Page
 *
 * Dashboard for managing document workflows across all applicants.
 * Shows:
 * - Applicants with documents pending review
 * - Applicants with outstanding document requests
 * - Completed applicants (finished financing)
 * - Summary statistics with loan search
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { smartDocsAPI } from '../services/smartDocsApi';
import { API_BASE_URL } from '../services/api';
import './SmartDocsDashboard.css';

const SmartDocsDashboard = () => {
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

  // Fetch dashboard summary
  const fetchSummary = useCallback(async () => {
    try {
      const data = await smartDocsAPI.getDashboardSummary();
      setSummary(data);
    } catch (err) {
      console.error('Error fetching summary:', err);
    }
  }, []);

  // Fetch pending review applicants
  const fetchPendingReview = useCallback(async () => {
    try {
      const data = await smartDocsAPI.getApplicantsPendingReview(pagination.page, pagination.limit);
      setPendingReview(data);
    } catch (err) {
      setError('Failed to load pending review data');
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
      setError('Failed to load outstanding documents data');
    }
  }, [pagination, overdueOnly]);

  // Fetch completed clients (loans that are funded/closed)
  const fetchCompletedClients = useCallback(async () => {
    try {
      // Fetch funded/closed loans
      const response = await fetch(`${API_BASE_URL}/api/v1/loans?status=funded&limit=${pagination.limit}&page=${pagination.page}`);
      if (response.ok) {
        const data = await response.json();
        const loans = data.loans || data || [];
        setCompletedClients({
          applicants: loans.map(loan => ({
            loan_id: loan.id,
            loan_number: loan.loan_number,
            borrower_name: loan.borrower_name,
            loan_purpose: loan.loan_purpose,
            funded_at: loan.funded_at,
            loan_amount: loan.loan_amount,
          })),
          total: loans.length,
          total_pages: Math.ceil(loans.length / pagination.limit) || 1,
        });
      }
    } catch (err) {
      setError('Failed to load completed clients data');
    }
  }, [pagination]);

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await fetchSummary();
      if (activeTab === 'documents-uploaded') {
        await fetchPendingReview();
      } else if (activeTab === 'documents-owed') {
        await fetchOutstandingDocs();
      } else if (activeTab === 'completed') {
        await fetchCompletedClients();
      }
      setLoading(false);
    };
    loadData();
  }, [activeTab, fetchSummary, fetchPendingReview, fetchOutstandingDocs, fetchCompletedClients]);

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
    <div className="smart-docs-dashboard">
      {/* Header with Summary Stats */}
      <div className="dashboard-header">
        <div className="header-content">
          <h1>Smart Docs</h1>
          <p>Review documents and track outstanding requests across all applicants</p>
        </div>

        {/* Search Bar */}
        <div className="search-section">
          <div className="search-input-wrapper">
            <span className="search-icon">🔍</span>
            <input
              type="text"
              className="search-input"
              placeholder="Search by client name or loan number..."
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
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      {/* Tabs */}
      <div className="dashboard-tabs">
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
      <div className="dashboard-content">
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
                >
                  <div className="applicant-header">
                    <div className="applicant-info">
                      <h3
                        className="clickable-name"
                        onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                      >
                        {applicant.borrower_name}
                      </h3>
                      <span className="loan-info">
                        {applicant.loan_number || `Loan #${applicant.loan_id}`}
                        {applicant.loan_purpose && ` • ${applicant.loan_purpose}`}
                      </span>
                    </div>
                    <div className="docs-progress">
                      <span className="docs-requested">
                        {applicant.outstanding_count || 0} requested
                      </span>
                      <span className="docs-received">
                        {applicant.received_count || 0} received
                      </span>
                      {applicant.overdue_count > 0 && (
                        <span className="overdue-badge">
                          {applicant.overdue_count} overdue
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="requests-preview">
                    {(applicant.requests || []).slice(0, 4).map((req) => {
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
                    {(applicant.requests || []).length > 4 && (
                      <div className="request-chip more">
                        +{applicant.requests.length - 4} more
                      </div>
                    )}
                  </div>
                  <div className="card-footer">
                    {applicant.nearest_due && (
                      <span className={`nearest-due ${formatDueDate(applicant.nearest_due).class}`}>
                        Next due: {formatDueDate(applicant.nearest_due).text}
                      </span>
                    )}
                    <button
                      className="btn-view"
                      onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                    >
                      View Documents →
                    </button>
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
                >
                  <div className="applicant-header">
                    <div className="applicant-info">
                      <h3
                        className="clickable-name"
                        onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                      >
                        {applicant.borrower_name}
                      </h3>
                      <span className="loan-info">
                        {applicant.loan_number || `Loan #${applicant.loan_id}`}
                        {applicant.loan_purpose && ` • ${applicant.loan_purpose}`}
                      </span>
                    </div>
                    <div className="docs-progress">
                      <span className="docs-received">
                        {applicant.pending_count || 0} pending review
                      </span>
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
                    <button
                      className="btn-review"
                      onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                    >
                      Review Documents →
                    </button>
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
                >
                  <div className="applicant-header">
                    <div className="applicant-info">
                      <h3
                        className="clickable-name"
                        onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                      >
                        {applicant.borrower_name}
                      </h3>
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
                    <button
                      className="btn-view"
                      onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                    >
                      View Archive →
                    </button>
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
};

export default SmartDocsDashboard;
