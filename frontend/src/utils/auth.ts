import { getItem, setItem, removeItem, getJSON, setJSON, STORAGE_KEYS, clearAllAuthTokens, migrateTokensToSecureStorage } from './storage';
import { setTokens, type UserData } from './tokenStore';

export interface AuthState {
  token: string | null;
  user: UserData | null;
}

export interface AuthHeaders {
  Authorization: string;
  'Content-Type': string;
}

export interface ContentTypeHeaders {
  'Content-Type': string;
}

export type AuthHeadersIfPresent = AuthHeaders | ContentTypeHeaders;

interface AuthChangeLoginDetail {
  type: 'login';
  user: UserData;
}

interface AuthChangeLogoutDetail {
  type: 'logout';
}

type AuthChangeDetail = AuthChangeLoginDetail | AuthChangeLogoutDetail;

export const setAuth = async (
  token: string,
  user: UserData,
  refreshToken?: string
): Promise<void> => {
  await setItem(STORAGE_KEYS.TOKEN, token);
  if (refreshToken) {
    await setItem(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
  }
  await setJSON(STORAGE_KEYS.USER, user);
  // Keep tokenStore in-memory cache in sync so getToken() returns the fresh
  // token immediately (otherwise the stale cached value wins over localStorage).
  await setTokens({
    access_token: token,
    ...(refreshToken ? { refresh_token: refreshToken } : {}),
    user_data: user,
  });
  // Dispatch custom event to notify contexts of auth change
  window.dispatchEvent(new CustomEvent<AuthChangeDetail>('authChange', { detail: { type: 'login', user } }));
};

export const getAuth = async (): Promise<AuthState> => {
  const token = await getItem(STORAGE_KEYS.TOKEN);
  const user = await getJSON<UserData>(STORAGE_KEYS.USER);
  return { token, user };
};

export const clearAuth = async (): Promise<void> => {
  // Clear from ALL storage locations (Preferences + localStorage) to prevent
  // stale tokens surviving in one store after logout.
  await clearAllAuthTokens();
  // Dispatch custom event to notify contexts of auth change
  window.dispatchEvent(new CustomEvent<AuthChangeDetail>('authChange', { detail: { type: 'logout' } }));
};

/**
 * Migrate any localStorage-only auth tokens to Capacitor Preferences.
 * Call once on app startup (before auth checks) to ensure the secure store
 * is authoritative on native platforms. No-op on web.
 */
export const migrateAuthTokens = migrateTokensToSecureStorage;

export const isAuthenticated = async (): Promise<boolean> => {
  const token = await getItem(STORAGE_KEYS.TOKEN);
  return !!token;
};

// Synchronous versions for backwards compatibility (web only)
// These use localStorage directly and should only be used where async isn't possible
export const getAuthSync = (): AuthState => {
  const token = localStorage.getItem(STORAGE_KEYS.TOKEN);
  const userStr = localStorage.getItem(STORAGE_KEYS.USER);
  const user = userStr ? (JSON.parse(userStr) as UserData) : null;
  return { token, user };
};

export const isAuthenticatedSync = (): boolean => {
  return !!localStorage.getItem(STORAGE_KEYS.TOKEN);
};

/**
 * Get authorization headers for API requests
 * Returns headers object with Bearer token and Content-Type
 */
export const getAuthHeaders = (): AuthHeaders => {
  const token = localStorage.getItem(STORAGE_KEYS.TOKEN);
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
};

/**
 * Get the current user from localStorage (set at login).
 * Returns { user_id, email, full_name, organization_id, ... } or null.
 * Avoids insecure client-side JWT decoding via atob().
 */
export const getCurrentUser = (): UserData | null => {
  const userStr = localStorage.getItem(STORAGE_KEYS.USER);
  if (userStr) {
    try {
      return JSON.parse(userStr) as UserData;
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
export const getCurrentUserId = (): number | string | null => {
  const user = getCurrentUser();
  return user?.id || user?.user_id || null;
};

export const getAuthHeadersIfPresent = (): AuthHeadersIfPresent => {
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
