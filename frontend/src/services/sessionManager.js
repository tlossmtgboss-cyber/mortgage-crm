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
import { getMDMSessionTimeout } from './mdmConfig';
import { getToken, getRefreshToken, getUserData, setTokens, clearTokens } from '../utils/tokenStore';

// ============================================================================
// CONFIGURATION
// ============================================================================

const SESSION_CONFIG = {
  inactivityTimeout: 15 * 60 * 1000,       // 15 minutes (GLBA maximum)
  warningBefore: 2 * 60 * 1000,            // Warn 2 min before expiry
  backgroundTimeout: 5 * 60 * 1000,        // 5 min in background
  requireBiometricOnResume: true,           // Re-auth after background
  maxSessionDuration: 8 * 60 * 60 * 1000,  // 8 hour absolute max
  tokenRefreshBeforeExpiry: 2 * 60 * 1000, // Refresh token 2 min before JWT expiry
};

// Apply MDM-managed session timeout override if available.
// MDM can set a shorter timeout (never longer than 15 min for GLBA).
function _applyMDMOverrides() {
  try {
    const mdmTimeout = getMDMSessionTimeout();
    if (mdmTimeout && mdmTimeout > 0) {
      // MDM can shorten but never exceed 15 min (GLBA ceiling)
      const maxAllowed = 15 * 60 * 1000;
      SESSION_CONFIG.inactivityTimeout = Math.min(mdmTimeout, maxAllowed);
      // Adjust warning to be proportional (but at least 30s)
      SESSION_CONFIG.warningBefore = Math.max(
        30 * 1000,
        Math.min(SESSION_CONFIG.warningBefore, SESSION_CONFIG.inactivityTimeout - 30 * 1000)
      );
      console.log(`[SessionManager] MDM timeout override: ${SESSION_CONFIG.inactivityTimeout / 1000}s`);
    }
  } catch (err) {
    // MDM config not available — use defaults
  }
}

const CREDENTIAL_SERVER = 'com.perenniaai.crm';

// ============================================================================
// STATE
// ============================================================================

let _inactivityTimer = null;
let _warningTimer = null;
let _absoluteTimer = null;
let _tokenRefreshTimer = null;
let _sessionStartTime = null;
let _lastActivityTime = null;
let _backgroundEnteredAt = null;
let _isLocked = false;
let _isWarning = false;
let _failedAttempts = 0;
let _listeners = new Set();
let _appStateListener = null;
let _visibilityHandler = null;
let _initialized = false;
let _tokenRefreshRetries = 0;
const _MAX_REFRESH_RETRIES = 5;

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
  if (_tokenRefreshTimer) {
    clearTimeout(_tokenRefreshTimer);
    _tokenRefreshTimer = null;
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

  // Clear auth state from ALL storage locations (localStorage + Capacitor Preferences).
  // clearAllAuthTokens is async but we fire-and-forget since we're navigating away.
  clearTokens().catch(() => {});

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

  const token = getToken();
  if (!token) return;

  // Apply MDM-managed session timeout before starting timers
  _applyMDMOverrides();

  _initialized = true;
  _isLocked = false;
  _isWarning = false;
  _failedAttempts = 0;

  // Start timers
  _startInactivityTimer();
  _startAbsoluteTimer();

  // Schedule proactive token refresh (avoids 401 during active use)
  _scheduleTokenRefresh(token);

  // Listen for user activity
  _attachActivityListeners();

  // Listen for app state changes (background/foreground) on native
  if (isNative) {
    _appStateListener = App.addListener('appStateChange', _handleAppStateChange);
  } else {
    // Web fallback: use visibility change
    _visibilityHandler = () => {
      _handleAppStateChange({ isActive: !document.hidden });
    };
    document.addEventListener('visibilitychange', _visibilityHandler);
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

  if (_visibilityHandler) {
    document.removeEventListener('visibilitychange', _visibilityHandler);
    _visibilityHandler = null;
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

      // Attempt silent token refresh using localStorage refresh token
      const refreshed = await _silentTokenRefresh();

      // If silent refresh failed (expired refresh token), try keychain credentials
      // The login page stores email+password under CREDENTIAL_SERVER via useBiometricLogin
      if (!refreshed && isNative) {
        console.log('[SessionManager] Silent refresh failed, trying keychain re-login');
        const reloginOk = await _reloginFromKeychain();
        if (!reloginOk) {
          // No valid tokens and no keychain credentials — force full login
          _forceLogout('token_expired');
          return false;
        }
      }

      // Restart timers
      _startInactivityTimer();

      // Schedule proactive token refresh for the current access token
      const currentToken = getToken();
      if (currentToken) _scheduleTokenRefresh(currentToken);

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
    const userData = getUserData();
    if (!userData) {
      _forceLogout('no_user_data');
      return false;
    }

    const user = typeof userData === 'string' ? JSON.parse(userData) : userData;
    const email = user.email;

    if (!email) {
      _forceLogout('no_email');
      return false;
    }

    // Attempt re-authentication
    const response = await authAPI.login(email, password);

    if (response && response.access_token) {
      // Store the new tokens in tokenStore (memory cache + Keychain on native)
      await setTokens({
        access_token: response.access_token,
        ...(response.refresh_token && { refresh_token: response.refresh_token }),
      });

      _isLocked = false;
      _isWarning = false;
      _failedAttempts = 0;

      // Restart timers
      _startInactivityTimer();

      // Schedule proactive token refresh for the new access token
      _scheduleTokenRefresh(response.access_token);

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
    const token = getToken();
    if (!token) return false;

    // Check token expiry client-side (no /auth/me endpoint exists)
    const exp = _getTokenExp(token);
    if (!exp) return true; // Can't parse — let API calls determine validity

    const now = Math.floor(Date.now() / 1000);
    if (exp > now + 120) {
      // Token valid for more than 2 minutes — no refresh needed
      return true;
    }

    // Token expired or expiring soon — try to refresh
    const refreshToken = getRefreshToken();
    if (!refreshToken) return exp > now; // No refresh token — valid only if not expired

    const response = await fetch(`${API_BASE_URL}/api/v1/account/renew`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (response.ok) {
      const data = await response.json();
      if (data.access_token) {
        setTokens({ access_token: data.access_token }).catch(() => {});
      }
      return true;
    }

    return exp > now; // Refresh failed — valid only if not expired
  } catch (err) {
    console.error('[SessionManager] Silent token refresh error:', err);
    return true; // Network error — don't force logout
  }
}

// ============================================================================
// KEYCHAIN RE-LOGIN (fallback when refresh token is expired)
// ============================================================================

/**
 * Attempt a full re-login using credentials stored in the iOS keychain.
 * The login page stores email+password via useBiometricLogin under CREDENTIAL_SERVER.
 * Biometric verification has already succeeded before this is called.
 *
 * @returns {Promise<boolean>} true if re-login succeeded
 */
async function _reloginFromKeychain() {
  try {
    const credentials = await biometrics.getCredentials(CREDENTIAL_SERVER);
    if (!credentials?.username || !credentials?.password) {
      console.log('[SessionManager] No keychain credentials found');
      return false;
    }

    const response = await authAPI.login(credentials.username, credentials.password);
    if (response && response.access_token) {
      await setTokens({
        access_token: response.access_token,
        ...(response.refresh_token && { refresh_token: response.refresh_token }),
        ...(response.user && { user_data: response.user }),
      });
      console.log('[SessionManager] Keychain re-login succeeded');
      return true;
    }

    return false;
  } catch (err) {
    console.error('[SessionManager] Keychain re-login error:', err);
    return false;
  }
}

// ============================================================================
// PROACTIVE TOKEN REFRESH
// ============================================================================

/**
 * Parse JWT payload to extract expiration time.
 * Returns the `exp` claim as a Unix timestamp (seconds), or null.
 */
function _getTokenExp(token) {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
    return payload.exp || null;
  } catch {
    return null;
  }
}

/**
 * Proactively refresh the access token BEFORE it expires.
 *
 * GLBA compliance requires that active users are never interrupted by a
 * 401 mid-workflow. This function exchanges the refresh token for a new
 * access token 2 minutes before the current access token expires, then
 * reschedules itself for the new token's expiry.
 */
async function _proactiveTokenRefresh() {
  if (_isLocked) return;

  try {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      console.log('[SessionManager] No refresh token — skipping proactive refresh');
      return;
    }

    const response = await fetch(`${API_BASE_URL}/api/v1/account/renew`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (response.ok) {
      const data = await response.json();
      if (data.access_token) {
        setTokens({ access_token: data.access_token }).catch(() => {});
        _tokenRefreshRetries = 0;
        console.log('[SessionManager] Proactive token refresh succeeded');
        // Schedule next refresh based on new token's expiry
        _scheduleTokenRefresh(data.access_token);
      }
    } else if (response.status === 401) {
      // Refresh token is expired or revoked — user must re-login.
      // Don't force logout here; the inactivity timer will handle it.
      console.warn('[SessionManager] Refresh token rejected (401) — next API call will force re-login');
    } else {
      console.warn(`[SessionManager] Proactive refresh failed: ${response.status}`);
      // Retry with exponential backoff on transient errors
      _tokenRefreshRetries++;
      if (_tokenRefreshRetries < _MAX_REFRESH_RETRIES) {
        const backoffMs = Math.min(60000 * Math.pow(2, _tokenRefreshRetries - 1), 300000);
        _tokenRefreshTimer = setTimeout(_proactiveTokenRefresh, backoffMs);
      }
    }
  } catch (err) {
    console.error('[SessionManager] Proactive token refresh error:', err);
    // Retry with exponential backoff on network errors
    _tokenRefreshRetries++;
    if (_tokenRefreshRetries < _MAX_REFRESH_RETRIES) {
      const backoffMs = Math.min(60000 * Math.pow(2, _tokenRefreshRetries - 1), 300000);
      _tokenRefreshTimer = setTimeout(_proactiveTokenRefresh, backoffMs);
    }
  }
}

/**
 * Schedule a proactive token refresh based on the access token's expiry.
 * Fires `tokenRefreshBeforeExpiry` ms before the token's `exp` claim.
 */
function _scheduleTokenRefresh(token) {
  if (_tokenRefreshTimer) {
    clearTimeout(_tokenRefreshTimer);
    _tokenRefreshTimer = null;
  }

  if (!token) return;

  const exp = _getTokenExp(token);
  if (!exp) return;

  const nowSec = Math.floor(Date.now() / 1000);
  const msUntilExpiry = (exp - nowSec) * 1000;
  const refreshIn = msUntilExpiry - SESSION_CONFIG.tokenRefreshBeforeExpiry;

  if (refreshIn <= 0) {
    // Token is already close to or past expiry — refresh immediately
    _proactiveTokenRefresh();
  } else {
    console.log(`[SessionManager] Token refresh scheduled in ${Math.round(refreshIn / 1000)}s`);
    _tokenRefreshTimer = setTimeout(_proactiveTokenRefresh, refreshIn);
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
