import { Preferences } from '@capacitor/preferences';
import { Capacitor } from '@capacitor/core';

const TOKEN_KEY = 'access_token';
const REFRESH_KEY = 'refresh_token';
const USER_KEY = 'user_data';

// ── In-memory cache ──────────────────────────────────────────
// Loaded once at app startup via initialize().
// All subsequent reads are synchronous from memory.
// Token never touches localStorage after migration.
const _cache = {
  access_token: null,
  refresh_token: null,
  user_data: null,
  initialized: false,
};

// ── Initialize — call once at app startup ────────────────────
// Loads tokens from Capacitor Preferences into memory.
// Also migrates any existing localStorage tokens on first run.
export async function initialize() {
  if (_cache.initialized) return;

  if (Capacitor.isNativePlatform()) {
    // Native: read from Keychain/Keystore via Capacitor Preferences
    const [accessResult, refreshResult, userResult] = await Promise.all([
      Preferences.get({ key: TOKEN_KEY }),
      Preferences.get({ key: REFRESH_KEY }),
      Preferences.get({ key: USER_KEY }),
    ]);
    _cache.access_token  = accessResult.value ?? null;
    _cache.refresh_token = refreshResult.value ?? null;
    _cache.user_data     = userResult.value ? JSON.parse(userResult.value) : null;
  } else {
    // Web: read from localStorage (acceptable on web — no Keychain available)
    _cache.access_token  = localStorage.getItem(TOKEN_KEY);
    _cache.refresh_token = localStorage.getItem(REFRESH_KEY);
    const raw = localStorage.getItem(USER_KEY);
    _cache.user_data     = raw ? JSON.parse(raw) : null;
  }

  // One-time migration: if localStorage has a token but Preferences doesn't,
  // migrate it to Preferences and delete from localStorage
  if (Capacitor.isNativePlatform()) {
    const lsToken = localStorage.getItem(TOKEN_KEY);
    if (lsToken && !_cache.access_token) {
      await setTokens({ access_token: lsToken });
      console.info('[TokenStore] Migrated token from localStorage to Preferences');
    }
    // Remove from localStorage regardless — this is the key security fix
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    // Keep USER_KEY in localStorage until all files are migrated (non-sensitive)
  }

  _cache.initialized = true;
}

// ── Synchronous read ─────────────────────────────────────────
// Safe to call anywhere — returns from memory cache after initialize().
// Returns null if initialize() hasn't been called yet (app startup race).
export function getToken() {
  if (!_cache.initialized && Capacitor.isNativePlatform()) {
    // Fallback during startup race — return from localStorage
    // This should only happen if a request fires before initialize() completes
    console.warn('[TokenStore] getToken() called before initialize() — using localStorage fallback');
    return localStorage.getItem(TOKEN_KEY);
  }
  return _cache.access_token;
}

export function getRefreshToken() {
  return _cache.refresh_token;
}

export function getUserData() {
  return _cache.user_data;
}

export function isAuthenticated() {
  return !!_cache.access_token;
}

// ── Async write ──────────────────────────────────────────────
export async function setTokens({
  access_token,
  refresh_token,
  user_data,
}) {
  if (access_token !== undefined) {
    _cache.access_token = access_token;
    if (Capacitor.isNativePlatform()) {
      await Preferences.set({ key: TOKEN_KEY, value: access_token });
    } else {
      localStorage.setItem(TOKEN_KEY, access_token);
    }
  }

  if (refresh_token !== undefined) {
    _cache.refresh_token = refresh_token;
    if (Capacitor.isNativePlatform()) {
      await Preferences.set({ key: REFRESH_KEY, value: refresh_token });
    } else {
      localStorage.setItem(REFRESH_KEY, refresh_token);
    }
  }

  if (user_data !== undefined) {
    _cache.user_data = user_data;
    const serialized = JSON.stringify(user_data);
    if (Capacitor.isNativePlatform()) {
      await Preferences.set({ key: USER_KEY, value: serialized });
    } else {
      localStorage.setItem(USER_KEY, serialized);
    }
  }
}

// ── Clear on logout ──────────────────────────────────────────
export async function clearTokens() {
  _cache.access_token  = null;
  _cache.refresh_token = null;
  _cache.user_data     = null;

  if (Capacitor.isNativePlatform()) {
    await Promise.all([
      Preferences.remove({ key: TOKEN_KEY }),
      Preferences.remove({ key: REFRESH_KEY }),
      Preferences.remove({ key: USER_KEY }),
    ]);
  }

  // Always clear localStorage regardless of platform
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
}
