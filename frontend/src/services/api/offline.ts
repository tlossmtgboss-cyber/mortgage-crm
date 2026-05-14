/**
 * Simple in-memory cache for offline GET fallback (last successful response per URL).
 */

const _offlineCache = new Map<string, { data: any; ts: number }>();
const _OFFLINE_CACHE_MAX = 150;
const _OFFLINE_CACHE_TTL = 10 * 60 * 1000; // 10 minutes

export function cacheSet(url: string, data: any): void {
  if (_offlineCache.size >= _OFFLINE_CACHE_MAX) {
    // Evict oldest entry
    const firstKey = _offlineCache.keys().next().value;
    if (firstKey !== undefined) {
      _offlineCache.delete(firstKey);
    }
  }
  _offlineCache.set(url, { data, ts: Date.now() });
}

export function cacheGet(url: string): any | null {
  const entry = _offlineCache.get(url);
  if (!entry) return null;
  if (Date.now() - entry.ts > _OFFLINE_CACHE_TTL) {
    _offlineCache.delete(url);
    return null;
  }
  return entry.data;
}

// Debounced CRM mutation event -- coalesces rapid-fire mutations (e.g. bulk ops)
let _mutationTimer: ReturnType<typeof setTimeout> | null = null;

export function dispatchMutationDebounced(): void {
  if (_mutationTimer) clearTimeout(_mutationTimer);
  _mutationTimer = setTimeout(() => {
    window.dispatchEvent(new CustomEvent('crm-mutation'));
    _mutationTimer = null;
  }, 300);
}
