/**
 * SmartDocsIncome Page
 *
 * Income calculation page with summary analytics cards, loan search,
 * and a maker-checker approval worksheet.
 */
import React, { useState, useEffect, useCallback } from 'react';
import AnalyticsCard from '../components/smart-docs/AnalyticsCard';
import IncomeWorksheet from '../components/smart-docs/IncomeWorksheet';
import {
  calculateIncome,
  getIncomeSources,
  approveIncome,
  rejectIncome,
  overrideSource,
} from '../services/docIncomeApi';
import { getIncomeSummary } from '../services/docAnalyticsApi';
import { toast } from '../utils/toast';
import './SmartDocsIncome.css';

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
  if (value == null) return '—';
  return `${Number(value).toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

function SmartDocsIncome() {
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  const [loanIdInput, setLoanIdInput] = useState('');
  const [loanId, setLoanId] = useState(null);

  const [income, setIncome] = useState(null);
  const [worksheetLoading, setWorksheetLoading] = useState(false);

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
    } catch (err) {
      toast.error(`Failed to load income sources: ${err.message}`);
    } finally {
      setWorksheetLoading(false);
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
    loadIncomeSources(id);
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
      toast.success('Income calculation complete');
      // Refresh summary after new calculation
      loadSummary();
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
    } catch (err) {
      toast.error(`Approval failed: ${err.message}`);
    }
  }

  async function handleReject() {
    if (!loanId) return;
    const reason = window.prompt('Enter rejection reason:');
    if (!reason) return;
    try {
      const updated = await rejectIncome(loanId, reason);
      setIncome((prev) => ({ ...prev, ...updated, status: 'REJECTED' }));
      toast.success('Income rejected');
      loadSummary();
    } catch (err) {
      toast.error(`Rejection failed: ${err.message}`);
    }
  }

  async function handleOverrideSource(sourceId) {
    const newAmountStr = window.prompt('Enter new monthly amount:');
    if (newAmountStr == null) return;
    const newAmount = parseFloat(newAmountStr);
    if (isNaN(newAmount) || newAmount < 0) {
      toast.error('Invalid amount entered');
      return;
    }
    try {
      await overrideSource(sourceId, { monthly_amount: newAmount });
      // Reload sources after override
      if (loanId) {
        await loadIncomeSources(loanId);
      }
      toast.success('Income source overridden');
    } catch (err) {
      toast.error(`Override failed: ${err.message}`);
    }
  }

  // ---------------------------------------------------------------------------
  // Derived summary card values
  // ---------------------------------------------------------------------------

  const totalCalculated = summary?.total_calculated ?? summary?.total_amount ?? null;
  const pendingCount = summary?.pending_approval ?? summary?.pending_count ?? null;
  const approvedCount = summary?.approved ?? summary?.approved_count ?? null;
  const avgConfidence = summary?.avg_confidence ?? summary?.average_confidence ?? null;

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
          value={summaryLoading ? '—' : formatCurrency(totalCalculated)}
          subtitle="Across all active loans"
          status="success"
        />
        <AnalyticsCard
          title="Pending Approval"
          value={summaryLoading ? '—' : (pendingCount ?? '—')}
          subtitle="Awaiting maker-checker review"
          status="warning"
        />
        <AnalyticsCard
          title="Approved"
          value={summaryLoading ? '—' : (approvedCount ?? '—')}
          subtitle="Last 30 days"
          status="success"
        />
        <AnalyticsCard
          title="Avg Confidence"
          value={summaryLoading ? '—' : formatPct(avgConfidence)}
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
        <input
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
        <button
          className="sd-income__btn sd-income__btn--secondary"
          onClick={handleLoad}
          type="button"
          aria-label="Load income sources for entered loan ID"
        >
          Load
        </button>
        <button
          className="sd-income__btn sd-income__btn--primary"
          onClick={handleCalculate}
          type="button"
          aria-label="Calculate income for entered loan ID"
        >
          Calculate Income
        </button>
      </div>

      {/* Worksheet */}
      {worksheetLoading ? (
        <div className="sd-income__loading" role="alert" aria-live="polite">
          <div className="sd-income__spinner" />
          <span>Loading income data...</span>
        </div>
      ) : income ? (
        <IncomeWorksheet
          income={income}
          onApprove={handleApprove}
          onReject={handleReject}
          onOverrideSource={handleOverrideSource}
        />
      ) : null}
    </div>
  );
}

export default SmartDocsIncome;
