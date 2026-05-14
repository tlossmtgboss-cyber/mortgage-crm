/**
 * Token refresh and CSRF management.
 */
import { getCSRFTokenFromCookie } from '../../utils/security.js';
import { getToken, getRefreshToken, setTokens, clearTokens } from '../../utils/tokenStore.js';
import { API_BASE_URL } from './client';

// ---------------------------------------------------------------------------
// CSRF token management
// ---------------------------------------------------------------------------

/** CSRF token cache -- fetched once, reused for all requests */
let csrfTokenPromise: Promise<string | null> | null = null;

export const fetchCSRFToken = async (): Promise<string | null> => {
  // Try cookie first (set by backend on GET responses)
  const cookieToken = getCSRFTokenFromCookie();
  if (cookieToken) return cookieToken;

  // Fetch from server if no cookie
  try {
    const { default: axios } = await import('axios');
    const response = await axios.get(`${API_BASE_URL}/api/v1/csrf-token`, {
      withCredentials: true,
    });
    return response.data?.csrf_token || null;
  } catch (error) {
    console.warn('Could not fetch CSRF token:', error);
    return null;
  }
};

export const getCSRFToken = (): Promise<string | null> => {
  // Check cookie synchronously first (fast path)
  const cookieToken = getCSRFTokenFromCookie();
  if (cookieToken) return Promise.resolve(cookieToken);

  // Fetch from server (deduplicated -- only one in-flight request)
  if (!csrfTokenPromise) {
    csrfTokenPromise = fetchCSRFToken().finally(() => {
      // Allow re-fetch after 5 minutes
      setTimeout(() => { csrfTokenPromise = null; }, 5 * 60 * 1000);
    });
  }
  return csrfTokenPromise;
};

export function resetCSRFTokenCache(): void {
  csrfTokenPromise = null;
}

export const CSRF_METHODS = ['post', 'put', 'patch', 'delete'];

// ---------------------------------------------------------------------------
// 401 token refresh -- attempt to refresh the access token once before
// clearing auth state and redirecting to login.
// Uses a single in-flight promise so concurrent 401s don't stampede.
// ---------------------------------------------------------------------------
let _refreshPromise: Promise<boolean> | null = null;

export async function attemptTokenRefresh(): Promise<boolean> {
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
