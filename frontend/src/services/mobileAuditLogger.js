/**
 * Mobile Audit Logger
 *
 * Enterprise compliance audit logging for the Perennia AI mobile app.
 * Tracks who accessed what sensitive data, from which device, and when.
 *
 * Privacy: Never logs actual PII values -- only entity IDs and access types.
 * Performance: Async, non-blocking, never delays user interactions.
 * Offline: Buffers events in Preferences, sends when reconnected.
 *
 * Usage:
 *   import { initAuditLogger, auditLog, AUDIT_EVENTS } from './mobileAuditLogger';
 *   await initAuditLogger(userId, organizationId);
 *   auditLog(AUDIT_EVENTS.LOAN_VIEWED, { loanId: '...', loanNumber: '...' });
 */

import { Capacitor } from '@capacitor/core';
import api from './api';

// ---------------------------------------------------------------------------
// Audit event constants
// ---------------------------------------------------------------------------

export const AUDIT_EVENTS = {
  // Authentication
  LOGIN_SUCCESS: 'auth.login.success',
  LOGIN_FAILED: 'auth.login.failed',
  BIOMETRIC_AUTH: 'auth.biometric',
  LOGOUT: 'auth.logout',
  SESSION_EXPIRED: 'auth.session_expired',

  // Data access
  LOAN_VIEWED: 'data.loan.viewed',
  LEAD_VIEWED: 'data.lead.viewed',
  DOCUMENT_VIEWED: 'data.document.viewed',
  DOCUMENT_DOWNLOADED: 'data.document.downloaded',
  PII_ACCESSED: 'data.pii.accessed',

  // Data modification
  LEAD_CREATED: 'data.lead.created',
  LEAD_UPDATED: 'data.lead.updated',
  LOAN_UPDATED: 'data.loan.updated',
  DOCUMENT_UPLOADED: 'data.document.uploaded',

  // Security
  SCREENSHOT_DETECTED: 'security.screenshot',
  JAILBREAK_DETECTED: 'security.jailbreak',
  PIN_FAILURE: 'security.cert_pin_failure',
  OFFLINE_MUTATION: 'security.offline_mutation',

  // App lifecycle
  APP_OPENED: 'app.opened',
  APP_BACKGROUNDED: 'app.backgrounded',
  DEEP_LINK_OPENED: 'app.deeplink',
};

// ---------------------------------------------------------------------------
// Internal state
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'audit_log_buffer';
const FLUSH_INTERVAL_MS = 30_000; // 30 seconds
const FLUSH_THRESHOLD = 20; // events before forced flush
const MAX_STORED_EVENTS = 500; // cap offline buffer to prevent storage exhaustion
const BATCH_ENDPOINT = '/api/v1/audit/mobile-events';

let _buffer = [];
let _userId = null;
let _organizationId = null;
let _sessionId = null;
let _deviceId = null;
let _platform = 'web';
let _appVersion = null;
let _flushTimer = null;
let _initialized = false;
let _flushing = false;
let _networkListenerCleanup = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Generate a UUID-v4-ish identifier.
 * crypto.randomUUID is available in modern browsers and iOS WKWebView.
 */
function generateId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for older environments
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Derive a stable device fingerprint from available signals.
 * On native, uses Capacitor device info stored once; on web, uses a
 * stored identifier so it persists across sessions.
 */
async function resolveDeviceId() {
  try {
    const storage = await getStorage();
    const existing = await storageGet(storage, 'audit_device_id');
    if (existing) return existing;

    // Generate and persist a new device id
    const id = generateId();
    await storageSet(storage, 'audit_device_id', id);
    return id;
  } catch (e) {
    // Non-fatal -- return a transient id
    return 'unknown-' + generateId().slice(0, 8);
  }
}

/**
 * Get app version. Uses package.json version on web,
 * App.getInfo() on native.
 */
async function resolveAppVersion() {
  if (Capacitor.isNativePlatform()) {
    try {
      const { App } = await import('@capacitor/app');
      const info = await App.getInfo();
      return info.version || info.build || '1.0.0';
    } catch (e) {
      // Fallback if App plugin unavailable
    }
  }
  // Fallback to REACT_APP env or hardcoded from package.json
  return process.env.REACT_APP_VERSION || '1.0.2';
}

// ---------------------------------------------------------------------------
// Cross-platform storage (mirrors useOfflineCache pattern)
// ---------------------------------------------------------------------------

async function getStorage() {
  if (Capacitor.isNativePlatform()) {
    const { Preferences } = await import('@capacitor/preferences');
    return { type: 'native', Preferences };
  }
  return { type: 'web' };
}

async function storageGet(storage, key) {
  if (storage.type === 'native') {
    const { value } = await storage.Preferences.get({ key });
    return value;
  }
  return localStorage.getItem(key);
}

async function storageSet(storage, key, value) {
  if (storage.type === 'native') {
    await storage.Preferences.set({ key, value });
  } else {
    try {
      localStorage.setItem(key, value);
    } catch (_) {
      // localStorage full -- silently drop (audit is best-effort)
    }
  }
}

async function storageRemove(storage, key) {
  if (storage.type === 'native') {
    await storage.Preferences.remove({ key });
  } else {
    localStorage.removeItem(key);
  }
}

// ---------------------------------------------------------------------------
// Offline persistence
// ---------------------------------------------------------------------------

async function persistBuffer() {
  if (_buffer.length === 0) return;
  try {
    const storage = await getStorage();
    // Merge with any events already persisted (e.g. from a previous crash)
    const existingRaw = await storageGet(storage, STORAGE_KEY);
    let merged = _buffer;
    if (existingRaw) {
      try {
        const existing = JSON.parse(existingRaw);
        if (Array.isArray(existing)) {
          merged = existing.concat(_buffer);
        }
      } catch (_) {
        // Corrupted data -- overwrite
      }
    }
    // Cap to prevent storage exhaustion
    if (merged.length > MAX_STORED_EVENTS) {
      merged = merged.slice(merged.length - MAX_STORED_EVENTS);
    }
    await storageSet(storage, STORAGE_KEY, JSON.stringify(merged));
  } catch (e) {
    // Best-effort -- don't crash the app for audit persistence failures
  }
}

async function loadPersistedBuffer() {
  try {
    const storage = await getStorage();
    const raw = await storageGet(storage, STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (e) {
    return [];
  }
}

async function clearPersistedBuffer() {
  try {
    const storage = await getStorage();
    await storageRemove(storage, STORAGE_KEY);
  } catch (_) {
    // Best-effort
  }
}

// ---------------------------------------------------------------------------
// Network awareness
// ---------------------------------------------------------------------------

function isOnline() {
  if (typeof navigator !== 'undefined' && typeof navigator.onLine === 'boolean') {
    return navigator.onLine;
  }
  return true; // Assume online if we can't tell
}

async function setupNetworkListener() {
  if (Capacitor.isNativePlatform()) {
    try {
      const { Network } = await import('@capacitor/network');
      const listener = await Network.addListener('networkStatusChange', (status) => {
        if (status.connected) {
          // Came back online -- flush buffered events
          flush();
        }
      });
      _networkListenerCleanup = () => listener.remove();
    } catch (e) {
      // Network plugin not available -- fall back to window events
      setupWebNetworkListener();
    }
  } else {
    setupWebNetworkListener();
  }
}

function setupWebNetworkListener() {
  const handler = () => flush();
  window.addEventListener('online', handler);
  _networkListenerCleanup = () => window.removeEventListener('online', handler);
}

// ---------------------------------------------------------------------------
// Flush logic
// ---------------------------------------------------------------------------

async function flush() {
  if (_flushing || _buffer.length === 0) return;
  if (!isOnline()) {
    // Persist for later
    await persistBuffer();
    return;
  }

  _flushing = true;

  // Grab current buffer + any persisted events from previous sessions
  const persisted = await loadPersistedBuffer();
  const allEvents = persisted.concat(_buffer);

  // Clear in-memory buffer immediately so new events don't get lost
  _buffer = [];
  await clearPersistedBuffer();

  if (allEvents.length === 0) {
    _flushing = false;
    return;
  }

  try {
    await api.post(BATCH_ENDPOINT, { events: allEvents });
  } catch (e) {
    // Send failed -- put events back for retry
    _buffer = allEvents.concat(_buffer);
    // Cap buffer size
    if (_buffer.length > MAX_STORED_EVENTS) {
      _buffer = _buffer.slice(_buffer.length - MAX_STORED_EVENTS);
    }
    // Persist so they survive app kills
    await persistBuffer();
  } finally {
    _flushing = false;
  }
}

function startFlushTimer() {
  stopFlushTimer();
  _flushTimer = setInterval(() => {
    flush();
  }, FLUSH_INTERVAL_MS);
}

function stopFlushTimer() {
  if (_flushTimer !== null) {
    clearInterval(_flushTimer);
    _flushTimer = null;
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Initialize the audit logger. Call once after the user authenticates.
 *
 * @param {string} userId - Current user UUID
 * @param {string} organizationId - Current org UUID
 */
export async function initAuditLogger(userId, organizationId) {
  _userId = userId;
  _organizationId = organizationId;
  _sessionId = generateId();
  _platform = Capacitor.getPlatform(); // 'ios', 'android', or 'web'

  // Resolve device id and app version in parallel (non-blocking)
  const [deviceId, appVersion] = await Promise.all([
    resolveDeviceId(),
    resolveAppVersion(),
  ]);
  _deviceId = deviceId;
  _appVersion = appVersion;

  // Load any events that were persisted while offline
  const persisted = await loadPersistedBuffer();
  if (persisted.length > 0) {
    _buffer = persisted.concat(_buffer);
    await clearPersistedBuffer();
  }

  await setupNetworkListener();
  startFlushTimer();
  _initialized = true;
}

/**
 * Log an audit event. This is fire-and-forget -- it never throws
 * and never blocks the caller.
 *
 * @param {string} event - One of AUDIT_EVENTS values
 * @param {Object} [metadata={}] - Entity IDs and context (never PII values)
 */
export function auditLog(event, metadata = {}) {
  // Fire-and-forget: wrap in a microtask so we never delay the caller
  Promise.resolve().then(() => {
    try {
      const entry = {
        event,
        timestamp: new Date().toISOString(),
        userId: _userId,
        organizationId: _organizationId,
        deviceId: _deviceId,
        platform: _platform,
        appVersion: _appVersion,
        metadata,
        sessionId: _sessionId,
        ipAddress: null, // Filled by server
      };

      _buffer.push(entry);

      // Flush immediately if threshold reached
      if (_buffer.length >= FLUSH_THRESHOLD) {
        flush();
      }
    } catch (_) {
      // Never let audit logging crash the app
    }
  });
}

/**
 * Tear down the logger (e.g. on logout). Flushes remaining events
 * and cleans up timers and listeners.
 */
export async function destroyAuditLogger() {
  stopFlushTimer();

  // Final flush attempt
  if (_buffer.length > 0) {
    if (isOnline()) {
      await flush();
    } else {
      await persistBuffer();
    }
  }

  if (_networkListenerCleanup) {
    _networkListenerCleanup();
    _networkListenerCleanup = null;
  }

  _userId = null;
  _organizationId = null;
  _sessionId = null;
  _initialized = false;
  _buffer = [];
}

/**
 * Returns whether the logger has been initialized.
 */
export function isAuditLoggerInitialized() {
  return _initialized;
}

/**
 * Returns the current session ID (useful for correlation).
 */
export function getAuditSessionId() {
  return _sessionId;
}

export default {
  initAuditLogger,
  auditLog,
  destroyAuditLogger,
  isAuditLoggerInitialized,
  getAuditSessionId,
  AUDIT_EVENTS,
};
