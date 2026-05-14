/**
 * Cross-platform storage utility
 * Uses Capacitor Preferences on native iOS/Android for secure storage
 * Falls back to localStorage on web
 */
import { Capacitor } from '@capacitor/core';
import { Preferences } from '@capacitor/preferences';

const isNative: boolean = Capacitor.isNativePlatform();

/**
 * Get a value from storage
 */
export const getItem = async (key: string): Promise<string | null> => {
  if (isNative) {
    const { value } = await Preferences.get({ key });
    return value;
  }
  return localStorage.getItem(key);
};

/**
 * Set a value in storage
 */
export const setItem = async (key: string, value: string): Promise<void> => {
  if (isNative) {
    await Preferences.set({ key, value });
    // NO localStorage mirror — tokens must not be exposed in WKWebView storage
  } else {
    localStorage.setItem(key, value);
  }
};

/**
 * Remove a value from storage
 */
export const removeItem = async (key: string): Promise<void> => {
  if (isNative) {
    await Preferences.remove({ key });
    // NO localStorage mirror
  } else {
    localStorage.removeItem(key);
  }
};

/**
 * Clear all stored values
 */
export const clear = async (): Promise<void> => {
  if (isNative) {
    await Preferences.clear();
  } else {
    localStorage.clear();
  }
};

/**
 * Get all keys in storage
 */
export const keys = async (): Promise<string[]> => {
  if (isNative) {
    const { keys: storedKeys } = await Preferences.keys();
    return storedKeys;
  }
  return Object.keys(localStorage);
};

/**
 * Get a JSON object from storage
 */
export const getJSON = async <T = unknown>(key: string): Promise<T | null> => {
  const value = await getItem(key);
  if (!value) return null;
  try {
    return JSON.parse(value) as T;
  } catch (error) {
    console.error(`Error parsing JSON for key "${key}":`, error);
    return null;
  }
};

/**
 * Set a JSON object in storage
 */
export const setJSON = async (key: string, value: unknown): Promise<void> => {
  await setItem(key, JSON.stringify(value));
};

// Storage keys constants
export const STORAGE_KEYS = {
  TOKEN: 'token',
  REFRESH_TOKEN: 'refresh_token',
  USER: 'user',
  IMPERSONATION: 'impersonation',
  DASHBOARD_ORDER: 'dashboardOrder',
} as const;

export type StorageKey = typeof STORAGE_KEYS[keyof typeof STORAGE_KEYS];

/**
 * Auth token migration: moves tokens from localStorage to Capacitor Preferences.
 *
 * On native platforms, tokens may exist only in localStorage (written by sync code
 * paths like sessionManager or older versions of the app). This function checks for
 * tokens in localStorage that are missing from Preferences and copies them over,
 * ensuring Capacitor Preferences is the authoritative store.
 *
 * Safe to call multiple times; only migrates if the Preferences entry is absent.
 * No-op on web (localStorage IS the primary store there).
 */
let _migrationDone = false;
export const migrateTokensToSecureStorage = async (): Promise<void> => {
  if (!isNative || _migrationDone) return;
  _migrationDone = true;

  const sensitiveKeys: string[] = [
    STORAGE_KEYS.TOKEN,
    STORAGE_KEYS.REFRESH_TOKEN,
    STORAGE_KEYS.USER,
  ];

  for (const key of sensitiveKeys) {
    try {
      const localValue = localStorage.getItem(key);
      if (!localValue) continue;

      const { value: prefsValue } = await Preferences.get({ key });
      if (prefsValue) continue; // Already in Preferences, no migration needed

      // Token exists in localStorage but not in Preferences — migrate it
      await Preferences.set({ key, value: localValue });
      console.log(`[Storage] Migrated '${key}' from localStorage to Capacitor Preferences`);
    } catch (err) {
      console.warn(`[Storage] Failed to migrate '${key}':`, err);
    }
  }
};

/**
 * Clear auth tokens from ALL storage locations (Preferences + localStorage).
 *
 * Call this on logout to ensure no stale tokens remain in either store.
 * This is the authoritative "wipe auth state" function that should be used
 * instead of manually calling localStorage.removeItem for auth keys.
 */
export const clearAllAuthTokens = async (): Promise<void> => {
  const authKeys: string[] = [
    STORAGE_KEYS.TOKEN,
    STORAGE_KEYS.REFRESH_TOKEN,
    STORAGE_KEYS.USER,
  ];

  for (const key of authKeys) {
    // Always clear localStorage (sync)
    try { localStorage.removeItem(key); } catch (_) { /* ignore */ }

    // Clear Capacitor Preferences on native
    if (isNative) {
      try { await Preferences.remove({ key }); } catch (_) { /* ignore */ }
    }
  }
};

export default {
  getItem,
  setItem,
  removeItem,
  clear,
  keys,
  getJSON,
  setJSON,
  isNative,
  STORAGE_KEYS,
  migrateTokensToSecureStorage,
  clearAllAuthTokens,
};
