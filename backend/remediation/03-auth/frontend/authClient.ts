/**
 * 03-auth/frontend/authClient.ts
 *
 * Replaces every localStorage.getItem('token') / setItem('token') pattern.
 * The auth token lives in an httpOnly cookie set by the backend — JS cannot
 * read it and that is the point. This module handles:
 *   - login / logout / refresh
 *   - reading CSRF cookie and attaching X-CSRF-Token header
 *   - automatic refresh retry on 401
 *   - broadcasting auth state across tabs
 *
 * Drop-in: frontend/src/lib/auth/authClient.ts
 */

const API_BASE = import.meta.env.VITE_API_URL || "/api";
const CSRF_COOKIE = "perennia_csrf";
const CSRF_HEADER = "X-CSRF-Token";

// Cross-tab sync
const AUTH_CHANNEL = new BroadcastChannel("perennia-auth");

// --- Cookie reader (only for CSRF, which is intentionally non-httpOnly) ---

function readCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)"),
  );
  return match ? decodeURIComponent(match[1]) : null;
}

// --- Fetch wrapper ---

type FetchOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  // Skip automatic refresh (used by refresh call itself to avoid loops)
  skipRefresh?: boolean;
};

export class AuthError extends Error {
  constructor(public code: string, public status: number) {
    super(code);
    this.name = "AuthError";
  }
}

let refreshInFlight: Promise<void> | null = null;

/**
 * Authenticated fetch. Use this for every API call.
 *
 *   const res = await authFetch("/loans/123", { method: "GET" });
 *   const res = await authFetch("/loans", { method: "POST", body: { ... } });
 */
export async function authFetch(
  path: string,
  options: FetchOptions = {},
): Promise<Response> {
  const { skipRefresh, body, headers: extraHeaders, ...rest } = options;

  const headers = new Headers(extraHeaders);
  headers.set("Accept", "application/json");

  if (body !== undefined && !(body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  // CSRF: mirror the cookie value in the header for state-changing methods
  const method = (rest.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set(CSRF_HEADER, csrf);
  }

  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;

  const res = await fetch(url, {
    ...rest,
    headers,
    credentials: "include", // send cookies
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
        ? body
        : JSON.stringify(body),
  });

  if (res.status !== 401 || skipRefresh) {
    return res;
  }

  // Parse the 401 reason
  const detail = await peekDetail(res);
  if (detail !== "access_token_expired") {
    // Non-recoverable auth failure — drop to login
    notifyUnauthenticated();
    throw new AuthError(detail, 401);
  }

  // Try to refresh (dedupe concurrent refreshes)
  if (!refreshInFlight) {
    refreshInFlight = refreshAccessToken().finally(() => {
      refreshInFlight = null;
    });
  }

  try {
    await refreshInFlight;
  } catch {
    notifyUnauthenticated();
    throw new AuthError("refresh_failed", 401);
  }

  // Retry original request once
  const retryHeaders = new Headers(extraHeaders);
  retryHeaders.set("Accept", "application/json");
  if (body !== undefined && !(body instanceof FormData)) {
    retryHeaders.set("Content-Type", "application/json");
  }
  if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) retryHeaders.set(CSRF_HEADER, csrf);
  }

  return fetch(url, {
    ...rest,
    headers: retryHeaders,
    credentials: "include",
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
        ? body
        : JSON.stringify(body),
  });
}

async function peekDetail(res: Response): Promise<string> {
  try {
    const clone = res.clone();
    const data = await clone.json();
    return data?.detail || "unauthorized";
  } catch {
    return "unauthorized";
  }
}

// --- Auth operations ---

export interface LoginResult {
  user_id: string;
  role: string;
  org_id: string;
  expires_in: number;
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    const detail = await peekDetail(res);
    throw new AuthError(detail, res.status);
  }

  const result = (await res.json()) as LoginResult;
  AUTH_CHANNEL.postMessage({ type: "login", user_id: result.user_id });
  scheduleRefresh(result.expires_in);
  return result;
}

export async function logout(): Promise<void> {
  await authFetch("/auth/logout", { method: "POST", skipRefresh: true });
  AUTH_CHANNEL.postMessage({ type: "logout" });
  cancelRefresh();
}

export async function logoutAll(): Promise<void> {
  await authFetch("/auth/logout-all", { method: "POST", skipRefresh: true });
  AUTH_CHANNEL.postMessage({ type: "logout" });
  cancelRefresh();
}

async function refreshAccessToken(): Promise<void> {
  const csrf = readCookie(CSRF_COOKIE);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) headers[CSRF_HEADER] = csrf;

  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers,
    credentials: "include",
  });

  if (!res.ok) {
    throw new AuthError("refresh_failed", res.status);
  }

  const data = await res.json();
  scheduleRefresh(data.expires_in);
}

// --- Proactive refresh (refresh 60s before expiry) ---

let refreshTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleRefresh(expiresInSeconds: number): void {
  cancelRefresh();
  const refreshIn = Math.max((expiresInSeconds - 60) * 1000, 5000);
  refreshTimer = setTimeout(() => {
    refreshAccessToken().catch(() => notifyUnauthenticated());
  }, refreshIn);
}

function cancelRefresh(): void {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

// --- Cross-tab coordination ---

type AuthListener = (event: { type: "login" | "logout"; user_id?: string }) => void;
const listeners = new Set<AuthListener>();

AUTH_CHANNEL.addEventListener("message", (ev) => {
  listeners.forEach((cb) => cb(ev.data));
});

export function onAuthEvent(cb: AuthListener): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

function notifyUnauthenticated(): void {
  AUTH_CHANNEL.postMessage({ type: "logout" });
  // Redirect to login — caller app router can also subscribe to onAuthEvent
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}
