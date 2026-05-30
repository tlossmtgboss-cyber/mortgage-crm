/**
 * API Client Tests
 *
 * Tests for the axios-based API client request-building logic (CSRF /
 * Authorization / 401 handling / base URL). Uses a self-contained
 * TestableAPIClient that mirrors the canonical client's behavior.
 *
 * Covers:
 *  - CSRF token inclusion for state-changing methods
 *  - Authorization header attachment
 *  - 401 handling / session cleanup
 *  - Base URL configuration
 *
 * All network calls are intercepted with vi.fn() / fetch mocks — no real
 * HTTP requests are made.
 */

import { beforeEach, afterEach, describe, test, expect, vi } from 'vitest';

// ---------------------------------------------------------------------------
// Helpers / stubs
// ---------------------------------------------------------------------------

/**
 * Minimal reproduction of the CSRF-cookie reader from src/utils/security.js,
 * so we can test the logic without importing the module (which has side-effects
 * like importing api.js at module level).
 */
function getCSRFTokenFromCookie(cookieString) {
  const cookies = cookieString.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === 'csrf_token') {
      return decodeURIComponent(value);
    }
  }
  return null;
}

/**
 * Determine base URL using the same logic as src/services/api.js.
 */
function resolveBaseURL(hostname, envApiUrl) {
  const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1';
  return isLocalhost
    ? (envApiUrl || 'http://localhost:8000')
    : 'https://api.perenniaai.com';
}

/**
 * Minimal APIClient-like class that mirrors the real implementation's
 * request-building logic, so we can assert on headers without a real network.
 */
class TestableAPIClient {
  constructor({ baseURL = 'http://localhost:8000', onUnauthorized } = {}) {
    this.baseURL = baseURL;
    this.onUnauthorized = onUnauthorized || (() => {});
    this._lastRequest = null;
  }

  _getToken() {
    return localStorage.getItem('token');
  }

  _buildHeaders(method, csrfToken) {
    const headers = { 'Content-Type': 'application/json' };
    const token = this._getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const CSRF_METHODS = ['post', 'put', 'patch', 'delete'];
    if (CSRF_METHODS.includes(method.toLowerCase()) && csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
    return headers;
  }

  async request(endpoint, options = {}) {
    const { method = 'GET', body, csrfToken, ...rest } = options;
    const headers = this._buildHeaders(method, csrfToken);
    const url = `${this.baseURL}${endpoint}`;

    // Capture what would be sent
    this._lastRequest = { url, method, headers, body };

    // Use the injected fetch spy
    const response = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      ...rest,
    });

    if (response.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      this.onUnauthorized();
    }

    if (!response.ok) {
      const err = new Error(`HTTP ${response.status}`);
      err.status = response.status;
      throw err;
    }

    const contentType = response.headers.get('content-type') || '';
    return contentType.includes('application/json') ? response.json() : response.text();
  }

  get(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'GET' });
  }

  post(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'POST', body });
  }

  put(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'PUT', body });
  }

  patch(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'PATCH', body });
  }

  delete(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'DELETE' });
  }
}

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const MOCK_TOKEN = 'eyJhbGciOiJSUzI1NiJ9.test-payload.signature';
const MOCK_CSRF  = 'csrf-abc-123-xyz';

function makeFetchMock(status = 200, body = { data: { ok: true } }, headers = {}) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name) => {
        const normalized = name.toLowerCase();
        if (normalized === 'content-type') return 'application/json';
        return headers[normalized] || null;
      },
    },
    json: async () => body,
    text: async () => JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CSRF Token Inclusion', () => {
  let client;

  beforeEach(() => {
    global.fetch = makeFetchMock();
    client = new TestableAPIClient({ baseURL: 'http://localhost:8000' });
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  test('POST request includes X-CSRF-Token header when token is available', async () => {
    await client.post('/api/v1/leads/', { name: 'Test Lead' }, { csrfToken: MOCK_CSRF });
    expect(client._lastRequest.headers['X-CSRF-Token']).toBe(MOCK_CSRF);
  });

  test('PUT request includes X-CSRF-Token header', async () => {
    await client.put('/api/v1/leads/1', { name: 'Updated' }, { csrfToken: MOCK_CSRF });
    expect(client._lastRequest.headers['X-CSRF-Token']).toBe(MOCK_CSRF);
  });

  test('PATCH request includes X-CSRF-Token header', async () => {
    await client.patch('/api/v1/leads/1', { stage: 'PROCESSING' }, { csrfToken: MOCK_CSRF });
    expect(client._lastRequest.headers['X-CSRF-Token']).toBe(MOCK_CSRF);
  });

  test('DELETE request includes X-CSRF-Token header', async () => {
    await client.delete('/api/v1/leads/1', { csrfToken: MOCK_CSRF });
    expect(client._lastRequest.headers['X-CSRF-Token']).toBe(MOCK_CSRF);
  });

  test('GET request does NOT include X-CSRF-Token header', async () => {
    await client.get('/api/v1/leads/', { csrfToken: MOCK_CSRF });
    expect(client._lastRequest.headers['X-CSRF-Token']).toBeUndefined();
  });

  test('POST request omits X-CSRF-Token when no token provided', async () => {
    await client.post('/api/v1/leads/', { name: 'Test' });
    expect(client._lastRequest.headers['X-CSRF-Token']).toBeUndefined();
  });
});

describe('CSRF Token Parsing from Cookie', () => {
  test('extracts csrf_token from a single-cookie string', () => {
    const token = getCSRFTokenFromCookie('csrf_token=secret-token-42');
    expect(token).toBe('secret-token-42');
  });

  test('extracts csrf_token from a multi-cookie string', () => {
    const token = getCSRFTokenFromCookie('session=abc; csrf_token=my-csrf; path=/');
    expect(token).toBe('my-csrf');
  });

  test('returns null when csrf_token cookie is absent', () => {
    const token = getCSRFTokenFromCookie('session=abc; other=xyz');
    expect(token).toBeNull();
  });

  test('returns null for an empty cookie string', () => {
    expect(getCSRFTokenFromCookie('')).toBeNull();
  });

  test('URL-decodes percent-encoded cookie values', () => {
    const token = getCSRFTokenFromCookie('csrf_token=hello%20world');
    expect(token).toBe('hello world');
  });
});

describe('Authorization Header Attachment', () => {
  let client;

  beforeEach(() => {
    global.fetch = makeFetchMock();
    client = new TestableAPIClient({ baseURL: 'http://localhost:8000' });
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  test('includes Bearer token when user is authenticated', async () => {
    localStorage.setItem('token', MOCK_TOKEN);
    await client.get('/api/v1/dashboard');
    expect(client._lastRequest.headers['Authorization']).toBe(`Bearer ${MOCK_TOKEN}`);
  });

  test('omits Authorization header when no token in localStorage', async () => {
    await client.get('/api/v1/dashboard');
    expect(client._lastRequest.headers['Authorization']).toBeUndefined();
  });

  test('attaches updated token after it changes in localStorage', async () => {
    localStorage.setItem('token', 'old-token');
    await client.get('/api/v1/leads/');
    expect(client._lastRequest.headers['Authorization']).toBe('Bearer old-token');

    localStorage.setItem('token', 'new-token');
    await client.get('/api/v1/leads/');
    expect(client._lastRequest.headers['Authorization']).toBe('Bearer new-token');
  });

  test('always sends Content-Type: application/json', async () => {
    localStorage.setItem('token', MOCK_TOKEN);
    await client.post('/api/v1/leads/', { name: 'Test' });
    expect(client._lastRequest.headers['Content-Type']).toBe('application/json');
  });
});

describe('401 Handling / Token Refresh Trigger', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  test('removes token from localStorage on 401 response', async () => {
    localStorage.setItem('token', MOCK_TOKEN);
    global.fetch = makeFetchMock(401, { detail: 'Unauthorized' });

    const client = new TestableAPIClient({ onUnauthorized: vi.fn() });
    await expect(client.get('/api/v1/dashboard')).rejects.toThrow('HTTP 401');
    expect(localStorage.getItem('token')).toBeNull();
  });

  test('removes user from localStorage on 401 response', async () => {
    localStorage.setItem('token', MOCK_TOKEN);
    localStorage.setItem('user', JSON.stringify({ id: 1, email: 'test@example.com' }));
    global.fetch = makeFetchMock(401, { detail: 'Unauthorized' });

    const client = new TestableAPIClient({ onUnauthorized: vi.fn() });
    await expect(client.get('/api/v1/dashboard')).rejects.toThrow('HTTP 401');
    expect(localStorage.getItem('user')).toBeNull();
  });

  test('calls onUnauthorized callback on 401', async () => {
    const onUnauthorized = vi.fn();
    localStorage.setItem('token', MOCK_TOKEN);
    global.fetch = makeFetchMock(401, { detail: 'Unauthorized' });

    const client = new TestableAPIClient({ onUnauthorized });
    await expect(client.get('/api/v1/dashboard')).rejects.toThrow();
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  test('does NOT call onUnauthorized on a 403 response', async () => {
    const onUnauthorized = vi.fn();
    global.fetch = makeFetchMock(403, { detail: 'Forbidden' });

    const client = new TestableAPIClient({ onUnauthorized });
    await expect(client.get('/api/v1/admin')).rejects.toThrow('HTTP 403');
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  test('does NOT remove token on a 500 error', async () => {
    localStorage.setItem('token', MOCK_TOKEN);
    global.fetch = makeFetchMock(500, { detail: 'Internal Server Error' });

    const client = new TestableAPIClient({ onUnauthorized: vi.fn() });
    await expect(client.get('/api/v1/leads/')).rejects.toThrow('HTTP 500');
    expect(localStorage.getItem('token')).toBe(MOCK_TOKEN);
  });
});

describe('Base URL Configuration', () => {
  test('resolves to localhost URL in development', () => {
    const url = resolveBaseURL('localhost', undefined);
    expect(url).toBe('http://localhost:8000');
  });

  test('resolves to localhost URL for 127.0.0.1', () => {
    const url = resolveBaseURL('127.0.0.1', undefined);
    expect(url).toBe('http://localhost:8000');
  });

  test('resolves to production Railway URL in production', () => {
    const url = resolveBaseURL('app.perenniaai.com', undefined);
    expect(url).toBe('https://api.perenniaai.com');
  });

  test('respects REACT_APP_API_URL env override in development', () => {
    const customUrl = 'http://192.168.1.50:8000';
    const url = resolveBaseURL('localhost', customUrl);
    expect(url).toBe(customUrl);
  });

  test('ignores REACT_APP_API_URL in production (always uses Railway)', () => {
    const url = resolveBaseURL('app.perenniaai.com', 'http://staging.example.com');
    expect(url).toBe('https://api.perenniaai.com');
  });

  test('constructed request URL combines baseURL and endpoint correctly', async () => {
    global.fetch = makeFetchMock();
    const client = new TestableAPIClient({ baseURL: 'https://api.perenniaai.com' });
    await client.get('/api/v1/leads/');
    expect(client._lastRequest.url).toBe('https://api.perenniaai.com/api/v1/leads/');
  });
});
