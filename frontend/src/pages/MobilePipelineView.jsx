import React, { useState, useMemo, useCallback, useRef, memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import { useVirtualList } from '../hooks/useVirtualList';
import { toast } from '../utils/toast';
import MobileBottomNav from '../components/mobile/MobileBottomNav';
import { CardSkeleton } from '../components/SkeletonLoader';
import './MobilePipelineView.css';

// ---------------------------------------------------------------------------
// Stage definitions
// ---------------------------------------------------------------------------
const PIPELINE_STAGES = [
  { key: 'APPLICATION', label: 'Application', color: 'blue' },
  { key: 'DISCLOSED', label: 'Disclosed', color: 'blue' },
  { key: 'PROCESSING', label: 'Processing', color: 'blue' },
  { key: 'SUBMITTED', label: 'Submitted', color: 'blue' },
  { key: 'UNDERWRITING', label: 'Underwriting', color: 'purple' },
  { key: 'UW_RECEIVED', label: 'UW Received', color: 'purple' },
  { key: 'CONDITIONAL_APPROVAL', label: 'Cond. Approval', color: 'purple' },
  { key: 'APPROVED', label: 'Approved', color: 'green' },
  { key: 'SUSPENDED', label: 'Suspended', color: 'amber' },
  { key: 'CTC', label: 'CTC', color: 'green' },
  { key: 'CLEAR_TO_CLOSE', label: 'Clear to Close', color: 'green' },
  { key: 'CLOSING', label: 'Closing', color: 'green' },
  { key: 'DOCS', label: 'Docs', color: 'teal' },
  { key: 'DOCS_OUT', label: 'Docs Out', color: 'teal' },
  { key: 'FUNDED', label: 'Funded', color: 'green' },
  { key: 'NURTURE', label: 'Nurture', color: 'indigo' },
];

const TERMINAL_STAGES = new Set([
  'FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY',
]);

const SORT_OPTIONS = [
  { value: 'days_desc', label: 'Days in Stage (high first)' },
  { value: 'days_asc', label: 'Days in Stage (low first)' },
  { value: 'amount_desc', label: 'Loan Amount (high first)' },
  { value: 'amount_asc', label: 'Loan Amount (low first)' },
  { value: 'closing_asc', label: 'Closing Date (soonest)' },
  { value: 'borrower_asc', label: 'Borrower Name (A-Z)' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const formatCurrency = (amount) => {
  if (amount == null) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

const formatCompactCurrency = (amount) => {
  if (amount == null || amount === 0) return '$0';
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `$${(amount / 1_000).toFixed(0)}K`;
  return formatCurrency(amount);
};

const calcDaysInStage = (loan) => {
  if (loan.days_in_stage != null) return loan.days_in_stage;
  if (!loan.stage_changed_at) return 0;
  const changed = new Date(loan.stage_changed_at);
  const now = new Date();
  return Math.max(0, Math.floor((now - changed) / 86400000));
};

const daysColor = (days) => {
  if (days < 5) return 'green';
  if (days <= 10) return 'amber';
  return 'red';
};

const truncate = (str, len = 40) => {
  if (!str) return '';
  return str.length > len ? str.slice(0, len) + '...' : str;
};

// ---------------------------------------------------------------------------
// Skeleton card placeholder -- uses shared SkeletonLoader component
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Loan Card
// ---------------------------------------------------------------------------
const LoanCard = ({ loan, onClick, onAskAria }) => {
  const days = calcDaysInStage(loan);
  const color = daysColor(days);
  const insightText = loan.ai_insights
    ? truncate(loan.ai_insights, 60)
    : null;

  return (
    <div className="mp-card-wrap">
      <button
        className="mp-card"
        onClick={() => onClick(loan.id)}
        type="button"
        aria-label={`View loan for ${loan.borrower_name || 'Unknown borrower'}`}
      >
        <div className="mp-card__top">
          <span className="mp-card__borrower">{loan.borrower_name || 'Unknown Borrower'}</span>
          <span className={`mp-card__days mp-card__days--${color}`}>
            {days}d
          </span>
        </div>

        <span className="mp-card__amount">{formatCurrency(loan.amount)}</span>

        <span className="mp-card__address">
          {truncate(loan.property_address) || 'No address on file'}
        </span>

        {loan.loan_number && (
          <span className="mp-card__loan-number">#{loan.loan_number}</span>
        )}

        <div className="mp-card__footer">
          <span className="mp-card__action">
            {loan.next_action || 'Review file'}
          </span>
          <svg className="mp-card__chevron" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        {/* Aria insight row */}
        {insightText && (
          <div className="mp-card__aria-row">
            <svg className="mp-card__aria-icon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2 L13.5 8.5 L20 10 L13.5 11.5 L12 18 L10.5 11.5 L4 10 L10.5 8.5 Z" />
            </svg>
            <span className="mp-card__aria-insight">{insightText}</span>
          </div>
        )}
      </button>

      {/* Ask Aria about this loan */}
      <button
        className="mp-card__ask-aria"
        onClick={(e) => { e.stopPropagation(); onAskAria(loan); }}
        type="button"
        aria-label={`Ask Aria about ${loan.borrower_name || 'this loan'}`}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2 L13.5 8.5 L20 10 L13.5 11.5 L12 18 L10.5 11.5 L4 10 L10.5 8.5 Z" />
        </svg>
        Ask Aria
      </button>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------
const EmptyState = ({ stageLabel }) => (
  <div className="mp-empty">
    <svg className="mp-empty__icon" width="64" height="64" viewBox="0 0 64 64" fill="none">
      <rect x="8" y="12" width="48" height="40" rx="4" stroke="#d1d5db" strokeWidth="2" />
      <path d="M8 22h48" stroke="#d1d5db" strokeWidth="2" />
      <rect x="16" y="30" width="20" height="3" rx="1.5" fill="#e5e7eb" />
      <rect x="16" y="37" width="14" height="3" rx="1.5" fill="#e5e7eb" />
      <rect x="16" y="44" width="24" height="3" rx="1.5" fill="#e5e7eb" />
    </svg>
    <p className="mp-empty__text">No loans in {stageLabel}</p>
    <p className="mp-empty__sub">Loans will appear here once they reach this stage.</p>
  </div>
);

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------
const MobilePipelineView = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const tabBarRef = useRef(null);

  const [activeStage, setActiveStage] = useState(PIPELINE_STAGES[0].key);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('days_desc');
  const [showSortDropdown, setShowSortDropdown] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Pull-to-refresh state
  const scrollContainerRef = useRef(null);
  const touchStartY = useRef(0);
  const pullDistance = useRef(0);
  const [pullState, setPullState] = useState('idle'); // idle | pulling | refreshing

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------
  const {
    data: rawLoans,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['pipeline-loans'],
    queryFn: async () => {
      const res = await api.get('/api/v1/loans/');
      return res.data;
    },
    staleTime: 1000 * 60 * 3,
    refetchOnWindowFocus: true,
  });

  // Normalize: API may return array or { loans: [...] }
  const allLoans = useMemo(() => {
    if (!rawLoans) return [];
    if (Array.isArray(rawLoans)) return rawLoans;
    if (rawLoans.loans && Array.isArray(rawLoans.loans)) return rawLoans.loans;
    return [];
  }, [rawLoans]);

  // -----------------------------------------------------------------------
  // Count badges per stage
  // -----------------------------------------------------------------------
  const stageCounts = useMemo(() => {
    const counts = {};
    PIPELINE_STAGES.forEach((s) => { counts[s.key] = 0; });
    allLoans.forEach((loan) => {
      const stage = (loan.stage || '').toUpperCase();
      if (counts[stage] !== undefined) {
        counts[stage]++;
      }
    });
    return counts;
  }, [allLoans]);

  // -----------------------------------------------------------------------
  // Filter + sort loans for active stage
  // -----------------------------------------------------------------------
  const filteredLoans = useMemo(() => {
    const search = searchTerm.toLowerCase().trim();

    let loans = allLoans.filter((loan) => {
      const stage = (loan.stage || '').toUpperCase();
      if (stage !== activeStage) return false;
      if (!search) return true;
      const name = (loan.borrower_name || '').toLowerCase();
      const num = (loan.loan_number || '').toLowerCase();
      return name.includes(search) || num.includes(search);
    });

    // Sort
    loans = [...loans];
    switch (sortBy) {
      case 'days_desc':
        loans.sort((a, b) => calcDaysInStage(b) - calcDaysInStage(a));
        break;
      case 'days_asc':
        loans.sort((a, b) => calcDaysInStage(a) - calcDaysInStage(b));
        break;
      case 'amount_desc':
        loans.sort((a, b) => (b.amount || 0) - (a.amount || 0));
        break;
      case 'amount_asc':
        loans.sort((a, b) => (a.amount || 0) - (b.amount || 0));
        break;
      case 'closing_asc':
        loans.sort((a, b) => {
          const da = a.closing_date ? new Date(a.closing_date) : new Date('9999-12-31');
          const db = b.closing_date ? new Date(b.closing_date) : new Date('9999-12-31');
          return da - db;
        });
        break;
      case 'borrower_asc':
        loans.sort((a, b) => (a.borrower_name || '').localeCompare(b.borrower_name || ''));
        break;
      default:
        break;
    }

    return loans;
  }, [allLoans, activeStage, searchTerm, sortBy]);

  // -----------------------------------------------------------------------
  // Virtual list for large stage lists — renders only visible cards.
  // itemHeight ~180px accounts for card-wrap height (card + ask-aria button + gap).
  // -----------------------------------------------------------------------
  const {
    containerRef: virtualContainerRef,
    visibleItems: virtualLoans,
    startIndex: _virtualStartIndex,
    totalHeight: virtualTotalHeight,
    offsetY: virtualOffsetY,
    isVirtualized,
  } = useVirtualList({
    items: filteredLoans,
    itemHeight: 180,
    overscan: 5,
    useWindowScroll: false,
    enabled: true,
  });

  // -----------------------------------------------------------------------
  // Summary for selected stage
  // -----------------------------------------------------------------------
  const stageSummary = useMemo(() => {
    const count = filteredLoans.length;
    const volume = filteredLoans.reduce((sum, l) => sum + (l.amount || 0), 0);
    return { count, volume };
  }, [filteredLoans]);

  // -----------------------------------------------------------------------
  // Stage tab click
  // -----------------------------------------------------------------------
  const handleStageClick = useCallback((key) => {
    setActiveStage(key);
    // Scroll tab into view
    const tabEl = document.getElementById(`mp-tab-${key}`);
    if (tabEl) {
      tabEl.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    }
  }, []);

  // -----------------------------------------------------------------------
  // Pull-to-refresh handlers
  // -----------------------------------------------------------------------
  const handleTouchStart = useCallback((e) => {
    const container = scrollContainerRef.current;
    if (!container || container.scrollTop > 0) return;
    touchStartY.current = e.touches[0].clientY;
  }, []);

  const handleTouchMove = useCallback((e) => {
    if (pullState === 'refreshing') return;
    const container = scrollContainerRef.current;
    if (!container || container.scrollTop > 0) return;

    const currentY = e.touches[0].clientY;
    const diff = currentY - touchStartY.current;
    if (diff > 0) {
      pullDistance.current = Math.min(diff, 120);
      setPullState('pulling');
    }
  }, [pullState]);

  const handleTouchEnd = useCallback(async () => {
    if (pullState !== 'pulling') return;

    if (pullDistance.current > 60) {
      setPullState('refreshing');
      setIsRefreshing(true);
      try {
        await refetch();
        toast.success('Pipeline refreshed');
      } catch (err) {
        toast.error('Failed to refresh');
      } finally {
        setIsRefreshing(false);
        setPullState('idle');
        pullDistance.current = 0;
      }
    } else {
      setPullState('idle');
      pullDistance.current = 0;
    }
  }, [pullState, refetch]);

  // -----------------------------------------------------------------------
  // Navigation
  // -----------------------------------------------------------------------
  const handleCardClick = useCallback((loanId) => {
    navigate(`/loans/${loanId}`);
  }, [navigate]);

  const handleAskAria = useCallback((loan) => {
    navigate(`/mobile-aria?loanId=${loan.id}&context=pipeline`);
  }, [navigate]);

  // -----------------------------------------------------------------------
  // Active stage label
  // -----------------------------------------------------------------------
  const activeStageLabel = PIPELINE_STAGES.find((s) => s.key === activeStage)?.label || activeStage;

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------
  return (
    <div className="mp-view">
      {/* Header */}
      <header className="mp-header">
        <h1 className="mp-header__title">Pipeline</h1>
        <button
          className="mp-header__refresh"
          onClick={async () => {
            setIsRefreshing(true);
            try {
              await refetch();
              toast.success('Pipeline refreshed');
            } catch (err) {
              toast.error('Failed to refresh');
            } finally {
              setIsRefreshing(false);
            }
          }}
          disabled={isRefreshing}
          aria-label="Refresh pipeline"
          type="button"
        >
          <svg
            className={`mp-header__refresh-icon ${isRefreshing ? 'mp-spin' : ''}`}
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
          >
            <path d="M21 12a9 9 0 11-2.64-6.36" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <path d="M21 3v6h-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </header>

      {/* Search bar */}
      <div className="mp-search">
        <svg className="mp-search__icon" width="18" height="18" viewBox="0 0 24 24" fill="none">
          <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
          <path d="M16 16l4.5 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          className="mp-search__input"
          type="text"
          placeholder="Search borrower or loan #..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          aria-label="Search loans"
        />
        {searchTerm && (
          <button
            className="mp-search__clear"
            onClick={() => setSearchTerm('')}
            type="button"
            aria-label="Clear search"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        )}
      </div>

      {/* Stage tabs */}
      <nav className="mp-tabs" ref={tabBarRef} aria-label="Pipeline stages">
        <div className="mp-tabs__track">
          {PIPELINE_STAGES.map((stage) => (
            <button
              key={stage.key}
              id={`mp-tab-${stage.key}`}
              className={`mp-tabs__tab ${activeStage === stage.key ? 'mp-tabs__tab--active' : ''}${stage.color ? ` mp-tabs__tab--${stage.color}` : ''}`}
              onClick={() => handleStageClick(stage.key)}
              type="button"
              role="tab"
              aria-selected={activeStage === stage.key}
            >
              <span className="mp-tabs__label">{stage.label}</span>
              <span className="mp-tabs__badge">{stageCounts[stage.key] || 0}</span>
            </button>
          ))}
        </div>
      </nav>

      {/* Summary bar */}
      <div className="mp-summary">
        <span className="mp-summary__count">
          {stageSummary.count} loan{stageSummary.count !== 1 ? 's' : ''}
        </span>
        <span className="mp-summary__sep" aria-hidden="true" />
        <span className="mp-summary__volume">{formatCompactCurrency(stageSummary.volume)}</span>

        {/* Sort toggle */}
        <div className="mp-sort">
          <button
            className="mp-sort__btn"
            onClick={() => setShowSortDropdown((v) => !v)}
            type="button"
            aria-label="Sort options"
            aria-expanded={showSortDropdown}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M3 6h18M6 12h12M9 18h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
          {showSortDropdown && (
            <>
              <div className="mp-sort__backdrop" onClick={() => setShowSortDropdown(false)} />
              <ul className="mp-sort__dropdown" role="listbox">
                {SORT_OPTIONS.map((opt) => (
                  <li key={opt.value}>
                    <button
                      className={`mp-sort__option ${sortBy === opt.value ? 'mp-sort__option--active' : ''}`}
                      onClick={() => {
                        setSortBy(opt.value);
                        setShowSortDropdown(false);
                      }}
                      type="button"
                      role="option"
                      aria-selected={sortBy === opt.value}
                    >
                      {opt.label}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>

      {/* Pull-to-refresh indicator */}
      {pullState !== 'idle' && (
        <div className="mp-pull-indicator">
          <svg
            className={`mp-pull-indicator__icon ${pullState === 'refreshing' ? 'mp-spin' : ''}`}
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
          >
            <path d="M21 12a9 9 0 11-2.64-6.36" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <path d="M21 3v6h-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>{pullState === 'refreshing' ? 'Refreshing...' : 'Pull to refresh'}</span>
        </div>
      )}

      {/* Card list */}
      <div
        className="mp-cards"
        ref={(el) => {
          scrollContainerRef.current = el;
          virtualContainerRef.current = el;
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Loading skeleton */}
        {isLoading && <CardSkeleton count={4} />}

        {/* Error state */}
        {isError && !isLoading && (
          <div className="mp-error">
            <p className="mp-error__text">Failed to load pipeline</p>
            <p className="mp-error__detail">{error?.message || 'Unknown error'}</p>
            <button className="mp-error__retry" onClick={() => refetch()} type="button">
              Try Again
            </button>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !isError && filteredLoans.length === 0 && (
          <EmptyState stageLabel={activeStageLabel} />
        )}

        {/* Loan cards — virtualized for large lists, standard for small */}
        {!isLoading && !isError && filteredLoans.length > 0 && (
          isVirtualized ? (
            <div style={{
              height: virtualTotalHeight,
              position: 'relative',
              gridColumn: '1 / -1', /* span all grid columns on tablet layout */
            }}>
              <div style={{
                transform: `translateY(${virtualOffsetY}px)`,
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
              }}>
                {virtualLoans.map((loan) => (
                  <LoanCard key={loan.id} loan={loan} onClick={handleCardClick} onAskAria={handleAskAria} />
                ))}
              </div>
            </div>
          ) : (
            filteredLoans.map((loan) => (
              <LoanCard key={loan.id} loan={loan} onClick={handleCardClick} onAskAria={handleAskAria} />
            ))
          )
        )}
      </div>

      <MobileBottomNav />
    </div>
  );
};

export default MobilePipelineView;
