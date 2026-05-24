/**
 * Auth flow tests.
 *
 * Tests cover: token storage/retrieval, token expiration detection,
 * login flow, logout flow, session timeout, getCurrentUserId.
 */
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock Capacitor — always web platform for these tests
// ---------------------------------------------------------------------------
vi.mock('@capacitor/core', () => ({
  Capacitor: {
    isNativePlatform: () => false,
  },
}));

vi.mock('@capacitor/preferences', () => ({
  Preferences: {
    get: vi.fn().mockResolvedValue({ value: null }),
    set: vi.fn().mockResolvedValue(undefined),
    remove: vi.fn().mockResolvedValue(undefined),
    clear: vi.fn().mockResolvedValue(undefined),
    keys: vi.fn().mockResolvedValue({ keys: [] }),
  },
}));

// ---------------------------------------------------------------------------
// Setup & import
// ---------------------------------------------------------------------------

let tokenStore;
let auth;
let storage;

beforeAll(async () => {
  tokenStore = await import('../utils/tokenStore');
  auth = await import('../utils/auth');
  storage = await import('../utils/storage');
});

beforeEach(async () => {
  vi.clearAllMocks();
  // Clear localStorage AND the in-memory cache in tokenStore
  localStorage.clear();
  // tokenStore uses an in-memory _cache that persists between tests.
  // clearTokens() resets both the cache and localStorage.
  if (tokenStore) {
    await tokenStore.clearTokens();
  }
});

afterEach(async () => {
  localStorage.clear();
  if (tokenStore) {
    await tokenStore.clearTokens();
  }
});

// ===========================================================================
// Tests
// ===========================================================================

describe('TokenStore', () => {
  // -----------------------------------------------------------------------
  // Token storage and retrieval
  // -----------------------------------------------------------------------
  describe('Token storage and retrieval', () => {
    it('getToken returns null when no token is stored', () => {
      const token = tokenStore.getToken();
      expect(token).toBeNull();
    });

    it('setTokens stores access token and getToken retrieves it', async () => {
      await tokenStore.setTokens({ access_token: 'abc123' });
      const token = tokenStore.getToken();
      expect(token).toBe('abc123');
    });

    it('getToken falls back to localStorage when cache is empty', () => {
      // Directly set in localStorage (simulating pre-migration state)
      localStorage.setItem('token', 'ls-token-value');
      // tokenStore cache is empty, should fall back
      const token = tokenStore.getToken();
      expect(token).toBe('ls-token-value');
    });

    it('setTokens stores refresh token and getRefreshToken retrieves it', async () => {
      await tokenStore.setTokens({ refresh_token: 'refresh-abc' });
      const refreshToken = tokenStore.getRefreshToken();
      expect(refreshToken).toBe('refresh-abc');
    });

    it('getRefreshToken falls back to localStorage', () => {
      localStorage.setItem('refresh_token', 'ls-refresh');
      const token = tokenStore.getRefreshToken();
      expect(token).toBe('ls-refresh');
    });

    it('setTokens stores user data and getUserData retrieves it', async () => {
      const userData = { id: 42, email: 'lo@test.com', full_name: 'Test LO' };
      await tokenStore.setTokens({ user_data: userData });
      const result = tokenStore.getUserData();
      expect(result).toEqual(userData);
    });

    it('getUserData falls back to localStorage', () => {
      const userData = { id: 99, email: 'fallback@test.com' };
      localStorage.setItem('user', JSON.stringify(userData));
      const result = tokenStore.getUserData();
      expect(result).toEqual(userData);
    });

    it('getUserData returns null for invalid JSON in localStorage', () => {
      localStorage.setItem('user', '{broken json');
      const result = tokenStore.getUserData();
      expect(result).toBeNull();
    });
  });

  // -----------------------------------------------------------------------
  // isAuthenticated
  // -----------------------------------------------------------------------
  describe('isAuthenticated', () => {
    it('returns false when no token is stored', () => {
      expect(tokenStore.isAuthenticated()).toBe(false);
    });

    it('returns true when a token exists', async () => {
      await tokenStore.setTokens({ access_token: 'valid-token' });
      expect(tokenStore.isAuthenticated()).toBe(true);
    });
  });

  // -----------------------------------------------------------------------
  // clearTokens
  // -----------------------------------------------------------------------
  describe('clearTokens', () => {
    it('clears all tokens from cache and localStorage', async () => {
      await tokenStore.setTokens({
        access_token: 'tok',
        refresh_token: 'ref',
        user_data: { id: 1 },
      });

      await tokenStore.clearTokens();

      expect(tokenStore.getToken()).toBeNull();
      expect(tokenStore.getRefreshToken()).toBeNull();
      expect(tokenStore.getUserData()).toBeNull();
      expect(localStorage.getItem('token')).toBeNull();
      expect(localStorage.getItem('refresh_token')).toBeNull();
      expect(localStorage.getItem('user')).toBeNull();
    });
  });
});

describe('Auth utilities', () => {
  // -----------------------------------------------------------------------
  // setAuth / getAuth
  // -----------------------------------------------------------------------
  describe('Login flow (setAuth)', () => {
    it('stores token and user data on login', async () => {
      const user = { id: 1, email: 'lo@test.com', full_name: 'Loan Officer' };
      await auth.setAuth('my-token', user, 'my-refresh');

      // Should be in storage
      const storedToken = await storage.getItem(storage.STORAGE_KEYS.TOKEN);
      expect(storedToken).toBe('my-token');

      const storedUser = await storage.getJSON(storage.STORAGE_KEYS.USER);
      expect(storedUser).toEqual(user);
    });

    it('dispatches authChange event with type "login" on setAuth', async () => {
      const handler = vi.fn();
      window.addEventListener('authChange', handler);

      const user = { id: 2, email: 'admin@test.com' };
      await auth.setAuth('tok', user);

      expect(handler).toHaveBeenCalledTimes(1);
      const detail = handler.mock.calls[0][0].detail;
      expect(detail.type).toBe('login');
      expect(detail.user).toEqual(user);

      window.removeEventListener('authChange', handler);
    });
  });

  describe('Logout flow (clearAuth)', () => {
    it('clears all auth data on logout', async () => {
      // First set auth
      await auth.setAuth('tok', { id: 1 }, 'ref');

      // Then clear
      await auth.clearAuth();

      const state = await auth.getAuth();
      expect(state.token).toBeNull();
      expect(state.user).toBeNull();
    });

    it('dispatches authChange event with type "logout" on clearAuth', async () => {
      const handler = vi.fn();
      window.addEventListener('authChange', handler);

      await auth.clearAuth();

      expect(handler).toHaveBeenCalledTimes(1);
      const detail = handler.mock.calls[0][0].detail;
      expect(detail.type).toBe('logout');

      window.removeEventListener('authChange', handler);
    });
  });

  // -----------------------------------------------------------------------
  // getCurrentUser / getCurrentUserId
  // -----------------------------------------------------------------------
  describe('getCurrentUser', () => {
    it('returns user object from localStorage', () => {
      const user = { id: 42, user_id: 42, email: 'lo@test.com', full_name: 'Test LO' };
      localStorage.setItem('user', JSON.stringify(user));

      const result = auth.getCurrentUser();
      expect(result).toEqual(user);
    });

    it('returns null when no user in localStorage', () => {
      expect(auth.getCurrentUser()).toBeNull();
    });

    it('returns null for corrupted user data', () => {
      localStorage.setItem('user', 'not-json');
      expect(auth.getCurrentUser()).toBeNull();
    });
  });

  describe('getCurrentUserId', () => {
    it('returns id from user object', () => {
      localStorage.setItem('user', JSON.stringify({ id: 7, email: 'x@x.com' }));
      expect(auth.getCurrentUserId()).toBe(7);
    });

    it('falls back to user_id when id is missing', () => {
      localStorage.setItem('user', JSON.stringify({ user_id: 99, email: 'x@x.com' }));
      expect(auth.getCurrentUserId()).toBe(99);
    });

    it('returns null when no user is stored', () => {
      expect(auth.getCurrentUserId()).toBeNull();
    });
  });

  // -----------------------------------------------------------------------
  // Sync helpers
  // -----------------------------------------------------------------------
  describe('Synchronous auth helpers', () => {
    it('isAuthenticatedSync returns true when token exists', () => {
      localStorage.setItem('token', 'tok');
      expect(auth.isAuthenticatedSync()).toBe(true);
    });

    it('isAuthenticatedSync returns false when no token', () => {
      expect(auth.isAuthenticatedSync()).toBe(false);
    });

    it('getAuthSync returns token and parsed user', () => {
      localStorage.setItem('token', 'my-tok');
      localStorage.setItem('user', JSON.stringify({ id: 5 }));
      const state = auth.getAuthSync();
      expect(state.token).toBe('my-tok');
      expect(state.user).toEqual({ id: 5 });
    });
  });

  // -----------------------------------------------------------------------
  // getAuthHeaders
  // -----------------------------------------------------------------------
  describe('getAuthHeaders', () => {
    it('returns Bearer Authorization header', () => {
      localStorage.setItem('token', 'hdr-token');
      const headers = auth.getAuthHeaders();
      expect(headers.Authorization).toBe('Bearer hdr-token');
      expect(headers['Content-Type']).toBe('application/json');
    });

    it('getAuthHeadersIfPresent omits Authorization when no token', () => {
      const headers = auth.getAuthHeadersIfPresent();
      expect(headers.Authorization).toBeUndefined();
      expect(headers['Content-Type']).toBe('application/json');
    });
  });

  // -----------------------------------------------------------------------
  // Session timeout
  // -----------------------------------------------------------------------
  describe('Session timeout detection', () => {
    it('detects expired session when token is cleared', async () => {
      // Set up an active session
      await auth.setAuth('active-token', { id: 1 });
      expect(auth.isAuthenticatedSync()).toBe(true);

      // Simulate session timeout (clearAuth called by API interceptor)
      await auth.clearAuth();
      expect(auth.isAuthenticatedSync()).toBe(false);
    });
  });
});
