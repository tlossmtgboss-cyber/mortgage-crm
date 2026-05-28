/**
 * Shared axios instance, interceptors, CSRF, retry logic, and error handling.
 *
 * All domain modules import `api` and `API_BASE_URL` from this file.
 */
import axios from 'axios';
import { Capacitor } from '@capacitor/core';
import { ensureArray } from '../../utils/arrayHelpers.js';
import { getCSRFTokenFromCookie } from '../../utils/security';
import { pinnedAdapter } from '../../utils/pinnedFetch';
import { getItem, setItem, removeItem, STORAGE_KEYS, clearAllAuthTokens } from '../../utils/storage';
import { getToken, getRefreshToken, setTokens, clearTokens } from '../../utils/tokenStore';

// Detect native mobile app FIRST — Capacitor serves from localhost,
// so we must check isNativePlatform() before the hostname check.
const isNativeApp = Capacitor.isNativePlatform();
const isLocalhost = !isNativeApp && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

export const API_BASE_URL = import.meta.env.VITE_API_URL || (
  isNativeApp
    ? 'https://api.perenniaai.com'  // Native iOS/Android — always production
    : isLocalhost
      ? 'http://localhost:8000'
      : 'https://api.perenniaai.com' // Production web
);

// Create axios instance with mobile app identification
// On native iOS, route through certificate-pinned URLSession
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 second timeout
  headers: {
    'Content-Type': 'application/json',
    // Identify mobile app requests to bypass IP blocking middleware
    ...(isNativeApp && { 'X-Mobile-App': 'capacitor-ios' }),
  },
  ...(isNativeApp && { adapter: pinnedAdapter }),
});

// CSRF token cache — fetched once, reused for all requests
let csrfTokenPromise = null;

const fetchCSRFToken = async () => {
  // Try cookie first (set by backend on GET responses)
  const cookieToken = getCSRFTokenFromCookie();
  if (cookieToken) return cookieToken;

  // Fetch from server if no cookie
  try {
    const response = await axios.get(`${API_BASE_URL}/api/v1/csrf-token`, {
      withCredentials: true,
    });
    return response.data?.csrf_token || null;
  } catch (error) {
    console.warn('Could not fetch CSRF token:', error);
    return null;
  }
};

const getCSRFToken = () => {
  // Check cookie synchronously first (fast path)
  const cookieToken = getCSRFTokenFromCookie();
  if (cookieToken) return Promise.resolve(cookieToken);

  // Fetch from server (deduplicated — only one in-flight request)
  if (!csrfTokenPromise) {
    csrfTokenPromise = fetchCSRFToken().finally(() => {
      // Allow re-fetch after 5 minutes
      setTimeout(() => { csrfTokenPromise = null; }, 5 * 60 * 1000);
    });
  }
  return csrfTokenPromise;
};

const CSRF_METHODS = ['post', 'put', 'patch', 'delete'];

// Add token, impersonation, and CSRF headers to requests
api.interceptors.request.use(
  async (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Add impersonation token if present
    const impersonationData = await getItem(STORAGE_KEYS.IMPERSONATION);
    if (impersonationData) {
      try {
        const data = JSON.parse(impersonationData);
        if (data.session_token) {
          config.headers['X-Impersonation-Token'] = data.session_token;
        }
      } catch (error) {
        console.error('Error parsing impersonation data:', error);
      }
    }

    // Add CSRF token for state-changing requests
    if (CSRF_METHODS.includes(config.method)) {
      const csrfToken = await getCSRFToken();
      if (csrfToken) {
        config.headers['X-CSRF-Token'] = csrfToken;
      }
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// ---------------------------------------------------------------------------
// Offline detection — fail fast with a friendly error when navigator.onLine
// is false, instead of waiting for a socket timeout.  For GET requests the
// response interceptor below will also check and surface a clean message.
// ---------------------------------------------------------------------------

/** Simple in-memory cache for offline GET fallback (last successful response per URL). */
const _offlineCache = new Map();
const _OFFLINE_CACHE_MAX = 150;
const _OFFLINE_CACHE_TTL = 10 * 60 * 1000; // 10 minutes

function _cacheSet(url, data) {
  if (_offlineCache.size >= _OFFLINE_CACHE_MAX) {
    // Evict oldest entry
    const firstKey = _offlineCache.keys().next().value;
    _offlineCache.delete(firstKey);
  }
  _offlineCache.set(url, { data, ts: Date.now() });
}

function _cacheGet(url) {
  const entry = _offlineCache.get(url);
  if (!entry) return null;
  if (Date.now() - entry.ts > _OFFLINE_CACHE_TTL) {
    _offlineCache.delete(url);
    return null;
  }
  return entry.data;
}

// Debounced CRM mutation event — coalesces rapid-fire mutations (e.g. bulk ops)
let _mutationTimer = null;
function _dispatchMutationDebounced() {
  if (_mutationTimer) clearTimeout(_mutationTimer);
  _mutationTimer = setTimeout(() => {
    window.dispatchEvent(new CustomEvent('crm-mutation'));
    _mutationTimer = null;
  }, 300);
}

// Cache successful GET responses for offline fallback
api.interceptors.response.use(
  (response) => {
    const method = (response.config?.method || 'get').toLowerCase();
    if (method === 'get' && response.config?.url) {
      _cacheSet(response.config.url, response.data);
    }
    if (['post', 'put', 'patch', 'delete'].includes(method)) {
      _dispatchMutationDebounced();
    }
    return response;
  },
  (error) => Promise.reject(error)
);

// ---------------------------------------------------------------------------
// Structured API error — every rejected promise from the interceptor carries
// this shape so callers can rely on a consistent contract:
//   { error: true, status, message, retryable, code, detail }
// The original axios error is preserved as `_axiosError` for callers that
// need low-level access (e.g. response headers).
// ---------------------------------------------------------------------------

/**
 * Build a structured error object from an axios error.
 * @param {number} status   HTTP status (0 for network errors)
 * @param {string} message  User-facing message
 * @param {object} opts     Additional fields (retryable, code, detail, _axiosError)
 * @returns {Error}         Error instance with structured fields
 */
function _buildApiError(status, message, opts = {}) {
  const err = new Error(message);
  err.error = true;
  err.status = status;
  err.message = message;
  err.retryable = opts.retryable ?? false;
  err.code = opts.code || null;
  err.detail = opts.detail || null;
  if (opts._axiosError) {
    err._axiosError = opts._axiosError;
    // Preserve response for callers that inspect error.response
    err.response = opts._axiosError.response;
    err.config = opts._axiosError.config;
  }
  return err;
}

// ---------------------------------------------------------------------------
// 429 retry with exponential backoff
// ---------------------------------------------------------------------------
const _429_MAX_RETRIES = 3;
const _429_BASE_DELAY_MS = 1000; // 1s, 2s, 4s

async function _retryWith429Backoff(config) {
  const attempt = (config._429RetryCount || 0);
  if (attempt >= _429_MAX_RETRIES) return null; // Give up

  config._429RetryCount = attempt + 1;
  const delay = _429_BASE_DELAY_MS * Math.pow(2, attempt);
  // Add jitter (0-25% of delay) to avoid thundering herd
  const jitter = Math.random() * delay * 0.25;
  console.warn(`[API] 429 — retry ${config._429RetryCount}/${_429_MAX_RETRIES} in ${Math.round(delay + jitter)}ms`);

  await new Promise((resolve) => setTimeout(resolve, delay + jitter));
  return api.request(config);
}

// ---------------------------------------------------------------------------
// 503 retry with exponential backoff
// 503 = Service Unavailable — transient (e.g., DB connection pool exhausted).
// Backend messages are intentionally user-friendly, so we preserve them.
// ---------------------------------------------------------------------------
const _503_MAX_RETRIES = 2;
const _503_BASE_DELAY_MS = 2000; // 2s, 4s

async function _retry503(config) {
  const attempt = (config._503RetryCount || 0);
  if (attempt >= _503_MAX_RETRIES) return null;

  config._503RetryCount = attempt + 1;
  const delay = _503_BASE_DELAY_MS * Math.pow(2, attempt);
  const jitter = Math.random() * delay * 0.25;
  console.warn(`[API] 503 — retry ${config._503RetryCount}/${_503_MAX_RETRIES} in ${Math.round(delay + jitter)}ms`);

  await new Promise((resolve) => setTimeout(resolve, delay + jitter));
  return api.request(config);
}

// ---------------------------------------------------------------------------
// 401 token refresh — attempt to refresh the access token once before
// clearing auth state and redirecting to login.
// Uses a single in-flight promise so concurrent 401s don't stampede.
// ---------------------------------------------------------------------------
let _refreshPromise = null;

export async function attemptTokenRefresh() {
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async () => {
    try {
      const refreshToken = getRefreshToken();
      if (!refreshToken) return false;

      const response = await fetch(`${API_BASE_URL}/api/v1/account/renew`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.access_token) {
          setTokens({
            access_token: data.access_token,
            ...(data.refresh_token ? { refresh_token: data.refresh_token } : {}),
          }).catch(() => {});
          console.log('[API] Token refresh succeeded');
          return true;
        }
      }
      return false;
    } catch (err) {
      console.error('[API] Token refresh failed:', err);
      return false;
    }
  })();

  try {
    return await _refreshPromise;
  } finally {
    _refreshPromise = null;
  }
}

// Handle response errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    // --- Timeout handling ---
    if (error.code === 'ECONNABORTED' || error.code === 'ERR_CANCELED') {
      const msg = error.code === 'ECONNABORTED'
        ? 'Request timed out. Please check your connection and try again.'
        : 'Request was cancelled.';
      return Promise.reject(_buildApiError(0, msg, {
        retryable: error.code === 'ECONNABORTED',
        code: error.code,
        _axiosError: error,
      }));
    }

    // --- Offline-aware error handling ---
    // When there's no response (network error) and the browser reports offline,
    // return cached data for GETs or a clear offline error for mutations.
    if (!error.response && !navigator.onLine) {
      const method = (error.config?.method || 'get').toLowerCase();
      const url = error.config?.url;

      if (method === 'get' && url) {
        const cached = _cacheGet(url);
        if (cached) {
          console.info('[API] Offline — returning cached response for:', url.split('?')[0]);
          return {
            data: cached,
            status: 200,
            statusText: 'OK (offline cache)',
            headers: {},
            config: error.config,
            _fromOfflineCache: true,
          };
        }
      }

      // For mutations or uncached GETs, reject with a structured offline error
      return Promise.reject(_buildApiError(0, "You're offline. This action will be available when you reconnect.", {
        retryable: true,
        code: 'ERR_OFFLINE',
        _axiosError: error,
      }));
    }

    // --- Network error (online but no response — server unreachable, DNS, etc.) ---
    if (!error.response) {
      console.error('[API] Network error (no response):', {
        message: error.message,
        code: error.code,
        method: error.config?.method,
        // OBS-001: Don't log full URL — may contain PII in query params
        path: error.config?.url?.split('?')[0],
        status: 'no_response'
      });

      return Promise.reject(_buildApiError(0, 'Network error. Please check your connection and try again.', {
        retryable: true,
        code: error.code || 'ERR_NETWORK',
        _axiosError: error,
      }));
    }

    // --- Retry once on CSRF token failure (token may have expired) ---
    if (
      error.response?.status === 403 &&
      error.response?.data?.code === 'CSRF_VALIDATION_FAILED' &&
      !error.config._csrfRetry
    ) {
      csrfTokenPromise = null;
      const newToken = await fetchCSRFToken();
      if (newToken) {
        error.config._csrfRetry = true;
        error.config.headers['X-CSRF-Token'] = newToken;
        return api.request(error.config);
      }
    }

    // --- 429 Too Many Requests — retry with exponential backoff ---
    if (error.response?.status === 429) {
      // DON'T retry auth endpoints — retries make rate limits worse
      const requestUrl = error.config?.url || '';
      const isAuthEndpoint = requestUrl.includes('/account/start') ||
                              requestUrl.includes('/account/renew') ||
                              requestUrl.includes('/auth/login') ||
                              requestUrl.includes('/account/recover');
      if (isAuthEndpoint) {
        return Promise.reject(_buildApiError(429,
          error.response?.data?.detail || 'Too many login attempts. Please wait a minute and try again.', {
          retryable: false,
          code: 'ERR_RATE_LIMITED',
          _axiosError: error,
        }));
      }

      // Respect Retry-After header if present
      const retryAfter = error.response.headers?.['retry-after'];
      if (retryAfter && !error.config._429RetryCount) {
        const delaySec = parseInt(retryAfter, 10);
        if (!isNaN(delaySec) && delaySec > 0 && delaySec <= 120) {
          error.config._429RetryCount = 0;
          await new Promise((resolve) => setTimeout(resolve, delaySec * 1000));
          error.config._429RetryCount = 1;
          return api.request(error.config);
        }
      }

      const retryResult = await _retryWith429Backoff(error.config);
      if (retryResult) return retryResult;

      // All retries exhausted
      return Promise.reject(_buildApiError(429, 'Too many requests. Please wait a moment and try again.', {
        retryable: true,
        code: 'ERR_RATE_LIMITED',
        _axiosError: error,
      }));
    }

    // --- 401 Unauthorized — attempt token refresh before logout ---
    if (error.response?.status === 401) {
      const isLoginPage = window.location.pathname === '/login';
      const isRefreshRequest = error.config?.url?.includes('/account/renew');

      // Don't logout for third-party integration token errors
      const requestUrl = error.config?.url || '';
      const isIntegrationEndpoint =
        requestUrl.includes('/salesforce/') ||
        requestUrl.includes('/hubspot/') ||
        requestUrl.includes('/google-calendar/') ||
        requestUrl.includes('/microsoft/') ||
        requestUrl.includes('/zoom/') ||
        requestUrl.includes('/docusign/') ||
        requestUrl.includes('/calendly/');

      if (!isLoginPage && !isIntegrationEndpoint && !isRefreshRequest && !error.config._authRetry) {
        // Attempt silent token refresh before giving up
        const refreshed = await attemptTokenRefresh();

        if (refreshed) {
          // Retry the original request with the new token
          const newToken = getToken();
          error.config._authRetry = true;
          error.config.headers.Authorization = `Bearer ${newToken}`;
          return api.request(error.config);
        }

        // Refresh failed — clear auth from ALL storage locations and redirect
        clearTokens().catch(() => {});
        window.location.href = '/login';
      }

      const detail401 = error.response?.data?.detail || error.response?.data?.error || 'Session expired. Please log in again.';
      return Promise.reject(_buildApiError(401, detail401, {
        retryable: false,
        code: 'ERR_UNAUTHORIZED',
        _axiosError: error,
      }));
    }

    // --- Sanitize error messages ---
    // For 500-level errors, replace the detail with a generic message.
    // For client errors (4xx), keep user-friendly messages from the backend.
    const SAFE_ERROR_MESSAGES = {
      400: "Invalid request. Please check your input.",
      403: "You don't have permission for this action.",
      404: "The requested resource was not found.",
      409: "A conflict occurred. Please refresh and try again.",
      422: "Invalid data submitted.",
    };

    const status = error.response.status;
    let message;

    // --- 503 Service Unavailable — transient, retryable. Backend detail is safe to show. ---
    if (status === 503) {
      const retryResult = await _retry503(error.config);
      if (retryResult) return retryResult;

      // All retries exhausted — preserve the backend's user-friendly message
      message = error.response.data?.detail || "Service temporarily unavailable. Please try again in a moment.";
      error.response.data = { ...error.response.data, detail: message };

      return Promise.reject(_buildApiError(503, message, {
        retryable: true,
        code: 'ERR_SERVICE_UNAVAILABLE',
        detail: message,
        _axiosError: error,
      }));
    }

    // --- 502/504 Gateway errors — transient, generic message (upstream may leak internals) ---
    if (status === 502 || status === 504) {
      message = "Server is temporarily unavailable. Please try again in a moment.";
      error.response.data = { ...error.response.data, detail: message };

      return Promise.reject(_buildApiError(status, message, {
        retryable: true,
        code: `ERR_HTTP_${status}`,
        detail: message,
        _axiosError: error,
      }));
    }

    if (status >= 500) {
      // 500 and other 5xx — sanitize (may contain implementation details)
      message = "An unexpected error occurred. Please try again later.";
      error.response.data = {
        ...error.response.data,
        detail: message,
      };
    } else {
      message = error.response.data?.detail || SAFE_ERROR_MESSAGES[status] || 'An error occurred.';
      if (!error.response.data?.detail && SAFE_ERROR_MESSAGES[status]) {
        error.response.data = {
          ...error.response.data,
          detail: SAFE_ERROR_MESSAGES[status],
        };
      }
    }

    // --- 403 Permission error (non-CSRF) ---
    if (status === 403) {
      return Promise.reject(_buildApiError(403, message, {
        retryable: false,
        code: 'ERR_FORBIDDEN',
        detail: error.response.data?.detail,
        _axiosError: error,
      }));
    }

    // --- All other errors — structured response ---
    const retryable = status >= 500 || status === 408;
    return Promise.reject(_buildApiError(status, message, {
      retryable,
      code: `ERR_HTTP_${status}`,
      detail: error.response.data?.detail,
      _axiosError: error,
    }));
  }
);

// Certificate pinning interceptors (native only — no-op on web)
import certificatePinning from '../certificatePinning.js';
const pinRequestInterceptor = certificatePinning.createAxiosInterceptor();
api.interceptors.request.use(pinRequestInterceptor);
const pinResponseInterceptor = certificatePinning.createAxiosResponseInterceptor();
api.interceptors.response.use(pinResponseInterceptor.onFulfilled, pinResponseInterceptor.onRejected);

// ---------------------------------------------------------------------------
// Per-request timeout — callers can pass { timeout: 60000 } in the axios
// config to override the default 30s.  This helper makes it explicit:
//
//   import { apiRequest } from './client.js';
//   const data = await apiRequest('/api/v1/slow-endpoint', { timeout: 120000 });
//
// It also wraps the response in a consistent shape and catches structured errors.
// ---------------------------------------------------------------------------

/**
 * Make an API request with an optional per-request timeout override.
 *
 * @param {string} url       The URL path (relative to API_BASE_URL)
 * @param {object} [options] Axios config overrides (method, data, params, timeout, etc.)
 * @returns {Promise<any>}   The response data
 */
export async function apiRequest(url, options = {}) {
  const { timeout, ...rest } = options;
  const config = { ...rest, url };
  if (timeout) config.timeout = timeout;
  const response = await api.request(config);
  return response.data;
}

/**
 * Check if the browser is currently offline.
 * Use this to guard UI actions before attempting API calls.
 */
export function isOffline() {
  return !navigator.onLine;
}

/**
 * Type guard to check if an error is a structured API error.
 */
export function isApiError(err) {
  return err && err.error === true && typeof err.status === 'number';
}

// Re-export ensureArray for domain modules that need it
export { ensureArray };

// Re-export bare axios for public endpoints that bypass interceptors
export { axios };

export default api;
