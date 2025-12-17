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
  USER: 'user',
  IMPERSONATION: 'impersonation',
  DASHBOARD_ORDER: 'dashboardOrder',
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
};
