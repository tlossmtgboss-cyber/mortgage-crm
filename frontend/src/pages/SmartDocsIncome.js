/**
 * SmartDocsIncome Page
 *
 * Income calculation page with summary analytics cards, loan search,
 * calculation history, Form 1084 generation, and a maker-checker
 * approval worksheet with modal-based overrides and rejections.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import AnalyticsCard from '../components/smart-docs/AnalyticsCard';
import IncomeWorksheet from '../components/smart-docs/IncomeWorksheet';
import IncomeOverrideModal from '../components/income/IncomeOverrideModal';
import IncomeRejectModal from '../components/income/IncomeRejectModal';
import {
  calculateIncome,
  getIncomeSources,
  getIncomeHistory,
  approveIncome,
  rejectIncome,
  overrideSource,
} from '../services/docIncomeApi';
import { getIncomeSummary } from '../services/docAnalyticsApi';
import { API_BASE_URL } from '../services/api';
import { toast } from '../utils/toast';
import './SmartDocsIncome.css';
import { getToken } from '../utils/tokenStore';

// ---------------------------------------------------------------------------
// Inline SVG icons
// ---------------------------------------------------------------------------

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M7 12A5 5 0 107 2a5 5 0 000 10zM14 14l-3.5-3.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M8 2v8m0 0l-3-3m3 3l3-3M3 12v1a1 1 0 001 1h8a1 1 0 001-1v-1"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 4.5V8l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CalculatorIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <rect x="8" y="4" width="24" height="32" rx="3" stroke="currentColor" strokeWidth="2" />
      <rect x="12" y="8" width="16" height="6" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="15" cy="20" r="1.5" fill="currentColor" />
      <circle cx="20" cy="20" r="1.5" fill="currentColor" />
      <circle cx="25" cy="20" r="1.5" fill="currentColor" />
      <circle cx="15" cy="26" r="1.5" fill="currentColor" />
      <circle cx="20" cy="26" r="1.5" fill="currentColor" />
      <circle cx="25" cy="26" r="1.5" fill="currentColor" />
      <circle cx="15" cy="32" r="1.5" fill="currentColor" />
      <rect x="19" y="30.5" width="8" height="3" rx="1" fill="currentColor" />
    </svg>
  );
}

function ClearIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M10.5 3.5l-7 7M3.5 3.5l7 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function ChevronIcon({ open }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      className={`sd-income__chevron ${open ? 'sd-income__chevron--open' : ''}`}
    >
      <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M3 7l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RejectIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M10 4L4 10M4 4l6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatCurrency(amount) {
  if (amount == null) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number(amount));
}

function formatPct(value) {
  if (value == null) return '--';
  return `${Number(value).toFixed(1)}%`;
}

function formatDate(dateStr) {
  if (!dateStr) return '--';
  try {
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(new Date(dateStr));
  } catch {
    return dateStr;
  }
}

function getStatusLabel(status) {
  const s = (status || '').toUpperCase();
  if (s === 'APPROVED') return 'Approved';
  if (s === 'REJECTED') return 'Rejected';
  if (s === 'PENDING') return 'Pending';
  return status || 'Unknown';
}

function getStatusClass(status) {
  const s = (status || '').toUpperCase();
  if (s === 'APPROVED') return 'sd-income__status-badge--success';
  if (s === 'REJECTED') return 'sd-income__status-badge--error';
  return 'sd-income__status-badge--warning';
}

function calcTotalMonthly(income) {
  const sources = income?.sources || income?.income_sources || [];
  if (!Array.isArray(sources)) return 0;
  return sources.reduce((sum, s) => sum + Number(s.monthly_amount || s.amount || 0), 0);
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

function SmartDocsIncome() {
  // Summary analytics
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  // Loan search
  const [loanIdInput, setLoanIdInput] = useState('');
  const [loanId, setLoanId] = useState(null);
  const [loanMeta, setLoanMeta] = useState(null); // { borrower_name, loan_number }
  const inputRef = useRef(null);

  // Income data
  const [income, setIncome] = useState(null);
  const [worksheetLoading, setWorksheetLoading] = useState(false);

  // Calculation history
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  // Recent calculations (empty state)
  const [recentCalcs, setRecentCalcs] = useState([]);
  const [recentLoading, setRecentLoading] = useState(false);

  // Form 1084 generation
  const [generating1084, setGenerating1084] = useState(false);

  // Override modal state
  const [overrideModal, setOverrideModal] = useState({
    isOpen: false,
    sourceId: null,
    sourceName: '',
    currentMonthly: 0,
    currentAnnual: 0,
  });

  // Reject modal state
  const [rejectModal, setRejectModal] = useState({
    isOpen: false,
  });

  // ---------------------------------------------------------------------------
  // Load summary analytics on mount
  // ---------------------------------------------------------------------------
  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const data = await getIncomeSummary(30);
      setSummary(data);
    } catch (err) {
      toast.error('Failed to load income summary analytics');
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  // ---------------------------------------------------------------------------
  // Load income sources for a loan
  // ---------------------------------------------------------------------------
  const loadIncomeSources = useCallback(async (id) => {
    setWorksheetLoading(true);
    setIncome(null);
    try {
      const data = await getIncomeSources(id);
      setIncome(data);
      // Extract loan metadata if available
      if (data?.borrower_name || data?.loan_number) {
        setLoanMeta({
          borrower_name: data.borrower_name || null,
          loan_number: data.loan_number || null,
        });
      }
    } catch (err) {
      toast.error(`Failed to load income sources: ${err.message}`);
    } finally {
      setWorksheetLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Load calculation history for a loan
  // ---------------------------------------------------------------------------
  const loadHistory = useCallback(async (id) => {
    if (!id) return;
    setHistoryLoading(true);
    try {
      const data = await getIncomeHistory(id);
      setHistory(Array.isArray(data) ? data : data?.calculations || []);
    } catch (err) {
      toast.error(`Failed to load history: ${err.message}`);
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Load recent calculations for empty state
  // ---------------------------------------------------------------------------
  const loadRecentCalcs = useCallback(async () => {
    setRecentLoading(true);
    try {
      // Attempt to fetch recent calculations across all loans
      const data = await getIncomeSummary(7);
      setRecentCalcs(data?.recent_calculations || []);
    } catch {
      setRecentCalcs([]);
    } finally {
      setRecentLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handleLoad() {
    const id = loanIdInput.trim();
    if (!id) {
      toast.warning('Please enter a Loan ID');
      return;
    }
    setLoanId(id);
    setLoanMeta(null);
    loadIncomeSources(id);
    loadHistory(id);
  }

  function handleClear() {
    setLoanIdInput('');
    setLoanId(null);
    setLoanMeta(null);
    setIncome(null);
    setHistory([]);
    setHistoryOpen(false);
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }

  async function handleCalculate() {
    const id = loanIdInput.trim();
    if (!id) {
      toast.warning('Please enter a Loan ID');
      return;
    }
    setWorksheetLoading(true);
    setIncome(null);
    try {
      const data = await calculateIncome(id);
      setLoanId(id);
      setIncome(data);
      if (data?.borrower_name || data?.loan_number) {
        setLoanMeta({
          borrower_name: data.borrower_name || null,
          loan_number: data.loan_number || null,
        });
      }
      toast.success('Income calculation complete');
      loadSummary();
      loadHistory(id);
    } catch (err) {
      toast.error(`Calculation failed: ${err.message}`);
    } finally {
      setWorksheetLoading(false);
    }
  }

  async function handleApprove() {
    if (!loanId) return;
    try {
      const updated = await approveIncome(loanId, 'Approved via Smart Docs');
      setIncome((prev) => ({ ...prev, ...updated, status: 'APPROVED' }));
      toast.success('Income approved');
      loadSummary();
      loadHistory(loanId);
    } catch (err) {
      toast.error(`Approval failed: ${err.message}`);
    }
  }

  function handleRejectClick() {
    if (!loanId) return;
    setRejectModal({ isOpen: true });
  }

  async function handleRejectConfirm({ reason, category, notes, requestRevision }) {
    if (!loanId) return;
    try {
      const fullReason = [
        category ? `[${category}]` : '',
        reason,
        notes ? `Notes: ${notes}` : '',
        requestRevision ? '(Revision requested)' : '',
      ].filter(Boolean).join(' ');

      const updated = await rejectIncome(loanId, fullReason);
      setIncome((prev) => ({ ...prev, ...updated, status: 'REJECTED' }));
      setRejectModal({ isOpen: false });
      toast.success('Income rejected');
      loadSummary();
      loadHistory(loanId);
    } catch (err) {
      toast.error(`Rejection failed: ${err.message}`);
    }
  }

  async function handleOverrideSource(sourceId, newAmount, reason) {
    // When called with newAmount/reason from inline override, apply directly
    if (newAmount != null && reason) {
      try {
        await overrideSource(sourceId, {
          monthly_amount: newAmount,
          annual_amount: newAmount * 12,
          reason,
        });
        if (loanId) {
          await loadIncomeSources(loanId);
        }
        toast.success('Income source overridden');
      } catch (err) {
        toast.error(`Override failed: ${err.message}`);
      }
      return;
    }
    // Fallback: open the override modal (legacy path)
    const sources = income?.sources || income?.income_sources || [];
    const source = sources.find(
      (s) => s.id === sourceId || s.source_id === sourceId
    );
    const monthly = Number(source?.monthly_amount || source?.amount || 0);
    setOverrideModal({
      isOpen: true,
      sourceId,
      sourceName: source?.source_name || source?.type || source?.name || 'Income Source',
      currentMonthly: monthly,
      currentAnnual: monthly * 12,
    });
  }

  async function handleOverrideConfirm({ monthlyAmount, annualAmount, reason, notes }) {
    const { sourceId } = overrideModal;
    if (!sourceId) return;
    try {
      await overrideSource(sourceId, {
        monthly_amount: monthlyAmount,
        annual_amount: annualAmount,
        reason,
        notes,
      });
      setOverrideModal((prev) => ({ ...prev, isOpen: false }));
      if (loanId) {
        await loadIncomeSources(loanId);
      }
      toast.success('Income source overridden');
    } catch (err) {
      toast.error(`Override failed: ${err.message}`);
    }
  }

  async function handleGenerate1084() {
    if (!loanId) return;
    setGenerating1084(true);
    try {
      const token = getToken();
      const response = await fetch(
        `${API_BASE_URL}/api/v1/income/form-1084/${loanId}/generate`,
        {
          method: 'POST',
          headers: {
            'Authorization': token ? `Bearer ${token}` : '',
            'Content-Type': 'application/json',
          },
        }
      );
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `Generation failed (${response.status})`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `Form-1084-${loanId}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Form 1084 downloaded');
    } catch (err) {
      toast.error(`Form 1084 generation failed: ${err.message}`);
    } finally {
      setGenerating1084(false);
    }
  }

  function handleLoadHistoryCalc(calc) {
    // Load a previous calculation's data
    if (calc.income_data) {
      setIncome(calc.income_data);
      toast.info(`Loaded calculation from ${formatDate(calc.created_at || calc.date)}`);
    } else if (loanId) {
      // Reload the current data
      loadIncomeSources(loanId);
    }
  }

  function handleRecentClick(calc) {
    const id = calc.loan_id || calc.loanId;
    if (!id) return;
    setLoanIdInput(id);
    setLoanId(id);
    setLoanMeta(null);
    loadIncomeSources(id);
    loadHistory(id);
  }

  // ---------------------------------------------------------------------------
  // Derived values
  // ---------------------------------------------------------------------------

  const totalCalculated = summary?.total_calculated ?? summary?.total_amount ?? null;
  const pendingCount = summary?.pending_approval ?? summary?.pending_count ?? null;
  const approvedCount = summary?.approved ?? summary?.approved_count ?? null;
  const avgConfidence = summary?.avg_confidence ?? summary?.average_confidence ?? null;

  const incomeStatus = (income?.status || '').toUpperCase();
  const isApproved = incomeStatus === 'APPROVED';
  const isRejected = incomeStatus === 'REJECTED';
  const totalMonthly = income ? calcTotalMonthly(income) : 0;

  const showFooter = income && !worksheetLoading;
  const showForm1084Btn = income && isApproved;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="sd-income" aria-busy={worksheetLoading}>
      {/* Page header */}
      <div className="sd-income__header">
        <div>
          <h1 className="sd-income__title">Income Calculation</h1>
          <p className="sd-income__subtitle">
            Calculate, verify, and approve borrower income sources with AI-assisted analysis.
          </p>
        </div>
      </div>

      {/* Summary analytics cards */}
      <div className="sd-income__summary-grid">
        <AnalyticsCard
          title="Total Calculated"
          value={summaryLoading ? '--' : formatCurrency(totalCalculated)}
          subtitle="Across all active loans"
          status="success"
        />
        <AnalyticsCard
          title="Pending Approval"
          value={summaryLoading ? '--' : (pendingCount ?? '--')}
          subtitle="Awaiting maker-checker review"
          status="warning"
        />
        <AnalyticsCard
          title="Approved"
          value={summaryLoading ? '--' : (approvedCount ?? '--')}
          subtitle="Last 30 days"
          status="success"
        />
        <AnalyticsCard
          title="Avg Confidence"
          value={summaryLoading ? '--' : formatPct(avgConfidence)}
          subtitle="AI extraction confidence"
          status={
            avgConfidence == null
              ? undefined
              : avgConfidence >= 90
              ? 'success'
              : avgConfidence >= 70
              ? 'warning'
              : 'error'
          }
        />
      </div>

      {/* Search / load section */}
      <div className="sd-income__search">
        <div className="sd-income__search-row">
          <div className="sd-income__input-wrapper">
            <span className="sd-income__input-icon"><SearchIcon /></span>
            <input
              ref={inputRef}
              className="sd-income__loan-input"
              type="text"
              placeholder="Enter Loan ID"
              value={loanIdInput}
              onChange={(e) => setLoanIdInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleLoad();
              }}
              aria-label="Loan ID"
            />
            {loanIdInput && (
              <button
                className="sd-income__input-clear"
                onClick={() => setLoanIdInput('')}
                type="button"
                aria-label="Clear input"
              >
                <ClearIcon />
              </button>
            )}
          </div>
          <span className="sd-income__input-hint">Press Enter to load</span>
          <div className="sd-income__search-actions">
            <button
              className="sd-income__btn sd-income__btn--secondary"
              onClick={handleLoad}
              type="button"
              disabled={worksheetLoading}
            >
              Load
            </button>
            <button
              className="sd-income__btn sd-income__btn--primary"
              onClick={handleCalculate}
              type="button"
              disabled={worksheetLoading}
            >
              {worksheetLoading ? 'Calculating...' : 'Calculate Income'}
            </button>
            {loanId && (
              <button
                className="sd-income__btn sd-income__btn--ghost"
                onClick={handleClear}
                type="button"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {/* Loan metadata bar */}
        {loanId && (
          <div className="sd-income__loan-meta">
            <span className="sd-income__loan-meta-label">Loan:</span>
            <span className="sd-income__loan-meta-id">{loanMeta?.loan_number || loanId}</span>
            {loanMeta?.borrower_name && (
              <>
                <span className="sd-income__loan-meta-sep" aria-hidden="true">|</span>
                <span className="sd-income__loan-meta-borrower">{loanMeta.borrower_name}</span>
              </>
            )}
            {income?.status && (
              <>
                <span className="sd-income__loan-meta-sep" aria-hidden="true">|</span>
                <span className={`sd-income__status-badge ${getStatusClass(income.status)}`}>
                  {getStatusLabel(income.status)}
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {/* Calculation history (collapsible) */}
      {loanId && (
        <div className="sd-income__history">
          <button
            className="sd-income__history-toggle"
            onClick={() => {
              const willOpen = !historyOpen;
              setHistoryOpen(willOpen);
              if (willOpen && history.length === 0) {
                loadHistory(loanId);
              }
            }}
            type="button"
            aria-expanded={historyOpen}
          >
            <ClockIcon />
            <span>Calculation History</span>
            {history.length > 0 && (
              <span className="sd-income__history-count">{history.length}</span>
            )}
            <ChevronIcon open={historyOpen} />
          </button>

          {historyOpen && (
            <div className="sd-income__history-panel">
              {historyLoading ? (
                <div className="sd-income__history-loading">
                  <div className="sd-income__spinner sd-income__spinner--sm" />
                  <span>Loading history...</span>
                </div>
              ) : history.length === 0 ? (
                <div className="sd-income__history-empty">
                  No previous calculations found for this loan.
                </div>
              ) : (
                <div className="sd-income__history-list">
                  <div className="sd-income__history-header-row">
                    <span>Date</span>
                    <span>Total Income</span>
                    <span>Status</span>
                    <span>Confidence</span>
                    <span></span>
                  </div>
                  {history.map((calc, idx) => {
                    const calcDate = calc.created_at || calc.date || calc.calculated_at;
                    const calcTotal = calc.total_monthly || calc.total_income || 0;
                    const calcStatus = calc.status || 'PENDING';
                    const calcConf = calc.confidence || calc.avg_confidence;
                    return (
                      <button
                        key={calc.id || idx}
                        className="sd-income__history-row"
                        onClick={() => handleLoadHistoryCalc(calc)}
                        type="button"
                        title="Load this calculation"
                      >
                        <span className="sd-income__history-date">{formatDate(calcDate)}</span>
                        <span className="sd-income__history-amount">{formatCurrency(calcTotal)}</span>
                        <span className={`sd-income__status-badge ${getStatusClass(calcStatus)}`}>
                          {getStatusLabel(calcStatus)}
                        </span>
                        <span className="sd-income__history-conf">
                          {calcConf != null ? formatPct(calcConf) : '--'}
                        </span>
                        <span className="sd-income__history-action">Load</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Main content area */}
      {worksheetLoading ? (
        <div className="sd-income__loading" role="alert" aria-live="polite">
          <div className="sd-income__spinner" />
          <span>Loading income data...</span>
        </div>
      ) : income ? (
        <IncomeWorksheet
          income={income}
          onApprove={handleApprove}
          onReject={handleRejectClick}
          onOverrideSource={handleOverrideSource}
        />
      ) : (
        <div className="sd-income__empty">
          <div className="sd-income__empty-illustration">
            <CalculatorIcon />
          </div>
          <h3 className="sd-income__empty-title">Enter a Loan ID to begin income analysis</h3>
          <p className="sd-income__empty-text">
            Search for a loan above to calculate, review, and approve borrower income.
          </p>

          {/* Recent calculations quick-actions */}
          <div className="sd-income__recent">
            <button
              className="sd-income__btn sd-income__btn--outline"
              onClick={() => {
                if (recentCalcs.length === 0) loadRecentCalcs();
              }}
              type="button"
              disabled={recentLoading}
            >
              <ClockIcon />
              {recentLoading ? 'Loading...' : 'Recent Calculations'}
            </button>

            {recentCalcs.length > 0 && (
              <div className="sd-income__recent-list">
                {recentCalcs.slice(0, 5).map((calc, idx) => {
                  const id = calc.loan_id || calc.loanId;
                  return (
                    <button
                      key={id || idx}
                      className="sd-income__recent-item"
                      onClick={() => handleRecentClick(calc)}
                      type="button"
                    >
                      <span className="sd-income__recent-id">{id}</span>
                      {calc.borrower_name && (
                        <span className="sd-income__recent-name">{calc.borrower_name}</span>
                      )}
                      <span className="sd-income__recent-date">
                        {formatDate(calc.created_at || calc.date)}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Sticky footer action bar */}
      {showFooter && (
        <div className="sd-income__footer">
          <div className="sd-income__footer-inner">
            <div className="sd-income__footer-info">
              <span className={`sd-income__status-badge ${getStatusClass(income.status)}`}>
                {getStatusLabel(income.status)}
              </span>
              <span className="sd-income__footer-total">
                Monthly: {formatCurrency(totalMonthly)}
              </span>
            </div>
            <div className="sd-income__footer-actions">
              {showForm1084Btn && (
                <button
                  className="sd-income__btn sd-income__btn--outline"
                  onClick={handleGenerate1084}
                  disabled={generating1084}
                  type="button"
                >
                  <DownloadIcon />
                  {generating1084 ? 'Generating...' : 'Generate Form 1084'}
                </button>
              )}
              {!isApproved && !isRejected && (
                <>
                  <button
                    className="sd-income__btn sd-income__btn--danger"
                    onClick={handleRejectClick}
                    type="button"
                  >
                    <RejectIcon />
                    Reject
                  </button>
                  <button
                    className="sd-income__btn sd-income__btn--success"
                    onClick={handleApprove}
                    type="button"
                  >
                    <CheckIcon />
                    Approve
                  </button>
                </>
              )}
              {isRejected && (
                <button
                  className="sd-income__btn sd-income__btn--primary"
                  onClick={handleCalculate}
                  type="button"
                >
                  Recalculate
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modals */}
      <IncomeOverrideModal
        isOpen={overrideModal.isOpen}
        onClose={() => setOverrideModal((prev) => ({ ...prev, isOpen: false }))}
        onConfirm={handleOverrideConfirm}
        sourceName={overrideModal.sourceName}
        currentMonthly={overrideModal.currentMonthly}
        currentAnnual={overrideModal.currentAnnual}
      />

      <IncomeRejectModal
        isOpen={rejectModal.isOpen}
        onClose={() => setRejectModal({ isOpen: false })}
        onConfirm={handleRejectConfirm}
        loanId={loanId}
        totalMonthlyIncome={totalMonthly}
      />
    </div>
  );
}

export default SmartDocsIncome;
