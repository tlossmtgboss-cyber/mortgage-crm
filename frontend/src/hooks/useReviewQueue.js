/**
 * Perennia AI - useReviewQueue Hook
 *
 * Manages document review queue state: items, stats, pagination, filtering,
 * and claim/release actions. Delegates API calls to docReviewApi.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { getQueue, getQueueStats, claimDocument, releaseDocument } from '../services/docReviewApi';

const DEFAULT_FILTERS = { limit: 50, offset: 0 };

export default function useReviewQueue() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFiltersState] = useState(DEFAULT_FILTERS);

  const mountedRef = useRef(true);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // Core load — always reads filtersRef.current so it never captures stale state
  const load = useCallback(async (filtersOverride) => {
    const activeFilters = filtersOverride ?? filtersRef.current;
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
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  // Load on mount
  useEffect(() => { load(); }, [load]);

  // Reload whenever filters change (skip mount — load above handles it)
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return; }
    load();
  }, [filters, load]);

  // Auto-refresh every 30s while the tab is visible
  useEffect(() => {
    let intervalId = null;
    const start = () => { if (!intervalId) intervalId = setInterval(() => { if (mountedRef.current) load(); }, 30_000); };
    const stop = () => { clearInterval(intervalId); intervalId = null; };
    const onVisibility = () => { document.hidden ? stop() : start(); };

    if (!document.hidden) start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => { stop(); document.removeEventListener('visibilitychange', onVisibility); };
  }, [load]);

  const setFilters = useCallback((newFilters) => {
    setFiltersState((prev) => ({ ...prev, ...newFilters, offset: 0 }));
  }, []);

  const nextPage = useCallback(() => {
    setFiltersState((prev) => ({ ...prev, offset: prev.offset + prev.limit }));
  }, []);

  const prevPage = useCallback(() => {
    setFiltersState((prev) => ({ ...prev, offset: Math.max(0, prev.offset - prev.limit) }));
  }, []);

  const claim = useCallback(async (documentId, reviewerId) => {
    await claimDocument(documentId, reviewerId);
    await load();
  }, [load]);

  const release = useCallback(async (documentId) => {
    await releaseDocument(documentId);
    await load();
  }, [load]);

  const refresh = useCallback(async () => { await load(); }, [load]);

  return { items, stats, total, loading, error, filters, setFilters, nextPage, prevPage, claim, release, refresh };
}
