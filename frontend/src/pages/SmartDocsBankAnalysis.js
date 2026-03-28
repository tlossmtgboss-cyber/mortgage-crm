/**
 * SmartDocsBankAnalysis Page
 *
 * Bank statement analysis tool. Users enter a Loan ID to retrieve
 * a full analysis including large deposits, NSF events, undisclosed
 * debts, and an overall risk score.
 *
 * Summary AnalyticsCards at the top show aggregate metrics across
 * all analyzed loans (fetched from docAnalyticsApi.getBankAnalysisSummary).
 */
import React, { useState, useEffect, useCallback } from 'react';
import AnalyticsCard from '../components/smart-docs/AnalyticsCard';
import BankAnalysisPanel from '../components/smart-docs/BankAnalysisPanel';
import { getBankSummary, sourceDeposit } from '../services/docBankAnalysisApi';
import { getBankAnalysisSummary } from '../services/docAnalyticsApi';
import { toast } from '../utils/toast';
import './SmartDocsBankAnalysis.css';

function SmartDocsBankAnalysis() {
  // Aggregate summary cards
  const [summaryStats, setSummaryStats] = useState(null);

  // Per-loan search
  const [loanId, setLoanId] = useState('');
  const [analysis, setAnalysis] = useState(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');

  // Load aggregate stats on mount
  useEffect(() => {
    let cancelled = false;

    async function loadSummary() {
      try {
        const data = await getBankAnalysisSummary(30);
        if (!cancelled) {
          setSummaryStats(data);
        }
      } catch (err) {
        if (!cancelled) {
          toast.error('Failed to load bank analysis summary');
        }
      }
    }

    loadSummary();

    return () => {
      cancelled = true;
    };
  }, []);

  // Run analysis for a loan ID
  const runAnalysis = useCallback(async (id) => {
    const trimmed = (id || '').trim();
    if (!trimmed) {
      toast.warning('Please enter a Loan ID');
      return;
    }

    setSearching(true);
    setSearchError('');
    setAnalysis(null);

    try {
      const data = await getBankSummary(trimmed);
      setAnalysis(data);
    } catch (err) {
      const msg = err.message || 'Failed to load bank analysis';
      setSearchError(msg);
      toast.error(msg);
    } finally {
      setSearching(false);
    }
  }, []);

  function handleInputChange(e) {
    setLoanId(e.target.value);
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') {
      runAnalysis(loanId);
    }
  }

  function handleAnalyzeClick() {
    runAnalysis(loanId);
  }

  async function handleSourceDeposit(deposit) {
    const description = window.prompt(
      'Enter source description for this deposit:',
      deposit.description || ''
    );

    // User cancelled
    if (description === null) return;

    if (!description.trim()) {
      toast.warning('Source description cannot be empty');
      return;
    }

    try {
      await sourceDeposit(deposit.id, { description: description.trim() });
      toast.success('Deposit sourced successfully');

      // Refresh analysis to reflect updated sourcing
      if (loanId.trim()) {
        runAnalysis(loanId);
      }
    } catch (err) {
      toast.error(err.message || 'Failed to source deposit');
    }
  }

  // Derive card values from summaryStats
  const s = summaryStats || {};
  const totalAnalyzed = s.total_analyzed ?? s.total ?? '—';
  const flagged = s.flagged ?? s.flagged_count ?? '—';
  const unsourcedDeposits = s.unsourced_deposits ?? s.unsourced ?? '—';
  const avgRiskScore = s.avg_risk_score != null
    ? Math.round(s.avg_risk_score)
    : '—';

  // Risk status for avg score card
  function riskStatus(score) {
    if (score === '—') return undefined;
    if (score >= 70) return 'error';
    if (score >= 40) return 'warning';
    return 'success';
  }

  return (
    <div className="sd-bank">
      {/* Page Header */}
      <div className="sd-bank__header">
        <h1 className="sd-bank__title">Bank Statement Analysis</h1>
        <p className="sd-bank__subtitle">
          Analyze bank statements for large deposits, overdrafts, and undisclosed debts
        </p>
      </div>

      {/* Summary Cards */}
      <div className="sd-bank__summary-grid">
        <AnalyticsCard
          title="Total Analyzed"
          value={totalAnalyzed}
          subtitle="Loans analyzed (30 days)"
        />
        <AnalyticsCard
          title="Flagged"
          value={flagged}
          status={typeof flagged === 'number' && flagged > 0 ? 'warning' : undefined}
          subtitle="Loans with flags"
        />
        <AnalyticsCard
          title="Unsourced Deposits"
          value={unsourcedDeposits}
          status={
            typeof unsourcedDeposits === 'number' && unsourcedDeposits > 0
              ? 'error'
              : undefined
          }
          subtitle="Deposits needing documentation"
        />
        <AnalyticsCard
          title="Avg Risk Score"
          value={avgRiskScore !== '—' ? `${avgRiskScore}` : '—'}
          status={riskStatus(avgRiskScore)}
          subtitle="Mean risk across active loans"
        />
      </div>

      {/* Loan Search */}
      <div className="sd-bank__search">
        <input
          className="sd-bank__search-input"
          type="text"
          value={loanId}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder="Enter Loan ID"
          aria-label="Loan ID"
          disabled={searching}
        />
        <button
          className="sd-bank__search-btn"
          onClick={handleAnalyzeClick}
          disabled={searching}
          type="button"
        >
          {searching ? 'Analyzing...' : 'Analyze'}
        </button>
      </div>

      {/* Error message */}
      {searchError && (
        <div className="sd-bank__error" role="alert">
          {searchError}
        </div>
      )}

      {/* Loading state */}
      {searching && (
        <div className="sd-bank__loading">
          Loading bank analysis...
        </div>
      )}

      {/* Analysis Panel */}
      {!searching && analysis && (
        <BankAnalysisPanel
          analysis={analysis}
          onSourceDeposit={handleSourceDeposit}
        />
      )}
    </div>
  );
}

export default SmartDocsBankAnalysis;
