/* Perennia AI — Service Worker Registration */
/* Registers the service worker and handles updates, offline sync triggers */

const SW_URL = '/service-worker.js';

// Check if running inside Capacitor native shell (iOS/Android)
function isNativePlatform() {
  return window.Capacitor?.isNativePlatform?.() || window.Capacitor?.isNative;
}

// Check if service workers are supported (and not in native WebView)
function isServiceWorkerSupported() {
  if (isNativePlatform()) {
    // WKWebView (iOS) does not support service workers and will error
    return false;
  }
  return 'serviceWorker' in navigator;
}

// Check if we're on localhost (for development)
function isLocalhost() {
  return (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '[::1]' ||
    /^127(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)){3}$/.test(window.location.hostname)
  );
}

/**
 * Register the service worker.
 * @param {Object} config - Optional configuration callbacks
 * @param {Function} config.onUpdate - Called when a new SW is available (receives registration)
 * @param {Function} config.onSuccess - Called when SW is registered and content is cached
 * @param {Function} config.onOfflineReady - Called when offline support is ready
 * @param {Function} config.onMutationQueued - Called when an offline mutation is queued
 * @param {Function} config.onSyncComplete - Called when offline mutations have been synced
 */
export function register(config = {}) {
  if (!isServiceWorkerSupported()) {
    console.log('[SW Registration] Service workers are not supported in this browser');
    return;
  }

  window.addEventListener('load', () => {
    if (isLocalhost()) {
      // On localhost, check if a service worker still exists or not
      checkValidServiceWorker(SW_URL, config);
      console.log('[SW Registration] Running in localhost mode');
    } else {
      // Production: register the service worker
      registerValidSW(SW_URL, config);
    }
  });

  // Listen for messages from the service worker
  if (navigator.serviceWorker) {
    navigator.serviceWorker.addEventListener('message', (event) => {
      if (event.data) {
        switch (event.data.type) {
          case 'MUTATION_QUEUED':
            if (config.onMutationQueued) {
              config.onMutationQueued(event.data);
            }
            break;
          case 'OFFLINE_SYNC_COMPLETE':
            if (config.onSyncComplete) {
              config.onSyncComplete(event.data);
            }
            break;
          case 'QUEUE_STATUS':
            if (config.onQueueStatus) {
              config.onQueueStatus(event.data);
            }
            break;
          default:
            break;
        }
      }
    });

    // Trigger sync when coming back online
    window.addEventListener('online', () => {
      console.log('[SW Registration] Back online — triggering sync');
      triggerSync();
    });
  }
}

function registerValidSW(swUrl, config) {
  navigator.serviceWorker
    .register(swUrl)
    .then((registration) => {
      console.log('[SW Registration] Registered successfully, scope:', registration.scope);

      // Check for updates periodically (every 30 minutes)
      setInterval(() => {
        registration.update();
      }, 30 * 60 * 1000);

      registration.onupdatefound = () => {
        const installingWorker = registration.installing;
        if (!installingWorker) return;

        installingWorker.onstatechange = () => {
          if (installingWorker.state === 'installed') {
            if (navigator.serviceWorker.controller) {
              // New content is available; old content has been purged
              console.log('[SW Registration] New content available, will be used on next reload');
              if (config.onUpdate) {
                config.onUpdate(registration);
              }
            } else {
              // Content cached for the first time (offline ready)
              console.log('[SW Registration] Content cached for offline use');
              if (config.onSuccess) {
                config.onSuccess(registration);
              }
              if (config.onOfflineReady) {
                config.onOfflineReady();
              }
            }
          }
        };
      };
    })
    .catch((error) => {
      console.error('[SW Registration] Error during registration:', error);
    });
}

function checkValidServiceWorker(swUrl, config) {
  // Check if the service worker file can be found
  fetch(swUrl, { headers: { 'Service-Worker': 'script' } })
    .then((response) => {
      const contentType = response.headers.get('content-type');
      if (
        response.status === 404 ||
        (contentType != null && contentType.indexOf('javascript') === -1)
      ) {
        // No service worker found — unregister and reload
        navigator.serviceWorker.ready.then((registration) => {
          registration.unregister().then(() => {
            window.location.reload();
          });
        });
      } else {
        // Service worker found — register as normal
        registerValidSW(swUrl, config);
      }
    })
    .catch(() => {
      console.log('[SW Registration] No internet connection found. App running in offline mode.');
    });
}

/**
 * Unregister the service worker.
 */
export function unregister() {
  if (!isServiceWorkerSupported()) return;

  navigator.serviceWorker.ready
    .then((registration) => {
      registration.unregister();
      console.log('[SW Registration] Service worker unregistered');
    })
    .catch((error) => {
      console.error('[SW Registration] Error during unregistration:', error);
    });
}

/**
 * Tell the waiting service worker to skip waiting and take over.
 * Useful when showing an "update available" prompt to the user.
 */
export function skipWaiting() {
  if (!isServiceWorkerSupported() || !navigator.serviceWorker.controller) return;

  navigator.serviceWorker.ready.then((registration) => {
    if (registration.waiting) {
      registration.waiting.postMessage({ type: 'SKIP_WAITING' });
    }
  });
}

/**
 * Trigger a sync of offline mutations.
 * Uses Background Sync API if available, falls back to message-based sync.
 */
export function triggerSync() {
  if (!isServiceWorkerSupported()) return;

  navigator.serviceWorker.ready.then((registration) => {
    if ('sync' in registration) {
      registration.sync.register('offline-mutations').catch((error) => {
        // Background Sync not supported or denied — fall back to message
        console.log('[SW Registration] Background Sync not available, using message sync');
        if (navigator.serviceWorker.controller) {
          navigator.serviceWorker.controller.postMessage({ type: 'SYNC_NOW' });
        }
      });
    } else if (navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ type: 'SYNC_NOW' });
    }
  });
}

/**
 * Request the current offline queue status from the service worker.
 */
export function getQueueStatus() {
  if (!isServiceWorkerSupported() || !navigator.serviceWorker.controller) return;

  navigator.serviceWorker.controller.postMessage({ type: 'GET_QUEUE_STATUS' });
}
