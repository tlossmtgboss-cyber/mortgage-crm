/**
 * Perennia AI - useReviewQueue Hook
 *
 * Manages document review queue state: items, stats, pagination, filtering,
 * and claim/release actions. Delegates API calls to docReviewApi.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { getQueue, getQueueStats, claimDocument, releaseDocument } from '../services/docReviewApi';

const DEFAULT_FILTERS = { limit: 50, offset: 0 };

/**
 * Hook for managing the document review queue.
 *
 * @returns {{
 *   items: Array,
 *   stats: object|null,
 *   total: number,
 *   loading: boolean,
 *   error: string|null,
 *   filters: object,
 *   setFilters: function,
 *   nextPage: function,
 *   prevPage: function,
 *   claim: function,
 *   release: function,
 *   refresh: function,
 * }}
 */
export default function useReviewQueue() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFiltersState] = useState(DEFAULT_FILTERS);

  // Track mounted state to prevent state updates after unmount
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Core load function — accepts an optional filters override so callers can
  // pass freshly-computed filters before the state update has propagated.
  // ---------------------------------------------------------------------------

  const load = useCallback(async (filtersOverride) => {
    const activeFilters = filtersOverride ?? filters;
    setLoading(true);
    setError(null);
    try {
      const [queueResponse, statsResponse] = await Promise.all([
        getQueue(activeFilters),
        getQueueStats(),
      ]);
      if (!mountedRef.current) return;
      setItems(queueResponse.items ?? []);
      setTotal(queueResponse.total ?? 0);
      setStats(statsResponse);
    } catch (err) {
      if (!mountedRef.current) return;
      setItems([]);
      setError(err.message ?? String(err));
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load on mount
  useEffect(() => {
    load(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reload whenever filters change (skip initial mount — load() above handles it)
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    load(filters);
  }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------------------
  // Filter management
  // ---------------------------------------------------------------------------

  const setFilters = useCallback((newFilters) => {
    setFiltersState((prev) => ({ ...prev, ...newFilters, offset: 0 }));
  }, []);

  // ---------------------------------------------------------------------------
  // Pagination
  // ---------------------------------------------------------------------------

  const nextPage = useCallback(() => {
    setFiltersState((prev) => ({ ...prev, offset: prev.offset + prev.limit }));
  }, []);

  const prevPage = useCallback(() => {
    setFiltersState((prev) => ({
      ...prev,
      offset: Math.max(0, prev.offset - prev.limit),
    }));
  }, []);

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const claim = useCallback(async (documentId, reviewerId) => {
    await claimDocument(documentId, reviewerId);
    await load();
  }, [load]);

  const release = useCallback(async (documentId) => {
    await releaseDocument(documentId);
    await load();
  }, [load]);

  const refresh = useCallback(async () => {
    await load();
  }, [load]);

  return {
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
  };
}
