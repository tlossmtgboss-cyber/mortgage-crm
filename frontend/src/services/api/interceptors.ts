/**
 * Request/response interceptors: auth headers, CSRF, offline cache,
 * retry logic (429, 503), 401 token refresh, error normalization.
 */
import type { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios';
import { getToken, clearTokens } from '../../utils/tokenStore';
import { getItem, STORAGE_KEYS } from '../../utils/storage';
import { getCSRFToken, fetchCSRFToken, resetCSRFTokenCache, CSRF_METHODS, attemptTokenRefresh } from './auth';
import { cacheSet, cacheGet, dispatchMutationDebounced } from './offline';
import { buildApiError, SAFE_ERROR_MESSAGES } from './errors';

// ---------------------------------------------------------------------------
// 429 retry with exponential backoff
// ---------------------------------------------------------------------------
const _429_MAX_RETRIES = 3;
const _429_BASE_DELAY_MS = 1000; // 1s, 2s, 4s

async function _retryWith429Backoff(api: AxiosInstance, config: any): Promise<any | null> {
  const attempt = (config._429RetryCount || 0);
  if (attempt >= _429_MAX_RETRIES) return null; // Give up

  config._429RetryCount = attempt + 1;
  const delay = _429_BASE_DELAY_MS * Math.pow(2, attempt);
  // Add jitter (0-25% of delay) to avoid thundering herd
  const jitter = Math.random() * delay * 0.25;
  console.warn(`[API] 429 -- retry ${config._429RetryCount}/${_429_MAX_RETRIES} in ${Math.round(delay + jitter)}ms`);

  await new Promise((resolve) => setTimeout(resolve, delay + jitter));
  return api.request(config);
}

// ---------------------------------------------------------------------------
// 503 retry with exponential backoff
// 503 = Service Unavailable -- transient (e.g., DB connection pool exhausted).
// Backend messages are intentionally user-friendly, so we preserve them.
// ---------------------------------------------------------------------------
const _503_MAX_RETRIES = 2;
const _503_BASE_DELAY_MS = 2000; // 2s, 4s

async function _retry503(api: AxiosInstance, config: any): Promise<any | null> {
  const attempt = (config._503RetryCount || 0);
  if (attempt >= _503_MAX_RETRIES) return null;

  config._503RetryCount = attempt + 1;
  const delay = _503_BASE_DELAY_MS * Math.pow(2, attempt);
  const jitter = Math.random() * delay * 0.25;
  console.warn(`[API] 503 -- retry ${config._503RetryCount}/${_503_MAX_RETRIES} in ${Math.round(delay + jitter)}ms`);

  await new Promise((resolve) => setTimeout(resolve, delay + jitter));
  return api.request(config);
}

/**
 * Attach all interceptors to the given axios instance.
 */
export function attachInterceptors(api: AxiosInstance): void {
  // ---------------------------------------------------------------------------
  // REQUEST: Add token, impersonation, and CSRF headers
  // ---------------------------------------------------------------------------
  api.interceptors.request.use(
    async (config: InternalAxiosRequestConfig) => {
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
      if (CSRF_METHODS.includes(config.method!)) {
        const csrfToken = await getCSRFToken();
        if (csrfToken) {
          config.headers['X-CSRF-Token'] = csrfToken;
        }
      }

      return config;
    },
    (error: any) => {
      return Promise.reject(error);
    }
  );

  // ---------------------------------------------------------------------------
  // RESPONSE: Cache successful GETs and dispatch mutation events
  // ---------------------------------------------------------------------------
  api.interceptors.response.use(
    (response: AxiosResponse) => {
      const method = (response.config?.method || 'get').toLowerCase();
      if (method === 'get' && response.config?.url) {
        cacheSet(response.config.url, response.data);
      }
      if (['post', 'put', 'patch', 'delete'].includes(method)) {
        dispatchMutationDebounced();
      }
      return response;
    },
    (error: any) => Promise.reject(error)
  );

  // ---------------------------------------------------------------------------
  // RESPONSE ERROR: Retry, refresh, offline, error normalization
  // ---------------------------------------------------------------------------
  api.interceptors.response.use(
    (response: AxiosResponse) => response,
    async (error: any) => {
      // --- Timeout handling ---
      if (error.code === 'ECONNABORTED' || error.code === 'ERR_CANCELED') {
        const msg = error.code === 'ECONNABORTED'
          ? 'Request timed out. Please check your connection and try again.'
          : 'Request was cancelled.';
        return Promise.reject(buildApiError(0, msg, {
          retryable: error.code === 'ECONNABORTED',
          code: error.code,
          _axiosError: error,
        }));
      }

      // --- Offline-aware error handling ---
      if (!error.response && !navigator.onLine) {
        const method = (error.config?.method || 'get').toLowerCase();
        const url = error.config?.url;

        if (method === 'get' && url) {
          const cached = cacheGet(url);
          if (cached) {
            console.info('[API] Offline -- returning cached response for:', url.split('?')[0]);
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
        return Promise.reject(buildApiError(0, "You're offline. This action will be available when you reconnect.", {
          retryable: true,
          code: 'ERR_OFFLINE',
          _axiosError: error,
        }));
      }

      // --- Network error (online but no response -- server unreachable, DNS, etc.) ---
      if (!error.response) {
        console.error('[API] Network error (no response):', {
          message: error.message,
          code: error.code,
          method: error.config?.method,
          // OBS-001: Don't log full URL -- may contain PII in query params
          path: error.config?.url?.split('?')[0],
          status: 'no_response'
        });

        return Promise.reject(buildApiError(0, 'Network error. Please check your connection and try again.', {
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
        resetCSRFTokenCache();
        const newToken = await fetchCSRFToken();
        if (newToken) {
          error.config._csrfRetry = true;
          error.config.headers['X-CSRF-Token'] = newToken;
          return api.request(error.config);
        }
      }

      // --- 429 Too Many Requests -- retry with exponential backoff ---
      if (error.response?.status === 429) {
        // DON'T retry auth endpoints -- retries make rate limits worse
        const requestUrl = error.config?.url || '';
        const isAuthEndpoint = requestUrl.includes('/account/start') ||
                                requestUrl.includes('/account/renew') ||
                                requestUrl.includes('/auth/login') ||
                                requestUrl.includes('/account/recover');
        if (isAuthEndpoint) {
          return Promise.reject(buildApiError(429,
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

        const retryResult = await _retryWith429Backoff(api, error.config);
        if (retryResult) return retryResult;

        // All retries exhausted
        return Promise.reject(buildApiError(429, 'Too many requests. Please wait a moment and try again.', {
          retryable: true,
          code: 'ERR_RATE_LIMITED',
          _axiosError: error,
        }));
      }

      // --- 401 Unauthorized -- attempt token refresh before logout ---
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

          // Refresh failed -- clear auth from ALL storage locations and redirect
          clearTokens().catch(() => {});
          window.location.href = '/login';
        }

        const detail401 = error.response?.data?.detail || error.response?.data?.error || 'Session expired. Please log in again.';
        return Promise.reject(buildApiError(401, detail401, {
          retryable: false,
          code: 'ERR_UNAUTHORIZED',
          _axiosError: error,
        }));
      }

      // --- Sanitize error messages ---
      const status = error.response.status;
      let message: string;

      // --- 503 Service Unavailable -- transient, retryable ---
      if (status === 503) {
        const retryResult = await _retry503(api, error.config);
        if (retryResult) return retryResult;

        message = error.response.data?.detail || "Service temporarily unavailable. Please try again in a moment.";
        error.response.data = { ...error.response.data, detail: message };

        return Promise.reject(buildApiError(503, message, {
          retryable: true,
          code: 'ERR_SERVICE_UNAVAILABLE',
          detail: message,
          _axiosError: error,
        }));
      }

      // --- 502/504 Gateway errors -- transient, generic message ---
      if (status === 502 || status === 504) {
        message = "Server is temporarily unavailable. Please try again in a moment.";
        error.response.data = { ...error.response.data, detail: message };

        return Promise.reject(buildApiError(status, message, {
          retryable: true,
          code: `ERR_HTTP_${status}`,
          detail: message,
          _axiosError: error,
        }));
      }

      if (status >= 500) {
        // 500 and other 5xx -- sanitize (may contain implementation details)
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
        return Promise.reject(buildApiError(403, message, {
          retryable: false,
          code: 'ERR_FORBIDDEN',
          detail: error.response.data?.detail,
          _axiosError: error,
        }));
      }

      // --- All other errors -- structured response ---
      const retryable = status >= 500 || status === 408;
      return Promise.reject(buildApiError(status, message, {
        retryable,
        code: `ERR_HTTP_${status}`,
        detail: error.response.data?.detail,
        _axiosError: error,
      }));
    }
  );

  // ---------------------------------------------------------------------------
  // Certificate pinning interceptors (native only -- no-op on web)
  // ---------------------------------------------------------------------------
  import('../../services/certificatePinning.js').then((mod) => {
    const certificatePinning = mod.default;
    const pinRequestInterceptor: any = certificatePinning.createAxiosInterceptor();
    api.interceptors.request.use(pinRequestInterceptor);
    const pinResponseInterceptor: any = certificatePinning.createAxiosResponseInterceptor();
    api.interceptors.response.use(pinResponseInterceptor.onFulfilled, pinResponseInterceptor.onRejected);
  }).catch(() => {
    // Certificate pinning module not available -- skip
  });
}
