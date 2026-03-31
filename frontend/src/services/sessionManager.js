/**
 * Session Manager
 *
 * Enterprise session timeout and auto-lock for the Perennia AI mobile app.
 * Handles inactivity detection, background timeout, token refresh,
 * and absolute session duration enforcement.
 */

import { App } from '@capacitor/app';
import { biometrics, isNative } from './nativeServices';
import { authAPI, API_BASE_URL } from './api';

// ============================================================================
// CONFIGURATION
// ============================================================================

const SESSION_CONFIG = {
  inactivityTimeout: 15 * 60 * 1000,       // 15 minutes
  warningBefore: 2 * 60 * 1000,            // Warn 2 min before expiry
  backgroundTimeout: 5 * 60 * 1000,        // 5 min in background
  requireBiometricOnResume: true,           // Re-auth after background
  maxSessionDuration: 8 * 60 * 60 * 1000,  // 8 hour absolute max
};

const CREDENTIAL_SERVER = 'com.perenniaai.crm';

// ============================================================================
// STATE
// ============================================================================

let _inactivityTimer = null;
let _warningTimer = null;
let _absoluteTimer = null;
let _sessionStartTime = null;
let _lastActivityTime = null;
let _backgroundEnteredAt = null;
let _isLocked = false;
let _isWarning = false;
let _failedAttempts = 0;
let _listeners = new Set();
let _appStateListener = null;
let _initialized = false;

// ============================================================================
// INTERNAL HELPERS
// ============================================================================

function _notifyListeners() {
  const state = getSessionState();
  _listeners.forEach((cb) => {
    try {
      cb(state);
    } catch (err) {
      console.error('Session listener error:', err);
    }
  });
}

function _clearTimers() {
  if (_inactivityTimer) {
    clearTimeout(_inactivityTimer);
    _inactivityTimer = null;
  }
  if (_warningTimer) {
    clearTimeout(_warningTimer);
    _warningTimer = null;
  }
  if (_absoluteTimer) {
    clearTimeout(_absoluteTimer);
    _absoluteTimer = null;
  }
}

function _startInactivityTimer() {
  // Clear existing timers
  if (_inactivityTimer) clearTimeout(_inactivityTimer);
  if (_warningTimer) clearTimeout(_warningTimer);

  _isWarning = false;
  _lastActivityTime = Date.now();

  // Warning fires when we are warningBefore ms away from timeout
  const warningDelay = SESSION_CONFIG.inactivityTimeout - SESSION_CONFIG.warningBefore;

  _warningTimer = setTimeout(() => {
    _isWarning = true;
    _notifyListeners();
  }, warningDelay);

  // Lock fires at the full inactivity timeout
  _inactivityTimer = setTimeout(() => {
    _lockSession('inactivity');
  }, SESSION_CONFIG.inactivityTimeout);
}

function _startAbsoluteTimer() {
  if (_absoluteTimer) clearTimeout(_absoluteTimer);

  _sessionStartTime = Date.now();

  _absoluteTimer = setTimeout(() => {
    _forceLogout('absolute_timeout');
  }, SESSION_CONFIG.maxSessionDuration);
}

function _lockSession(reason) {
  if (_isLocked) return;

  _isLocked = true;
  _isWarning = false;
  _clearTimers();

  // Keep the absolute timer running — it should still force logout
  if (reason !== 'absolute_timeout') {
    // Restart absolute timer only if it was cleared
    // Actually, we should preserve the absolute timer. Re-check:
    // _clearTimers clears it, so recalculate remaining absolute time.
    const elapsed = Date.now() - (_sessionStartTime || Date.now());
    const remaining = SESSION_CONFIG.maxSessionDuration - elapsed;
    if (remaining > 0) {
      _absoluteTimer = setTimeout(() => {
        _forceLogout('absolute_timeout');
      }, remaining);
    } else {
      _forceLogout('absolute_timeout');
      return;
    }
  }

  console.log(`[SessionManager] Session locked: ${reason}`);
  _notifyListeners();
}

function _forceLogout(reason) {
  console.log(`[SessionManager] Force logout: ${reason}`);
  _clearTimers();
  _isLocked = true;
  _isWarning = false;
  _failedAttempts = 0;

  // Clear auth state
  localStorage.removeItem('token');
  localStorage.removeItem('user');

  _notifyListeners();

  // Navigate to login
  window.location.href = '/login';
}

function _handleActivity() {
  if (_isLocked) return;

  _lastActivityTime = Date.now();

  // Reset inactivity timer on activity
  _startInactivityTimer();
}

async function _handleAppStateChange(state) {
  if (!state.isActive) {
    // App went to background
    _backgroundEnteredAt = Date.now();
    _clearTimers();
    console.log('[SessionManager] App backgrounded');
  } else {
    // App resumed from background
    if (_backgroundEnteredAt) {
      const backgroundDuration = Date.now() - _backgroundEnteredAt;
      _backgroundEnteredAt = null;

      console.log(`[SessionManager] App resumed after ${Math.round(backgroundDuration / 1000)}s`);

      // Check absolute timeout first
      const totalElapsed = Date.now() - (_sessionStartTime || Date.now());
      if (totalElapsed >= SESSION_CONFIG.maxSessionDuration) {
        _forceLogout('absolute_timeout');
        return;
      }

      // Check background timeout
      if (backgroundDuration >= SESSION_CONFIG.backgroundTimeout) {
        _lockSession('background_timeout');
        return;
      }

      // Check if biometric re-auth is required on resume
      if (SESSION_CONFIG.requireBiometricOnResume && isNative && backgroundDuration > 30000) {
        // More than 30 seconds in background on native — require biometric
        _lockSession('background_resume');
        return;
      }

      // Otherwise, restart timers with adjusted remaining time
      _startInactivityTimer();

      // Restart absolute timer with remaining time
      const remainingAbsolute = SESSION_CONFIG.maxSessionDuration - totalElapsed;
      if (remainingAbsolute > 0) {
        _absoluteTimer = setTimeout(() => {
          _forceLogout('absolute_timeout');
        }, remainingAbsolute);
      }
    }
  }
}

// ============================================================================
// ACTIVITY EVENT LISTENERS
// ============================================================================

const ACTIVITY_EVENTS = ['touchstart', 'touchmove', 'mousedown', 'mousemove', 'keydown', 'scroll'];

// Throttle activity handler to avoid excessive timer resets
let _activityThrottleTimer = null;
function _throttledActivityHandler() {
  if (_activityThrottleTimer) return;
  _activityThrottleTimer = setTimeout(() => {
    _activityThrottleTimer = null;
  }, 5000); // Throttle to once per 5 seconds
  _handleActivity();
}

function _attachActivityListeners() {
  ACTIVITY_EVENTS.forEach((event) => {
    document.addEventListener(event, _throttledActivityHandler, { passive: true });
  });
}

function _detachActivityListeners() {
  ACTIVITY_EVENTS.forEach((event) => {
    document.removeEventListener(event, _throttledActivityHandler);
  });
}

// ============================================================================
// PUBLIC API
// ============================================================================

/**
 * Initialize the session manager. Call once after successful login.
 */
export function initSession() {
  if (_initialized) return;

  const token = localStorage.getItem('token');
  if (!token) return;

  _initialized = true;
  _isLocked = false;
  _isWarning = false;
  _failedAttempts = 0;

  // Start timers
  _startInactivityTimer();
  _startAbsoluteTimer();

  // Listen for user activity
  _attachActivityListeners();

  // Listen for app state changes (background/foreground) on native
  if (isNative) {
    _appStateListener = App.addListener('appStateChange', _handleAppStateChange);
  } else {
    // Web fallback: use visibility change
    document.addEventListener('visibilitychange', () => {
      _handleAppStateChange({ isActive: !document.hidden });
    });
  }

  console.log('[SessionManager] Initialized');
}

/**
 * Destroy the session manager. Call on logout.
 */
export function destroySession() {
  _clearTimers();
  _detachActivityListeners();

  if (_appStateListener) {
    _appStateListener.remove();
    _appStateListener = null;
  }

  _initialized = false;
  _isLocked = false;
  _isWarning = false;
  _sessionStartTime = null;
  _lastActivityTime = null;
  _backgroundEnteredAt = null;
  _failedAttempts = 0;

  console.log('[SessionManager] Destroyed');
}

/**
 * Get current session state.
 */
export function getSessionState() {
  const now = Date.now();
  let timeRemaining = 0;

  if (_lastActivityTime && !_isLocked) {
    const elapsed = now - _lastActivityTime;
    timeRemaining = Math.max(0, SESSION_CONFIG.inactivityTimeout - elapsed);
  }

  return {
    isLocked: _isLocked,
    isWarning: _isWarning,
    timeRemaining: Math.ceil(timeRemaining / 1000), // seconds
    failedAttempts: _failedAttempts,
    sessionDuration: _sessionStartTime ? now - _sessionStartTime : 0,
    maxSessionDuration: SESSION_CONFIG.maxSessionDuration,
  };
}

/**
 * Extend the session by resetting the inactivity timer.
 * Called when user clicks "Stay logged in" on the warning modal.
 */
export function extendSession() {
  if (_isLocked) return false;

  _handleActivity();
  return true;
}

/**
 * Manually lock the session (e.g., user taps lock icon).
 */
export function lockSession() {
  _lockSession('manual');
}

/**
 * Attempt to unlock the session with biometrics.
 * Returns true on success, false on failure.
 */
export async function unlockWithBiometrics() {
  if (!_isLocked) return true;

  try {
    const authenticated = await biometrics.authenticate('Unlock Perennia AI');
    if (authenticated) {
      _isLocked = false;
      _isWarning = false;
      _failedAttempts = 0;

      // Attempt silent token refresh
      await _silentTokenRefresh();

      // Restart timers
      _startInactivityTimer();

      // Restart absolute timer with remaining time
      const totalElapsed = Date.now() - (_sessionStartTime || Date.now());
      const remainingAbsolute = SESSION_CONFIG.maxSessionDuration - totalElapsed;
      if (remainingAbsolute > 0) {
        _absoluteTimer = setTimeout(() => {
          _forceLogout('absolute_timeout');
        }, remainingAbsolute);
      } else {
        _forceLogout('absolute_timeout');
        return false;
      }

      _notifyListeners();
      return true;
    }

    _failedAttempts++;
    if (_failedAttempts >= 3) {
      _forceLogout('max_failed_attempts');
      return false;
    }

    _notifyListeners();
    return false;
  } catch (err) {
    console.error('[SessionManager] Biometric unlock error:', err);
    _failedAttempts++;
    if (_failedAttempts >= 3) {
      _forceLogout('max_failed_attempts');
    }
    _notifyListeners();
    return false;
  }
}

/**
 * Attempt to unlock the session with a password.
 * Returns true on success, false on failure.
 */
export async function unlockWithPassword(password) {
  if (!_isLocked) return true;

  try {
    // Get stored email from user data
    const userData = localStorage.getItem('user');
    if (!userData) {
      _forceLogout('no_user_data');
      return false;
    }

    const user = JSON.parse(userData);
    const email = user.email;

    if (!email) {
      _forceLogout('no_email');
      return false;
    }

    // Attempt re-authentication
    const response = await authAPI.login(email, password);

    if (response && response.access_token) {
      // Store the new token
      localStorage.setItem('token', response.access_token);

      _isLocked = false;
      _isWarning = false;
      _failedAttempts = 0;

      // Restart timers
      _startInactivityTimer();

      // Restart absolute timer with remaining time
      const totalElapsed = Date.now() - (_sessionStartTime || Date.now());
      const remainingAbsolute = SESSION_CONFIG.maxSessionDuration - totalElapsed;
      if (remainingAbsolute > 0) {
        _absoluteTimer = setTimeout(() => {
          _forceLogout('absolute_timeout');
        }, remainingAbsolute);
      } else {
        // Max duration exceeded — start a fresh absolute session
        _startAbsoluteTimer();
      }

      _notifyListeners();
      return true;
    }

    _failedAttempts++;
    if (_failedAttempts >= 3) {
      _forceLogout('max_failed_attempts');
      return false;
    }

    _notifyListeners();
    return false;
  } catch (err) {
    console.error('[SessionManager] Password unlock error:', err);
    _failedAttempts++;
    if (_failedAttempts >= 3) {
      _forceLogout('max_failed_attempts');
    }
    _notifyListeners();
    return false;
  }
}

/**
 * Register a callback to be notified of session state changes.
 * Returns an unsubscribe function.
 */
export function onSessionStateChange(callback) {
  _listeners.add(callback);
  return () => _listeners.delete(callback);
}

/**
 * Notify the session manager that an API call was made.
 * Call this from the axios interceptor to count API activity.
 */
export function notifyApiActivity() {
  if (!_isLocked && _initialized) {
    _handleActivity();
  }
}

/**
 * Get the session configuration (read-only).
 */
export function getSessionConfig() {
  return { ...SESSION_CONFIG };
}

// ============================================================================
// SILENT TOKEN REFRESH
// ============================================================================

async function _silentTokenRefresh() {
  try {
    const token = localStorage.getItem('token');
    if (!token) return false;

    // Attempt to hit a lightweight auth endpoint to validate/refresh the token
    const response = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (response.ok) {
      // Token is still valid — check for a refreshed token in the response
      const data = await response.json();
      if (data.access_token) {
        localStorage.setItem('token', data.access_token);
      }
      return true;
    }

    if (response.status === 401) {
      // Token expired — cannot recover without re-login
      return false;
    }

    return true; // Non-auth errors are OK; token may still be valid
  } catch (err) {
    console.error('[SessionManager] Silent token refresh error:', err);
    return true; // Network error — don't force logout; let user try
  }
}

// ============================================================================
// DEFAULT EXPORT
// ============================================================================

export default {
  initSession,
  destroySession,
  getSessionState,
  extendSession,
  lockSession,
  unlockWithBiometrics,
  unlockWithPassword,
  onSessionStateChange,
  notifyApiActivity,
  getSessionConfig,
  SESSION_CONFIG,
};
