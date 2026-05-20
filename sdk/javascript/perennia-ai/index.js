/**
 * Perennia AI — official JavaScript SDK.
 *
 * Read-only client for the public REST surface. Requires Node >= 18 (uses
 * the global `fetch` available since Node 18) or any modern browser.
 *
 *   const { Client } = require('@perennia-ai/sdk');
 *   const client = new Client({ apiKey: 'sk_live_...' });
 *   await client.leads.list();
 *   await client.leads.get('lead_123');
 *   await client.loans.list();
 *   await client.loans.get(42);
 *   await client.calls.list();
 */
'use strict';

const VERSION = '0.1.0';
const DEFAULT_BASE_URL = 'https://api.perenniaai.com';
const USER_AGENT = `perennia-ai-js/${VERSION}`;

class PerenniaError extends Error {
  constructor(message, { status, body } = {}) {
    super(message);
    this.name = 'PerenniaError';
    this.status = status;
    this.body = body;
  }
}

function _buildQuery(params) {
  if (!params) return '';
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');
  return qs ? `?${qs}` : '';
}

class _HTTP {
  constructor({ baseUrl, apiKey, timeout, fetchImpl }) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.apiKey = apiKey;
    this.timeout = timeout;
    // Allow tests / Node < 18 / custom transports to inject a fetch impl.
    this._fetch = fetchImpl || (typeof fetch !== 'undefined' ? fetch : null);
    if (!this._fetch) {
      throw new Error(
        'No fetch implementation available. Use Node >= 18 or pass `fetchImpl`.',
      );
    }
  }

  _headers() {
    return {
      Authorization: `Bearer ${this.apiKey}`,
      Accept: 'application/json',
      'User-Agent': USER_AGENT,
    };
  }

  async get(path, params) {
    const url = `${this.baseUrl}${path}${_buildQuery(params)}`;
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), this.timeout);
    let resp;
    try {
      resp = await this._fetch(url, {
        method: 'GET',
        headers: this._headers(),
        signal: controller.signal,
      });
    } catch (err) {
      throw new PerenniaError(`Network error: ${err.message || err}`);
    } finally {
      clearTimeout(t);
    }
    const text = await resp.text();
    if (!resp.ok) {
      throw new PerenniaError(`HTTP ${resp.status} for ${path}`, {
        status: resp.status,
        body: text,
      });
    }
    return text ? JSON.parse(text) : null;
  }
}

class _Leads {
  constructor(http) { this._http = http; }
  list({ limit = 50, cursor = null } = {}) {
    return this._http.get('/api/v1/leads', { limit, cursor });
  }
  get(leadId) {
    return this._http.get(`/api/v1/leads/${leadId}`);
  }
}

class _Loans {
  constructor(http) { this._http = http; }
  list({ stage = null, limit = 50 } = {}) {
    return this._http.get('/api/v1/loans', { stage, limit });
  }
  get(loanId) {
    return this._http.get(`/api/v1/loans/${loanId}`);
  }
}

class _Calls {
  constructor(http) { this._http = http; }
  list({ limit = 50, since = null } = {}) {
    return this._http.get('/api/v1/calls', { limit, since });
  }
}

class Client {
  /**
   * @param {object} opts
   * @param {string} opts.apiKey  Bearer token from the Perennia dashboard.
   * @param {string} [opts.baseUrl]  Override the API base URL.
   * @param {number} [opts.timeout]  Per-request timeout in ms (default 30000).
   * @param {Function} [opts.fetchImpl]  Custom fetch (for tests / older Node).
   */
  constructor({ apiKey, baseUrl = DEFAULT_BASE_URL, timeout = 30000, fetchImpl } = {}) {
    if (!apiKey) throw new Error('apiKey is required');
    this._http = new _HTTP({ baseUrl, apiKey, timeout, fetchImpl });
    this.leads = new _Leads(this._http);
    this.loans = new _Loans(this._http);
    this.calls = new _Calls(this._http);
  }

  get baseUrl() { return this._http.baseUrl; }
  get apiKey() { return this._http.apiKey; }
}

module.exports = { Client, PerenniaError, VERSION };
