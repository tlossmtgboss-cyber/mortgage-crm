/**
 * SmartDocsReviewQueue Page
 *
 * Displays the document review queue with:
 * - Summary stat cards (In Queue, High Priority, Claimed, Avg Wait)
 * - Priority filter tabs
 * - Paginated list of ReviewQueueItem rows
 * - Claim / release / AI review actions with toast feedback
 * - Batch AI Review for all unclaimed items grouped by loan
 */
import React, { useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '../utils/toast';

import useReviewQueue from '../hooks/useReviewQueue';
import ReviewQueueItem from '../components/smart-docs/ReviewQueueItem';
import AnalyticsCard from '../components/smart-docs/AnalyticsCard';
import SectionErrorBoundary from '../components/SectionErrorBoundary';
import docReviewApi from '../services/docReviewApi';

import './SmartDocsReviewQueue.css';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PRIORITY_FILTERS = ['ALL', 'CRITICAL', 'HIGH', 'NORMAL', 'LOW'];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatAvgWait(minutes) {
  if (minutes == null) return '—';
  if (minutes < 60) return `${Math.round(minutes)}m`;
  return `${(minutes / 60).toFixed(1)}h`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SmartDocsReviewQueue() {
  const navigate = useNavigate();
  const currentUserId = localStorage.getItem('userId') || localStorage.getItem('user_id') || null;

  const {
    items,
    stats,
    total,
    loading,
    error,
    filters,
    setFilters,
    nextPage,
    prevPage,
    claim,
    release,
    refresh,
  } = useReviewQueue();

  const [activePriority, setActivePriority] = useState('ALL');
  const [batchLoading, setBatchLoading] = useState(false);
  const filterPillRefs = useRef({});

  // ---------------------------------------------------------------------------
  // Priority filter
  // ---------------------------------------------------------------------------

  const handlePriorityFilter = useCallback((priority) => {
    setActivePriority(priority);
    if (priority === 'ALL') {
      setFilters({ priority: undefined });
    } else {
      setFilters({ priority });
    }
  }, [setFilters]);

  const handleFilterKeyDown = useCallback((e, priority) => {
    const currentIndex = PRIORITY_FILTERS.indexOf(priority);
    let newIndex;
    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        e.preventDefault();
        newIndex = (currentIndex + 1) % PRIORITY_FILTERS.length;
        handlePriorityFilter(PRIORITY_FILTERS[newIndex]);
        filterPillRefs.current[PRIORITY_FILTERS[newIndex]]?.focus();
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        e.preventDefault();
        newIndex = (currentIndex - 1 + PRIORITY_FILTERS.length) % PRIORITY_FILTERS.length;
        handlePriorityFilter(PRIORITY_FILTERS[newIndex]);
        filterPillRefs.current[PRIORITY_FILTERS[newIndex]]?.focus();
        break;
      case 'Home':
        e.preventDefault();
        handlePriorityFilter(PRIORITY_FILTERS[0]);
        filterPillRefs.current[PRIORITY_FILTERS[0]]?.focus();
        break;
      case 'End':
        e.preventDefault();
        handlePriorityFilter(PRIORITY_FILTERS[PRIORITY_FILTERS.length - 1]);
        filterPillRefs.current[PRIORITY_FILTERS[PRIORITY_FILTERS.length - 1]]?.focus();
        break;
      default:
        break;
    }
  }, [handlePriorityFilter]);

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const handleClaim = useCallback(async (documentId) => {
    try {
      await claim(documentId, currentUserId);
      toast.success('Document claimed for review');
    } catch (err) {
      toast.error(err.message || 'Failed to claim document');
    }
  }, [claim, currentUserId]);

  const handleRelease = useCallback(async (documentId) => {
    try {
      await release(documentId);
      toast.success('Document released back to queue');
    } catch (err) {
      toast.error(err.message || 'Failed to release document');
    }
  }, [release]);

  const handleAiReview = useCallback(async (documentId) => {
    try {
      await docReviewApi.aiReview(documentId);
      toast.success('AI review started');
      await refresh();
    } catch (err) {
      toast.error(err.message || 'AI review failed');
    }
  }, [refresh]);

  const handleViewDetail = useCallback((documentId) => {
    navigate(`/smart-docs/document/${documentId}`);
  }, [navigate]);

  const handleBatchAiReview = useCallback(async () => {
    const unclaimed = items.filter((item) => !item.claimed_by_id);
    if (!unclaimed.length) {
      toast.info('No unclaimed documents to review');
      return;
    }

    // Group by loan_id
    const byLoan = unclaimed.reduce((acc, item) => {
      const key = item.loan_id || 'unknown';
      if (!acc[key]) acc[key] = [];
      acc[key].push(item);
      return acc;
    }, {});

    const loanIds = Object.keys(byLoan).filter((k) => k !== 'unknown');
    if (!loanIds.length) {
      toast.error('Could not determine loan IDs for batch review');
      return;
    }

    setBatchLoading(true);
    let successCount = 0;
    let errorCount = 0;

    await Promise.all(
      loanIds.map(async (loanId) => {
        try {
          await docReviewApi.batchAiReview(loanId);
          successCount += byLoan[loanId].length;
        } catch (err) {
          console.error(`Batch AI review failed for loan ${loanId}:`, err);
          errorCount += byLoan[loanId].length;
        }
      })
    );

    setBatchLoading(false);
    await refresh();

    if (errorCount === 0) {
      toast.success(`Batch AI review started for ${successCount} document${successCount !== 1 ? 's' : ''}`);
    } else if (successCount === 0) {
      toast.error('Batch AI review failed');
    } else {
      toast.success(`Batch AI review: ${successCount} started, ${errorCount} failed`);
    }
  }, [items, refresh]);

  // ---------------------------------------------------------------------------
  // Stat card values
  // ---------------------------------------------------------------------------

  const inQueue       = stats?.in_queue       ?? total ?? 0;
  const highPriority  = stats?.high_priority  ?? 0;
  const claimed       = stats?.claimed        ?? 0;
  const avgWaitMins   = stats?.avg_wait_minutes ?? null;

  // ---------------------------------------------------------------------------
  // Pagination display
  // ---------------------------------------------------------------------------

  const limit   = filters.limit  ?? 50;
  const offset  = filters.offset ?? 0;
  const from    = total === 0 ? 0 : offset + 1;
  const to      = Math.min(offset + limit, total);
  const hasPrev = offset > 0;
  const hasNext = to < total;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="sd-review-queue">

      {/* ── Header ── */}
      <div className="sd-review-queue__header">
        <div className="sd-review-queue__header-text">
          <h1 className="sd-review-queue__title">Document Review Queue</h1>
          <p className="sd-review-queue__subtitle">
            Claim, review, and AI-analyze uploaded borrower documents.
          </p>
        </div>
        <div className="sd-review-queue__header-actions">
          <button
            className="sd-review-queue__btn sd-review-queue__btn--secondary"
            onClick={refresh}
            disabled={loading}
            aria-label="Refresh review queue"
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
          <button
            className="sd-review-queue__btn sd-review-queue__btn--primary"
            onClick={handleBatchAiReview}
            disabled={batchLoading || loading}
            aria-label="Run batch AI review on all unclaimed documents"
          >
            {batchLoading ? 'Running…' : 'Batch AI Review'}
          </button>
        </div>
      </div>

      {/* ── Stat cards ── */}
      <div className="sd-review-queue__stats">
        <AnalyticsCard
          title="In Queue"
          value={inQueue}
          subtitle="documents awaiting review"
        />
        <AnalyticsCard
          title="High Priority"
          value={highPriority}
          subtitle="CRITICAL + HIGH items"
          status={highPriority > 0 ? 'error' : undefined}
        />
        <AnalyticsCard
          title="Claimed"
          value={claimed}
          subtitle="currently being reviewed"
          status="warning"
        />
        <AnalyticsCard
          title="Avg Wait"
          value={formatAvgWait(avgWaitMins)}
          subtitle="time in queue"
        />
      </div>

      {/* ── Priority filter tabs ── */}
      <div className="sd-review-queue__filters" role="tablist" aria-label="Filter by priority">
        {PRIORITY_FILTERS.map((p) => (
          <button
            key={p}
            role="tab"
            aria-selected={activePriority === p}
            aria-current={activePriority === p ? 'true' : undefined}
            tabIndex={activePriority === p ? 0 : -1}
            ref={(el) => { filterPillRefs.current[p] = el; }}
            className={[
              'sd-review-queue__filter-pill',
              activePriority === p ? 'sd-review-queue__filter-pill--active' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            onClick={() => handlePriorityFilter(p)}
            onKeyDown={(e) => handleFilterKeyDown(e, p)}
          >
            {p}
          </button>
        ))}
      </div>

      {/* ── Error state ── */}
      {error && (
        <div className="sd-review-queue__error" role="alert">
          <span>Could not load queue: {error}</span>
          <button onClick={refresh}>Retry</button>
        </div>
      )}

      {/* ── Loading skeleton ── */}
      {loading && !error && items.length === 0 && (
        <div className="sd-review-queue__loading">
          <div className="sd-review-queue__spinner" />
          <p>Loading review queue…</p>
        </div>
      )}

      {/* ── Empty state ── */}
      {!loading && !error && items.length === 0 && (
        <div className="sd-review-queue__empty">
          <span className="sd-review-queue__empty-icon">📋</span>
          <p>No documents in the review queue.</p>
          {activePriority !== 'ALL' && (
            <button
              className="sd-review-queue__btn sd-review-queue__btn--ghost"
              onClick={() => handlePriorityFilter('ALL')}
            >
              Clear filter
            </button>
          )}
        </div>
      )}

      {/* ── Queue list ── */}
      <SectionErrorBoundary sectionName="Review Queue List">
      {items.length > 0 && (
        <div className="sd-review-queue__list" aria-busy={loading}>
          {items.map((doc) => (
            <ReviewQueueItem
              key={doc.id}
              document={doc}
              onClaim={handleClaim}
              onRelease={handleRelease}
              onAiReview={handleAiReview}
              onViewDetail={handleViewDetail}
              currentUserId={currentUserId}
            />
          ))}
        </div>
      )}
      </SectionErrorBoundary>

      {/* ── Pagination ── */}
      {total > limit && (
        <div className="sd-review-queue__pagination">
          <button
            className="sd-review-queue__btn sd-review-queue__btn--secondary"
            onClick={prevPage}
            disabled={!hasPrev || loading}
            aria-label="Previous page"
          >
            Previous
          </button>
          <span className="sd-review-queue__page-info" aria-live="polite">
            Showing {from}–{to} of {total}
          </span>
          <button
            className="sd-review-queue__btn sd-review-queue__btn--secondary"
            onClick={nextPage}
            disabled={!hasNext || loading}
            aria-label="Next page"
          >
            Next
          </button>
        </div>
      )}

    </div>
  );
}
