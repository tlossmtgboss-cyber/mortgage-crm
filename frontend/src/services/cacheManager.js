/**
 * cacheManager — Per-endpoint TTL caching with priority-based eviction.
 *
 * Uses @capacitor/preferences on native, localStorage on web.
 * Supports cache versioning, size management, and pattern-based invalidation.
 */
import { Capacitor } from '@capacitor/core';

// ---------------------------------------------------------------------------
// Cache configuration by endpoint pattern
// ---------------------------------------------------------------------------

const CACHE_CONFIG = {
  '/api/v1/pipeline':      { ttl: 300000,   priority: 'high' },     // 5 min
  '/api/v1/notifications':  { ttl: 30000,    priority: 'high' },     // 30 sec
  '/api/v1/tasks':          { ttl: 120000,   priority: 'high' },     // 2 min
  '/api/v1/leads':          { ttl: 300000,   priority: 'medium' },   // 5 min
  '/api/v1/loans':          { ttl: 300000,   priority: 'medium' },   // 5 min
  '/api/v1/calendar':       { ttl: 60000,    priority: 'medium' },   // 1 min
  '/api/v1/dashboard':      { ttl: 120000,   priority: 'medium' },   // 2 min
  '/api/v1/analytics':      { ttl: 1800000,  priority: 'low' },      // 30 min
  '/api/v1/users/me':       { ttl: 3600000,  priority: 'low' },      // 1 hour
  '/api/v1/team':           { ttl: 600000,   priority: 'low' },      // 10 min
  _default:                 { ttl: 300000,   priority: 'medium' },   // 5 min default
};

// Priority weights for eviction — lower weight gets evicted first.
const PRIORITY_WEIGHT = { low: 1, medium: 2, high: 3 };

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CACHE_PREFIX = 'pc_';           // "perennia cache"
const META_KEY = 'pc__meta';          // metadata / index entry
const CACHE_SCHEMA_VERSION = 1;       // bump to invalidate all caches
const MAX_CACHE_BYTES = 10 * 1024 * 1024; // 10 MB

// ---------------------------------------------------------------------------
// Storage abstraction
// ---------------------------------------------------------------------------

let _Preferences = null;

async function getPreferences() {
  if (_Preferences) return _Preferences;
  if (Capacitor.isNativePlatform()) {
    const mod = await import('@capacitor/preferences');
    _Preferences = mod.Preferences;
  }
  return _Preferences;
}

async function storageSet(key, value) {
  const prefs = await getPreferences();
  if (prefs) {
    await prefs.set({ key, value });
  } else {
    try {
      localStorage.setItem(key, value);
    } catch {
      // localStorage full — eviction should have handled this, but guard anyway
    }
  }
}

async function storageGet(key) {
  const prefs = await getPreferences();
  if (prefs) {
    const result = await prefs.get({ key });
    return result.value;
  }
  return localStorage.getItem(key);
}

async function storageRemove(key) {
  const prefs = await getPreferences();
  if (prefs) {
    await prefs.remove({ key });
  } else {
    localStorage.removeItem(key);
  }
}

// ---------------------------------------------------------------------------
// Internal metadata index
//
// We keep a lightweight in-memory index that is persisted to storage.
// Structure: { version, entries: { [cacheKey]: { url, size, priority, storedAt, ttl } } }
// ---------------------------------------------------------------------------

let _meta = null;

async function loadMeta() {
  if (_meta) return _meta;
  const raw = await storageGet(META_KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (parsed.version === CACHE_SCHEMA_VERSION) {
        _meta = parsed;
        return _meta;
      }
    } catch {
      // corrupt — fall through to reset
    }
  }
  // First load or version mismatch — start fresh
  _meta = { version: CACHE_SCHEMA_VERSION, entries: {} };
  await persistMeta();
  return _meta;
}

async function persistMeta() {
  if (!_meta) return;
  await storageSet(META_KEY, JSON.stringify(_meta));
}

// ---------------------------------------------------------------------------
// Config resolution
// ---------------------------------------------------------------------------

/**
 * Resolve the cache config for a given URL/key by matching against
 * CACHE_CONFIG patterns (longest prefix match).
 */
function resolveConfig(url) {
  let bestMatch = '';
  let bestConfig = CACHE_CONFIG._default;

  for (const pattern of Object.keys(CACHE_CONFIG)) {
    if (pattern === '_default') continue;
    if (url.startsWith(pattern) && pattern.length > bestMatch.length) {
      bestMatch = pattern;
      bestConfig = CACHE_CONFIG[pattern];
    }
  }

  return bestConfig;
}

// ---------------------------------------------------------------------------
// Size tracking helpers
// ---------------------------------------------------------------------------

function estimateSize(str) {
  // Rough byte estimate — JS strings are UTF-16 but JSON is typically ASCII-ish
  return typeof str === 'string' ? str.length * 2 : 0;
}

function totalCacheSize(meta) {
  let total = 0;
  for (const key of Object.keys(meta.entries)) {
    total += meta.entries[key].size || 0;
  }
  return total;
}

// ---------------------------------------------------------------------------
// Eviction
// ---------------------------------------------------------------------------

/**
 * Evict lowest-priority, oldest entries until total size is under the limit.
 * Returns the number of evicted entries.
 */
async function evictIfNeeded(meta, reserveBytes = 0) {
  const target = MAX_CACHE_BYTES - reserveBytes;
  let currentSize = totalCacheSize(meta);
  if (currentSize <= target) return 0;

  // Build a sorted list: lowest priority first, then oldest first
  const entries = Object.entries(meta.entries).map(([key, info]) => ({
    key,
    ...info,
  }));

  entries.sort((a, b) => {
    const pa = PRIORITY_WEIGHT[a.priority] || 0;
    const pb = PRIORITY_WEIGHT[b.priority] || 0;
    if (pa !== pb) return pa - pb;       // lower priority first
    return (a.storedAt || 0) - (b.storedAt || 0); // older first
  });

  let evicted = 0;
  for (const entry of entries) {
    if (currentSize <= target) break;
    await storageRemove(CACHE_PREFIX + entry.key);
    currentSize -= entry.size || 0;
    delete meta.entries[entry.key];
    evicted++;
  }

  await persistMeta();
  return evicted;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Retrieve a cached entry.
 *
 * @param {string} key - The cache key (typically the request URL or a custom key).
 * @returns {Promise<{ data: any, isFresh: boolean, age: number, fromCache: true } | null>}
 *   Returns null if the entry does not exist in the cache at all.
 *   `isFresh` is false when the entry has exceeded its TTL but is still returned
 *   so callers can use it as stale data while revalidating.
 */
async function getFromCache(key) {
  const meta = await loadMeta();
  const info = meta.entries[key];
  if (!info) return null;

  const raw = await storageGet(CACHE_PREFIX + key);
  if (!raw) {
    // Orphaned metadata — clean up
    delete meta.entries[key];
    await persistMeta();
    return null;
  }

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    delete meta.entries[key];
    await storageRemove(CACHE_PREFIX + key);
    await persistMeta();
    return null;
  }

  const now = Date.now();
  const age = now - (info.storedAt || 0);
  const isFresh = age < (info.ttl || CACHE_CONFIG._default.ttl);

  return {
    data: parsed,
    isFresh,
    age,
    fromCache: true,
  };
}

/**
 * Store data in the cache.
 *
 * @param {string} key - The cache key.
 * @param {any} data - The data to store (must be JSON-serializable).
 * @param {object} [overrides] - Optional overrides for ttl and priority.
 */
async function setCache(key, data, overrides = {}) {
  const meta = await loadMeta();
  const config = resolveConfig(key);
  const serialized = JSON.stringify(data);
  const size = estimateSize(serialized);

  // Evict if necessary to make room
  await evictIfNeeded(meta, size);

  await storageSet(CACHE_PREFIX + key, serialized);

  meta.entries[key] = {
    url: key,
    size,
    priority: overrides.priority || config.priority,
    storedAt: Date.now(),
    ttl: overrides.ttl || config.ttl,
  };

  await persistMeta();
}

/**
 * Invalidate cached entries whose key contains the given pattern string.
 *
 * @param {string} pattern - Substring to match against cache keys.
 * @returns {Promise<number>} Number of entries removed.
 */
async function invalidateCache(pattern) {
  const meta = await loadMeta();
  let removed = 0;

  for (const key of Object.keys(meta.entries)) {
    if (key.includes(pattern)) {
      await storageRemove(CACHE_PREFIX + key);
      delete meta.entries[key];
      removed++;
    }
  }

  if (removed > 0) {
    await persistMeta();
  }

  return removed;
}

/**
 * Invalidate a single cache key exactly.
 *
 * @param {string} key - The exact cache key to remove.
 */
async function invalidateExact(key) {
  const meta = await loadMeta();
  if (meta.entries[key]) {
    await storageRemove(CACHE_PREFIX + key);
    delete meta.entries[key];
    await persistMeta();
  }
}

/**
 * Clear the entire cache (all entries + metadata).
 */
async function clearAll() {
  const meta = await loadMeta();
  for (const key of Object.keys(meta.entries)) {
    await storageRemove(CACHE_PREFIX + key);
  }
  _meta = { version: CACHE_SCHEMA_VERSION, entries: {} };
  await persistMeta();
}

/**
 * Get cache statistics.
 *
 * @returns {Promise<{ totalSize: number, itemCount: number, oldestEntry: number|null, byPriority: object }>}
 */
async function getCacheStats() {
  const meta = await loadMeta();
  const entries = Object.values(meta.entries);

  let oldestEntry = null;
  const byPriority = { high: 0, medium: 0, low: 0 };

  for (const entry of entries) {
    if (oldestEntry === null || (entry.storedAt || 0) < oldestEntry) {
      oldestEntry = entry.storedAt || 0;
    }
    const p = entry.priority || 'medium';
    byPriority[p] = (byPriority[p] || 0) + 1;
  }

  return {
    totalSize: totalCacheSize(meta),
    itemCount: entries.length,
    oldestEntry,
    byPriority,
  };
}

/**
 * Get the resolved TTL for a URL / cache key.
 * Useful for external callers that want to know how long a key will be fresh.
 */
function getTTL(url) {
  return resolveConfig(url).ttl;
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export {
  getFromCache,
  setCache,
  invalidateCache,
  invalidateExact,
  clearAll,
  getCacheStats,
  getTTL,
  resolveConfig,
  CACHE_CONFIG,
  CACHE_SCHEMA_VERSION,
  MAX_CACHE_BYTES,
};

export default {
  getFromCache,
  setCache,
  invalidateCache,
  invalidateExact,
  clearAll,
  getCacheStats,
  getTTL,
};
