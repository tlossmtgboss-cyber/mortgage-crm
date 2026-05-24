/**
 * Centralized API client tests.
 *
 * Tests cover: token injection, CSRF handling, 401 token refresh (single-flight),
 * 429 retry logic (auth endpoints skip retry), 503 retry, network errors,
 * offline cache, structured errors, and module export verification.
 */
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock dependencies BEFORE importing the API module
// ---------------------------------------------------------------------------

// Track what getToken / getRefreshToken return
let mockToken = 'test-access-token';
let mockRefreshToken = 'test-refresh-token';

vi.mock('../utils/tokenStore', () => ({
  getToken: () => mockToken,
  getRefreshToken: () => mockRefreshToken,
  setTokens: vi.fn().mockResolvedValue(undefined),
  clearTokens: vi.fn().mockResolvedValue(undefined),
  getUserData: () => null,
  initialize: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../utils/storage', () => ({
  getItem: vi.fn().mockResolvedValue(null),
  setItem: vi.fn().mockResolvedValue(undefined),
  removeItem: vi.fn().mockResolvedValue(undefined),
  clearAllAuthTokens: vi.fn().mockResolvedValue(undefined),
  STORAGE_KEYS: {
    TOKEN: 'token',
    REFRESH_TOKEN: 'refresh_token',
    USER: 'user',
    IMPERSONATION: 'impersonation',
    DASHBOARD_ORDER: 'dashboardOrder',
  },
}));

vi.mock('../utils/security', () => ({
  getCSRFTokenFromCookie: vi.fn().mockReturnValue('mock-csrf-token'),
}));

vi.mock('../utils/pinnedFetch', () => ({
  pinnedAdapter: undefined,
}));

vi.mock('../services/certificatePinning.js', () => ({
  default: {
    createAxiosInterceptor: () => (config) => config,
    createAxiosResponseInterceptor: () => ({
      onFulfilled: (r) => r,
      onRejected: (e) => Promise.reject(e),
    }),
  },
}));

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
  },
}));

vi.mock('../utils/arrayHelpers.js', () => ({
  ensureArray: (data, key) => {
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data[key])) return data[key];
    return [];
  },
}));

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------
let api, leadsAPI, loansAPI, authAPI, dashboardAPI, tasksAPI, aiAPI,
    portfolioAPI, calendarAPI, schedulerAPI, attemptTokenRefresh,
    API_BASE_URL, apiRequest, isApiError;

beforeAll(async () => {
  const mod = await import('../services/api');
  api = mod.default;
  leadsAPI = mod.leadsAPI;
  loansAPI = mod.loansAPI;
  authAPI = mod.authAPI;
  dashboardAPI = mod.dashboardAPI;
  tasksAPI = mod.tasksAPI;
  aiAPI = mod.aiAPI;
  portfolioAPI = mod.portfolioAPI;
  calendarAPI = mod.calendarAPI;
  schedulerAPI = mod.schedulerAPI;
  attemptTokenRefresh = mod.attemptTokenRefresh;
  API_BASE_URL = mod.API_BASE_URL;
  apiRequest = mod.apiRequest;
  isApiError = mod.isApiError;
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Use axios interceptors by making real requests through the instance.
// We intercept at the adapter level to avoid actual HTTP calls.
function installMockAdapter(handler) {
  // Replace the axios adapter with our mock
  api.defaults.adapter = async (config) => {
    const result = await handler(config);
    // Simulate axios response shape
    return {
      data: result.data ?? {},
      status: result.status ?? 200,
      statusText: result.statusText ?? 'OK',
      headers: result.headers ?? {},
      config,
    };
  };
}

function installMockAdapterWithError(handler) {
  api.defaults.adapter = async (config) => {
    const result = await handler(config);
    if (result.error) {
      const err = new Error('Request failed');
      err.response = {
        data: result.data ?? {},
        status: result.status ?? 500,
        statusText: result.statusText ?? 'Error',
        headers: result.headers ?? {},
      };
      err.config = config;
      err.code = result.code;
      throw err;
    }
    return {
      data: result.data ?? {},
      status: result.status ?? 200,
      statusText: result.statusText ?? 'OK',
      headers: result.headers ?? {},
      config,
    };
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockToken = 'test-access-token';
  mockRefreshToken = 'test-refresh-token';
  // Ensure we're "online"
  Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true });
});

afterEach(() => {
  // Reset adapter
  delete api.defaults.adapter;
});

// ===========================================================================
// Tests
// ===========================================================================

describe('API Client', () => {
  // -----------------------------------------------------------------------
  // Token injection
  // -----------------------------------------------------------------------
  describe('Token injection', () => {
    it('adds Authorization header with Bearer token from tokenStore', async () => {
      let capturedConfig;
      installMockAdapter((config) => {
        capturedConfig = config;
        return { data: { ok: true }, status: 200 };
      });

      await api.get('/api/v1/dashboard');
      expect(capturedConfig.headers.Authorization).toBe('Bearer test-access-token');
    });

    it('omits Authorization header when no token is present', async () => {
      mockToken = null;
      let capturedConfig;
      installMockAdapter((config) => {
        capturedConfig = config;
        return { data: { ok: true }, status: 200 };
      });

      await api.get('/api/v1/dashboard');
      expect(capturedConfig.headers.Authorization).toBeUndefined();
    });
  });

  // -----------------------------------------------------------------------
  // CSRF token handling
  // -----------------------------------------------------------------------
  describe('CSRF token handling', () => {
    it('injects X-CSRF-Token on POST requests', async () => {
      let capturedConfig;
      installMockAdapter((config) => {
        capturedConfig = config;
        return { data: { ok: true }, status: 200 };
      });

      await api.post('/api/v1/leads/', { first_name: 'Test' });
      expect(capturedConfig.headers['X-CSRF-Token']).toBe('mock-csrf-token');
    });

    it('injects X-CSRF-Token on PUT requests', async () => {
      let capturedConfig;
      installMockAdapter((config) => {
        capturedConfig = config;
        return { data: { ok: true }, status: 200 };
      });

      await api.put('/api/v1/leads/1', { first_name: 'Test' });
      expect(capturedConfig.headers['X-CSRF-Token']).toBe('mock-csrf-token');
    });

    it('injects X-CSRF-Token on PATCH requests', async () => {
      let capturedConfig;
      installMockAdapter((config) => {
        capturedConfig = config;
        return { data: { ok: true }, status: 200 };
      });

      await api.patch('/api/v1/leads/1', { first_name: 'Test' });
      expect(capturedConfig.headers['X-CSRF-Token']).toBe('mock-csrf-token');
    });

    it('injects X-CSRF-Token on DELETE requests', async () => {
      let capturedConfig;
      installMockAdapter((config) => {
        capturedConfig = config;
        return { data: {}, status: 200 };
      });

      await api.delete('/api/v1/leads/1');
      expect(capturedConfig.headers['X-CSRF-Token']).toBe('mock-csrf-token');
    });

    it('does NOT inject X-CSRF-Token on GET requests', async () => {
      let capturedConfig;
      installMockAdapter((config) => {
        capturedConfig = config;
        return { data: { ok: true }, status: 200 };
      });

      await api.get('/api/v1/leads/');
      expect(capturedConfig.headers['X-CSRF-Token']).toBeUndefined();
    });
  });

  // -----------------------------------------------------------------------
  // 401 token refresh
  // -----------------------------------------------------------------------
  describe('401 token refresh', () => {
    it('attempts single-flight token refresh on 401 (no stampede)', async () => {
      // The attemptTokenRefresh function deduplicates via _refreshPromise.
      // We verify the function itself handles deduplication by calling it
      // concurrently and checking that the refresh endpoint is hit only once.
      const fetchSpy = vi.spyOn(global, 'fetch');
      fetchSpy.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ access_token: 'new-token' }),
      });

      // Call concurrently
      const [result1, result2] = await Promise.all([
        attemptTokenRefresh(),
        attemptTokenRefresh(),
      ]);

      // Both should resolve with the same result
      expect(result1).toBe(true);
      expect(result2).toBe(true);

      // fetch should have been called exactly once (single-flight)
      const renewCalls = fetchSpy.mock.calls.filter(
        ([url]) => typeof url === 'string' && url.includes('/account/renew')
      );
      expect(renewCalls.length).toBe(1);

      fetchSpy.mockRestore();
    });

    it('returns false when no refresh token is available', async () => {
      mockRefreshToken = null;
      const result = await attemptTokenRefresh();
      expect(result).toBe(false);
    });

    it('returns false when refresh endpoint fails', async () => {
      const fetchSpy = vi.spyOn(global, 'fetch');
      fetchSpy.mockResolvedValue({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Invalid refresh token' }),
      });

      const result = await attemptTokenRefresh();
      expect(result).toBe(false);

      fetchSpy.mockRestore();
    });
  });

  // -----------------------------------------------------------------------
  // 429 handling — auth endpoints do NOT retry
  // -----------------------------------------------------------------------
  describe('429 rate limiting', () => {
    it('does NOT retry 429 on auth endpoints (/account/start)', async () => {
      let requestCount = 0;
      installMockAdapterWithError((config) => {
        requestCount++;
        return {
          error: true,
          status: 429,
          data: { detail: 'Too many login attempts' },
        };
      });

      try {
        await api.post('/api/v1/account/start', { x1: 'test@test.com', x2: 'pass' });
      } catch (err) {
        expect(err.status).toBe(429);
        expect(err.retryable).toBe(false);
        expect(err.code).toBe('ERR_RATE_LIMITED');
      }

      // Should only have been called once — no retries
      expect(requestCount).toBe(1);
    });

    it('does NOT retry 429 on /account/renew endpoint', async () => {
      let requestCount = 0;
      installMockAdapterWithError((config) => {
        requestCount++;
        return {
          error: true,
          status: 429,
          data: { detail: 'Rate limited' },
        };
      });

      try {
        await api.post('/api/v1/account/renew', { refresh_token: 'abc' });
      } catch (err) {
        expect(err.status).toBe(429);
        expect(err.retryable).toBe(false);
      }

      expect(requestCount).toBe(1);
    });

    it('does NOT retry 429 on /auth/login endpoint', async () => {
      let requestCount = 0;
      installMockAdapterWithError((config) => {
        requestCount++;
        return {
          error: true,
          status: 429,
          data: { detail: 'Rate limited' },
        };
      });

      try {
        await api.post('/api/v1/auth/login', { email: 'a', password: 'b' });
      } catch (err) {
        expect(err.status).toBe(429);
      }

      expect(requestCount).toBe(1);
    });

    it('retries 429 on non-auth endpoints with backoff', async () => {
      let requestCount = 0;
      installMockAdapterWithError((config) => {
        requestCount++;
        if (requestCount <= 1) {
          return {
            error: true,
            status: 429,
            data: { detail: 'Too many requests' },
          };
        }
        // Succeed on retry
        return { data: { leads: [] }, status: 200 };
      });

      const response = await api.get('/api/v1/leads/');
      expect(response.data.leads).toEqual([]);
      expect(requestCount).toBe(2);
    }, 15000);
  });

  // -----------------------------------------------------------------------
  // 503 retry
  // -----------------------------------------------------------------------
  describe('503 retry', () => {
    it('retries 503 responses with backoff', async () => {
      let requestCount = 0;
      installMockAdapterWithError((config) => {
        requestCount++;
        if (requestCount <= 1) {
          return {
            error: true,
            status: 503,
            data: { detail: 'Database pool exhausted' },
          };
        }
        return { data: { ok: true }, status: 200 };
      });

      const response = await api.get('/api/v1/dashboard');
      expect(response.data.ok).toBe(true);
      expect(requestCount).toBe(2);
    }, 15000);

    it('gives up after max retries on 503', async () => {
      let requestCount = 0;
      installMockAdapterWithError((config) => {
        requestCount++;
        return {
          error: true,
          status: 503,
          data: { detail: 'Service unavailable' },
        };
      });

      try {
        await api.get('/api/v1/dashboard');
      } catch (err) {
        expect(err.status).toBe(503);
        expect(err.retryable).toBe(true);
        expect(err.code).toBe('ERR_SERVICE_UNAVAILABLE');
      }

      // Initial + 2 retries = 3 total
      expect(requestCount).toBe(3);
    }, 30000);
  });

  // -----------------------------------------------------------------------
  // Network errors
  // -----------------------------------------------------------------------
  describe('Network errors', () => {
    it('produces structured error on network failure', async () => {
      api.defaults.adapter = async (config) => {
        const err = new Error('Network Error');
        err.config = config;
        err.code = 'ERR_NETWORK';
        // No response property = network error
        throw err;
      };

      try {
        await api.get('/api/v1/dashboard');
        expect.fail('Should have thrown');
      } catch (err) {
        expect(err.status).toBe(0);
        expect(err.retryable).toBe(true);
        expect(err.code).toBe('ERR_NETWORK');
        expect(err.message).toContain('Network error');
      }
    });

    it('produces structured error on timeout', async () => {
      api.defaults.adapter = async (config) => {
        const err = new Error('timeout of 30000ms exceeded');
        err.config = config;
        err.code = 'ECONNABORTED';
        throw err;
      };

      try {
        await api.get('/api/v1/dashboard');
        expect.fail('Should have thrown');
      } catch (err) {
        expect(err.status).toBe(0);
        expect(err.retryable).toBe(true);
        expect(err.code).toBe('ECONNABORTED');
        expect(err.message).toContain('timed out');
      }
    });
  });

  // -----------------------------------------------------------------------
  // Structured error shape
  // -----------------------------------------------------------------------
  describe('Structured error responses', () => {
    it('500 errors are sanitized with generic message', async () => {
      installMockAdapterWithError(() => ({
        error: true,
        status: 500,
        data: { detail: 'SQL error: relation "users" does not exist' },
      }));

      try {
        await api.get('/api/v1/dashboard');
        expect.fail('Should have thrown');
      } catch (err) {
        expect(err.status).toBe(500);
        // Should NOT leak the SQL error
        expect(err.message).not.toContain('SQL');
        expect(err.message).toContain('unexpected error');
        expect(err.retryable).toBe(true);
      }
    });

    it('400 errors preserve backend message', async () => {
      installMockAdapterWithError(() => ({
        error: true,
        status: 400,
        data: { detail: 'Email is required' },
      }));

      try {
        await api.post('/api/v1/leads/', {});
        expect.fail('Should have thrown');
      } catch (err) {
        expect(err.status).toBe(400);
        expect(err.message).toBe('Email is required');
      }
    });

    it('404 errors use fallback message when no detail', async () => {
      installMockAdapterWithError(() => ({
        error: true,
        status: 404,
        data: {},
      }));

      try {
        await api.get('/api/v1/leads/99999');
        expect.fail('Should have thrown');
      } catch (err) {
        expect(err.status).toBe(404);
        expect(err.message).toContain('not found');
      }
    });
  });

  // -----------------------------------------------------------------------
  // API module exports
  // -----------------------------------------------------------------------
  describe('API module exports', () => {
    it('exports leadsAPI with expected CRUD methods', () => {
      expect(leadsAPI).toBeDefined();
      expect(typeof leadsAPI.getAll).toBe('function');
      expect(typeof leadsAPI.getById).toBe('function');
      expect(typeof leadsAPI.create).toBe('function');
      expect(typeof leadsAPI.update).toBe('function');
      expect(typeof leadsAPI.delete).toBe('function');
    });

    it('exports loansAPI with expected methods', () => {
      expect(loansAPI).toBeDefined();
      expect(typeof loansAPI.getAll).toBe('function');
      expect(typeof loansAPI.getById).toBe('function');
    });

    it('exports authAPI with login and register', () => {
      expect(authAPI).toBeDefined();
      expect(typeof authAPI.login).toBe('function');
      expect(typeof authAPI.register).toBe('function');
    });

    it('exports dashboardAPI', () => {
      expect(dashboardAPI).toBeDefined();
      expect(typeof dashboardAPI.getDashboard).toBe('function');
    });

    it('exports tasksAPI', () => {
      expect(tasksAPI).toBeDefined();
      expect(typeof tasksAPI.getAll).toBe('function');
    });

    it('exports aiAPI', () => {
      expect(aiAPI).toBeDefined();
    });

    it('exports calendarAPI and schedulerAPI', () => {
      expect(calendarAPI).toBeDefined();
      expect(schedulerAPI).toBeDefined();
    });

    it('exports API_BASE_URL string', () => {
      expect(typeof API_BASE_URL).toBe('string');
      // Should be a valid URL (either localhost or production)
      expect(API_BASE_URL).toMatch(/^https?:\/\//);
    });

    it('exports attemptTokenRefresh function', () => {
      expect(typeof attemptTokenRefresh).toBe('function');
    });

    it('exports apiRequest helper', () => {
      expect(typeof apiRequest).toBe('function');
    });

    it('exports isApiError helper', () => {
      expect(typeof isApiError).toBe('function');
    });
  });
});
