const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_MAX_RETRIES = 2;
const RETRY_STATUS = new Set([408, 429, 500, 502, 503, 504]);

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.status = status;
    this.body = body;
    this.name = 'ApiError';
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

export interface ApiFetchOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  timeoutMs?: number;
  maxRetries?: number;
}

export async function apiFetch<T = unknown>(
  url: string,
  {
    method = 'GET',
    body,
    headers = {},
    signal,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    maxRetries = DEFAULT_MAX_RETRIES,
  }: ApiFetchOptions = {}
): Promise<T | null> {
  let attempt = 0;
  while (true) {
    const timeoutCtrl = new AbortController();
    const onAbort = (): void => timeoutCtrl.abort();
    if (signal) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      signal.addEventListener('abort', onAbort, { once: true });
    }
    const timeoutId = setTimeout(() => timeoutCtrl.abort(), timeoutMs);

    try {
      const fetchOpts: RequestInit & { headers: Record<string, string> } = {
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
        let parsed: unknown;
        try { parsed = await res.json(); } catch { parsed = await res.text(); }
        if (RETRY_STATUS.has(res.status) && attempt < maxRetries) {
          const backoff = Math.min(2 ** attempt * 500, 4000) + Math.floor(Math.random() * 250);
          attempt += 1;
          await sleep(backoff);
          continue;
        }
        const parsedObj = parsed as { detail?: string | Array<{ msg?: string }> } | undefined;
        const msg = parsedObj?.detail
          ? (Array.isArray(parsedObj.detail)
            ? parsedObj.detail.map((d) => d.msg || String(d)).join('; ')
            : String(parsedObj.detail))
          : `HTTP ${res.status}`;
        throw new ApiError(res.status, msg, parsed);
      }

      if (res.status === 204) return null;
      return await res.json() as T;
    } catch (err) {
      const error = err as Error & { name: string };
      if (error.name === 'AbortError') {
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

export interface ApiClient {
  get: <T = unknown>(url: string, opts?: ApiFetchOptions) => Promise<T | null>;
  post: <T = unknown>(url: string, body?: unknown, opts?: ApiFetchOptions) => Promise<T | null>;
  put: <T = unknown>(url: string, body?: unknown, opts?: ApiFetchOptions) => Promise<T | null>;
  patch: <T = unknown>(url: string, body?: unknown, opts?: ApiFetchOptions) => Promise<T | null>;
  del: <T = unknown>(url: string, opts?: ApiFetchOptions) => Promise<T | null>;
}

export const apiClient: ApiClient = {
  get:   <T = unknown>(url: string, opts?: ApiFetchOptions) => apiFetch<T>(url, { ...opts, method: 'GET' }),
  post:  <T = unknown>(url: string, body?: unknown, opts?: ApiFetchOptions) => apiFetch<T>(url, { ...opts, method: 'POST', body }),
  put:   <T = unknown>(url: string, body?: unknown, opts?: ApiFetchOptions) => apiFetch<T>(url, { ...opts, method: 'PUT', body }),
  patch: <T = unknown>(url: string, body?: unknown, opts?: ApiFetchOptions) => apiFetch<T>(url, { ...opts, method: 'PATCH', body }),
  del:   <T = unknown>(url: string, opts?: ApiFetchOptions) => apiFetch<T>(url, { ...opts, method: 'DELETE' }),
};
