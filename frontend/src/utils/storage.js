/**
 * Cross-platform storage utility
 * Uses Capacitor Preferences on native iOS/Android for secure storage
 * Falls back to localStorage on web
 */
import { Capacitor } from '@capacitor/core';
import { Preferences } from '@capacitor/preferences';

const isNative = Capacitor.isNativePlatform();

/**
 * Get a value from storage
 * @param {string} key - The key to retrieve
 * @returns {Promise<string|null>} - The stored value or null
 */
export const getItem = async (key) => {
  if (isNative) {
    const { value } = await Preferences.get({ key });
    return value;
  }
  return localStorage.getItem(key);
};

/**
 * Set a value in storage
 * @param {string} key - The key to store
 * @param {string} value - The value to store
 * @returns {Promise<void>}
 */
export const setItem = async (key, value) => {
  if (isNative) {
    await Preferences.set({ key, value });
    // Mirror to localStorage so synchronous readers (getAuthHeaders, etc.) work
    try { localStorage.setItem(key, value); } catch (_) { /* WKWebView may restrict */ }
  } else {
    localStorage.setItem(key, value);
  }
};

/**
 * Remove a value from storage
 * @param {string} key - The key to remove
 * @returns {Promise<void>}
 */
export const removeItem = async (key) => {
  if (isNative) {
    await Preferences.remove({ key });
    try { localStorage.removeItem(key); } catch (_) { /* WKWebView may restrict */ }
  } else {
    localStorage.removeItem(key);
  }
};

/**
 * Clear all stored values
 * @returns {Promise<void>}
 */
export const clear = async () => {
  if (isNative) {
    await Preferences.clear();
  } else {
    localStorage.clear();
  }
};

/**
 * Get all keys in storage
 * @returns {Promise<string[]>}
 */
export const keys = async () => {
  if (isNative) {
    const { keys: storedKeys } = await Preferences.keys();
    return storedKeys;
  }
  return Object.keys(localStorage);
};

/**
 * Get a JSON object from storage
 * @param {string} key - The key to retrieve
 * @returns {Promise<any|null>} - The parsed object or null
 */
export const getJSON = async (key) => {
  const value = await getItem(key);
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch (error) {
    console.error(`Error parsing JSON for key "${key}":`, error);
    return null;
  }
};

/**
 * Set a JSON object in storage
 * @param {string} key - The key to store
 * @param {any} value - The object to store
 * @returns {Promise<void>}
 */
export const setJSON = async (key, value) => {
  await setItem(key, JSON.stringify(value));
};

// Storage keys constants
export const STORAGE_KEYS = {
  TOKEN: 'token',
  REFRESH_TOKEN: 'refresh_token',
  USER: 'user',
  IMPERSONATION: 'impersonation',
  DASHBOARD_ORDER: 'dashboardOrder',
};

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
export const migrateTokensToSecureStorage = async () => {
  if (!isNative || _migrationDone) return;
  _migrationDone = true;

  const sensitiveKeys = [
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
export const clearAllAuthTokens = async () => {
  const authKeys = [
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
