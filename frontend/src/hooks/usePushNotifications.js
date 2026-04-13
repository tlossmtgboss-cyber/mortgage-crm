/**
 * usePushNotifications Hook
 *
 * Manages push notification registration, lifecycle, and routing for the mobile app.
 * Handles:
 * - Token registration with backend (with retry/backoff)
 * - Token refresh detection and backend sync
 * - Logout cleanup (unregister token, remove listeners)
 * - Notification tap deep-link routing
 * - Badge count management
 * - Permission denial tracking to avoid re-prompting
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Capacitor } from '@capacitor/core';
import { PushNotifications } from '@capacitor/push-notifications';
import { App } from '@capacitor/app';
import { isNative } from '../services/nativeServices';
import { API_BASE_URL } from '../services/api';
import { getItem, setItem, removeItem } from '../utils/storage';
import { parseDeepLink } from '../services/deepLinkRouter';

// ============================================================================
// Storage keys for push notification state
// ============================================================================
const PUSH_TOKEN_KEY = 'push_device_token';
const PUSH_TOKEN_TIMESTAMP_KEY = 'push_device_token_ts';
const PUSH_PERMISSION_DENIED_KEY = 'push_permission_denied';

// ============================================================================
// Retry configuration
// ============================================================================
const MAX_RETRIES = 3;
const BASE_RETRY_DELAY_MS = 1000;

// ============================================================================
// Module-level listener handles for cleanup
// ============================================================================
let _registrationListener = null;
let _registrationErrorListener = null;
let _notificationReceivedListener = null;
let _notificationActionListener = null;
let _appStateListener = null;

// ============================================================================
// Standalone functions (usable outside the hook)
// ============================================================================

/**
 * Get the stored device token from Preferences.
 * @returns {Promise<string|null>}
 */
async function getStoredToken() {
  return await getItem(PUSH_TOKEN_KEY);
}

/**
 * Store the device token in Preferences with a timestamp.
 * @param {string} token
 */
async function storeToken(token) {
  await setItem(PUSH_TOKEN_KEY, token);
  await setItem(PUSH_TOKEN_TIMESTAMP_KEY, String(Date.now()));
}

/**
 * Remove the device token from Preferences.
 */
async function clearStoredToken() {
  await removeItem(PUSH_TOKEN_KEY);
  await removeItem(PUSH_TOKEN_TIMESTAMP_KEY);
}

/**
 * Check whether the user previously denied push permission.
 * @returns {Promise<boolean>}
 */
async function wasPermissionDenied() {
  const val = await getItem(PUSH_PERMISSION_DENIED_KEY);
  return val === 'true';
}

/**
 * Record that push permission was denied so we do not re-prompt.
 */
async function markPermissionDenied() {
  await setItem(PUSH_PERMISSION_DENIED_KEY, 'true');
}

/**
 * Send the device token to the backend registration endpoint.
 * Retries with exponential backoff on failure.
 *
 * @param {string} token - APNs/FCM device token
 * @param {number} attempt - Current retry attempt (0-based)
 * @returns {Promise<boolean>} Whether the registration succeeded
 */
async function registerTokenWithBackend(token, attempt = 0) {
  const authToken = localStorage.getItem('token');
  if (!authToken) {
    console.warn('Push: no auth token, skipping backend registration');
    return false;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/push/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`,
      },
      body: JSON.stringify({
        device_token: token,
        platform: Capacitor.getPlatform(),
      }),
    });

    if (response.ok) {
      console.log('Push: token registered with backend');
      return true;
    }

    console.error('Push: backend registration failed, status', response.status);
  } catch (err) {
    console.error('Push: backend registration error', err);
  }

  // Retry with exponential backoff
  if (attempt < MAX_RETRIES - 1) {
    const delay = BASE_RETRY_DELAY_MS * Math.pow(2, attempt);
    console.log(`Push: retrying registration in ${delay}ms (attempt ${attempt + 1}/${MAX_RETRIES})`);
    await new Promise((resolve) => setTimeout(resolve, delay));
    return registerTokenWithBackend(token, attempt + 1);
  }

  console.error('Push: registration failed after all retries');
  return false;
}

/**
 * Tell the backend to forget this device token, then clean up local state
 * and remove all Capacitor push listeners.
 *
 * Call this on logout.
 *
 * @returns {Promise<void>}
 */
export async function unregisterPushNotifications() {
  if (!isNative) return;

  try {
    const token = await getStoredToken();

    // Tell backend to forget the token
    if (token) {
      const authToken = localStorage.getItem('token');
      if (authToken) {
        try {
          await fetch(`${API_BASE_URL}/api/v1/push/unregister`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${authToken}`,
            },
            body: JSON.stringify({
              device_token: token,
              platform: Capacitor.getPlatform(),
            }),
          });
          console.log('Push: token unregistered from backend');
        } catch (err) {
          // Best-effort; the server can also expire stale tokens
          console.warn('Push: backend unregister failed', err);
        }
      }
    }

    // Remove stored token
    await clearStoredToken();

    // Remove all push listeners
    removeAllListeners();

    console.log('Push: cleanup complete');
  } catch (err) {
    console.error('Push: unregister error', err);
  }
}

/**
 * Remove all Capacitor push and app-state listeners that this module owns.
 */
function removeAllListeners() {
  if (_registrationListener) {
    _registrationListener.remove();
    _registrationListener = null;
  }
  if (_registrationErrorListener) {
    _registrationErrorListener.remove();
    _registrationErrorListener = null;
  }
  if (_notificationReceivedListener) {
    _notificationReceivedListener.remove();
    _notificationReceivedListener = null;
  }
  if (_notificationActionListener) {
    _notificationActionListener.remove();
    _notificationActionListener = null;
  }
  if (_appStateListener) {
    _appStateListener.remove();
    _appStateListener = null;
  }
}

/**
 * Navigate to the correct page based on notification payload.
 * Supports both warm start (app in background) and cold start (app killed).
 *
 * Uses the deep link router's parseDeepLink for consistency with URL scheme
 * and universal link handling. Falls back to pushState/popstate since this
 * module runs outside React Router context.
 *
 * Expected data shapes:
 *   { type: 'loan',   id: '123' }        -> /loans/123
 *   { type: 'lead',   id: '456' }        -> /leads/456
 *   { type: 'task',   id: '789' }        -> /tasks
 *   { type: 'route',  path: '/foo/bar' } -> /foo/bar
 *
 * @param {object} data - The notification data payload
 */
function routeFromNotification(data) {
  if (!data) return;

  let targetPath = null;

  if (data.path) {
    // Explicit path override
    targetPath = data.path;
  } else if (data.type) {
    // Use the deep link router's notification resolver for consistent routing
    const deepLinkUrl = `perenniaai://notification?type=${encodeURIComponent(data.type)}${data.id ? `&id=${encodeURIComponent(data.id)}` : ''}`;
    const { route } = parseDeepLink(deepLinkUrl);
    if (route) {
      targetPath = route;
    }
  } else if (data.route) {
    // Legacy fallback
    targetPath = data.route;
  }

  if (targetPath) {
    console.log('Push: navigating to', targetPath);
    // Use pushState + popstate for reliability on both warm and cold starts.
    // React Router's navigate() may not be mounted yet on cold start.
    // The initDeepLinkRouter in PushNotificationInitializer handles the
    // navigate()-based routing for appUrlOpen events.
    window.location.hash = '';
    window.history.pushState({}, '', targetPath);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }
}

// ============================================================================
// Hook
// ============================================================================

export function usePushNotifications() {
  const [isRegistered, setIsRegistered] = useState(false);
  const [deviceToken, setDeviceToken] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);

  // Track whether the hook has been unmounted
  const unmountedRef = useRef(false);

  // -----------------------------------------------------------------------
  // Register for push notifications
  // -----------------------------------------------------------------------
  const register = useCallback(async () => {
    if (!isNative) {
      console.log('Push: not available on web');
      return null;
    }

    // Do not re-prompt if user previously denied
    const denied = await wasPermissionDenied();
    if (denied) {
      console.log('Push: permission previously denied, skipping');
      setPermissionDenied(true);
      return null;
    }

    setIsLoading(true);
    setError(null);

    try {
      // Check / request permission
      const permStatus = await PushNotifications.requestPermissions();

      if (permStatus.receive !== 'granted') {
        console.log('Push: permission denied');
        await markPermissionDenied();
        if (!unmountedRef.current) {
          setPermissionDenied(true);
          setIsLoading(false);
        }
        return null;
      }

      // Register with APNs / FCM
      await PushNotifications.register();

      // Wait for the registration event to deliver the token
      const token = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error('Push registration timed out'));
        }, 15000);

        // Use one-shot listeners for the initial registration
        PushNotifications.addListener('registration', (result) => {
          clearTimeout(timeout);
          resolve(result.value);
        });

        PushNotifications.addListener('registrationError', (err) => {
          clearTimeout(timeout);
          reject(err);
        });
      });

      if (!token) {
        throw new Error('No token received from APNs/FCM');
      }

      // Store locally
      await storeToken(token);

      if (!unmountedRef.current) {
        setDeviceToken(token);
      }

      // Register with backend (with retry)
      const ok = await registerTokenWithBackend(token);

      if (!unmountedRef.current) {
        setIsRegistered(ok);
      }

      return token;
    } catch (err) {
      console.error('Push: registration error', err);
      if (!unmountedRef.current) {
        setError(err.message || String(err));
      }
      return null;
    } finally {
      if (!unmountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  // -----------------------------------------------------------------------
  // Listen for incoming notifications (foreground)
  // -----------------------------------------------------------------------
  const onNotification = useCallback((callback) => {
    if (!isNative) return () => {};

    const receivedHandle = PushNotifications.addListener(
      'pushNotificationReceived',
      (notification) => {
        callback(notification, { tapped: false });
      }
    );

    const tappedHandle = PushNotifications.addListener(
      'pushNotificationActionPerformed',
      (action) => {
        callback(action.notification, {
          tapped: true,
          actionId: action.actionId,
        });
      }
    );

    return () => {
      receivedHandle.remove();
      tappedHandle.remove();
    };
  }, []);

  // -----------------------------------------------------------------------
  // Clear all delivered notifications
  // -----------------------------------------------------------------------
  const clearNotifications = useCallback(async () => {
    if (!isNative) return;
    await PushNotifications.removeAllDeliveredNotifications();
  }, []);

  // -----------------------------------------------------------------------
  // Get badge count (number of delivered notifications)
  // -----------------------------------------------------------------------
  const getBadgeCount = useCallback(async () => {
    if (!isNative) return 0;
    try {
      const delivered = await PushNotifications.getDeliveredNotifications();
      return delivered.notifications?.length || 0;
    } catch {
      return 0;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Set up persistent listeners on mount
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!isNative) return;

    // --- Token refresh listener -------------------------------------------
    // APNs can refresh the token at any time. If the new token differs from
    // what we stored, push the update to the backend.
    _registrationListener = PushNotifications.addListener(
      'registration',
      async (result) => {
        const newToken = result.value;
        const storedToken = await getStoredToken();

        if (newToken && newToken !== storedToken) {
          console.log('Push: token refreshed, updating backend');
          await storeToken(newToken);
          await registerTokenWithBackend(newToken);
          if (!unmountedRef.current) {
            setDeviceToken(newToken);
          }
        }
      }
    );

    _registrationErrorListener = PushNotifications.addListener(
      'registrationError',
      (err) => {
        console.error('Push: registration error event', err);
        if (!unmountedRef.current) {
          setError(err.error || String(err));
        }
      }
    );

    // --- Notification received in foreground (badge update) ----------------
    _notificationReceivedListener = PushNotifications.addListener(
      'pushNotificationReceived',
      (_notification) => {
        // Badge count auto-increments on iOS via the notification payload.
        // We could update local state here if needed.
        console.log('Push: notification received in foreground');
      }
    );

    // --- Notification tap (deep-link routing) -----------------------------
    _notificationActionListener = PushNotifications.addListener(
      'pushNotificationActionPerformed',
      (action) => {
        console.log('Push: notification tapped', action);
        const data = action.notification?.data;
        routeFromNotification(data);
      }
    );

    // --- App state change (clear badge on foreground) ---------------------
    (async () => {
      try {
        _appStateListener = await App.addListener('appStateChange', async (state) => {
          if (state.isActive) {
            // Clear the badge when the user opens the app
            try {
              await PushNotifications.removeAllDeliveredNotifications();
            } catch {
              // Best-effort
            }
          }
        });
      } catch (err) {
        console.warn('Push: could not attach app state listener', err);
      }
    })();

    // --- Listen for logout event to auto-cleanup --------------------------
    const handleAuthChange = (event) => {
      if (event.detail?.type === 'logout') {
        unregisterPushNotifications();
      }
    };
    window.addEventListener('authChange', handleAuthChange);

    // --- Auto-register if user is already logged in -----------------------
    const token = localStorage.getItem('token');
    if (token) {
      // Hydrate stored token into state immediately
      (async () => {
        const stored = await getStoredToken();
        if (stored && !unmountedRef.current) {
          setDeviceToken(stored);
          setIsRegistered(true);
        }
      })();
    }

    // Cleanup on unmount
    return () => {
      unmountedRef.current = true;
      removeAllListeners();
      window.removeEventListener('authChange', handleAuthChange);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // -----------------------------------------------------------------------
  // Auto-register on mount when user is authenticated
  // -----------------------------------------------------------------------
  useEffect(() => {
    const authToken = localStorage.getItem('token');
    if (authToken && isNative && !isRegistered && !permissionDenied) {
      register();
    }
  }, [register, isRegistered, permissionDenied]);

  // -----------------------------------------------------------------------
  // Handle cold start: check if the app was launched from a notification
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!isNative) return;

    // On iOS, if the app was killed and the user tapped a notification,
    // the launch URL / initial notification may already be queued.
    // The pushNotificationActionPerformed listener above will fire for it.
    // As a fallback, check App.getLaunchUrl for URL-scheme deep links.
    (async () => {
      try {
        const launchUrl = await App.getLaunchUrl();
        if (launchUrl?.url) {
          console.log('Push: app launched with URL', launchUrl.url);
          // If the URL matches our scheme, parse and route
          const path = launchUrl.url.replace(/^[^:]+:\/\//, '/');
          if (path && path !== '/') {
            routeFromNotification({ path });
          }
        }
      } catch {
        // App.getLaunchUrl may not be available in all contexts
      }
    })();
  }, []);

  return {
    // State
    isNative,
    isRegistered,
    deviceToken,
    error,
    isLoading,
    permissionDenied,

    // Actions
    register,
    onNotification,
    clearNotifications,
    getBadgeCount,
    unregisterPushNotifications,
  };
}

export default usePushNotifications;
