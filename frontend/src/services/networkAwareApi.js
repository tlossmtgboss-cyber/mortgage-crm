/**
 * Network-Aware API Request Manager
 *
 * Wraps the existing axios-based api instance with intelligent network
 * awareness for the Perennia AI mobile app (Capacitor/iOS).
 *
 * Behaviors by connection type:
 *   WiFi    -> immediate execution, 30s timeout, no throttling
 *   Cellular -> request dedup, reduced polling, 15s timeout
 *   Offline  -> GET returns cached data; mutations queue for replay
 *
 * Features:
 *   - Request deduplication (same GET within 1s shares a single promise)
 *   - Retry with exponential backoff on network errors (not 4xx)
 *   - Priority queue (HIGH > MEDIUM > LOW) processed in order on reconnect
 *   - Bandwidth tracking with getDataUsage()
 *   - Drop-in replacement for axios: networkApi.get(), .post(), .put(), etc.
 */

import { Capacitor } from '@capacitor/core';
import api from './api';

// ---------------------------------------------------------------------------
// Connection state singleton
// ---------------------------------------------------------------------------

const CONNECTION_TYPES = {
  WIFI: 'wifi',
  CELLULAR: 'cellular',
  NONE: 'none',
  UNKNOWN: 'unknown',
};

const connectionState = {
  connected: true,
  type: CONNECTION_TYPES.UNKNOWN,
  /** @type {Array<() => void>} */
  _listeners: [],
};

/**
 * Initialize Capacitor Network listener (called once at module load on native).
 * Falls back to browser online/offline events on web.
 */
function _initNetworkListener() {
  if (Capacitor.isNativePlatform()) {
    import('@capacitor/network').then(({ Network }) => {
      Network.getStatus().then((status) => {
        connectionState.connected = status.connected;
        connectionState.type = _normalizeConnectionType(status.connectionType);
      });

      Network.addListener('networkStatusChange', (status) => {
        const wasOffline = !connectionState.connected;
        connectionState.connected = status.connected;
        connectionState.type = _normalizeConnectionType(status.connectionType);

        if (wasOffline && status.connected) {
          _drainOfflineQueue();
        }

        connectionState._listeners.forEach((fn) => fn());
      });
    });
  } else {
    // Web fallback
    connectionState.connected = navigator.onLine;
    connectionState.type = navigator.onLine ? CONNECTION_TYPES.WIFI : CONNECTION_TYPES.NONE;

    window.addEventListener('online', () => {
      const wasOffline = !connectionState.connected;
      connectionState.connected = true;
      connectionState.type = CONNECTION_TYPES.WIFI;
      if (wasOffline) _drainOfflineQueue();
      connectionState._listeners.forEach((fn) => fn());
    });

    window.addEventListener('offline', () => {
      connectionState.connected = false;
      connectionState.type = CONNECTION_TYPES.NONE;
      connectionState._listeners.forEach((fn) => fn());
    });
  }
}

function _normalizeConnectionType(raw) {
  if (!raw) return CONNECTION_TYPES.UNKNOWN;
  const lower = raw.toLowerCase();
  if (lower === 'wifi') return CONNECTION_TYPES.WIFI;
  if (['cellular', '4g', '3g', '2g', 'lte', '5g'].includes(lower)) return CONNECTION_TYPES.CELLULAR;
  if (lower === 'none') return CONNECTION_TYPES.NONE;
  return CONNECTION_TYPES.UNKNOWN;
}

// ---------------------------------------------------------------------------
// Priority levels
// ---------------------------------------------------------------------------

const PRIORITY = {
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
};

/**
 * Per-request priority overrides. Callers can set these before issuing a
 * request, or pass _priority in the axios config.
 */
const _priorityOverrides = new Map();

/**
 * Set the priority for the *next* request to a given URL pattern.
 * Example: setRequestPriority('/api/v1/auth/', 'HIGH');
 */
function setRequestPriority(urlPattern, level) {
  const numericLevel = typeof level === 'number' ? level : PRIORITY[level] || PRIORITY.MEDIUM;
  _priorityOverrides.set(urlPattern, numericLevel);
}

function _resolvePriority(config) {
  // Explicit per-request override
  if (config._priority) {
    return typeof config._priority === 'number' ? config._priority : PRIORITY[config._priority] || PRIORITY.MEDIUM;
  }

  const url = config.url || '';
  const method = (config.method || 'get').toLowerCase();

  // Check pattern overrides (longest match wins)
  let matched = null;
  let matchLen = 0;
  for (const [pattern, pri] of _priorityOverrides.entries()) {
    if (url.includes(pattern) && pattern.length > matchLen) {
      matched = pri;
      matchLen = pattern.length;
    }
  }
  if (matched !== null) return matched;

  // Heuristic defaults
  if (url.includes('/auth/') || url.includes('/csrf-token')) return PRIORITY.HIGH;
  if (['post', 'put', 'patch', 'delete'].includes(method)) return PRIORITY.HIGH;
  if (url.includes('/push-token') || url.includes('/device-token')) return PRIORITY.HIGH;
  if (url.includes('/analytics') || url.includes('/prefetch')) return PRIORITY.LOW;
  return PRIORITY.MEDIUM;
}

// ---------------------------------------------------------------------------
// Timeout management
// ---------------------------------------------------------------------------

function _getTimeout(config) {
  // Honor explicit timeouts
  if (config.timeout) return config.timeout;

  switch (connectionState.type) {
    case CONNECTION_TYPES.WIFI:
      return 30_000;
    case CONNECTION_TYPES.CELLULAR:
      return 15_000;
    default:
      return 20_000;
  }
}

// ---------------------------------------------------------------------------
// Request deduplication
// ---------------------------------------------------------------------------

/** @type {Map<string, { promise: Promise, timestamp: number }>} */
const _inflightGets = new Map();
const DEDUP_WINDOW_MS = 1_000;

function _dedupKey(config) {
  // Only dedup GETs
  const method = (config.method || 'get').toLowerCase();
  if (method !== 'get') return null;
  // Build a stable key from URL + sorted params
  const url = config.url || '';
  const params = config.params ? JSON.stringify(config.params, Object.keys(config.params).sort()) : '';
  return `GET:${url}:${params}`;
}

// ---------------------------------------------------------------------------
// Response cache (offline reads)
// ---------------------------------------------------------------------------

const _responseCache = new Map();
const MAX_CACHE_ENTRIES = 200;
const CACHE_TTL_MS = 5 * 60 * 1_000; // 5 minutes

function _cacheKey(config) {
  const url = config.url || '';
  const params = config.params ? JSON.stringify(config.params, Object.keys(config.params).sort()) : '';
  return `${url}:${params}`;
}

function _cacheResponse(config, response) {
  const method = (config.method || 'get').toLowerCase();
  if (method !== 'get') return;

  const key = _cacheKey(config);

  // Evict oldest if over limit
  if (_responseCache.size >= MAX_CACHE_ENTRIES) {
    const oldest = _responseCache.keys().next().value;
    _responseCache.delete(oldest);
  }

  _responseCache.set(key, {
    data: response.data,
    status: response.status,
    headers: response.headers,
    cachedAt: Date.now(),
  });
}

function _getCached(config) {
  const key = _cacheKey(config);
  const entry = _responseCache.get(key);
  if (!entry) return null;

  // Check TTL
  if (Date.now() - entry.cachedAt > CACHE_TTL_MS) {
    _responseCache.delete(key);
    return null;
  }

  return {
    data: entry.data,
    status: entry.status,
    headers: entry.headers,
    config,
    _fromCache: true,
  };
}

// ---------------------------------------------------------------------------
// Offline mutation queue
// ---------------------------------------------------------------------------

/** @type {Array<{ config: object, priority: number, resolve: Function, reject: Function, queuedAt: number }>} */
const _offlineQueue = [];

function _enqueueOffline(config) {
  const priority = _resolvePriority(config);
  return new Promise((resolve, reject) => {
    _offlineQueue.push({ config, priority, resolve, reject, queuedAt: Date.now() });
    // Keep sorted by priority (lower number = higher priority)
    _offlineQueue.sort((a, b) => a.priority - b.priority);
  });
}

async function _drainOfflineQueue() {
  if (_offlineQueue.length === 0) return;

  // Snapshot and clear — if something fails it will be re-enqueued
  const batch = _offlineQueue.splice(0);

  for (const item of batch) {
    try {
      const response = await _executeRequest(item.config, true);
      item.resolve(response);
    } catch (err) {
      // If still offline, re-queue
      if (!connectionState.connected) {
        _offlineQueue.push(item);
        _offlineQueue.sort((a, b) => a.priority - b.priority);
      } else {
        item.reject(err);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Retry with exponential backoff
// ---------------------------------------------------------------------------

const DEFAULT_MAX_RETRIES = 3;
const BASE_DELAY_MS = 1_000;

function _isRetryable(error) {
  // Don't retry client errors (4xx)
  if (error.response && error.response.status >= 400 && error.response.status < 500) {
    return false;
  }
  // Retry network errors, timeouts, 5xx
  if (!error.response) return true; // network error
  if (error.code === 'ECONNABORTED') return true; // timeout
  if (error.response.status >= 500) return true;
  return false;
}

function _delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function _retryRequest(config, maxRetries = DEFAULT_MAX_RETRIES) {
  let lastError;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await api.request({
        ...config,
        timeout: _getTimeout(config),
      });
      return response;
    } catch (error) {
      lastError = error;

      if (attempt < maxRetries && _isRetryable(error)) {
        const delayMs = BASE_DELAY_MS * Math.pow(2, attempt); // 1s, 2s, 4s
        await _delay(delayMs);
        continue;
      }

      throw error;
    }
  }

  throw lastError;
}

// ---------------------------------------------------------------------------
// Bandwidth tracking
// ---------------------------------------------------------------------------

const _bandwidth = {
  sent: 0,
  received: 0,
  requestCount: 0,
  startedAt: Date.now(),
};

function _estimateRequestSize(config) {
  let size = 0;

  // URL + method
  size += (config.url || '').length;
  size += (config.method || '').length;

  // Headers (rough estimate)
  if (config.headers) {
    for (const [key, value] of Object.entries(config.headers)) {
      size += key.length + String(value).length;
    }
  }

  // Body
  if (config.data) {
    if (typeof config.data === 'string') {
      size += config.data.length;
    } else {
      try {
        size += JSON.stringify(config.data).length;
      } catch (_) {
        size += 256; // fallback estimate
      }
    }
  }

  return size;
}

function _estimateResponseSize(response) {
  if (!response) return 0;
  let size = 0;

  // Content-Length header is the most accurate
  const contentLength = response.headers?.['content-length'];
  if (contentLength) {
    return parseInt(contentLength, 10);
  }

  // Estimate from data
  if (response.data) {
    if (typeof response.data === 'string') {
      size = response.data.length;
    } else {
      try {
        size = JSON.stringify(response.data).length;
      } catch (_) {
        size = 512;
      }
    }
  }

  return size;
}

function _trackBandwidth(config, response) {
  _bandwidth.requestCount += 1;
  _bandwidth.sent += _estimateRequestSize(config);
  if (response) {
    _bandwidth.received += _estimateResponseSize(response);
  }
}

/**
 * Get data usage statistics.
 * Returns bytes sent/received and request count since module init.
 */
function getDataUsage() {
  const elapsed = Date.now() - _bandwidth.startedAt;
  const elapsedMinutes = elapsed / 60_000;

  return {
    sent: _bandwidth.sent,
    received: _bandwidth.received,
    total: _bandwidth.sent + _bandwidth.received,
    requestCount: _bandwidth.requestCount,
    elapsedMs: elapsed,
    // Formatted helpers
    sentFormatted: _formatBytes(_bandwidth.sent),
    receivedFormatted: _formatBytes(_bandwidth.received),
    totalFormatted: _formatBytes(_bandwidth.sent + _bandwidth.received),
    ratePerMinute: elapsedMinutes > 0
      ? _formatBytes((_bandwidth.sent + _bandwidth.received) / elapsedMinutes) + '/min'
      : '0 B/min',
  };
}

function _formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(1)} ${units[i] || 'TB'}`;
}

// ---------------------------------------------------------------------------
// Core request execution
// ---------------------------------------------------------------------------

/**
 * Execute a single request through the network-aware pipeline.
 * @param {object} config - axios request config
 * @param {boolean} skipOfflineQueue - true when draining the offline queue
 */
async function _executeRequest(config, skipOfflineQueue = false) {
  const method = (config.method || 'get').toLowerCase();
  const isGet = method === 'get';

  // --- Offline handling ---
  if (!connectionState.connected && !skipOfflineQueue) {
    if (isGet) {
      const cached = _getCached(config);
      if (cached) return cached;
    }
    // Queue mutations (and uncached GETs) for later
    return _enqueueOffline(config);
  }

  // --- Deduplication (GET only, online) ---
  if (isGet) {
    const key = _dedupKey(config);
    if (key) {
      const inflight = _inflightGets.get(key);
      if (inflight && Date.now() - inflight.timestamp < DEDUP_WINDOW_MS) {
        return inflight.promise;
      }

      const promise = _retryRequest(config)
        .then((response) => {
          _cacheResponse(config, response);
          _trackBandwidth(config, response);
          return response;
        })
        .catch((err) => {
          // On network failure, attempt cache fallback
          if (!err.response) {
            const cached = _getCached(config);
            if (cached) return cached;
          }
          throw err;
        })
        .finally(() => {
          // Clean up after dedup window
          setTimeout(() => _inflightGets.delete(key), DEDUP_WINDOW_MS);
        });

      _inflightGets.set(key, { promise, timestamp: Date.now() });
      return promise;
    }
  }

  // --- Mutations / non-dedup requests ---
  const response = await _retryRequest(config);
  _trackBandwidth(config, response);
  return response;
}

// ---------------------------------------------------------------------------
// Public API — drop-in axios replacement
// ---------------------------------------------------------------------------

/**
 * Network-aware API instance.
 *
 * Usage:
 *   import { networkApi } from './networkAwareApi';
 *   const res = await networkApi.get('/api/v1/loans');
 *   const res = await networkApi.post('/api/v1/leads', data);
 */
const networkApi = {
  /**
   * GET request — supports dedup, caching, offline fallback.
   */
  get(url, config = {}) {
    return _executeRequest({ ...config, method: 'get', url });
  },

  /**
   * POST request — queued offline, retried on network errors.
   */
  post(url, data, config = {}) {
    return _executeRequest({ ...config, method: 'post', url, data });
  },

  /**
   * PUT request.
   */
  put(url, data, config = {}) {
    return _executeRequest({ ...config, method: 'put', url, data });
  },

  /**
   * PATCH request.
   */
  patch(url, data, config = {}) {
    return _executeRequest({ ...config, method: 'patch', url, data });
  },

  /**
   * DELETE request.
   */
  delete(url, config = {}) {
    return _executeRequest({ ...config, method: 'delete', url });
  },

  /**
   * Generic request (matches axios.request signature).
   */
  request(config) {
    return _executeRequest(config);
  },

  // ---- Utility accessors ----

  /** Current connection state (read-only snapshot) */
  getConnectionState() {
    return {
      connected: connectionState.connected,
      type: connectionState.type,
      isWifi: connectionState.type === CONNECTION_TYPES.WIFI,
      isCellular: connectionState.type === CONNECTION_TYPES.CELLULAR,
      isOffline: !connectionState.connected,
    };
  },

  /** Number of requests waiting in offline queue */
  getQueueLength() {
    return _offlineQueue.length;
  },

  /** Subscribe to connection changes. Returns unsubscribe function. */
  onConnectionChange(callback) {
    connectionState._listeners.push(callback);
    return () => {
      const idx = connectionState._listeners.indexOf(callback);
      if (idx >= 0) connectionState._listeners.splice(idx, 1);
    };
  },

  /** Manually clear the response cache */
  clearCache() {
    _responseCache.clear();
  },

  /** Force-drain the offline queue (e.g. after manual reconnect) */
  flushQueue() {
    return _drainOfflineQueue();
  },
};

// ---------------------------------------------------------------------------
// Initialize on module load
// ---------------------------------------------------------------------------

_initNetworkListener();

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export { networkApi, getDataUsage, setRequestPriority };
export default networkApi;
