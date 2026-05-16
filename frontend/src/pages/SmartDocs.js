/**
 * SmartDocs Page — Cream Classic Theme
 *
 * Dashboard for managing document workflows across all applicants.
 * Shows:
 * - Stats grid with overdue, needs review, collected, and outstanding counts
 * - Alert banner for past-due clients
 * - Filter pills, search, and sort controls
 * - Client cards with document progress and actions
 */
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useDebounce } from '../hooks/useDebounce';
import { useNavigate } from 'react-router-dom';
import { smartDocsAPI } from '../services/smartDocsApi.js';
import { API_BASE_URL } from '../services/api.js';
import { usePermissions } from '../contexts/PermissionContext.js';
import BatchReminderModal from '../components/smart-docs/BatchReminderModal.jsx';
import SectionErrorBoundary from '../components/SectionErrorBoundary.jsx';
import './SmartDocs.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

function SmartDocs() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin, isPlatformAdmin } = usePermissions();

  // Permission check - require documents/loans access
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
  const [searchInput, setSearchInput] = useState('');
  const searchQuery = useDebounce(searchInput, 300);
  const [statusFilter, setStatusFilter] = useState('all');
  const [docTypeFilter, setDocTypeFilter] = useState('all');
  const [duplicateMap, setDuplicateMap] = useState({});
  const [duplicateTasksCreated, setDuplicateTasksCreated] = useState(false);
  const [sortBy, setSortBy] = useState('nearest-due');

  // Queue view state
  const [queueData, setQueueData] = useState({ queue: [], total: 0, summary: {} });
  const [queueSummary, setQueueSummary] = useState(null);
  const [slaFilter, setSlaFilter] = useState('all');

  // Batch reminder modal state
  const [batchReminderOpen, setBatchReminderOpen] = useState(false);

  // Fetch all loans and categorize them
  const fetchAllLoans = useCallback(async () => {
    try {
      let loans = [];
      const token = getToken();
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

      let response = await fetch(`${API_BASE_URL}/api/v1/smart-docs/loans`, { headers });

      if (response.ok) {
        const data = await response.json();
        loans = data.loans || [];
      } else {
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
          record_type: loan.record_type || 'loan',
          requests: loan.requests || [],
          documents: loan.documents || [],
        };

        const stage = (loan.stage || loan.status || '').toLowerCase();
        if (stage === 'funded' || stage === 'closed') {
          completed.push(loanData);
        } else {
          owed.push({ ...loanData, outstanding_count: loanData.outstanding_count || 1 });
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
        outstanding_requests: { applicants: owed.length, overdue: owed.filter(o => o.overdue_count > 0).length },
        pending_review: { applicants: uploaded.length, documents: uploaded.reduce((sum, u) => sum + (u.pending_count || 0), 0) },
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
    } catch (err) {
      console.error('Error fetching loans:', err);
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
    }
  }, []);

  // Fetch pending review applicants
  const fetchPendingReview = useCallback(async () => {
    try {
      const data = await smartDocsAPI.getApplicantsPendingReview(pagination.page, pagination.limit);
      setPendingReview(data);
    } catch (err) {
      console.error('Error fetching pending review:', err);
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
    }
  }, [pagination, overdueOnly]);

  // Fetch completed clients
  const fetchCompletedClients = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/loans?status=funded&limit=${pagination.limit}&page=${pagination.page}`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`,
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
        fetchQueue();
      } else {
        toast.error(result.message || 'Could not send reminder');
      }
    } catch (err) {
      console.error('Error sending reminder:', err);
      toast.error('Failed to send reminder');
    }
  };

  // Initial load
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

  // Fetch tab-specific data with abort on tab switch
  const abortRef = useRef(null);
  useEffect(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    if (activeTab === 'queue') {
      fetchQueue();
    } else if (activeTab === 'documents-uploaded') {
      fetchPendingReview();
    } else if (activeTab === 'documents-owed') {
      fetchOutstandingDocs();
    } else if (activeTab === 'completed') {
      fetchCompletedClients();
    }

    return () => controller.abort();
  }, [activeTab, fetchQueue, fetchPendingReview, fetchOutstandingDocs, fetchCompletedClients]);

  // Handle tab change
  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setPagination({ page: 1, limit: 20 });
  };

  // Keyboard navigation for tab list
  const TAB_KEYS = ['documents-owed', 'documents-uploaded', 'completed', 'queue'];
  const handleTabKeyDown = (e, currentTab) => {
    const currentIdx = TAB_KEYS.indexOf(currentTab);
    let nextIdx = currentIdx;
    if (e.key === 'ArrowRight') {
      nextIdx = (currentIdx + 1) % TAB_KEYS.length;
    } else if (e.key === 'ArrowLeft') {
      nextIdx = (currentIdx - 1 + TAB_KEYS.length) % TAB_KEYS.length;
    } else if (e.key === 'Home') {
      nextIdx = 0;
    } else if (e.key === 'End') {
      nextIdx = TAB_KEYS.length - 1;
    } else {
      return;
    }
    e.preventDefault();
    handleTabChange(TAB_KEYS[nextIdx]);
    document.querySelector(`[data-tab="${TAB_KEYS[nextIdx]}"]`)?.focus();
  };

  // Filter applicants by search query
  const filterBySearch = useCallback((applicants) => {
    if (!searchQuery.trim()) return applicants;
    const query = searchQuery.toLowerCase();
    return applicants.filter(applicant =>
      (applicant.borrower_name && applicant.borrower_name.toLowerCase().includes(query)) ||
      (applicant.loan_number && applicant.loan_number.toLowerCase().includes(query)) ||
      (applicant.borrower_email && applicant.borrower_email.toLowerCase().includes(query)) ||
      (applicant.loan_id && String(applicant.loan_id).includes(query))
    );
  }, [searchQuery]);

  // Sort logic
  const sortData = useCallback((data) => {
    const sorted = [...data];
    switch (sortBy) {
      case 'nearest-due':
        return sorted.sort((a, b) => {
          const aDue = a.requests?.[0]?.due_date || a.closing_date || '9999-12-31';
          const bDue = b.requests?.[0]?.due_date || b.closing_date || '9999-12-31';
          return new Date(aDue) - new Date(bDue);
        });
      case 'most-overdue':
        return sorted.sort((a, b) => (b.overdue_count || 0) - (a.overdue_count || 0));
      case 'client-name':
        return sorted.sort((a, b) => (a.borrower_name || '').localeCompare(b.borrower_name || ''));
      case 'most-docs':
        return sorted.sort((a, b) => (b.outstanding_count || 0) - (a.outstanding_count || 0));
      default:
        return sorted;
    }
  }, [sortBy]);

  // Get filtered data based on active tab
  const getFilteredData = useMemo(() => {
    let data = [];
    if (activeTab === 'documents-uploaded') {
      data = filterBySearch(pendingReview.applicants);
    } else if (activeTab === 'documents-owed') {
      let applicants = outstandingDocs.applicants;
      if (overdueOnly) {
        applicants = applicants.filter(a => a.overdue_count > 0);
      }
      data = filterBySearch(applicants);
    } else if (activeTab === 'completed') {
      data = filterBySearch(completedClients.applicants);
    }
    return sortData(data);
  }, [activeTab, filterBySearch, sortData, pendingReview.applicants, outstandingDocs.applicants, completedClients.applicants, overdueOnly]);

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

  // Create tasks for all duplicates
  const handleCreateDuplicateTasks = async () => {
    try {
      const token = getToken();
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
        const errorData = await response.json();
        toast.error(`Error: ${errorData.detail || 'Failed to create tasks'}`);
      }
    } catch (err) {
      console.error('Error creating duplicate tasks:', err);
      toast.error('Failed to create duplicate tasks');
    }
  };

  // Compute stats
  const overdueCount = useMemo(() => {
    return outstandingDocs.applicants.filter(a => a.overdue_count > 0).length;
  }, [outstandingDocs.applicants]);

  const reviewCount = useMemo(() => {
    return pendingReview.total || 0;
  }, [pendingReview.total]);

  const collectedCount = useMemo(() => {
    return completedClients.total || 0;
  }, [completedClients.total]);

  const totalOutstanding = useMemo(() => {
    return outstandingDocs.total || 0;
  }, [outstandingDocs.total]);

  // Get nearest due text for a client
  const getNearestDue = (applicant) => {
    if (applicant.requests && applicant.requests.length > 0) {
      const dueDates = applicant.requests
        .filter(r => r.due_date)
        .map(r => new Date(r.due_date))
        .sort((a, b) => a - b);
      if (dueDates.length > 0) {
        return formatDueDate(dueDates[0].toISOString());
      }
    }
    if (applicant.closing_date) {
      return formatDueDate(applicant.closing_date);
    }
    return { text: 'No due date set', class: '' };
  };

  // Access denied
  if (!canAccessSmartDocs) {
    return (
      <div className="sd2">
        <div className="sd2-denied">
          <div className="sd2-denied__icon">&#128274;</div>
          <h2 className="sd2-denied__title">Access Denied</h2>
          <p className="sd2-denied__text">You don't have permission to access Smart Docs.</p>
          <button className="sd2-btn sd2-btn--primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const filteredData = getFilteredData;

  // Map activeTab to filter pill keys
  const tabToPill = {
    'documents-owed': overdueCount > 0 ? 'past-due' : 'all-outstanding',
    'documents-uploaded': 'needs-review',
    'completed': 'completed',
  };

  return (
    <div className="sd2">
      {/* Page Header */}
      <header className="sd2-header">
        <h1 className="sd2-title">Smart Docs</h1>
        <p className="sd2-subtitle">Track document collections, review uploads, and manage past-due requests</p>
      </header>

      {/* Stats Grid */}
      <div className="sd2-stats">
        <div
          className="sd2-stat sd2-stat--overdue"
          onClick={() => { setOverdueOnly(true); handleTabChange('documents-owed'); }}
        >
          <div className="sd2-stat__label">Past Due</div>
          <div className="sd2-stat__value">{overdueCount}</div>
          <div className="sd2-stat__sub">{overdueCount} client{overdueCount !== 1 ? 's' : ''} with overdue documents</div>
        </div>
        <div
          className="sd2-stat sd2-stat--review"
          onClick={() => handleTabChange('documents-uploaded')}
        >
          <div className="sd2-stat__label">Needs Review</div>
          <div className="sd2-stat__value">{reviewCount}</div>
          <div className="sd2-stat__sub">{summary?.pending_review?.documents || 0} documents uploaded</div>
        </div>
        <div
          className="sd2-stat sd2-stat--collected"
          onClick={() => handleTabChange('completed')}
        >
          <div className="sd2-stat__label">Collected</div>
          <div className="sd2-stat__value">{collectedCount}</div>
          <div className="sd2-stat__sub">Fully completed files</div>
        </div>
        <div
          className="sd2-stat sd2-stat--total"
          onClick={() => { setOverdueOnly(false); handleTabChange('documents-owed'); }}
        >
          <div className="sd2-stat__label">Total Outstanding</div>
          <div className="sd2-stat__value">{totalOutstanding}</div>
          <div className="sd2-stat__sub">Active document requests</div>
        </div>
      </div>

      {/* Alert Banner — only when past-due > 0 */}
      {overdueCount > 0 && (
        <div className="sd2-banner">
          <div className="sd2-banner__seal">!</div>
          <div className="sd2-banner__body">
            <div className="sd2-banner__title">
              {overdueCount} client{overdueCount !== 1 ? 's' : ''} {overdueCount !== 1 ? 'have' : 'has'} past-due documents
            </div>
            <p className="sd2-banner__desc">These borrowers have missed their document submission deadlines. Send reminders or escalate as needed.</p>
          </div>
          <button
            className="sd2-btn sd2-btn--primary"
            onClick={() => setBatchReminderOpen(true)}
          >
            Send Batch Reminder
          </button>
        </div>
      )}

      {/* Filter Pills */}
      <div className="sd2-filters">
        <button
          className={`sd2-filter ${activeTab === 'documents-owed' && overdueOnly ? 'active' : ''}`}
          onClick={() => { setOverdueOnly(true); handleTabChange('documents-owed'); }}
        >
          {overdueCount > 0 && <span className="sd2-filter__pulse"></span>}
          Past Due
          {overdueCount > 0 && <span className="sd2-filter__count">{overdueCount}</span>}
        </button>
        <button
          className={`sd2-filter ${activeTab === 'documents-uploaded' ? 'active' : ''}`}
          onClick={() => handleTabChange('documents-uploaded')}
        >
          Needs Review
          {reviewCount > 0 && <span className="sd2-filter__count">{reviewCount}</span>}
        </button>
        <button
          className={`sd2-filter ${activeTab === 'documents-owed' && !overdueOnly ? 'active' : ''}`}
          onClick={() => { setOverdueOnly(false); handleTabChange('documents-owed'); }}
        >
          All Outstanding
          {totalOutstanding > 0 && <span className="sd2-filter__count">{totalOutstanding}</span>}
        </button>
        <button
          className={`sd2-filter ${activeTab === 'completed' ? 'active' : ''}`}
          onClick={() => handleTabChange('completed')}
        >
          Completed
          {collectedCount > 0 && <span className="sd2-filter__count">{collectedCount}</span>}
        </button>
      </div>

      {/* Search Bar */}
      <div className="sd2-search">
        <svg className="sd2-search__icon" width="18" height="18" viewBox="0 0 18 18" fill="none">
          <path d="M8 14A6 6 0 108 2a6 6 0 000 12zM16 16l-3.5-3.5" stroke="#9ca3af" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <input
          type="text"
          className="sd2-search__input"
          placeholder="Search by client name or loan number..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        {searchInput && (
          <button className="sd2-search__clear" onClick={() => setSearchInput('')}>
            &times;
          </button>
        )}
      </div>

      {/* Controls Row */}
      <div className="sd2-controls">
        <label className="sd2-overdue-toggle">
          <input
            type="checkbox"
            checked={overdueOnly}
            onChange={(e) => setOverdueOnly(e.target.checked)}
          />
          <span>Overdue only</span>
        </label>
        <div className="sd2-sort">
          <span className="sd2-sort__label">Sort:</span>
          <select
            className="sd2-sort__select"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
          >
            <option value="nearest-due">Nearest Due Date</option>
            <option value="most-overdue">Most Overdue</option>
            <option value="client-name">Client Name (A-Z)</option>
            <option value="most-docs">Most Docs Owed</option>
          </select>
        </div>
      </div>

      {/* Section Header */}
      <SectionErrorBoundary sectionName="Smart Docs Content">
        <div className="sd2-section">
          <div className="sd2-section__header">
            <h2 className="sd2-section__title">
              {activeTab === 'documents-owed' && overdueOnly && 'Past-Due Clients'}
              {activeTab === 'documents-owed' && !overdueOnly && 'All Outstanding'}
              {activeTab === 'documents-uploaded' && 'Needs Review'}
              {activeTab === 'completed' && 'Completed Files'}
              {activeTab === 'queue' && 'Queue View'}
            </h2>
            <div className="sd2-section__line"></div>
            <span className="sd2-section__count">{filteredData.length}</span>
          </div>

          {/* Content */}
          {loading ? (
            <div className="sd2-loading">
              <div className="sd2-spinner"></div>
              <p>Loading documents...</p>
            </div>
          ) : error ? (
            <div className="sd2-empty">
              <h3>Unable to load documents</h3>
              <p>{typeof error === 'string' ? error : 'Something went wrong. Please try again.'}</p>
              <button className="sd2-btn sd2-btn--primary" onClick={() => { setError(null); fetchAllLoans(); }}>Retry</button>
            </div>
          ) : activeTab === 'queue' ? (
            /* Queue View */
            <div className="sd2-queue">
              <div className="sd2-queue__filters">
                <select
                  className="sd2-sort__select"
                  value={slaFilter}
                  onChange={(e) => setSlaFilter(e.target.value)}
                >
                  <option value="all">All SLA Status</option>
                  <option value="BREACHED">Breached</option>
                  <option value="AT_RISK">At Risk</option>
                  <option value="GOOD">Good</option>
                </select>
              </div>
              {queueData.queue.length === 0 ? (
                <div className="sd2-empty">
                  <h3>No clients in queue</h3>
                  <p>All document requests have been fulfilled</p>
                </div>
              ) : (
                <div className="sd2-card-list">
                  {queueData.queue.map((item) => (
                    <div
                      key={item.loan_id}
                      className={`sd2-card ${item.has_sla_breach ? 'sd2-card--overdue' : ''}`}
                    >
                      <div className="sd2-card__header">
                        <div>
                          <h3
                            className="sd2-card__name"
                            onClick={() => navigate(`/smart-docs/client/${item.loan_id}`)}
                          >
                            {item.borrower_name}
                          </h3>
                          <span className="sd2-card__loan">{item.loan_number || `#${item.loan_id}`}</span>
                        </div>
                        <div className="sd2-card__badges">
                          <span className={`sd2-pill sd2-pill--${item.sla_status?.toLowerCase() === 'breached' ? 'overdue' : item.sla_status?.toLowerCase() === 'at_risk' ? 'pending' : 'collected'}`}>
                            {item.sla_status}
                          </span>
                        </div>
                      </div>
                      <div className="sd2-progress">
                        <div className="sd2-progress__track">
                          <div className="sd2-progress__fill" style={{ width: `${item.completion_percentage || 0}%` }}></div>
                        </div>
                        <span className="sd2-progress__label">{item.received_valid || 0}/{item.total_requested || 0} collected</span>
                      </div>
                      <div className="sd2-card__footer">
                        <span className="sd2-card__meta">Last activity: {formatDate(item.last_activity)}</span>
                        <div className="sd2-card__actions">
                          <button
                            className="sd2-btn sd2-btn--ghost"
                            onClick={() => handleSendReminder(item.loan_id)}
                          >
                            Send Reminder
                          </button>
                          <button
                            className="sd2-btn sd2-btn--primary"
                            onClick={() => navigate(`/smart-docs/client/${item.loan_id}`)}
                          >
                            Request Docs
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : filteredData.length === 0 ? (
            <div className="sd2-empty">
              <h3>{searchQuery ? 'No matching clients' : activeTab === 'completed' ? 'No completed loans yet' : 'No outstanding document requests'}</h3>
              <p>{searchQuery ? 'Try a different search term' : activeTab === 'completed' ? 'Funded loans will appear here' : 'All documents have been collected for active loans.'}</p>
            </div>
          ) : (
            /* Client Cards */
            <div className="sd2-card-list">
              {filteredData.map((applicant) => {
                const docsCollected = applicant.documents?.length || 0;
                const totalDocs = (applicant.outstanding_count || 0) + docsCollected;
                const totalForProgress = totalDocs || 1;
                const progressPct = Math.round((docsCollected / totalForProgress) * 100);
                const isOverdue = (applicant.overdue_count || 0) > 0;
                const requests = applicant.requests || [];
                const displayedDocs = requests.slice(0, 4);
                const remainingDocs = Math.max(0, requests.length - 4);
                const nearestDue = getNearestDue(applicant);

                return (
                  <div
                    key={applicant.loan_id}
                    className={`sd2-card ${isOverdue ? 'sd2-card--overdue' : ''}`}
                  >
                    <div className="sd2-card__header">
                      <div>
                        <h3
                          className="sd2-card__name"
                          onClick={() => navigate(`/smart-docs/client/${applicant.loan_id}`)}
                        >
                          {applicant.borrower_name}
                        </h3>
                        <span className="sd2-card__loan">
                          {applicant.loan_number || `#${applicant.loan_id}`}
                          {applicant.loan_purpose ? ` · ${applicant.loan_purpose}` : ''}
                        </span>
                      </div>
                      <div className="sd2-card__badges">
                        {(applicant.overdue_count || 0) > 0 && (
                          <span className="sd2-pill sd2-pill--overdue">{applicant.overdue_count} OVERDUE</span>
                        )}
                        {(applicant.outstanding_count || 0) > 0 && (
                          <span className="sd2-pill sd2-pill--pending">{applicant.outstanding_count} REQUESTED</span>
                        )}
                        {docsCollected > 0 && (
                          <span className="sd2-pill sd2-pill--collected">{docsCollected} RECEIVED</span>
                        )}
                      </div>
                    </div>

                    <div className="sd2-progress">
                      <div className="sd2-progress__track">
                        <div className="sd2-progress__fill" style={{ width: `${progressPct}%` }}></div>
                      </div>
                      <span className="sd2-progress__label">{docsCollected}/{totalForProgress} collected</span>
                    </div>

                    {displayedDocs.length > 0 && (
                      <div className="sd2-docs">
                        {displayedDocs.map((doc, idx) => {
                          const docDue = formatDueDate(doc.due_date);
                          const docIsOverdue = docDue.class === 'overdue';
                          return (
                            <span key={idx} className={`sd2-doc ${docIsOverdue ? 'sd2-doc--overdue' : ''}`}>
                              <span className={`sd2-doc__dot sd2-doc__dot--${getPriorityClass(doc.priority)}`}></span>
                              {doc.document_type || doc.title || doc.name || 'Document'}
                              <span className={`sd2-doc__due ${docIsOverdue ? 'sd2-doc__due--overdue' : ''}`}>{docDue.text}</span>
                            </span>
                          );
                        })}
                        {remainingDocs > 0 && (
                          <span className="sd2-doc">+{remainingDocs} more</span>
                        )}
                      </div>
                    )}

                    <div className="sd2-card__footer">
                      <span className={`sd2-card__meta ${nearestDue.class === 'overdue' ? 'sd2-card__meta--overdue' : ''}`}>
                        Next due: {nearestDue.text}
                      </span>
                      <div className="sd2-card__actions">
                        <button
                          className="sd2-btn sd2-btn--ghost"
                          onClick={(e) => { e.stopPropagation(); handleSendReminder(applicant.loan_id); }}
                        >
                          Send Reminder
                        </button>
                        <button
                          className="sd2-btn sd2-btn--primary"
                          onClick={(e) => { e.stopPropagation(); navigate(`/smart-docs/client/${applicant.loan_id}`); }}
                        >
                          Request Docs
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </SectionErrorBoundary>

      {/* Pagination */}
      {((activeTab === 'documents-uploaded' && pendingReview.total_pages > 1) ||
        (activeTab === 'documents-owed' && outstandingDocs.total_pages > 1) ||
        (activeTab === 'completed' && completedClients.total_pages > 1) ||
        (activeTab === 'queue' && queueData.total_pages > 1)) && (
        <div className="sd2-pagination">
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

      {/* Batch Reminder Modal */}
      <BatchReminderModal
        isOpen={batchReminderOpen}
        onClose={() => setBatchReminderOpen(false)}
        loanIds={outstandingDocs.applicants.map((a) => a.loan_id)}
        loanCount={outstandingDocs.applicants.length}
      />
    </div>
  );
}

export default SmartDocs;
