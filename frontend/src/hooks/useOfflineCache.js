/**
 * useOfflineCache — Caches API responses for offline access.
 * Uses @capacitor/preferences on native, localStorage on web.
 */
import { useCallback } from 'react';
import { Capacitor } from '@capacitor/core';

const CACHE_PREFIX = 'offline_cache_';
const CACHE_TTL_MS = 30 * 60 * 1000; // 30 minutes

async function setCache(key, data) {
  const entry = JSON.stringify({ data, timestamp: Date.now() });
  if (Capacitor.isNativePlatform()) {
    const { Preferences } = await import('@capacitor/preferences');
    await Preferences.set({ key: CACHE_PREFIX + key, value: entry });
  } else {
    try { localStorage.setItem(CACHE_PREFIX + key, entry); } catch {}
  }
}

async function getCache(key) {
  let raw;
  if (Capacitor.isNativePlatform()) {
    const { Preferences } = await import('@capacitor/preferences');
    const result = await Preferences.get({ key: CACHE_PREFIX + key });
    raw = result.value;
  } else {
    raw = localStorage.getItem(CACHE_PREFIX + key);
  }

  if (!raw) return null;
  try {
    const entry = JSON.parse(raw);
    if (Date.now() - entry.timestamp > CACHE_TTL_MS) return null;
    return entry.data;
  } catch {
    return null;
  }
}

/**
 * Hook that wraps a fetch function with offline caching.
 *
 * Usage:
 *   const { fetchWithCache } = useOfflineCache();
 *   const data = await fetchWithCache('dashboard', () => api.get('/api/v1/dashboard'));
 */
export function useOfflineCache() {
  const fetchWithCache = useCallback(async (cacheKey, fetchFn) => {
    try {
      const data = await fetchFn();
      await setCache(cacheKey, data);
      return { data, fromCache: false };
    } catch (error) {
      const cached = await getCache(cacheKey);
      if (cached) {
        return { data: cached, fromCache: true };
      }
      throw error;
    }
  }, []);

  const getCached = useCallback(async (cacheKey) => {
    return await getCache(cacheKey);
  }, []);

  const invalidateCache = useCallback(async (cacheKey) => {
    if (Capacitor.isNativePlatform()) {
      const { Preferences } = await import('@capacitor/preferences');
      await Preferences.remove({ key: CACHE_PREFIX + cacheKey });
    } else {
      localStorage.removeItem(CACHE_PREFIX + cacheKey);
    }
  }, []);

  return { fetchWithCache, getCached, invalidateCache };
}

export default useOfflineCache;
