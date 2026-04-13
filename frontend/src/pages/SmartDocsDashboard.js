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
import { toast } from 'react-toastify';
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
  const [selectedCards, setSelectedCards] = useState(new Set());
  const [sortBy, setSortBy] = useState('nearest-due');
  const showBatchToolbar = activeTab === 'documents-owed' && selectedCards.size > 0;

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

  // Clear selections when tab changes
  useEffect(() => {
    setSelectedCards(new Set());
  }, [activeTab]);

  // Toggle card selection
  const toggleCardSelection = (loanId) => {
    setSelectedCards((prev) => {
      const next = new Set(prev);
      if (next.has(loanId)) {
        next.delete(loanId);
      } else {
        next.add(loanId);
      }
      return next;
    });
  };

  // Select / Deselect all visible cards
  const toggleSelectAll = (applicants) => {
    const allIds = applicants.map((a) => a.loan_id);
    const allSelected = allIds.every((id) => selectedCards.has(id));
    if (allSelected) {
      setSelectedCards(new Set());
    } else {
      setSelectedCards(new Set(allIds));
    }
  };

  // Batch send reminders (placeholder)
  const handleBatchSendReminders = () => {
    toast.info(`Sending reminders to ${selectedCards.size} client(s)...`);
    // TODO: integrate with backend reminder endpoint
    setSelectedCards(new Set());
  };

  // Batch export (placeholder)
  const handleBatchExport = () => {
    toast.info(`Exporting data for ${selectedCards.size} client(s)...`);
    // TODO: integrate with backend export endpoint
  };

  // Single card send reminder (placeholder)
  const handleSendReminder = (applicant) => {
    toast.info(`Reminder sent to ${applicant.borrower_name}`);
    // TODO: integrate with backend reminder endpoint
  };

  // Sort applicants
  const sortApplicants = useCallback((applicants) => {
    if (activeTab !== 'documents-owed') return applicants;
    const sorted = [...applicants];
    switch (sortBy) {
      case 'most-overdue':
        sorted.sort((a, b) => (b.overdue_count || 0) - (a.overdue_count || 0));
        break;
      case 'client-name':
        sorted.sort((a, b) =>
          (a.borrower_name || '').localeCompare(b.borrower_name || '')
        );
        break;
      case 'most-docs-owed':
        sorted.sort((a, b) => (b.outstanding_count || 0) - (a.outstanding_count || 0));
        break;
      case 'nearest-due':
      default:
        sorted.sort((a, b) => {
          if (!a.nearest_due) return 1;
          if (!b.nearest_due) return -1;
          return new Date(a.nearest_due) - new Date(b.nearest_due);
        });
        break;
    }
    return sorted;
  }, [activeTab, sortBy]);

  // Get filtered data based on active tab
  const getFilteredData = () => {
    if (activeTab === 'documents-uploaded') {
      return filterBySearch(pendingReview.applicants);
    } else if (activeTab === 'documents-owed') {
      return sortApplicants(filterBySearch(outstandingDocs.applicants));
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
            <span className="search-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            </span>
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
              <div className="card-value animate-count-in">{summary.outstanding_requests?.applicants || 0}</div>
              <div className="card-label">Documents Owed</div>
              <div className="card-sub">
                {(summary.outstanding_requests?.overdue || 0) > 0 && (
                  <span className="trend-indicator trend-warning">
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M5 2L8 7H2L5 2Z" fill="currentColor"/></svg>
                  </span>
                )}
                {summary.outstanding_requests?.overdue || 0} overdue
              </div>
            </div>
            <div
              className={`summary-card pending ${activeTab === 'documents-uploaded' ? 'active' : ''}`}
              onClick={() => handleTabChange('documents-uploaded')}
            >
              <div className="card-value animate-count-in">{summary.pending_review?.applicants || 0}</div>
              <div className="card-label">Documents Uploaded</div>
              <div className="card-sub">
                {(summary.pending_review?.documents || 0) > 0 && (
                  <span className="trend-indicator trend-info">
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M5 2L8 7H2L5 2Z" fill="currentColor"/></svg>
                  </span>
                )}
                {summary.pending_review?.documents || 0} documents to review
              </div>
            </div>
            <div
              className={`summary-card completed ${activeTab === 'completed' ? 'active' : ''}`}
              onClick={() => handleTabChange('completed')}
            >
              <div className="card-value animate-count-in">{completedClients.total || 0}</div>
              <div className="card-label">Completed</div>
              <div className="card-sub">
                {(completedClients.total || 0) > 0 && (
                  <span className="trend-indicator trend-success">
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M5 2L8 7H2L5 2Z" fill="currentColor"/></svg>
                  </span>
                )}
                Finished financing
              </div>
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
              <div className="sort-dropdown-wrapper">
                <label className="sort-label" htmlFor="sort-select">Sort by</label>
                <select
                  id="sort-select"
                  className="sort-dropdown"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                >
                  <option value="nearest-due">Nearest Due Date</option>
                  <option value="most-overdue">Most Overdue</option>
                  <option value="client-name">Client Name (A-Z)</option>
                  <option value="most-docs-owed">Most Documents Owed</option>
                </select>
              </div>
            </div>

            {filteredData.length > 0 && (
              <div className="batch-select-row">
                <label className="filter-checkbox">
                  <input
                    type="checkbox"
                    checked={filteredData.length > 0 && filteredData.every((a) => selectedCards.has(a.loan_id))}
                    onChange={() => toggleSelectAll(filteredData)}
                  />
                  {filteredData.every((a) => selectedCards.has(a.loan_id)) ? 'Deselect All' : 'Select All'}
                </label>
              </div>
            )}

            {filteredData.length === 0 ? (
              <div className="empty-state empty-state-owed">
                <div className="empty-illustration-owed">
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <circle cx="24" cy="24" r="22" stroke="var(--color-success)" strokeWidth="2" strokeDasharray="4 2" />
                    <path d="M16 24L22 30L32 18" stroke="var(--color-success)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <h3>{searchQuery ? 'No matching clients' : 'All documents collected!'}</h3>
                <p>{searchQuery ? 'Try a different search term' : 'Your pipeline is clean.'}</p>
              </div>
            ) : (
              filteredData.map((applicant) => {
                const received = applicant.received_count || 0;
                const outstanding = applicant.outstanding_count || 0;
                const total = received + outstanding;
                const progressPct = total > 0 ? (received / total) * 100 : 0;
                const isSelected = selectedCards.has(applicant.loan_id);

                return (
                  <div
                    key={applicant.loan_id}
                    className={`applicant-card ${applicant.overdue_count > 0 ? 'has-overdue' : ''} ${isSelected ? 'card-selected' : ''}`}
                  >
                    <div className="applicant-header">
                      <div className="applicant-info-row">
                        <input
                          type="checkbox"
                          className="card-checkbox"
                          checked={isSelected}
                          onChange={() => toggleCardSelection(applicant.loan_id)}
                        />
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
                      </div>
                      <div className="docs-progress">
                        <span className="docs-requested">
                          {outstanding} requested
                        </span>
                        <span className="docs-received">
                          {received} received
                        </span>
                        {applicant.overdue_count > 0 && (
                          <span className="overdue-badge">
                            {applicant.overdue_count} overdue
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div className="progress-bar-container">
                      <div className="progress-bar-track">
                        <div
                          className="progress-bar-fill"
                          style={{ width: `${progressPct}%` }}
                        />
                      </div>
                      <span className="progress-bar-label">{received}/{total} collected</span>
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
                      <div className="card-footer-left">
                        {applicant.nearest_due && (
                          <span className={`nearest-due ${formatDueDate(applicant.nearest_due).class}`}>
                            Next due: {formatDueDate(applicant.nearest_due).text}
                          </span>
                        )}
                      </div>
                      <div className="card-actions">
                        <button
                          className="btn-action btn-action-secondary"
                          onClick={(e) => { e.stopPropagation(); handleSendReminder(applicant); }}
                        >
                          Send Reminder
                        </button>
                        <button
                          className="btn-action btn-action-primary"
                          onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                        >
                          Request Docs
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })
            )}

            {/* Batch Operations Toolbar */}
            {showBatchToolbar && (
              <div className="batch-toolbar">
                <span className="batch-toolbar-count">{selectedCards.size} selected</span>
                <div className="batch-toolbar-actions">
                  <button className="btn-batch" onClick={handleBatchSendReminders}>
                    Send Reminders
                  </button>
                  <button className="btn-batch btn-batch-secondary" onClick={handleBatchExport}>
                    Export
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : activeTab === 'documents-uploaded' ? (
          /* Documents Uploaded Tab */
          <div className="applicants-list">
            {filteredData.length === 0 ? (
              <div className="empty-state empty-state-uploaded">
                <div className="empty-illustration-uploaded">
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <rect x="8" y="6" width="32" height="36" rx="4" stroke="var(--color-primary)" strokeWidth="2" />
                    <path d="M16 20H32M16 26H28M16 32H24" stroke="var(--color-primary)" strokeWidth="2" strokeLinecap="round" />
                    <circle cx="36" cy="36" r="8" fill="var(--color-success)" />
                    <path d="M33 36L35 38L39 34" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <h3>{searchQuery ? 'No matching clients' : 'All caught up!'}</h3>
                <p>{searchQuery ? 'Try a different search term' : 'No documents pending your review.'}</p>
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
              <div className="empty-state empty-state-completed">
                <div className="empty-illustration-completed">
                  <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
                    <rect x="6" y="12" width="44" height="32" rx="3" stroke="var(--color-text-tertiary)" strokeWidth="2" />
                    <path d="M6 20H50" stroke="var(--color-text-tertiary)" strokeWidth="2" />
                    <rect x="12" y="26" width="14" height="3" rx="1.5" fill="var(--color-border)" />
                    <rect x="12" y="33" width="20" height="3" rx="1.5" fill="var(--color-border)" />
                    <circle cx="42" cy="16" r="8" fill="var(--color-bg-secondary)" stroke="var(--color-text-tertiary)" strokeWidth="2" />
                    <path d="M39 16L41 18L45 14" stroke="var(--color-text-tertiary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <h3>{searchQuery ? 'No matching clients' : 'No completed loans yet'}</h3>
                <p>{searchQuery ? 'Try a different search term' : 'Funded loans will appear here as files close.'}</p>
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
