const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_MAX_RETRIES = 2;
const RETRY_STATUS = new Set([408, 429, 500, 502, 503, 504]);

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message);
    this.status = status;
    this.body = body;
    this.name = 'ApiError';
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

export async function apiFetch(url, {
  method = 'GET',
  body,
  headers = {},
  signal,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  maxRetries = DEFAULT_MAX_RETRIES,
} = {}) {
  let attempt = 0;
  while (true) {
    const timeoutCtrl = new AbortController();
    const onAbort = () => timeoutCtrl.abort();
    if (signal) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      signal.addEventListener('abort', onAbort, { once: true });
    }
    const timeoutId = setTimeout(() => timeoutCtrl.abort(), timeoutMs);

    try {
      const fetchOpts = {
        method,
        headers: { ...headers },
        signal: timeoutCtrl.signal,
      };
      if (body !== undefined) {
        fetchOpts.headers['Content-Type'] = 'application/json';
        fetchOpts.body = JSON.stringify(body);
      }
      const res = await fetch(url, fetchOpts);

      if (!res.ok) {
        let parsed;
        try { parsed = await res.json(); } catch { parsed = await res.text(); }
        if (RETRY_STATUS.has(res.status) && attempt < maxRetries) {
          const backoff = Math.min(2 ** attempt * 500, 4000) + Math.floor(Math.random() * 250);
          attempt += 1;
          await sleep(backoff);
          continue;
        }
        const msg = parsed?.detail
          ? (Array.isArray(parsed.detail)
            ? parsed.detail.map(d => d.msg || d).join('; ')
            : String(parsed.detail))
          : `HTTP ${res.status}`;
        throw new ApiError(res.status, msg, parsed);
      }

      if (res.status === 204) return null;
      return await res.json();
    } catch (err) {
      if (err.name === 'AbortError') {
        if (signal?.aborted) throw err;
        if (attempt < maxRetries) {
          attempt += 1;
          await sleep(Math.min(2 ** attempt * 500, 4000));
          continue;
        }
        throw new ApiError(408, 'Request timed out');
      }
      if (err instanceof ApiError) throw err;
      if (attempt < maxRetries) {
        attempt += 1;
        await sleep(Math.min(2 ** attempt * 500, 4000));
        continue;
      }
      throw err;
    } finally {
      clearTimeout(timeoutId);
      if (signal) signal.removeEventListener('abort', onAbort);
    }
  }
}

export const apiClient = {
  get:   (url, opts)       => apiFetch(url, { ...opts, method: 'GET' }),
  post:  (url, body, opts) => apiFetch(url, { ...opts, method: 'POST', body }),
  put:   (url, body, opts) => apiFetch(url, { ...opts, method: 'PUT', body }),
  patch: (url, body, opts) => apiFetch(url, { ...opts, method: 'PATCH', body }),
  del:   (url, opts)       => apiFetch(url, { ...opts, method: 'DELETE' }),
};
