/**
 * Mobile Analytics Tracking Service
 *
 * Tracks user behavior in the Perennia AI mobile app to understand how LOs
 * use the product. Buffers events locally and sends in batches.
 *
 * Privacy: No PII is collected. Only entity IDs, screen names, and action
 * categories are tracked. Users can opt out via preferences.
 *
 * Exports: initAnalytics, trackScreen, trackAction, trackError,
 *          startFunnel, completeFunnelStep, getSessionSummary, shutdownAnalytics
 */

import { Capacitor } from '@capacitor/core';
import { Network } from '@capacitor/network';
import { Preferences } from '@capacitor/preferences';
import { App } from '@capacitor/app';
import { axiosInstance } from './api';
import { isAuthenticated } from '../utils/tokenStore';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FLUSH_INTERVAL_MS = 30_000; // 30 seconds
const MAX_BUFFER_SIZE = 200; // flush early if buffer gets large
const SESSION_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes of inactivity = new session
const STORAGE_KEY_OPT_OUT = 'perennia_analytics_opt_out';
const STORAGE_KEY_PENDING = 'perennia_analytics_pending';

// ---------------------------------------------------------------------------
// Internal state
// ---------------------------------------------------------------------------

let _initialized = false;
let _optedOut = false;
let _session = null;
let _eventBuffer = [];
let _flushTimer = null;
let _currentScreen = null;
let _currentScreenStartedAt = null;
let _previousScreen = null;
let _sessionStartedAt = null;
let _lastActivityAt = null;
let _firstActionRecorded = false;
let _loginTimestamp = null;
let _activeFunnels = {};
let _appStateListener = null;
let _networkListener = null;

// ---------------------------------------------------------------------------
// UUID helper (no external dependency)
// ---------------------------------------------------------------------------

function generateId() {
  // crypto.randomUUID available in modern browsers and iOS WKWebView
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

// ---------------------------------------------------------------------------
// Device info (collected once at init)
// ---------------------------------------------------------------------------

function collectDeviceInfo() {
  const ua = navigator.userAgent;

  // Extract iOS model from UA string if available
  let deviceModel = 'unknown';
  const iosMatch = ua.match(/\((iPhone|iPad|iPod)[^)]*\)/);
  if (iosMatch) {
    deviceModel = iosMatch[1];
  } else if (/Android/.test(ua)) {
    const androidMatch = ua.match(/;\s*([^;)]+)\s*Build/);
    deviceModel = androidMatch ? androidMatch[1].trim() : 'Android';
  }

  // OS version
  let osVersion = 'unknown';
  const iosVersionMatch = ua.match(/OS (\d+[_.\d]*)/);
  if (iosVersionMatch) {
    osVersion = iosVersionMatch[1].replace(/_/g, '.');
  } else {
    const androidVersionMatch = ua.match(/Android (\d+[.\d]*)/);
    if (androidVersionMatch) {
      osVersion = androidVersionMatch[1];
    }
  }

  return {
    platform: Capacitor.getPlatform(), // 'ios', 'android', 'web'
    appVersion: '1.0.2', // matches package.json
    deviceModel,
    osVersion,
    screenSize: `${window.screen.width}x${window.screen.height}`,
    isNative: Capacitor.isNativePlatform(),
  };
}

// ---------------------------------------------------------------------------
// Session management
// ---------------------------------------------------------------------------

function createSession(userId) {
  const device = collectDeviceInfo();
  const now = new Date().toISOString();

  _session = {
    sessionId: generateId(),
    userId: userId || null,
    startTime: now,
    platform: device.platform,
    appVersion: device.appVersion,
    deviceModel: device.deviceModel,
    osVersion: device.osVersion,
    screenSize: device.screenSize,
    connectionType: 'unknown', // updated async below
    screens: [],
    actions: [],
    duration: 0,
  };

  _sessionStartedAt = Date.now();
  _lastActivityAt = Date.now();
  _firstActionRecorded = false;
  _loginTimestamp = Date.now();
  _currentScreen = null;
  _currentScreenStartedAt = null;
  _previousScreen = null;
  _activeFunnels = {};

  // Fetch connection type asynchronously
  Network.getStatus().then((status) => {
    if (_session) {
      _session.connectionType = status.connected
        ? status.connectionType // 'wifi', 'cellular', 'none', 'unknown'
        : 'none';
    }
  }).catch(() => {
    // Non-critical, leave as unknown
  });

  return _session;
}

function ensureSession(userId) {
  const now = Date.now();
  // Start new session if none exists or if timed out
  if (!_session || (now - _lastActivityAt > SESSION_TIMEOUT_MS)) {
    // Flush old session data before creating new one
    if (_session && _eventBuffer.length > 0) {
      flush();
    }
    createSession(userId);
  }
  _lastActivityAt = now;
  return _session;
}

// ---------------------------------------------------------------------------
// Event buffering and flushing
// ---------------------------------------------------------------------------

function bufferEvent(event) {
  if (_optedOut) return;

  _eventBuffer.push(event);

  // Flush early if buffer is getting large
  if (_eventBuffer.length >= MAX_BUFFER_SIZE) {
    flush();
  }
}

async function flush() {
  if (_eventBuffer.length === 0 || _optedOut) return;

  // Snapshot and clear the buffer atomically
  const events = _eventBuffer.splice(0);

  // Update session duration
  if (_session && _sessionStartedAt) {
    _session.duration = Math.round((Date.now() - _sessionStartedAt) / 1000);
  }

  const payload = {
    session: _session ? { ..._session } : null,
    events,
    sentAt: new Date().toISOString(),
  };

  try {
    if (!isAuthenticated()) {
      // No auth token -- persist events for later
      await persistPendingEvents(events);
      return;
    }

    const networkStatus = await Network.getStatus().catch(() => ({ connected: true }));
    if (!networkStatus.connected) {
      await persistPendingEvents(events);
      return;
    }

    await axiosInstance.post('/api/v1/analytics/mobile', payload);
  } catch (error) {
    // Network error -- persist for retry
    await persistPendingEvents(events);
    if (process.env.NODE_ENV === 'development') {
      console.warn('[MobileAnalytics] Flush failed, events persisted locally:', error.message);
    }
  }
}

async function persistPendingEvents(events) {
  try {
    const { value } = await Preferences.get({ key: STORAGE_KEY_PENDING });
    const existing = value ? JSON.parse(value) : [];
    // Cap stored events to prevent unbounded growth
    const combined = [...existing, ...events].slice(-500);
    await Preferences.set({
      key: STORAGE_KEY_PENDING,
      value: JSON.stringify(combined),
    });
  } catch (error) {
    // If preferences are unavailable, silently drop
    if (process.env.NODE_ENV === 'development') {
      console.warn('[MobileAnalytics] Could not persist pending events:', error.message);
    }
  }
}

async function retryPendingEvents() {
  try {
    const { value } = await Preferences.get({ key: STORAGE_KEY_PENDING });
    if (!value) return;

    const pending = JSON.parse(value);
    if (pending.length === 0) return;

    // Clear storage first to avoid duplicate retries
    await Preferences.remove({ key: STORAGE_KEY_PENDING });

    // Re-buffer so they go out with the next flush
    _eventBuffer.push(...pending);
  } catch (error) {
    // Non-critical
  }
}

function startFlushTimer() {
  stopFlushTimer();
  _flushTimer = setInterval(() => {
    flush();
  }, FLUSH_INTERVAL_MS);
}

function stopFlushTimer() {
  if (_flushTimer) {
    clearInterval(_flushTimer);
    _flushTimer = null;
  }
}

// ---------------------------------------------------------------------------
// Error tracking setup
// ---------------------------------------------------------------------------

function installErrorHandlers() {
  // Global JS errors
  const originalOnError = window.onerror;
  window.onerror = (message, source, lineno, colno, error) => {
    trackError('js_error', {
      message: String(message).slice(0, 200),
      source: source ? source.split('/').pop() : 'unknown',
      line: lineno,
      column: colno,
      stack: error?.stack ? error.stack.slice(0, 300) : undefined,
    });
    if (originalOnError) {
      return originalOnError(message, source, lineno, colno, error);
    }
    return false;
  };

  // Unhandled promise rejections
  const originalOnUnhandledRejection = window.onunhandledrejection;
  window.onunhandledrejection = (event) => {
    const reason = event.reason;
    trackError('unhandled_rejection', {
      message: reason?.message ? String(reason.message).slice(0, 200) : 'Unknown rejection',
      stack: reason?.stack ? reason.stack.slice(0, 300) : undefined,
    });
    if (originalOnUnhandledRejection) {
      return originalOnUnhandledRejection.call(window, event);
    }
  };
}

// ---------------------------------------------------------------------------
// App lifecycle listeners
// ---------------------------------------------------------------------------

function installLifecycleListeners() {
  // Track app going to background / returning to foreground
  if (Capacitor.isNativePlatform()) {
    _appStateListener = App.addListener('appStateChange', ({ isActive }) => {
      if (isActive) {
        // App returned to foreground
        ensureSession(_session?.userId);
        startFlushTimer();
        retryPendingEvents();
        bufferEvent({
          type: 'lifecycle',
          action: 'app_foreground',
          timestamp: new Date().toISOString(),
        });
      } else {
        // App going to background -- flush immediately
        bufferEvent({
          type: 'lifecycle',
          action: 'app_background',
          timestamp: new Date().toISOString(),
        });
        flush();
        stopFlushTimer();
      }
    });
  }

  // Listen for network changes
  _networkListener = Network.addListener('networkStatusChange', (status) => {
    if (_session) {
      _session.connectionType = status.connected ? status.connectionType : 'none';
    }
    // When coming back online, retry pending events
    if (status.connected) {
      retryPendingEvents();
    }
  });
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Initialize the mobile analytics service.
 * Call once at app startup, after the user has logged in.
 *
 * @param {Object} options
 * @param {string} options.userId - Opaque user ID (UUID). No PII.
 */
export async function initAnalytics({ userId } = {}) {
  if (_initialized) return;

  // Check opt-out preference
  try {
    const { value } = await Preferences.get({ key: STORAGE_KEY_OPT_OUT });
    if (value === 'true') {
      _optedOut = true;
      _initialized = true;
      return;
    }
  } catch (error) {
    // Preferences might not be available on web -- continue
  }

  createSession(userId);
  installErrorHandlers();
  installLifecycleListeners();
  startFlushTimer();

  // Retry any events that were persisted from a previous session
  await retryPendingEvents();

  _initialized = true;

  if (process.env.NODE_ENV === 'development') {
    console.log('[MobileAnalytics] Initialized', {
      sessionId: _session.sessionId,
      platform: _session.platform,
      device: _session.deviceModel,
    });
  }
}

/**
 * Track a screen view.
 * Automatically measures time spent on the previous screen and builds
 * the session navigation flow.
 *
 * @param {string} screenName - e.g. 'MobilePipeline', 'LoanDetail'
 * @param {Object} metadata - Additional context (no PII)
 */
export function trackScreen(screenName, metadata = {}) {
  if (_optedOut || !_initialized) return;

  const now = Date.now();
  const session = ensureSession(_session?.userId);

  // Close out previous screen with duration
  if (_currentScreen && _currentScreenStartedAt) {
    const durationMs = now - _currentScreenStartedAt;
    const screenRecord = {
      name: _currentScreen,
      duration: Math.round(durationMs / 1000),
      exitedAt: new Date().toISOString(),
    };
    session.screens.push(screenRecord);
  }

  _previousScreen = _currentScreen;
  _currentScreen = screenName;
  _currentScreenStartedAt = now;

  bufferEvent({
    type: 'screen',
    screen: screenName,
    previousScreen: _previousScreen,
    timestamp: new Date().toISOString(),
    metadata: sanitizeMetadata(metadata),
  });

  if (process.env.NODE_ENV === 'development') {
    console.log('[MobileAnalytics] Screen:', screenName, metadata);
  }
}

/**
 * Track a user action.
 *
 * @param {string} action - e.g. 'quick_add_lead', 'tap_pipeline_card'
 * @param {string} category - One of: 'navigation', 'engagement', 'feature_use', 'error'
 * @param {Object} metadata - Additional context (no PII)
 */
export function trackAction(action, category, metadata = {}) {
  if (_optedOut || !_initialized) return;

  const VALID_CATEGORIES = ['navigation', 'engagement', 'feature_use', 'error'];
  const safeCategory = VALID_CATEGORIES.includes(category) ? category : 'engagement';

  const session = ensureSession(_session?.userId);

  // Time-to-first-action metric
  let timeToFirstAction = null;
  if (!_firstActionRecorded && _loginTimestamp) {
    timeToFirstAction = Math.round((Date.now() - _loginTimestamp) / 1000);
    _firstActionRecorded = true;
  }

  const event = {
    type: 'action',
    action,
    category: safeCategory,
    screen: _currentScreen,
    timestamp: new Date().toISOString(),
    metadata: sanitizeMetadata(metadata),
  };

  if (timeToFirstAction !== null) {
    event.timeToFirstAction = timeToFirstAction;
  }

  // Track in session actions summary
  session.actions.push({
    action,
    category: safeCategory,
    screen: _currentScreen,
    timestamp: event.timestamp,
  });

  bufferEvent(event);

  if (process.env.NODE_ENV === 'development') {
    console.log('[MobileAnalytics] Action:', action, safeCategory, metadata);
  }
}

/**
 * Track an error event.
 * For API errors, JS errors, network timeouts, etc.
 *
 * @param {string} errorType - e.g. 'api_error', 'js_error', 'network_timeout', 'unhandled_rejection'
 * @param {Object} details - Error details (no PII). Auto-truncated.
 */
export function trackError(errorType, details = {}) {
  if (_optedOut) return;
  // Allow error tracking even before full init, as errors can happen early

  const event = {
    type: 'error',
    errorType,
    screen: _currentScreen,
    timestamp: new Date().toISOString(),
    details: {
      ...sanitizeMetadata(details),
      // Truncate any string values to prevent oversized payloads
      message: details.message ? String(details.message).slice(0, 200) : undefined,
      stack: details.stack ? String(details.stack).slice(0, 300) : undefined,
    },
  };

  bufferEvent(event);

  if (process.env.NODE_ENV === 'development') {
    console.log('[MobileAnalytics] Error:', errorType, details);
  }
}

/**
 * Track an API error from a response object.
 * Convenience wrapper for tracking HTTP errors without PII.
 *
 * @param {number} status - HTTP status code
 * @param {string} endpoint - API path (stripped of query params)
 * @param {string} method - HTTP method
 */
export function trackApiError(status, endpoint, method = 'GET') {
  // Strip query params which may contain PII
  const cleanEndpoint = endpoint ? endpoint.split('?')[0] : 'unknown';
  trackError('api_error', {
    status,
    endpoint: cleanEndpoint,
    method,
  });
}

/**
 * Start tracking a multi-step funnel.
 * Useful for understanding where users drop off in flows like lead creation.
 *
 * @param {string} funnelName - e.g. 'lead_creation', 'loan_application'
 * @param {string[]} steps - Ordered step names
 */
export function startFunnel(funnelName, steps) {
  if (_optedOut || !_initialized) return;

  _activeFunnels[funnelName] = {
    name: funnelName,
    steps,
    completedSteps: [],
    startedAt: new Date().toISOString(),
    startTimestamp: Date.now(),
  };

  bufferEvent({
    type: 'funnel',
    action: 'start',
    funnel: funnelName,
    totalSteps: steps.length,
    steps,
    timestamp: new Date().toISOString(),
  });

  if (process.env.NODE_ENV === 'development') {
    console.log('[MobileAnalytics] Funnel started:', funnelName, steps);
  }
}

/**
 * Record completion of a funnel step.
 *
 * @param {string} funnelName - Must match a previously started funnel
 * @param {string} stepName - The step that was completed
 */
export function completeFunnelStep(funnelName, stepName) {
  if (_optedOut || !_initialized) return;

  const funnel = _activeFunnels[funnelName];
  if (!funnel) {
    if (process.env.NODE_ENV === 'development') {
      console.warn('[MobileAnalytics] completeFunnelStep: no active funnel', funnelName);
    }
    return;
  }

  // Avoid duplicate step completion
  if (funnel.completedSteps.includes(stepName)) return;

  funnel.completedSteps.push(stepName);

  const stepIndex = funnel.steps.indexOf(stepName);
  const isComplete = funnel.completedSteps.length === funnel.steps.length;
  const elapsedMs = Date.now() - funnel.startTimestamp;

  bufferEvent({
    type: 'funnel',
    action: 'step_complete',
    funnel: funnelName,
    step: stepName,
    stepIndex,
    completedCount: funnel.completedSteps.length,
    totalSteps: funnel.steps.length,
    elapsedSeconds: Math.round(elapsedMs / 1000),
    timestamp: new Date().toISOString(),
  });

  if (isComplete) {
    bufferEvent({
      type: 'funnel',
      action: 'complete',
      funnel: funnelName,
      totalSeconds: Math.round(elapsedMs / 1000),
      timestamp: new Date().toISOString(),
    });
    delete _activeFunnels[funnelName];
  }

  if (process.env.NODE_ENV === 'development') {
    console.log('[MobileAnalytics] Funnel step:', funnelName, stepName,
      `(${funnel.completedSteps.length}/${funnel.steps.length})`,
      isComplete ? '-- COMPLETE' : '');
  }
}

/**
 * Abandon a funnel (user navigated away without completing).
 * Automatically records which step they dropped off at.
 *
 * @param {string} funnelName - The funnel to abandon
 */
export function abandonFunnel(funnelName) {
  if (_optedOut || !_initialized) return;

  const funnel = _activeFunnels[funnelName];
  if (!funnel) return;

  const elapsedMs = Date.now() - funnel.startTimestamp;
  const lastCompletedStep = funnel.completedSteps.length > 0
    ? funnel.completedSteps[funnel.completedSteps.length - 1]
    : null;

  // Determine which step they dropped off at
  const lastCompletedIndex = lastCompletedStep
    ? funnel.steps.indexOf(lastCompletedStep)
    : -1;
  const droppedAtStep = lastCompletedIndex + 1 < funnel.steps.length
    ? funnel.steps[lastCompletedIndex + 1]
    : null;

  bufferEvent({
    type: 'funnel',
    action: 'abandon',
    funnel: funnelName,
    completedSteps: funnel.completedSteps.length,
    totalSteps: funnel.steps.length,
    lastCompletedStep,
    droppedAtStep,
    elapsedSeconds: Math.round(elapsedMs / 1000),
    timestamp: new Date().toISOString(),
  });

  delete _activeFunnels[funnelName];
}

/**
 * Get a summary of the current session for debugging or display.
 * Returns null if analytics is opted out or not initialized.
 *
 * @returns {Object|null}
 */
export function getSessionSummary() {
  if (_optedOut || !_session) return null;

  const duration = _sessionStartedAt
    ? Math.round((Date.now() - _sessionStartedAt) / 1000)
    : 0;

  // Count feature usage by action
  const featureCounts = {};
  for (const action of _session.actions) {
    featureCounts[action.action] = (featureCounts[action.action] || 0) + 1;
  }

  // Sort by most used
  const mostUsedFeatures = Object.entries(featureCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([feature, count]) => ({ feature, count }));

  // Count quick action (FAB) usage
  const quickActionCount = _session.actions
    .filter((a) => a.category === 'engagement' && a.action.startsWith('quick_'))
    .length;

  return {
    sessionId: _session.sessionId,
    duration,
    screenCount: _session.screens.length + (_currentScreen ? 1 : 0),
    actionCount: _session.actions.length,
    errorCount: _eventBuffer.filter((e) => e.type === 'error').length,
    mostUsedFeatures,
    quickActionCount,
    currentScreen: _currentScreen,
    connectionType: _session.connectionType,
    activeFunnels: Object.keys(_activeFunnels),
    bufferedEvents: _eventBuffer.length,
  };
}

/**
 * Set the user's analytics opt-out preference.
 *
 * @param {boolean} optOut - true to disable analytics collection
 */
export async function setOptOut(optOut) {
  _optedOut = optOut;
  try {
    await Preferences.set({
      key: STORAGE_KEY_OPT_OUT,
      value: String(optOut),
    });
  } catch (error) {
    // Non-critical
  }

  if (optOut) {
    // Clear any buffered data
    _eventBuffer = [];
    _session = null;
    stopFlushTimer();
    try {
      await Preferences.remove({ key: STORAGE_KEY_PENDING });
    } catch (error) {
      // Non-critical
    }
  }
}

/**
 * Check whether the user has opted out of analytics.
 *
 * @returns {boolean}
 */
export function isOptedOut() {
  return _optedOut;
}

/**
 * Update the user ID on the current session (e.g., after login completes).
 *
 * @param {string} userId - Opaque user UUID
 */
export function setUserId(userId) {
  if (_session) {
    _session.userId = userId;
  }
  _loginTimestamp = Date.now();
  _firstActionRecorded = false;
}

/**
 * Shut down analytics gracefully.
 * Flushes remaining events and cleans up listeners.
 */
export async function shutdownAnalytics() {
  if (!_initialized) return;

  // Close current screen
  if (_currentScreen && _currentScreenStartedAt && _session) {
    const durationMs = Date.now() - _currentScreenStartedAt;
    _session.screens.push({
      name: _currentScreen,
      duration: Math.round(durationMs / 1000),
      exitedAt: new Date().toISOString(),
    });
  }

  // Abandon any open funnels
  for (const funnelName of Object.keys(_activeFunnels)) {
    abandonFunnel(funnelName);
  }

  // Final flush
  await flush();

  // Clean up
  stopFlushTimer();
  if (_appStateListener) {
    _appStateListener.remove();
    _appStateListener = null;
  }
  if (_networkListener) {
    _networkListener.remove();
    _networkListener = null;
  }

  _initialized = false;
  _session = null;
  _eventBuffer = [];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Strip any potential PII from metadata.
 * Removes keys that commonly contain personal information.
 */
function sanitizeMetadata(metadata) {
  if (!metadata || typeof metadata !== 'object') return {};

  const PII_KEYS = [
    'email', 'phone', 'name', 'firstName', 'lastName', 'first_name', 'last_name',
    'address', 'ssn', 'dob', 'dateOfBirth', 'password', 'token', 'secret',
    'borrowerName', 'borrower_name', 'borrowerEmail', 'borrower_email',
    'borrowerPhone', 'borrower_phone',
  ];

  const sanitized = {};
  for (const [key, value] of Object.entries(metadata)) {
    if (PII_KEYS.includes(key)) continue;
    // Recursively strip nested objects
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      sanitized[key] = sanitizeMetadata(value);
    } else {
      sanitized[key] = value;
    }
  }
  return sanitized;
}

// ---------------------------------------------------------------------------
// Default export
// ---------------------------------------------------------------------------

export default {
  initAnalytics,
  trackScreen,
  trackAction,
  trackError,
  trackApiError,
  startFunnel,
  completeFunnelStep,
  abandonFunnel,
  getSessionSummary,
  setOptOut,
  isOptedOut,
  setUserId,
  shutdownAnalytics,
};
