import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import { toast } from '../utils/toast';
import './AppCompletionScoring.css';
import { getToken } from '../utils/tokenStore';

// Severity filter tabs
const SEVERITY_TABS = [
  { id: 'all', label: 'All' },
  { id: 'critical', label: 'Critical' },
  { id: 'high', label: 'High' },
  { id: 'medium', label: 'Medium' },
  { id: 'low', label: 'Low' },
];

// Item type badge colors
const TYPE_COLORS = {
  FIELD: '#3B82F6',
  DOC: '#B8924A',
  CLARIFICATION: '#F59E0B',
};

// Score color thresholds
function getScoreColor(score) {
  if (score >= 90) return '#2D7A52';
  if (score >= 75) return '#F59E0B';
  if (score >= 50) return '#F97316';
  return '#EF4444';
}

// Auth headers helper
function authHeaders(json = false) {
  const headers = {
    'Authorization': 'Bearer ' + getToken(),
  };
  if (json) {
    headers['Content-Type'] = 'application/json';
  }
  return headers;
}

// ---------------------------------------------------------------------------
// Score Gauge Component (circular SVG)
// ---------------------------------------------------------------------------
function ScoreGauge({ score, size = 160 }) {
  const radius = (size - 20) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;
  const color = getScoreColor(score);

  return (
    <div className="aco-score-gauge">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth="10"
        />
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          className="aco-gauge-progress"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        {/* Score text */}
        <text
          x={size / 2}
          y={size / 2 - 8}
          textAnchor="middle"
          className="aco-gauge-score"
          fill={color}
        >
          {score}
        </text>
        <text
          x={size / 2}
          y={size / 2 + 14}
          textAnchor="middle"
          className="aco-gauge-label"
          fill="#6b7280"
        >
          out of 100
        </text>
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Score Breakdown Bar
// ---------------------------------------------------------------------------
function BreakdownBar({ label, value, maxValue, weight, color }) {
  const pct = maxValue > 0 ? Math.min((value / maxValue) * 100, 100) : 0;

  return (
    <div className="aco-breakdown-item">
      <div className="aco-breakdown-header">
        <span className="aco-breakdown-label">{label}</span>
        <span className="aco-breakdown-value">
          {Math.round(value)}/{maxValue} <span className="aco-breakdown-weight">({weight}%)</span>
        </span>
      </div>
      <div className="aco-breakdown-track">
        <div
          className="aco-breakdown-fill"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trend Chart (inline SVG)
// ---------------------------------------------------------------------------
function TrendChart({ data }) {
  if (!data || data.length < 2) {
    return (
      <div className="aco-trend-empty">
        Not enough data points to display trend.
      </div>
    );
  }

  const width = 600;
  const height = 160;
  const paddingX = 40;
  const paddingY = 20;
  const chartW = width - paddingX * 2;
  const chartH = height - paddingY * 2;

  const scores = data.map(d => d.score);
  const minScore = Math.max(0, Math.min(...scores) - 10);
  const maxScore = Math.min(100, Math.max(...scores) + 10);
  const range = maxScore - minScore || 1;

  const points = data.map((d, i) => {
    const x = paddingX + (i / (data.length - 1)) * chartW;
    const y = paddingY + chartH - ((d.score - minScore) / range) * chartH;
    return { x, y, score: d.score, date: d.date };
  });

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

  // Area fill path
  const areaPath = linePath
    + ` L ${points[points.length - 1].x} ${paddingY + chartH}`
    + ` L ${points[0].x} ${paddingY + chartH} Z`;

  return (
    <div className="aco-trend-chart">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
          const y = paddingY + chartH - pct * chartH;
          const val = Math.round(minScore + pct * range);
          return (
            <g key={i}>
              <line
                x1={paddingX}
                y1={y}
                x2={paddingX + chartW}
                y2={y}
                stroke="#e5e7eb"
                strokeDasharray="4 4"
              />
              <text x={paddingX - 8} y={y + 4} textAnchor="end" fill="#9ca3af" fontSize="10">
                {val}
              </text>
            </g>
          );
        })}

        {/* Area */}
        <path d={areaPath} fill="rgba(33, 141, 141, 0.08)" />

        {/* Line */}
        <path d={linePath} fill="none" stroke="#1F3D2E" strokeWidth="2.5" strokeLinejoin="round" />

        {/* Points */}
        {points.map((p, i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r="4" fill="#1F3D2E" stroke="white" strokeWidth="2" />
            {/* Date labels on bottom */}
            {(i === 0 || i === points.length - 1 || i % Math.ceil(points.length / 5) === 0) && (
              <text
                x={p.x}
                y={paddingY + chartH + 14}
                textAnchor="middle"
                fill="#9ca3af"
                fontSize="9"
              >
                {p.date}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton loaders
// ---------------------------------------------------------------------------
function SkeletonBlock({ width, height }) {
  return (
    <div
      className="aco-skeleton"
      style={{ width: width || '100%', height: height || '20px' }}
    />
  );
}

function ScoreSkeleton() {
  return (
    <div className="aco-score-card aco-card">
      <div className="aco-score-card-inner">
        <div className="aco-score-gauge-col">
          <SkeletonBlock width="160px" height="160px" />
        </div>
        <div className="aco-score-details-col">
          <SkeletonBlock width="200px" height="24px" />
          <SkeletonBlock width="100%" height="16px" />
          <SkeletonBlock width="100%" height="16px" />
          <SkeletonBlock width="100%" height="16px" />
          <SkeletonBlock width="140px" height="36px" />
        </div>
      </div>
    </div>
  );
}

function ItemsSkeleton() {
  return (
    <div className="aco-items-section aco-card">
      <SkeletonBlock width="200px" height="24px" />
      <div style={{ marginTop: 16 }}>
        {[1, 2, 3].map(i => (
          <div key={i} style={{ marginBottom: 12 }}>
            <SkeletonBlock width="100%" height="72px" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------
function AppCompletionScoring() {
  const { loanId: urlLoanId } = useParams();

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const searchRef = useRef(null);

  // Selected loan
  const [selectedLoan, setSelectedLoan] = useState(null);

  // Scoring data
  const [scoring, setScoring] = useState(null);
  const [isLoadingScore, setIsLoadingScore] = useState(false);

  // Missing items
  const [items, setItems] = useState([]);
  const [isLoadingItems, setIsLoadingItems] = useState(false);
  const [severityFilter, setSeverityFilter] = useState('all');

  // Document staging
  const [documents, setDocuments] = useState([]);
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);

  // Communications
  const [communications, setCommunications] = useState([]);
  const [isLoadingComms, setIsLoadingComms] = useState(false);
  const [commsExpanded, setCommsExpanded] = useState(false);

  // Trend data
  const [trendData, setTrendData] = useState([]);
  const [isLoadingTrend, setIsLoadingTrend] = useState(false);

  // Running review
  const [isRunningReview, setIsRunningReview] = useState(false);

  // Inline resolve
  const [resolveItemId, setResolveItemId] = useState(null);
  const [resolveValue, setResolveValue] = useState('');

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e) {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // ---------------------------------------------------------------------------
  // Loan search
  // ---------------------------------------------------------------------------
  const searchLoans = useCallback(async () => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    setIsSearching(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/loans/search?q=${encodeURIComponent(searchQuery)}&limit=10`,
        { headers: authHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setSearchResults(data.loans || data || []);
        setShowDropdown(true);
      } else {
        setSearchResults([]);
      }
    } catch (err) {
      console.error('Loan search failed:', err);
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  }, [searchQuery]);

  // Debounced search
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      setShowDropdown(false);
      return;
    }
    const timer = setTimeout(() => {
      searchLoans();
    }, 350);
    return () => clearTimeout(timer);
  }, [searchQuery, searchLoans]);

  // ---------------------------------------------------------------------------
  // Data fetchers
  // ---------------------------------------------------------------------------
  const fetchScoring = useCallback(async (loanId) => {
    setIsLoadingScore(true);
    setScoring(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/smart-docs/app-complete/scoring/${loanId}`,
        { headers: authHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setScoring(data);
      } else if (response.status === 404) {
        setScoring(null);
      } else {
        toast.error('Failed to load scoring data');
      }
    } catch (err) {
      console.error('Failed to fetch scoring:', err);
      toast.error('Failed to load scoring data');
    } finally {
      setIsLoadingScore(false);
    }
  }, []);

  const fetchItems = useCallback(async (loanId) => {
    setIsLoadingItems(true);
    setItems([]);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/smart-docs/app-complete/items/${loanId}`,
        { headers: authHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setItems(data.items || data || []);
      }
    } catch (err) {
      console.error('Failed to fetch items:', err);
    } finally {
      setIsLoadingItems(false);
    }
  }, []);

  const fetchDocuments = useCallback(async (loanId) => {
    setIsLoadingDocs(true);
    setDocuments([]);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/smart-docs/app-complete/documents/${loanId}`,
        { headers: authHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setDocuments(data.documents || data || []);
      }
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    } finally {
      setIsLoadingDocs(false);
    }
  }, []);

  const fetchCommunications = useCallback(async (loanId) => {
    setIsLoadingComms(true);
    setCommunications([]);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/smart-docs/app-complete/communications/${loanId}`,
        { headers: authHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setCommunications(data.communications || data || []);
      }
    } catch (err) {
      console.error('Failed to fetch communications:', err);
    } finally {
      setIsLoadingComms(false);
    }
  }, []);

  const fetchTrend = useCallback(async (loanId) => {
    setIsLoadingTrend(true);
    setTrendData([]);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/smart-docs/app-complete/scoring/${loanId}/trend`,
        { headers: authHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setTrendData(data.trend || data || []);
      }
    } catch (err) {
      console.error('Failed to fetch trend:', err);
    } finally {
      setIsLoadingTrend(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Select loan and load all data
  // ---------------------------------------------------------------------------
  const handleSelectLoan = useCallback((loan) => {
    setSelectedLoan(loan);
    setShowDropdown(false);
    setSearchQuery(loan.loan_number || loan.borrower_name || '');

    const loanId = loan.id;
    fetchScoring(loanId);
    fetchItems(loanId);
    fetchDocuments(loanId);
    fetchCommunications(loanId);
    fetchTrend(loanId);
  }, [fetchScoring, fetchItems, fetchDocuments, fetchCommunications, fetchTrend]);

  // Auto-load loan from URL parameter (e.g., /smart-docs/app-scoring/123)
  useEffect(() => {
    if (urlLoanId && !selectedLoan) {
      handleSelectLoan({ id: urlLoanId });
    }
  }, [urlLoanId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------------------
  // Run Review
  // ---------------------------------------------------------------------------
  const handleRunReview = useCallback(async () => {
    if (!selectedLoan) return;
    setIsRunningReview(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/smart-docs/app-complete/review/${selectedLoan.id}`,
        {
          method: 'POST',
          headers: authHeaders(true),
        }
      );
      if (response.ok) {
        toast.success('Review completed successfully');
        // Refresh all data
        fetchScoring(selectedLoan.id);
        fetchItems(selectedLoan.id);
        fetchDocuments(selectedLoan.id);
        fetchTrend(selectedLoan.id);
      } else {
        const errData = await response.json().catch(() => ({}));
        toast.error(errData.detail || 'Failed to run review');
      }
    } catch (err) {
      console.error('Run review failed:', err);
      toast.error('Failed to run review');
    } finally {
      setIsRunningReview(false);
    }
  }, [selectedLoan, fetchScoring, fetchItems, fetchDocuments, fetchTrend]);

  // ---------------------------------------------------------------------------
  // Item actions
  // ---------------------------------------------------------------------------
  const handleResolveItem = useCallback(async (itemId) => {
    if (!resolveValue.trim()) {
      toast.warning('Please enter a value');
      return;
    }
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/smart-docs/app-complete/items/${itemId}/resolve`,
        {
          method: 'POST',
          headers: authHeaders(true),
          body: JSON.stringify({ value: resolveValue }),
        }
      );
      if (response.ok) {
        toast.success('Item resolved');
        setResolveItemId(null);
        setResolveValue('');
        if (selectedLoan) {
          fetchItems(selectedLoan.id);
          fetchScoring(selectedLoan.id);
        }
      } else {
        toast.error('Failed to resolve item');
      }
    } catch (err) {
      console.error('Resolve failed:', err);
      toast.error('Failed to resolve item');
    }
  }, [resolveValue, selectedLoan, fetchItems, fetchScoring]);

  const handleItemAction = useCallback(async (itemId, action) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/smart-docs/app-complete/items/${itemId}/${action}`,
        {
          method: 'POST',
          headers: authHeaders(true),
        }
      );
      if (response.ok) {
        const labels = { ask: 'Borrower notified', escalate: 'Issue escalated', defer: 'Item deferred' };
        toast.success(labels[action] || 'Action completed');
        if (selectedLoan) {
          fetchItems(selectedLoan.id);
          fetchScoring(selectedLoan.id);
        }
      } else {
        toast.error(`Failed to ${action} item`);
      }
    } catch (err) {
      console.error(`${action} failed:`, err);
      toast.error(`Failed to ${action} item`);
    }
  }, [selectedLoan, fetchItems, fetchScoring]);

  // ---------------------------------------------------------------------------
  // Document staging actions
  // ---------------------------------------------------------------------------
  const handleSelectAllDocs = useCallback(async () => {
    if (!selectedLoan) return;
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/smart-docs/app-complete/documents/select-all/${selectedLoan.id}`,
        {
          method: 'POST',
          headers: authHeaders(true),
        }
      );
      if (response.ok) {
        toast.success('All documents selected');
        fetchDocuments(selectedLoan.id);
      } else {
        toast.error('Failed to select documents');
      }
    } catch (err) {
      console.error('Select all failed:', err);
      toast.error('Failed to select documents');
    }
  }, [selectedLoan, fetchDocuments]);

  const handleSendToBorrower = useCallback(async () => {
    if (!selectedLoan) return;
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/smart-docs/app-complete/documents/send/${selectedLoan.id}`,
        {
          method: 'POST',
          headers: authHeaders(true),
        }
      );
      if (response.ok) {
        toast.success('Documents sent to borrower');
        fetchDocuments(selectedLoan.id);
        fetchCommunications(selectedLoan.id);
      } else {
        toast.error('Failed to send documents');
      }
    } catch (err) {
      console.error('Send to borrower failed:', err);
      toast.error('Failed to send documents');
    }
  }, [selectedLoan, fetchDocuments, fetchCommunications]);

  // ---------------------------------------------------------------------------
  // Filtered items
  // ---------------------------------------------------------------------------
  const filteredItems = severityFilter === 'all'
    ? items
    : items.filter(item => (item.severity || '').toLowerCase() === severityFilter);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="aco-page">
      {/* Header */}
      <div className="aco-header">
        <div className="aco-header-text">
          <h1 className="aco-title">Application Completeness</h1>
          <p className="aco-subtitle">
            Track and manage application data, documents, and scoring for submission readiness.
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="aco-search-section" ref={searchRef}>
        <div className="aco-search-wrapper">
          <span className="aco-search-icon">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M7 12A5 5 0 1 0 7 2a5 5 0 0 0 0 10zM14 14l-3.5-3.5"
                stroke="#9ca3af"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          <input
            type="text"
            className="aco-search-input"
            placeholder="Search by loan number or borrower name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => {
              if (searchResults.length > 0) setShowDropdown(true);
            }}
          />
          {isSearching && <span className="aco-search-spinner" />}
          {searchQuery && !isSearching && (
            <button
              className="aco-search-clear"
              onClick={() => {
                setSearchQuery('');
                setSearchResults([]);
                setShowDropdown(false);
              }}
            >
              x
            </button>
          )}
        </div>

        {/* Search dropdown */}
        {showDropdown && searchResults.length > 0 && (
          <div className="aco-search-dropdown">
            {searchResults.map((loan) => (
              <button
                key={loan.id}
                className="aco-search-result"
                onClick={() => handleSelectLoan(loan)}
              >
                <span className="aco-result-number">{loan.loan_number || 'N/A'}</span>
                <span className="aco-result-borrower">{loan.borrower_name || 'Unknown'}</span>
                <span className="aco-result-stage">{loan.stage || ''}</span>
              </button>
            ))}
          </div>
        )}

        {showDropdown && !isSearching && searchResults.length === 0 && searchQuery.trim().length > 0 && (
          <div className="aco-search-dropdown">
            <div className="aco-search-empty">No loans found</div>
          </div>
        )}
      </div>

      {/* No loan selected */}
      {!selectedLoan && (
        <div className="aco-empty-state">
          <div className="aco-empty-icon">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <rect x="8" y="6" width="32" height="36" rx="4" stroke="#d1d5db" strokeWidth="2" />
              <path d="M16 18h16M16 26h12M16 34h8" stroke="#d1d5db" strokeWidth="2" strokeLinecap="round" />
              <circle cx="36" cy="36" r="10" fill="white" stroke="#1F3D2E" strokeWidth="2" />
              <path d="M33 36h6M36 33v6" stroke="#1F3D2E" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>
          <h2 className="aco-empty-title">Search for a Loan</h2>
          <p className="aco-empty-text">
            Enter a loan number or borrower name above to view the application completeness score and manage missing items.
          </p>
        </div>
      )}

      {/* Loan selected — show dashboard */}
      {selectedLoan && (
        <div className="aco-dashboard">
          {/* Selected loan banner */}
          <div className="aco-loan-banner">
            <div className="aco-loan-banner-info">
              <span className="aco-loan-banner-label">Loan</span>
              <span className="aco-loan-banner-number">{selectedLoan.loan_number || 'N/A'}</span>
              <span className="aco-loan-banner-sep">|</span>
              <span className="aco-loan-banner-borrower">{selectedLoan.borrower_name || 'Unknown Borrower'}</span>
              {selectedLoan.stage && (
                <>
                  <span className="aco-loan-banner-sep">|</span>
                  <span className="aco-loan-banner-stage">{selectedLoan.stage}</span>
                </>
              )}
            </div>
            <button
              className="aco-btn aco-btn-outline"
              onClick={() => {
                setSelectedLoan(null);
                setSearchQuery('');
                setScoring(null);
                setItems([]);
                setDocuments([]);
                setCommunications([]);
                setTrendData([]);
              }}
            >
              Clear
            </button>
          </div>

          {/* Score Overview */}
          {isLoadingScore ? (
            <ScoreSkeleton />
          ) : scoring ? (
            <div className="aco-score-card aco-card">
              <div className="aco-card-header">
                <h2 className="aco-card-title">Completeness Score</h2>
                <button
                  className="aco-btn aco-btn-primary"
                  onClick={handleRunReview}
                  disabled={isRunningReview}
                >
                  {isRunningReview ? 'Running...' : 'Run Review'}
                </button>
              </div>
              <div className="aco-score-card-inner">
                <div className="aco-score-gauge-col">
                  <ScoreGauge score={scoring.overall_score || scoring.score || 0} />
                  {scoring.complexity_level && (
                    <span
                      className="aco-complexity-badge"
                      data-level={scoring.complexity_level.toLowerCase()}
                    >
                      {scoring.complexity_level} Complexity
                    </span>
                  )}
                </div>
                <div className="aco-score-details-col">
                  <div className="aco-breakdown-list">
                    <BreakdownBar
                      label="Data Completeness"
                      value={scoring.data_completeness ?? scoring.completeness ?? 0}
                      maxValue={100}
                      weight={60}
                      color="#3B82F6"
                    />
                    <BreakdownBar
                      label="Data Consistency"
                      value={scoring.data_consistency ?? scoring.consistency ?? 0}
                      maxValue={100}
                      weight={25}
                      color="#B8924A"
                    />
                    <BreakdownBar
                      label="Document Readiness"
                      value={scoring.document_readiness ?? scoring.doc_readiness ?? 0}
                      maxValue={100}
                      weight={15}
                      color="#2D7A52"
                    />
                  </div>
                  {scoring.next_action && (
                    <div className="aco-next-action">
                      <span className="aco-next-action-label">Next Action:</span>
                      <span className="aco-next-action-text">{scoring.next_action}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="aco-card aco-empty-card">
              <p>No review yet. Click "Run Review" to analyze this application.</p>
              <button
                className="aco-btn aco-btn-primary"
                onClick={handleRunReview}
                disabled={isRunningReview}
              >
                {isRunningReview ? 'Running...' : 'Run Review'}
              </button>
            </div>
          )}

          {/* Missing Items */}
          {isLoadingItems ? (
            <ItemsSkeleton />
          ) : (
            <div className="aco-items-section aco-card">
              <div className="aco-card-header">
                <h2 className="aco-card-title">Missing Items</h2>
                <span className="aco-items-count">{items.length} items</span>
              </div>

              {/* Severity tabs */}
              <div className="aco-severity-tabs">
                {SEVERITY_TABS.map(tab => {
                  const count = tab.id === 'all'
                    ? items.length
                    : items.filter(i => (i.severity || '').toLowerCase() === tab.id).length;
                  return (
                    <button
                      key={tab.id}
                      className={`aco-severity-tab ${severityFilter === tab.id ? 'active' : ''}`}
                      data-severity={tab.id}
                      onClick={() => setSeverityFilter(tab.id)}
                    >
                      {tab.label}
                      <span className="aco-tab-count">{count}</span>
                    </button>
                  );
                })}
              </div>

              {/* Items list */}
              {filteredItems.length === 0 ? (
                <div className="aco-items-empty">
                  {items.length === 0
                    ? 'No missing items found. Run a review to check.'
                    : 'No items match the selected filter.'}
                </div>
              ) : (
                <div className="aco-items-list">
                  {filteredItems.map((item) => (
                    <div
                      key={item.id}
                      className="aco-item-card"
                      data-severity={item.severity ? item.severity.toLowerCase() : 'low'}
                    >
                      <div className="aco-item-main">
                        <div className="aco-item-top">
                          <span className="aco-item-name">{item.field_name || item.name || 'Unknown Field'}</span>
                          <div className="aco-item-badges">
                            {item.type && (
                              <span
                                className="aco-item-type-badge"
                                style={{ backgroundColor: TYPE_COLORS[item.type] || '#6b7280' }}
                              >
                                {item.type}
                              </span>
                            )}
                            <span
                              className="aco-item-severity-badge"
                              data-severity={item.severity ? item.severity.toLowerCase() : 'low'}
                            >
                              {item.severity || 'LOW'}
                            </span>
                          </div>
                        </div>
                        {item.suggested_action && (
                          <p className="aco-item-suggestion">{item.suggested_action}</p>
                        )}
                        {item.status && (
                          <span className="aco-item-status">{item.status}</span>
                        )}
                      </div>

                      {/* Actions */}
                      <div className="aco-item-actions">
                        {resolveItemId === item.id ? (
                          <div className="aco-resolve-inline">
                            <input
                              type="text"
                              className="aco-resolve-input"
                              placeholder="Enter value..."
                              value={resolveValue}
                              onChange={(e) => setResolveValue(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') handleResolveItem(item.id);
                                if (e.key === 'Escape') {
                                  setResolveItemId(null);
                                  setResolveValue('');
                                }
                              }}
                              autoFocus
                            />
                            <button
                              className="aco-btn aco-btn-sm aco-btn-success"
                              onClick={() => handleResolveItem(item.id)}
                            >
                              Save
                            </button>
                            <button
                              className="aco-btn aco-btn-sm aco-btn-ghost"
                              onClick={() => {
                                setResolveItemId(null);
                                setResolveValue('');
                              }}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <>
                            <button
                              className="aco-btn aco-btn-sm aco-btn-success"
                              onClick={() => {
                                setResolveItemId(item.id);
                                setResolveValue('');
                              }}
                            >
                              Resolve
                            </button>
                            <button
                              className="aco-btn aco-btn-sm aco-btn-info"
                              onClick={() => handleItemAction(item.id, 'ask')}
                            >
                              Ask Borrower
                            </button>
                            <button
                              className="aco-btn aco-btn-sm aco-btn-warning"
                              onClick={() => handleItemAction(item.id, 'escalate')}
                            >
                              Escalate
                            </button>
                            <button
                              className="aco-btn aco-btn-sm aco-btn-ghost"
                              onClick={() => handleItemAction(item.id, 'defer')}
                            >
                              Defer
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Document Staging */}
          {isLoadingDocs ? (
            <div className="aco-card">
              <SkeletonBlock width="200px" height="24px" />
              <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                {[1, 2, 3, 4, 5, 6].map(i => (
                  <SkeletonBlock key={i} width="100%" height="80px" />
                ))}
              </div>
            </div>
          ) : documents.length > 0 && (
            <div className="aco-docs-section aco-card">
              <div className="aco-card-header">
                <h2 className="aco-card-title">Document Staging</h2>
                <div className="aco-docs-actions">
                  <button
                    className="aco-btn aco-btn-outline aco-btn-sm"
                    onClick={handleSelectAllDocs}
                  >
                    Select All
                  </button>
                  <button
                    className="aco-btn aco-btn-primary aco-btn-sm"
                    onClick={handleSendToBorrower}
                  >
                    Send to Borrower
                  </button>
                </div>
              </div>

              <div className="aco-docs-grid">
                {documents.map((doc, idx) => (
                  <div
                    key={doc.id || idx}
                    className="aco-doc-card"
                    data-status={doc.status ? doc.status.toLowerCase() : 'pending'}
                  >
                    <div className="aco-doc-icon">
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                        <path
                          d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z"
                          stroke="#6b7280"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                        <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="#6b7280" strokeWidth="1.5" strokeLinecap="round" />
                      </svg>
                    </div>
                    <div className="aco-doc-info">
                      <span className="aco-doc-name">{doc.doc_type || doc.name || 'Document'}</span>
                      <span className="aco-doc-category">{doc.doc_category || doc.category || ''}</span>
                    </div>
                    <span
                      className="aco-doc-status-badge"
                      data-status={doc.status ? doc.status.toLowerCase() : 'pending'}
                    >
                      {doc.status || 'Pending'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Communication Log */}
          <div className="aco-comms-section aco-card">
            <button
              className="aco-comms-toggle"
              onClick={() => setCommsExpanded(!commsExpanded)}
            >
              <h2 className="aco-card-title">Communication Log</h2>
              <span className="aco-comms-count">{communications.length} messages</span>
              <span className={`aco-chevron ${commsExpanded ? 'expanded' : ''}`}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M4 6l4 4 4-4" stroke="#6b7280" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
            </button>

            {commsExpanded && (
              <div className="aco-comms-content">
                {isLoadingComms ? (
                  <div style={{ padding: '16px 0' }}>
                    {[1, 2, 3].map(i => (
                      <SkeletonBlock key={i} width="100%" height="60px" />
                    ))}
                  </div>
                ) : communications.length === 0 ? (
                  <div className="aco-comms-empty">No communications recorded.</div>
                ) : (
                  <div className="aco-comms-timeline">
                    {communications.map((comm, idx) => (
                      <div key={comm.id || idx} className="aco-comm-entry">
                        <div className="aco-comm-dot" data-channel={comm.channel ? comm.channel.toLowerCase() : 'email'} />
                        <div className="aco-comm-body">
                          <div className="aco-comm-header">
                            <span className="aco-comm-channel">
                              {comm.channel === 'sms' ? 'SMS' : comm.channel === 'email' ? 'Email' : comm.channel || 'Message'}
                            </span>
                            {comm.sender && (
                              <span className="aco-comm-sender">{comm.sender}</span>
                            )}
                            <span className="aco-comm-time">
                              {comm.timestamp
                                ? new Date(comm.timestamp).toLocaleString()
                                : comm.created_at
                                  ? new Date(comm.created_at).toLocaleString()
                                  : ''}
                            </span>
                          </div>
                          <p className="aco-comm-preview">
                            {comm.content || comm.message || comm.preview || ''}
                          </p>
                          {comm.sentiment && (
                            <span
                              className="aco-comm-sentiment"
                              data-sentiment={comm.sentiment.toLowerCase()}
                            >
                              {comm.sentiment}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Score Trend */}
          <div className="aco-trend-section aco-card">
            <h2 className="aco-card-title">Score Trend</h2>
            {isLoadingTrend ? (
              <SkeletonBlock width="100%" height="160px" />
            ) : (
              <TrendChart data={trendData} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default AppCompletionScoring;
