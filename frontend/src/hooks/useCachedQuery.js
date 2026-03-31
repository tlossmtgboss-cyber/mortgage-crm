/**
 * useCachedQuery — Stale-while-revalidate hook with per-endpoint TTL caching.
 *
 * Returns cached data immediately when available, fetches fresh data in the
 * background, and falls back to cache on network errors.  Integrates with
 * React Query when it is available in the component tree; otherwise operates
 * standalone.
 *
 * Usage:
 *   const { data, isLoading, isStale, error, refresh, cacheInfo } = useCachedQuery(
 *     '/api/v1/pipeline/metrics',
 *     () => axios.get('/api/v1/pipeline/metrics').then(r => r.data),
 *     { enabled: true }
 *   );
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getFromCache,
  setCache,
  invalidateExact,
  getTTL,
} from '../services/cacheManager';

// Try to detect React Query in the tree at module level — if the package is
// not installed the import will throw and we gracefully degrade.
let useQueryClient;
try {
  // eslint-disable-next-line
  const rq = require('@tanstack/react-query');
  useQueryClient = rq.useQueryClient;
} catch {
  useQueryClient = null;
}

/**
 * @param {string} cacheKey          Cache key (typically the API URL path).
 * @param {() => Promise<any>} fetchFn  Function that returns a promise resolving to data.
 * @param {object} [options]
 * @param {boolean} [options.enabled=true]  Whether to run the query.
 * @param {number}  [options.ttl]           Override TTL in ms.
 * @param {string}  [options.priority]      Override cache priority ('high'|'medium'|'low').
 * @param {boolean} [options.cacheOnly=false]  If true, only return cached data — never fetch.
 * @param {function} [options.onSuccess]    Callback when fresh data arrives.
 * @param {function} [options.onError]      Callback on fetch error.
 */
export function useCachedQuery(cacheKey, fetchFn, options = {}) {
  const {
    enabled = true,
    ttl,
    priority,
    cacheOnly = false,
    onSuccess,
    onError,
  } = options;

  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isStale, setIsStale] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const [cacheInfo, setCacheInfo] = useState(null);

  // Track whether the component is still mounted.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // Stable reference to the latest fetchFn to avoid stale closures.
  const fetchFnRef = useRef(fetchFn);
  fetchFnRef.current = fetchFn;

  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;

  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  // Optionally notify React Query so its cache stays in sync.
  let queryClient = null;
  try {
    if (useQueryClient) {
      // eslint-disable-next-line react-hooks/rules-of-hooks
      queryClient = useQueryClient();
    }
  } catch {
    // Not inside a QueryClientProvider — that's fine.
    queryClient = null;
  }

  // -----------------------------------------------------------------------
  // Core: load cached + revalidate
  // -----------------------------------------------------------------------

  const execute = useCallback(async (forceRefresh = false) => {
    if (!mountedRef.current) return;

    // 1. Serve from cache immediately
    const cached = await getFromCache(cacheKey);

    if (cached) {
      if (mountedRef.current) {
        setData(cached.data);
        setCacheInfo({ age: cached.age, isFresh: cached.isFresh });
        setIsLoading(false);

        if (cached.isFresh && !forceRefresh) {
          setIsStale(false);
          return; // Cache is fresh — no network call needed.
        }

        // Data exists but is stale — show it while we revalidate.
        setIsStale(true);
      }
    }

    // 2. Skip network if cacheOnly
    if (cacheOnly) {
      if (mountedRef.current && !cached) {
        setIsLoading(false);
      }
      return;
    }

    // 3. Fetch fresh data in the background
    if (mountedRef.current) setIsFetching(true);

    try {
      const freshData = await fetchFnRef.current();

      if (!mountedRef.current) return;

      setData(freshData);
      setError(null);
      setIsStale(false);
      setIsLoading(false);
      setIsFetching(false);
      setCacheInfo({ age: 0, isFresh: true });

      // Persist to offline cache
      await setCache(cacheKey, freshData, {
        ...(ttl != null && { ttl }),
        ...(priority != null && { priority }),
      });

      // Keep React Query cache in sync if available
      if (queryClient) {
        try {
          queryClient.setQueryData([cacheKey], freshData);
        } catch {
          // Non-critical — ignore
        }
      }

      if (onSuccessRef.current) onSuccessRef.current(freshData);
    } catch (fetchError) {
      if (!mountedRef.current) return;

      setIsFetching(false);

      // If we already have cached data, keep showing it.
      if (data || cached) {
        setIsStale(true);
        setError(fetchError);
        // Don't set isLoading — we have data.
      } else {
        setError(fetchError);
        setIsLoading(false);
      }

      if (onErrorRef.current) onErrorRef.current(fetchError);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey, cacheOnly, ttl, priority]);

  // -----------------------------------------------------------------------
  // Run on mount / when enabled or cacheKey changes
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!enabled) {
      setIsLoading(false);
      return;
    }

    // Reset state for a new cacheKey
    setIsLoading(true);
    setError(null);
    setIsStale(false);

    execute(false);
  }, [cacheKey, enabled, execute]);

  // -----------------------------------------------------------------------
  // Manual refresh (always forces a network call)
  // -----------------------------------------------------------------------

  const refresh = useCallback(() => {
    setIsFetching(true);
    return execute(true);
  }, [execute]);

  // -----------------------------------------------------------------------
  // Manual invalidation — clears cache and refetches
  // -----------------------------------------------------------------------

  const invalidate = useCallback(async () => {
    await invalidateExact(cacheKey);
    setIsStale(true);
    return execute(true);
  }, [cacheKey, execute]);

  return {
    data,
    error,
    isLoading,     // True only when there is no data at all yet.
    isStale,       // True when showing cached data while revalidating.
    isFetching,    // True during any active network request.
    cacheInfo,     // { age: ms, isFresh: bool } or null
    refresh,       // Force refetch (keeps existing data visible).
    invalidate,    // Clear cache + refetch.
  };
}

export default useCachedQuery;
