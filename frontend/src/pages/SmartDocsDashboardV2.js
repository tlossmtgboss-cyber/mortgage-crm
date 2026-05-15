import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { smartDocsAPI } from '../services/smartDocsApi';
import { API_BASE_URL } from '../services/api';
import './SmartDocsDashboardV2.css';

const THEMES = [
  { id: 'cream-classic', label: 'Cream Classic', type: 'light' },
  { id: 'green-slate', label: 'Green Slate', type: 'light' },
  { id: 'gold-command', label: 'Gold Command', type: 'light' },
  { id: 'soft-linen', label: 'Soft Linen', type: 'light' },
  { id: 'deep-forest', label: 'Deep Forest', type: 'dark' },
  { id: 'midnight-gold', label: 'Midnight Gold', type: 'dark' },
  { id: 'obsidian', label: 'Obsidian', type: 'dark' },
  { id: 'carbon', label: 'Carbon', type: 'dark' },
];

const SmartDocsDashboardV2 = () => {
  const navigate = useNavigate();
  const [theme, setTheme] = useState('cream-classic');
  const [activeFilter, setActiveFilter] = useState('past-due');
  const [summary, setSummary] = useState(null);
  const [pendingReview, setPendingReview] = useState({ applicants: [], total: 0 });
  const [outstandingDocs, setOutstandingDocs] = useState({ applicants: [], total: 0 });
  const [completedClients, setCompletedClients] = useState({ applicants: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ page: 1, limit: 20 });
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCards, setSelectedCards] = useState(new Set());
  const [sortBy, setSortBy] = useState('nearest-due');

  const fetchSummary = useCallback(async () => {
    try {
      const data = await smartDocsAPI.getDashboardSummary();
      setSummary(data);
    } catch (err) {
      console.error('Error fetching summary:', err);
    }
  }, []);

  const fetchPendingReview = useCallback(async () => {
    try {
      const data = await smartDocsAPI.getApplicantsPendingReview(pagination.page, pagination.limit);
      setPendingReview(data);
    } catch (err) {
      console.error('Failed to load pending review data');
    }
  }, [pagination]);

  const fetchOutstandingDocs = useCallback(async () => {
    try {
      const data = await smartDocsAPI.getApplicantsOutstandingDocs(
        pagination.page, pagination.limit, overdueOnly
      );
      setOutstandingDocs(data);
    } catch (err) {
      console.error('Failed to load outstanding documents data');
    }
  }, [pagination, overdueOnly]);

  const fetchCompletedClients = useCallback(async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/loans?status=funded&limit=${pagination.limit}&page=${pagination.page}`
      );
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
      console.error('Failed to load completed clients data');
    }
  }, [pagination]);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await fetchSummary();
      if (activeFilter === 'review') {
        await fetchPendingReview();
      } else if (activeFilter === 'past-due' || activeFilter === 'all-owed') {
        await fetchOutstandingDocs();
      } else if (activeFilter === 'completed') {
        await fetchCompletedClients();
      }
      setLoading(false);
    };
    loadData();
  }, [activeFilter, fetchSummary, fetchPendingReview, fetchOutstandingDocs, fetchCompletedClients]);

  useEffect(() => {
    setSelectedCards(new Set());
  }, [activeFilter]);

  const filterBySearch = (applicants) => {
    if (!searchQuery.trim()) return applicants;
    const query = searchQuery.toLowerCase();
    return applicants.filter(a =>
      (a.borrower_name && a.borrower_name.toLowerCase().includes(query)) ||
      (a.loan_number && a.loan_number.toLowerCase().includes(query)) ||
      (a.loan_id && String(a.loan_id).includes(query))
    );
  };

  const sortApplicants = useCallback((applicants) => {
    const sorted = [...applicants];
    switch (sortBy) {
      case 'most-overdue':
        sorted.sort((a, b) => (b.overdue_count || 0) - (a.overdue_count || 0));
        break;
      case 'client-name':
        sorted.sort((a, b) => (a.borrower_name || '').localeCompare(b.borrower_name || ''));
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
  }, [sortBy]);

  const getFilteredData = () => {
    if (activeFilter === 'review') return filterBySearch(pendingReview.applicants);
    if (activeFilter === 'past-due') {
      const filtered = outstandingDocs.applicants.filter(a => (a.overdue_count || 0) > 0);
      return sortApplicants(filterBySearch(filtered));
    }
    if (activeFilter === 'all-owed') return sortApplicants(filterBySearch(outstandingDocs.applicants));
    if (activeFilter === 'completed') return filterBySearch(completedClients.applicants);
    return [];
  };

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

  const formatDueDate = (dateString) => {
    if (!dateString) return { text: 'No due date', cls: '' };
    const date = new Date(dateString);
    const now = new Date();
    const diffDays = Math.ceil((date - now) / (1000 * 60 * 60 * 24));
    if (diffDays < 0) return { text: `${Math.abs(diffDays)}d overdue`, cls: 'overdue' };
    if (diffDays === 0) return { text: 'Due today', cls: 'overdue' };
    if (diffDays <= 3) return { text: `Due in ${diffDays}d`, cls: 'soon' };
    return { text: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), cls: '' };
  };

  const formatCurrency = (amount) => {
    if (!amount) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: 'USD',
      minimumFractionDigits: 0, maximumFractionDigits: 0,
    }).format(amount);
  };

  const toggleCard = (id) => {
    setSelectedCards(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleSendReminder = (applicant) => {
    toast.info(`Reminder sent to ${applicant.borrower_name}`);
  };

  const overdueCount = summary?.outstanding_requests?.overdue || 0;
  const pendingCount = summary?.pending_review?.applicants || 0;
  const pendingDocs = summary?.pending_review?.documents || 0;
  const totalOwed = summary?.outstanding_requests?.applicants || 0;
  const collectedCount = completedClients.total || 0;
  const filteredData = getFilteredData();

  return (
    <>
      {/* Theme Picker */}
      <div className="sd2-theme-picker">
        {THEMES.map(t => (
          <button
            key={t.id}
            className={`sd2-theme-btn ${theme === t.id ? 'active' : ''}`}
            data-theme={t.id}
            onClick={() => setTheme(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="sd2" data-theme={theme}>
        {/* Header */}
        <div className="sd2-header">
          <h1 className="sd2-title">Smart Docs</h1>
          <p className="sd2-subtitle">
            Track document collections, review uploads, and manage past-due requests
          </p>
        </div>

        {/* Stats Grid */}
        <div className="sd2-stats">
          <div
            className={`sd2-stat sd2-stat--overdue ${activeFilter === 'past-due' ? 'active' : ''}`}
            onClick={() => setActiveFilter('past-due')}
          >
            <p className="sd2-stat__label">Past Due</p>
            <p className="sd2-stat__value">{overdueCount}</p>
            <p className="sd2-stat__sub">
              {overdueCount === 1 ? 'client' : 'clients'} with overdue documents
            </p>
          </div>
          <div
            className={`sd2-stat sd2-stat--review ${activeFilter === 'review' ? 'active' : ''}`}
            onClick={() => setActiveFilter('review')}
          >
            <p className="sd2-stat__label">Needs Review</p>
            <p className="sd2-stat__value">{pendingCount}</p>
            <p className="sd2-stat__sub">{pendingDocs} documents uploaded</p>
          </div>
          <div
            className={`sd2-stat sd2-stat--collected ${activeFilter === 'completed' ? 'active' : ''}`}
            onClick={() => setActiveFilter('completed')}
          >
            <p className="sd2-stat__label">Collected</p>
            <p className="sd2-stat__value">{collectedCount}</p>
            <p className="sd2-stat__sub">Fully completed files</p>
          </div>
          <div
            className={`sd2-stat sd2-stat--total ${activeFilter === 'all-owed' ? 'active' : ''}`}
            onClick={() => setActiveFilter('all-owed')}
          >
            <p className="sd2-stat__label">Total Outstanding</p>
            <p className="sd2-stat__value">{totalOwed}</p>
            <p className="sd2-stat__sub">Active document requests</p>
          </div>
        </div>

        {/* Alert Banner (only when overdue exists) */}
        {overdueCount > 0 && activeFilter === 'past-due' && (
          <div className="sd2-banner">
            <div className="sd2-banner__seal">!</div>
            <div>
              <div className="sd2-banner__title">
                {overdueCount} {overdueCount === 1 ? 'client has' : 'clients have'} past-due documents
              </div>
              <p className="sd2-banner__desc">
                These borrowers have missed their document submission deadlines.
                Send reminders or escalate as needed.
              </p>
            </div>
          </div>
        )}

        {/* Filter Pills */}
        <div className="sd2-filters">
          <button
            className={`sd2-filter ${activeFilter === 'past-due' ? 'active' : ''}`}
            onClick={() => setActiveFilter('past-due')}
          >
            {overdueCount > 0 && <span className="sd2-filter__pulse" />}
            Past Due
            <span className="sd2-filter__count">{overdueCount}</span>
          </button>
          <button
            className={`sd2-filter ${activeFilter === 'review' ? 'active' : ''}`}
            onClick={() => setActiveFilter('review')}
          >
            Needs Review
            <span className="sd2-filter__count">{pendingCount}</span>
          </button>
          <button
            className={`sd2-filter ${activeFilter === 'all-owed' ? 'active' : ''}`}
            onClick={() => setActiveFilter('all-owed')}
          >
            All Outstanding
            <span className="sd2-filter__count">{totalOwed}</span>
          </button>
          <button
            className={`sd2-filter ${activeFilter === 'completed' ? 'active' : ''}`}
            onClick={() => setActiveFilter('completed')}
          >
            Completed
            <span className="sd2-filter__count">{collectedCount}</span>
          </button>
        </div>

        {/* Search */}
        <div className="sd2-search">
          <span className="sd2-search__icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
            </svg>
          </span>
          <input
            type="text"
            className="sd2-search__input"
            placeholder="Search by client name or loan number..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="sd2-search__clear" onClick={() => setSearchQuery('')}>
              &times;
            </button>
          )}
        </div>

        {/* Sort Controls (for owed tabs) */}
        {(activeFilter === 'past-due' || activeFilter === 'all-owed') && (
          <div className="sd2-controls">
            <label className="sd2-overdue-toggle">
              <input
                type="checkbox"
                checked={overdueOnly}
                onChange={(e) => setOverdueOnly(e.target.checked)}
              />
              Overdue only
            </label>
            <div className="sd2-sort">
              <span className="sd2-sort__label">Sort by</span>
              <select
                className="sd2-sort__select"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
              >
                <option value="nearest-due">Nearest Due Date</option>
                <option value="most-overdue">Most Overdue</option>
                <option value="client-name">Client Name (A-Z)</option>
                <option value="most-docs-owed">Most Docs Owed</option>
              </select>
            </div>
          </div>
        )}

        {/* Content */}
        {loading ? (
          <div className="sd2-loading">
            <div className="sd2-spinner" />
            <p>Loading...</p>
          </div>
        ) : filteredData.length === 0 ? (
          <div className="sd2-empty">
            <div className="sd2-empty__icon">
              {activeFilter === 'past-due' ? '✓' :
               activeFilter === 'review' ? '📋' :
               activeFilter === 'completed' ? '🏠' : '📄'}
            </div>
            <h3 className="sd2-empty__title">
              {searchQuery ? 'No matching clients' :
               activeFilter === 'past-due' ? 'No past-due documents' :
               activeFilter === 'review' ? 'All caught up!' :
               activeFilter === 'completed' ? 'No completed loans yet' :
               'All documents collected!'}
            </h3>
            <p className="sd2-empty__desc">
              {searchQuery ? 'Try a different search term' :
               activeFilter === 'past-due' ? 'All borrowers are on track with their documents.' :
               activeFilter === 'review' ? 'No documents pending your review.' :
               activeFilter === 'completed' ? 'Funded loans will appear here as files close.' :
               'Your pipeline is clean.'}
            </p>
          </div>
        ) : (
          <>
            {/* Section Header */}
            <div className="sd2-section">
              <div className="sd2-section__header">
                <h2 className="sd2-section__title">
                  {activeFilter === 'past-due' ? 'Past-Due Clients' :
                   activeFilter === 'review' ? 'Pending Review' :
                   activeFilter === 'completed' ? 'Completed Files' :
                   'Outstanding Requests'}
                </h2>
                <div className="sd2-section__line" />
                <span className="sd2-section__count">{filteredData.length}</span>
              </div>

              <div className="sd2-card-list">
                {filteredData.map(applicant => {
                  const received = applicant.received_count || 0;
                  const outstanding = applicant.outstanding_count || 0;
                  const total = received + outstanding;
                  const progressPct = total > 0 ? (received / total) * 100 : 0;
                  const isOverdue = (applicant.overdue_count || 0) > 0;
                  const isSelected = selectedCards.has(applicant.loan_id);

                  if (activeFilter === 'review') {
                    return (
                      <div
                        key={applicant.loan_id}
                        className="sd2-card"
                        onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                      >
                        <div className="sd2-card__header">
                          <div>
                            <h3 className="sd2-card__name">{applicant.borrower_name}</h3>
                            <span className="sd2-card__loan">
                              {applicant.loan_number || `Loan #${applicant.loan_id}`}
                              {applicant.loan_purpose && ` · ${applicant.loan_purpose}`}
                            </span>
                          </div>
                          <div className="sd2-card__badges">
                            <span className="sd2-pill sd2-pill--review">
                              {applicant.pending_count || 0} to review
                            </span>
                          </div>
                        </div>
                        <div className="sd2-docs">
                          {(applicant.documents || []).slice(0, 3).map(doc => (
                            <span key={doc.id} className="sd2-doc">
                              <span className="sd2-doc__dot sd2-doc__dot--normal" />
                              {doc.doc_type || 'Document'}
                              <span className="sd2-doc__due">{formatDate(doc.uploaded_at)}</span>
                            </span>
                          ))}
                          {(applicant.documents || []).length > 3 && (
                            <span className="sd2-doc">+{applicant.documents.length - 3} more</span>
                          )}
                        </div>
                        <div className="sd2-card__footer">
                          <span className="sd2-card__meta">
                            Oldest: {formatDate(applicant.oldest_upload)}
                          </span>
                          <div className="sd2-card__actions">
                            <button className="sd2-btn sd2-btn--primary">
                              Review Documents →
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  if (activeFilter === 'completed') {
                    return (
                      <div
                        key={applicant.loan_id}
                        className="sd2-card"
                        onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                      >
                        <div className="sd2-card__header">
                          <div>
                            <h3 className="sd2-card__name">{applicant.borrower_name}</h3>
                            <span className="sd2-card__loan">
                              {applicant.loan_number || `Loan #${applicant.loan_id}`}
                              {applicant.loan_purpose && ` · ${applicant.loan_purpose}`}
                            </span>
                          </div>
                          <div className="sd2-card__badges">
                            <span className="sd2-pill sd2-pill--collected">COMPLETED</span>
                          </div>
                        </div>
                        <div className="sd2-docs">
                          <span className="sd2-doc">
                            {formatCurrency(applicant.loan_amount)}
                          </span>
                          <span className="sd2-doc">
                            Funded {formatDate(applicant.funded_at)}
                          </span>
                        </div>
                        <div className="sd2-card__footer">
                          <span className="sd2-card__meta">All documents collected</span>
                          <div className="sd2-card__actions">
                            <button className="sd2-btn sd2-btn--ghost">View Archive →</button>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  // Past-due / All Outstanding cards
                  return (
                    <div
                      key={applicant.loan_id}
                      className={`sd2-card ${isOverdue ? 'sd2-card--overdue' : ''} ${isSelected ? 'sd2-card--selected' : ''}`}
                    >
                      <div className="sd2-card__header">
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleCard(applicant.loan_id)}
                            style={{ width: 16, height: 16, marginTop: 4, accentColor: 'currentColor' }}
                          />
                          <div>
                            <h3
                              className="sd2-card__name"
                              style={{ cursor: 'pointer' }}
                              onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                            >
                              {applicant.borrower_name}
                            </h3>
                            <span className="sd2-card__loan">
                              {applicant.loan_number || `Loan #${applicant.loan_id}`}
                              {applicant.loan_purpose && ` · ${applicant.loan_purpose}`}
                            </span>
                          </div>
                        </div>
                        <div className="sd2-card__badges">
                          {isOverdue && (
                            <span className="sd2-pill sd2-pill--overdue">
                              {applicant.overdue_count} overdue
                            </span>
                          )}
                          <span className="sd2-pill sd2-pill--pending">
                            {outstanding} requested
                          </span>
                          {received > 0 && (
                            <span className="sd2-pill sd2-pill--collected">
                              {received} received
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Progress */}
                      <div className="sd2-progress">
                        <div className="sd2-progress__track">
                          <div className="sd2-progress__fill" style={{ width: `${progressPct}%` }} />
                        </div>
                        <span className="sd2-progress__label">{received}/{total} collected</span>
                      </div>

                      {/* Doc chips */}
                      <div className="sd2-docs">
                        {(applicant.requests || []).slice(0, 4).map(req => {
                          const dueInfo = formatDueDate(req.due_date);
                          return (
                            <span
                              key={req.id}
                              className={`sd2-doc ${req.is_overdue ? 'sd2-doc--overdue' : ''}`}
                            >
                              <span className={`sd2-doc__dot sd2-doc__dot--${(req.priority || 'normal').toLowerCase()}`} />
                              {req.title}
                              {req.due_date && (
                                <span className={`sd2-doc__due ${dueInfo.cls === 'overdue' ? 'sd2-doc__due--overdue' : ''}`}>
                                  {dueInfo.text}
                                </span>
                              )}
                            </span>
                          );
                        })}
                        {(applicant.requests || []).length > 4 && (
                          <span className="sd2-doc">+{applicant.requests.length - 4} more</span>
                        )}
                      </div>

                      {/* Footer */}
                      <div className="sd2-card__footer">
                        <span className={`sd2-card__meta ${isOverdue ? 'sd2-card__meta--overdue' : ''}`}>
                          {applicant.nearest_due
                            ? `Next due: ${formatDueDate(applicant.nearest_due).text}`
                            : 'No due date set'}
                        </span>
                        <div className="sd2-card__actions">
                          <button
                            className="sd2-btn sd2-btn--ghost"
                            onClick={(e) => { e.stopPropagation(); handleSendReminder(applicant); }}
                          >
                            Send Reminder
                          </button>
                          <button
                            className="sd2-btn sd2-btn--primary"
                            onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                          >
                            Request Docs
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}

        {/* Batch Toolbar */}
        {selectedCards.size > 0 && (
          <div className="sd2-batch">
            <span className="sd2-batch__count">{selectedCards.size} selected</span>
            <div className="sd2-batch__actions">
              <button
                className="sd2-btn sd2-btn--primary"
                onClick={() => {
                  toast.info(`Sending reminders to ${selectedCards.size} client(s)...`);
                  setSelectedCards(new Set());
                }}
              >
                Send Reminders
              </button>
              <button
                className="sd2-btn sd2-btn--ghost"
                onClick={() => {
                  toast.info(`Exporting data for ${selectedCards.size} client(s)...`);
                }}
              >
                Export
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
};

export default SmartDocsDashboardV2;
