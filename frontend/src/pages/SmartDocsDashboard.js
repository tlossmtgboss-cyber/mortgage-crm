/**
 * SmartDocsDashboard Page
 *
 * Dashboard for managing document workflows across all applicants.
 * Shows:
 * - Applicants with documents pending review
 * - Applicants with outstanding document requests
 * - Summary statistics
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { smartDocsAPI } from '../services/smartDocsApi';
import './SmartDocsDashboard.css';

const SmartDocsDashboard = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('pending-review');
  const [summary, setSummary] = useState(null);
  const [pendingReview, setPendingReview] = useState({ applicants: [], total: 0 });
  const [outstandingDocs, setOutstandingDocs] = useState({ applicants: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pagination, setPagination] = useState({ page: 1, limit: 20 });
  const [overdueOnly, setOverdueOnly] = useState(false);

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

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await fetchSummary();
      if (activeTab === 'pending-review') {
        await fetchPendingReview();
      } else {
        await fetchOutstandingDocs();
      }
      setLoading(false);
    };
    loadData();
  }, [activeTab, fetchSummary, fetchPendingReview, fetchOutstandingDocs]);

  // Handle tab change
  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setPagination({ page: 1, limit: 20 });
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

  return (
    <div className="smart-docs-dashboard">
      {/* Header with Summary Stats */}
      <div className="dashboard-header">
        <div className="header-content">
          <h1>Document Management</h1>
          <p>Review documents and track outstanding requests across all applicants</p>
        </div>
        {summary && (
          <div className="summary-cards">
            <div
              className={`summary-card pending ${activeTab === 'pending-review' ? 'active' : ''}`}
              onClick={() => handleTabChange('pending-review')}
            >
              <div className="card-value">{summary.pending_review?.applicants || 0}</div>
              <div className="card-label">Applicants with Pending Documents</div>
              <div className="card-sub">{summary.pending_review?.documents || 0} documents to review</div>
            </div>
            <div
              className={`summary-card outstanding ${activeTab === 'outstanding' ? 'active' : ''}`}
              onClick={() => handleTabChange('outstanding')}
            >
              <div className="card-value">{summary.outstanding_requests?.applicants || 0}</div>
              <div className="card-label">Applicants with Outstanding Requests</div>
              <div className="card-sub">
                {summary.outstanding_requests?.overdue || 0} overdue
              </div>
            </div>
            <div className="summary-card activity">
              <div className="card-value">{summary.activity?.processed_today || 0}</div>
              <div className="card-label">Processed Today</div>
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
          className={`tab-btn ${activeTab === 'pending-review' ? 'active' : ''}`}
          onClick={() => handleTabChange('pending-review')}
        >
          Pending Review
          {pendingReview.total > 0 && (
            <span className="tab-badge">{pendingReview.total}</span>
          )}
        </button>
        <button
          className={`tab-btn ${activeTab === 'outstanding' ? 'active' : ''}`}
          onClick={() => handleTabChange('outstanding')}
        >
          Outstanding Documents
          {outstandingDocs.total > 0 && (
            <span className="tab-badge">{outstandingDocs.total}</span>
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
        ) : activeTab === 'pending-review' ? (
          /* Pending Review Tab */
          <div className="applicants-list">
            {pendingReview.applicants.length === 0 ? (
              <div className="empty-state">
                <span className="empty-icon">✓</span>
                <h3>All caught up!</h3>
                <p>No documents pending review</p>
              </div>
            ) : (
              pendingReview.applicants.map((applicant) => (
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
                    {applicant.documents.slice(0, 3).map((doc) => (
                      <div key={doc.id} className="doc-chip">
                        <span className="doc-type">{doc.doc_type || 'Document'}</span>
                        <span className="doc-date">{formatDate(doc.uploaded_at)}</span>
                      </div>
                    ))}
                    {applicant.documents.length > 3 && (
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
          /* Outstanding Documents Tab */
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
            {outstandingDocs.applicants.length === 0 ? (
              <div className="empty-state">
                <span className="empty-icon">✓</span>
                <h3>All documents collected!</h3>
                <p>No outstanding document requests</p>
              </div>
            ) : (
              outstandingDocs.applicants.map((applicant) => (
                <div
                  key={applicant.loan_id}
                  className={`applicant-card ${applicant.overdue_count > 0 ? 'has-overdue' : ''}`}
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
                    <div className="outstanding-badges">
                      <span className="outstanding-badge">
                        {applicant.outstanding_count} needed
                      </span>
                      {applicant.overdue_count > 0 && (
                        <span className="overdue-badge">
                          {applicant.overdue_count} overdue
                        </span>
                      )}
                    </div>
                  </div>
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
                  <div className="card-footer">
                    {applicant.nearest_due && (
                      <span className={`nearest-due ${formatDueDate(applicant.nearest_due).class}`}>
                        Next due: {formatDueDate(applicant.nearest_due).text}
                      </span>
                    )}
                    <button className="btn-view">View Details →</button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Pagination */}
      {((activeTab === 'pending-review' && pendingReview.total_pages > 1) ||
        (activeTab === 'outstanding' && outstandingDocs.total_pages > 1)) && (
        <div className="pagination">
          <button
            disabled={pagination.page === 1}
            onClick={() => setPagination((prev) => ({ ...prev, page: prev.page - 1 }))}
          >
            Previous
          </button>
          <span>
            Page {pagination.page} of{' '}
            {activeTab === 'pending-review' ? pendingReview.total_pages : outstandingDocs.total_pages}
          </span>
          <button
            disabled={
              pagination.page >=
              (activeTab === 'pending-review' ? pendingReview.total_pages : outstandingDocs.total_pages)
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
