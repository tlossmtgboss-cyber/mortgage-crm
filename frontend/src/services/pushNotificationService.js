/**
 * Push Notification Service
 *
 * Unified push notification handling for both web (Web Push API) and
 * native iOS (Capacitor @capacitor/push-notifications).
 *
 * Usage:
 *   import { initializePushNotifications } from './pushNotificationService';
 *   await initializePushNotifications();
 *
 * On native: uses @capacitor/push-notifications for APNs registration.
 * On web: uses the Web Push API (Notification.requestPermission).
 *
 * All native-only code is guarded with Capacitor.isNativePlatform() checks
 * so the service is safe to import and call from any environment.
 */

import api from './api';
import { isAuthenticated } from '../utils/tokenStore';

// ============================================================================
// Platform detection (safe even when Capacitor is not installed)
// ============================================================================

function isNativePlatform() {
  try {
    return window.Capacitor?.isNativePlatform?.() === true;
  } catch {
    return false;
  }
}

function getPlatformName() {
  try {
    return window.Capacitor?.getPlatform?.() || 'web';
  } catch {
    return 'web';
  }
}

// ============================================================================
// Internal state
// ============================================================================

let _initialized = false;
let _deviceToken = null;
let _notificationCallbacks = [];

// ============================================================================
// Token registration with backend
// ============================================================================

/**
 * Send a device/subscription token to the backend so it can send pushes.
 *
 * @param {string} token - APNs device token (native) or serialized PushSubscription (web)
 * @returns {Promise<boolean>} Whether the registration succeeded
 */
export async function registerDeviceToken(token) {
  if (!isAuthenticated()) {
    console.warn('PushService: no auth token, skipping backend registration');
    return false;
  }

  const MAX_RETRIES = 3;
  const BASE_DELAY = 1000;

  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      const response = await api.post('/api/v1/push/register', {
        device_token: token,
        platform: getPlatformName(),
        // Include subscription details for web push
        ...(typeof token === 'object' ? { subscription: token } : {}),
      });

      console.log('PushService: token registered with backend');
      return true;
    } catch (err) {
      const status = err.response?.status;
      // 4xx errors (except 429) are not retriable
      if (status >= 400 && status < 500 && status !== 429) {
        console.error('PushService: backend rejected token, status', status);
        return false;
      }
      console.error('PushService: backend registration error', err);
    }

    // Exponential backoff before retry
    if (attempt < MAX_RETRIES - 1) {
      const delay = BASE_DELAY * Math.pow(2, attempt);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  console.error('PushService: registration failed after all retries');
  return false;
}

// ============================================================================
// Notification handlers
// ============================================================================

/**
 * Process an incoming notification (foreground).
 * Dispatches a custom event that other components can listen to.
 *
 * @param {object} notification - The notification payload
 */
export function handleNotificationReceived(notification) {
  console.log('PushService: notification received', notification);

  // Notify all registered callbacks
  for (const cb of _notificationCallbacks) {
    try {
      cb(notification, { tapped: false });
    } catch (err) {
      console.error('PushService: callback error', err);
    }
  }

  // Dispatch a DOM event so any component can react
  window.dispatchEvent(
    new CustomEvent('pushNotificationReceived', {
      detail: notification,
    })
  );
}

/**
 * Handle a tap/action on a notification (background or lock screen).
 * Routes the user to the appropriate screen.
 *
 * @param {object} notification - The notification action payload
 */
export function handleNotificationAction(notification) {
  console.log('PushService: notification action', notification);

  // Extract data from the notification
  const data = notification?.notification?.data || notification?.data || notification || {};

  // Notify all registered callbacks
  for (const cb of _notificationCallbacks) {
    try {
      cb(notification, { tapped: true, actionId: notification?.actionId });
    } catch (err) {
      console.error('PushService: callback error', err);
    }
  }

  // Dispatch a DOM event for routing
  window.dispatchEvent(
    new CustomEvent('pushNotificationAction', {
      detail: { data, actionId: notification?.actionId },
    })
  );

  // Attempt to route based on the data payload
  let targetPath = null;

  if (data.path) {
    targetPath = data.path;
  } else if (data.type && data.id) {
    const typeRoutes = {
      loan: `/loans/${data.id}`,
      lead: `/leads/${data.id}`,
      task: `/tasks/${data.id}`,
      client: `/clients/${data.id}`,
      document: `/smart-docs/client/${data.id}`,
    };
    targetPath = typeRoutes[data.type] || null;
  } else if (data.route) {
    targetPath = data.route;
  } else if (data.link) {
    targetPath = data.link;
  }

  if (targetPath) {
    console.log('PushService: navigating to', targetPath);
    window.history.pushState({}, '', targetPath);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }
}

/**
 * Register a callback for incoming notifications.
 * Returns an unsubscribe function.
 *
 * @param {Function} callback - Called with (notification, { tapped: boolean })
 * @returns {Function} Unsubscribe function
 */
export function onNotification(callback) {
  _notificationCallbacks.push(callback);
  return () => {
    _notificationCallbacks = _notificationCallbacks.filter((cb) => cb !== callback);
  };
}

// ============================================================================
// Native (Capacitor) push setup
// ============================================================================

async function initializeNativePush() {
  let PushNotifications;
  try {
    const module = await import('@capacitor/push-notifications');
    PushNotifications = module.PushNotifications;
  } catch (err) {
    console.warn('PushService: @capacitor/push-notifications not available', err);
    return null;
  }

  try {
    // Request permission
    const permStatus = await PushNotifications.requestPermissions();

    if (permStatus.receive !== 'granted') {
      console.log('PushService: native push permission denied');
      return null;
    }

    // Register with APNs / FCM
    await PushNotifications.register();

    // Wait for the registration token
    const token = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Push registration timed out'));
      }, 15000);

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

    _deviceToken = token;

    // Listen for foreground notifications
    PushNotifications.addListener('pushNotificationReceived', (notification) => {
      handleNotificationReceived(notification);
    });

    // Listen for notification taps
    PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
      handleNotificationAction(action);
    });

    // Listen for token refresh
    PushNotifications.addListener('registration', (result) => {
      const newToken = result.value;
      if (newToken && newToken !== _deviceToken) {
        console.log('PushService: token refreshed');
        _deviceToken = newToken;
        registerDeviceToken(newToken);
      }
    });

    return token;
  } catch (err) {
    console.error('PushService: native registration error', err);
    return null;
  }
}

// ============================================================================
// Web Push setup
// ============================================================================

async function initializeWebPush() {
  // Check if the Web Push API is available
  if (!('Notification' in window)) {
    console.log('PushService: Web Notifications API not supported');
    return null;
  }

  try {
    // Request permission
    const permission = await Notification.requestPermission();

    if (permission !== 'granted') {
      console.log('PushService: web notification permission denied');
      return null;
    }

    // If Service Worker + PushManager are available, try to get a push subscription
    if ('serviceWorker' in navigator && 'PushManager' in window) {
      try {
        const registration = await navigator.serviceWorker.ready;
        let subscription = await registration.pushManager.getSubscription();

        if (!subscription) {
          // Try to subscribe. This requires a VAPID public key from the server.
          // If the server hasn't provided one, we fall back to basic web notifications.
          try {
            const response = await api.get('/api/v1/notifications/vapid-key');

            const { vapid_public_key } = response.data;
            if (vapid_public_key) {
              const applicationServerKey = urlBase64ToUint8Array(vapid_public_key);
              subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey,
              });
            }
          } catch (err) {
            // VAPID key endpoint may not exist yet; fall back to basic notifications
            console.log('PushService: VAPID key not available, using basic web notifications');
          }
        }

        if (subscription) {
          _deviceToken = JSON.stringify(subscription.toJSON());
          return _deviceToken;
        }
      } catch (err) {
        console.warn('PushService: PushManager subscription failed', err);
      }
    }

    // Fallback: permission was granted but no PushManager subscription.
    // We can still show local notifications via the Notifications API.
    // Return a synthetic token so the caller knows permission was granted.
    _deviceToken = 'web-notification-granted';
    return _deviceToken;
  } catch (err) {
    console.error('PushService: web push init error', err);
    return null;
  }
}

// ============================================================================
// Public API
// ============================================================================

/**
 * Initialize push notifications for the current platform.
 * - On native (iOS/Android): registers with APNs/FCM via Capacitor
 * - On web: requests Notification permission and subscribes via PushManager
 *
 * Sends the resulting token to the backend for storage.
 *
 * @returns {Promise<string|null>} The device token, or null if denied/unavailable
 */
export async function initializePushNotifications() {
  if (_initialized) {
    console.log('PushService: already initialized');
    return _deviceToken;
  }

  // Must be authenticated
  if (!isAuthenticated()) {
    console.log('PushService: not authenticated, skipping push init');
    return null;
  }

  let token = null;

  if (isNativePlatform()) {
    token = await initializeNativePush();
  } else {
    token = await initializeWebPush();
  }

  if (token) {
    // Register with backend
    await registerDeviceToken(token);
    _initialized = true;
  }

  return token;
}

/**
 * Get the current device token (if registered).
 * @returns {string|null}
 */
export function getDeviceToken() {
  return _deviceToken;
}

/**
 * Check if push notifications are initialized.
 * @returns {boolean}
 */
export function isInitialized() {
  return _initialized;
}

/**
 * Check if push notifications are supported on this platform.
 * @returns {boolean}
 */
export function isSupported() {
  if (isNativePlatform()) return true;
  return 'Notification' in window;
}

/**
 * Get current permission status without requesting.
 * @returns {Promise<'granted'|'denied'|'default'|'unknown'>}
 */
export async function getPermissionStatus() {
  if (isNativePlatform()) {
    try {
      const module = await import('@capacitor/push-notifications');
      const status = await module.PushNotifications.checkPermissions();
      return status.receive; // 'granted', 'denied', or 'prompt'
    } catch {
      return 'unknown';
    }
  }

  if ('Notification' in window) {
    return Notification.permission; // 'granted', 'denied', or 'default'
  }

  return 'unknown';
}

/**
 * Clean up push notification state (call on logout).
 * Unregisters the device token from the backend and removes listeners.
 */
export async function teardownPushNotifications() {
  // Tell backend to forget this device
  if (_deviceToken && isAuthenticated()) {
    try {
      await api.post('/api/v1/push/unregister', {
        device_token: _deviceToken,
        platform: getPlatformName(),
      });
    } catch (err) {
      console.warn('PushService: backend unregister failed', err);
    }
  }

  // Remove native listeners
  if (isNativePlatform()) {
    try {
      const module = await import('@capacitor/push-notifications');
      await module.PushNotifications.removeAllListeners();
    } catch {
      // Plugin may not be available
    }
  }

  _deviceToken = null;
  _initialized = false;
  _notificationCallbacks = [];

  console.log('PushService: teardown complete');
}

// ============================================================================
// Utility
// ============================================================================

/**
 * Convert a base64-encoded VAPID public key to a Uint8Array
 * (required by PushManager.subscribe).
 */
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export default {
  initializePushNotifications,
  registerDeviceToken,
  handleNotificationReceived,
  handleNotificationAction,
  onNotification,
  teardownPushNotifications,
  getDeviceToken,
  isInitialized,
  isSupported,
  getPermissionStatus,
};
