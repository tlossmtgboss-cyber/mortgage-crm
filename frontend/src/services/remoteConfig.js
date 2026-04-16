/**
 * Remote Configuration Service
 *
 * Fetches and caches mobile app configuration from the backend,
 * allowing behavior changes without deploying new builds.
 *
 * - Fetches config from GET /api/v1/config/mobile on app launch
 * - Caches locally via Capacitor Preferences (native) or localStorage (web)
 * - Uses 1-hour TTL; serves cached config when offline
 * - Emits change events when remote config differs from previous
 * - Provides dot-notation access via getConfig('features.voiceAssistant')
 */

import { Capacitor } from '@capacitor/core';
import { getJSON, setJSON } from '../utils/storage';
import { getToken } from '../utils/tokenStore';

// Use the same base URL logic as api.js
const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API_BASE_URL = isLocalhost
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

// ---------------------------------------------------------------------------
// Storage keys
// ---------------------------------------------------------------------------
const STORAGE_KEY_CONFIG = 'remote_config';
const STORAGE_KEY_TIMESTAMP = 'remote_config_ts';

// 1-hour cache TTL
const CACHE_TTL_MS = 60 * 60 * 1000;

// ---------------------------------------------------------------------------
// Default configuration — used as the base layer. Remote values override these.
// ---------------------------------------------------------------------------
const DEFAULT_CONFIG = {
  // Feature flags
  features: {
    voiceAssistant: true,
    documentScanner: true,
    offlineMode: true,
    biometricLogin: true,
    pushNotifications: true,
    rateLockAlerts: true,
    darkMode: true,
  },
  // UI configuration
  ui: {
    mobileHomeScreen: 'dashboard', // 'dashboard' | 'aria' | 'pipeline'
    maxCacheSize: 10 * 1024 * 1024, // 10 MB
    syncInterval: 300000,            // 5 min
    animationsEnabled: true,
  },
  // Security
  security: {
    sessionTimeout: 900000,          // 15 min
    requireBiometric: false,
    allowScreenshots: true,
    maxLoginAttempts: 5,
    lockoutDuration: 300000,         // 5 min
  },
  // Maintenance mode
  maintenance: {
    enabled: false,
    message: '',
    estimatedEnd: null,
  },
};

// ---------------------------------------------------------------------------
// In-memory state
// ---------------------------------------------------------------------------
let _currentConfig = null;
let _cacheTimestamp = null;
let _listeners = [];
let _fetchPromise = null;

// ---------------------------------------------------------------------------
// Change-detection event bus
// ---------------------------------------------------------------------------

/**
 * Subscribe to config change events.
 * Callback receives { path, oldValue, newValue } for each changed key.
 * Returns an unsubscribe function.
 */
export function onConfigChange(callback) {
  _listeners.push(callback);
  return () => {
    _listeners = _listeners.filter((cb) => cb !== callback);
  };
}

function _emitChanges(changes) {
  if (!changes || changes.length === 0) return;
  for (const listener of _listeners) {
    try {
      listener(changes);
    } catch (err) {
      console.error('Remote config change listener error:', err);
    }
  }
}

// ---------------------------------------------------------------------------
// Deep merge + diff helpers
// ---------------------------------------------------------------------------

/**
 * Deep merge source into target. Source values override target values.
 * Returns a new object (does not mutate either argument).
 */
function deepMerge(target, source) {
  if (!source || typeof source !== 'object') return target;
  const result = { ...target };
  for (const key of Object.keys(source)) {
    if (
      source[key] !== null &&
      typeof source[key] === 'object' &&
      !Array.isArray(source[key]) &&
      typeof result[key] === 'object' &&
      result[key] !== null &&
      !Array.isArray(result[key])
    ) {
      result[key] = deepMerge(result[key], source[key]);
    } else {
      result[key] = source[key];
    }
  }
  return result;
}

/**
 * Compute flat list of changed paths between two config objects.
 * Returns [{ path, oldValue, newValue }, ...]
 */
function diffConfigs(prev, next, prefix = '') {
  const changes = [];
  if (!prev || !next) return changes;

  const allKeys = new Set([...Object.keys(prev), ...Object.keys(next)]);
  for (const key of allKeys) {
    const path = prefix ? `${prefix}.${key}` : key;
    const oldVal = prev[key];
    const newVal = next[key];

    if (
      oldVal !== null &&
      typeof oldVal === 'object' &&
      !Array.isArray(oldVal) &&
      newVal !== null &&
      typeof newVal === 'object' &&
      !Array.isArray(newVal)
    ) {
      changes.push(...diffConfigs(oldVal, newVal, path));
    } else if (JSON.stringify(oldVal) !== JSON.stringify(newVal)) {
      changes.push({ path, oldValue: oldVal, newValue: newVal });
    }
  }
  return changes;
}

// ---------------------------------------------------------------------------
// Dot-notation accessor
// ---------------------------------------------------------------------------

/**
 * Resolve a dot-notation path against an object.
 *   _resolve(config, 'features.voiceAssistant') -> true
 */
function _resolve(obj, path) {
  if (!path) return obj;
  return path.split('.').reduce((acc, part) => {
    if (acc === undefined || acc === null) return undefined;
    return acc[part];
  }, obj);
}

// ---------------------------------------------------------------------------
// Cache management
// ---------------------------------------------------------------------------

async function _loadFromCache() {
  try {
    const config = await getJSON(STORAGE_KEY_CONFIG);
    const tsRaw = await getJSON(STORAGE_KEY_TIMESTAMP);
    if (config && tsRaw) {
      _currentConfig = config;
      _cacheTimestamp = tsRaw;
      return true;
    }
  } catch (err) {
    console.warn('Failed to load remote config from cache:', err);
  }
  return false;
}

async function _saveToCache(config) {
  try {
    await setJSON(STORAGE_KEY_CONFIG, config);
    await setJSON(STORAGE_KEY_TIMESTAMP, Date.now());
    _cacheTimestamp = Date.now();
  } catch (err) {
    console.warn('Failed to save remote config to cache:', err);
  }
}

function _isCacheValid() {
  return _currentConfig && _cacheTimestamp && (Date.now() - _cacheTimestamp < CACHE_TTL_MS);
}

// ---------------------------------------------------------------------------
// Network fetch
// ---------------------------------------------------------------------------

async function _fetchRemoteConfig() {
  const url = `${API_BASE_URL}/api/v1/config/mobile`;
  const headers = { 'Content-Type': 'application/json' };

  // Include auth token if available (allows org-specific config)
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Identify mobile app requests
  if (Capacitor.isNativePlatform()) {
    headers['X-Mobile-App'] = 'capacitor-ios';
  }

  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`Remote config fetch failed: ${response.status}`);
  }
  const data = await response.json();
  return data.config || data;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Initialize the remote config service.
 * Should be called once on app launch.
 *
 * 1. Loads cached config from Preferences/localStorage
 * 2. Merges defaults as the base layer
 * 3. Fetches fresh config from the server (non-blocking if cache exists)
 *
 * @param {Object} options
 * @param {boolean} options.forceRefresh - Skip cache and always fetch
 * @returns {Promise<Object>} The resolved config
 */
export async function initialize({ forceRefresh = false } = {}) {
  // Load cache first for instant availability
  if (!_currentConfig) {
    await _loadFromCache();
  }

  // Apply defaults as the base layer
  if (!_currentConfig) {
    _currentConfig = { ...DEFAULT_CONFIG };
  } else {
    _currentConfig = deepMerge(DEFAULT_CONFIG, _currentConfig);
  }

  // Fetch fresh config
  if (forceRefresh || !_isCacheValid()) {
    // Don't await if we already have a cached config — fetch in background
    const fetchTask = refreshConfig();
    if (!_cacheTimestamp) {
      // No cache at all — must wait
      await fetchTask;
    }
  }

  return _currentConfig;
}

/**
 * Force-refresh config from the server.
 * Detects changes and emits events.
 */
export async function refreshConfig() {
  // Deduplicate concurrent fetches
  if (_fetchPromise) return _fetchPromise;

  _fetchPromise = (async () => {
    try {
      const remoteConfig = await _fetchRemoteConfig();
      const previousConfig = _currentConfig ? { ..._currentConfig } : null;
      const merged = deepMerge(DEFAULT_CONFIG, remoteConfig);

      // Detect changes
      if (previousConfig) {
        const changes = diffConfigs(previousConfig, merged);
        _emitChanges(changes);
      }

      _currentConfig = merged;
      await _saveToCache(merged);
      return merged;
    } catch (err) {
      console.warn('Failed to refresh remote config:', err);
      // Keep using cached/default config
      return _currentConfig;
    } finally {
      _fetchPromise = null;
    }
  })();

  return _fetchPromise;
}

/**
 * Get a config value by dot-notation path.
 *
 * @param {string} path - e.g. 'features.voiceAssistant', 'ui.syncInterval'
 * @param {*} defaultValue - Fallback if the path is not found
 * @returns {*} The config value
 *
 * @example
 *   getConfig('features.voiceAssistant') // true
 *   getConfig('ui.mobileHomeScreen')     // 'dashboard'
 *   getConfig('security.sessionTimeout') // 900000
 */
export function getConfig(path, defaultValue = undefined) {
  const config = _currentConfig || DEFAULT_CONFIG;
  const value = _resolve(config, path);
  return value !== undefined ? value : defaultValue;
}

/**
 * Shorthand to check if a feature flag is enabled.
 *
 * @param {string} feature - Feature name (key under `features.*`)
 * @returns {boolean}
 *
 * @example
 *   isFeatureEnabled('voiceAssistant')   // true
 *   isFeatureEnabled('darkMode')         // true
 */
export function isFeatureEnabled(feature) {
  return getConfig(`features.${feature}`, false) === true;
}

/**
 * Check if the app is in maintenance mode.
 * This is the first thing the app should check on launch.
 */
export function isMaintenanceMode() {
  return getConfig('maintenance.enabled', false) === true;
}

/**
 * Get the maintenance message (if any).
 */
export function getMaintenanceInfo() {
  return {
    enabled: getConfig('maintenance.enabled', false),
    message: getConfig('maintenance.message', ''),
    estimatedEnd: getConfig('maintenance.estimatedEnd', null),
  };
}

/**
 * Get the full resolved config object.
 * Returns a shallow copy to prevent external mutation.
 */
export function getFullConfig() {
  return { ...(_currentConfig || DEFAULT_CONFIG) };
}

/**
 * Clear cached config. Useful on logout.
 */
export async function clearConfig() {
  _currentConfig = null;
  _cacheTimestamp = null;
  _listeners = [];
  try {
    const { removeItem } = await import('../utils/storage');
    await removeItem(STORAGE_KEY_CONFIG);
    await removeItem(STORAGE_KEY_TIMESTAMP);
  } catch (err) {
    console.warn('Failed to clear remote config cache:', err);
  }
}

// ---------------------------------------------------------------------------
// Default export — all public functions
// ---------------------------------------------------------------------------
export default {
  initialize,
  refreshConfig,
  getConfig,
  isFeatureEnabled,
  isMaintenanceMode,
  getMaintenanceInfo,
  getFullConfig,
  clearConfig,
  onConfigChange,
  DEFAULT_CONFIG,
};
