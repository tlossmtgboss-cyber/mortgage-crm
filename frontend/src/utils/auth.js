import { getItem, setItem, removeItem, getJSON, setJSON, STORAGE_KEYS, clearAllAuthTokens, migrateTokensToSecureStorage } from './storage';

export const setAuth = async (token, user, refreshToken) => {
  await setItem(STORAGE_KEYS.TOKEN, token);
  if (refreshToken) {
    await setItem(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
  }
  await setJSON(STORAGE_KEYS.USER, user);
  // Dispatch custom event to notify contexts of auth change
  window.dispatchEvent(new CustomEvent('authChange', { detail: { type: 'login', user } }));
};

export const getAuth = async () => {
  const token = await getItem(STORAGE_KEYS.TOKEN);
  const user = await getJSON(STORAGE_KEYS.USER);
  return { token, user };
};

export const clearAuth = async () => {
  // Clear from ALL storage locations (Preferences + localStorage) to prevent
  // stale tokens surviving in one store after logout.
  await clearAllAuthTokens();
  // Dispatch custom event to notify contexts of auth change
  window.dispatchEvent(new CustomEvent('authChange', { detail: { type: 'logout' } }));
};

/**
 * Migrate any localStorage-only auth tokens to Capacitor Preferences.
 * Call once on app startup (before auth checks) to ensure the secure store
 * is authoritative on native platforms. No-op on web.
 */
export const migrateAuthTokens = migrateTokensToSecureStorage;

export const isAuthenticated = async () => {
  const token = await getItem(STORAGE_KEYS.TOKEN);
  return !!token;
};

// Synchronous versions for backwards compatibility (web only)
// These use localStorage directly and should only be used where async isn't possible
export const getAuthSync = () => {
  const token = localStorage.getItem(STORAGE_KEYS.TOKEN);
  const userStr = localStorage.getItem(STORAGE_KEYS.USER);
  const user = userStr ? JSON.parse(userStr) : null;
  return { token, user };
};

export const isAuthenticatedSync = () => {
  return !!localStorage.getItem(STORAGE_KEYS.TOKEN);
};

/**
 * Get authorization headers for API requests
 * Returns headers object with Bearer token and Content-Type
 * @returns {Object} Headers object with Authorization and Content-Type
 */
export const getAuthHeaders = () => {
  const token = localStorage.getItem(STORAGE_KEYS.TOKEN);
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
};

/**
 * Get authorization headers only if token exists
 * Returns headers with auth if logged in, just content-type if not
 * @returns {Object} Headers object
 */
/**
 * Get the current user from localStorage (set at login).
 * Returns { user_id, email, full_name, organization_id, ... } or null.
 * Avoids insecure client-side JWT decoding via atob().
 */
export const getCurrentUser = () => {
  const userStr = localStorage.getItem(STORAGE_KEYS.USER);
  if (userStr) {
    try {
      return JSON.parse(userStr);
    } catch {
      return null;
    }
  }
  return null;
};

/**
 * Get the current user ID from localStorage.
 * Returns the user_id number, or null if not logged in.
 */
export const getCurrentUserId = () => {
  const user = getCurrentUser();
  return user?.id || user?.user_id || null;
};

export const getAuthHeadersIfPresent = () => {
  const token = localStorage.getItem(STORAGE_KEYS.TOKEN);
  if (token) {
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }
  return {
    'Content-Type': 'application/json'
  };
};
