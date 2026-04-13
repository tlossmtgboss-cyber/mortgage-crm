/**
 * Deep Link Handler Utility
 *
 * Handles deep links when the app is opened from a push notification,
 * Spotlight search, or universal/custom-scheme link. Parses URLs like:
 *
 *   perenniaai://leads/123  ->  /leads/123
 *   perenniaai://loans/456  ->  /loans/456
 *   perenniaai://tasks/789  ->  /tasks
 *   https://app.perenniaai.com/leads/123  ->  /leads/123
 *
 * Works with both Capacitor App.addListener('appUrlOpen') and web URL params.
 *
 * Usage (from a React component inside <Router>):
 *
 *   import { setupDeepLinking } from '../utils/deepLinkHandler';
 *
 *   function MyComponent() {
 *     const navigate = useNavigate();
 *     useEffect(() => setupDeepLinking(navigate), [navigate]);
 *   }
 *
 * If the app hasn't completed auth yet, the deep link is stored and can be
 * consumed after login via consumePendingDeepLink().
 */

import { Capacitor } from '@capacitor/core';
import {
  initDeepLinkRouter,
  consumePendingDeepLink,
  parseDeepLink,
  DEEP_LINK_ROUTES,
} from '../services/deepLinkRouter';
import { isAuthenticatedSync } from './auth';

// ---------------------------------------------------------------------------
// Pending deep link for cold-start (stores link before auth is complete)
// ---------------------------------------------------------------------------

const PENDING_KEY = 'perennia_pending_deep_link';
let _pendingDeepLink = null;

/**
 * Store a deep link to process after the user authenticates.
 * Called automatically when a deep link arrives before login.
 *
 * @param {string} route - The resolved React Router path
 */
export function storePendingDeepLink(route) {
  _pendingDeepLink = route;
  try {
    sessionStorage.setItem(PENDING_KEY, route);
  } catch (_) {
    // sessionStorage may be unavailable
  }
}

/**
 * Retrieve and clear any pending deep link (in-memory or sessionStorage).
 * Call this after successful auth to navigate the user to their intended
 * destination.
 *
 * @returns {string|null} The stored route, or null if none
 */
export function getPendingDeepLink() {
  // Check in-memory first (survives within the same JS session)
  if (_pendingDeepLink) {
    const route = _pendingDeepLink;
    _pendingDeepLink = null;
    try { sessionStorage.removeItem(PENDING_KEY); } catch (_) {}
    return route;
  }

  // Fall back to the deepLinkRouter's sessionStorage-based pending link
  return consumePendingDeepLink();
}

// ---------------------------------------------------------------------------
// URL parsing helpers
// ---------------------------------------------------------------------------

/**
 * Parse a deep link URL into a React Router path.
 *
 * Supports:
 *   - Custom scheme:    perenniaai://leads/123
 *   - Universal links:  https://app.perenniaai.com/leads/123
 *   - Bare paths:       /leads/123
 *   - Web query params: ?deeplink=leads/123
 *
 * @param {string} url - The raw URL string
 * @returns {string|null} The resolved React Router path, or null if unrecognized
 */
export function resolveDeepLink(url) {
  if (!url) return null;

  const { route } = parseDeepLink(url);
  return route;
}

/**
 * Check if a URL matches any known deep link route.
 *
 * @param {string} url
 * @returns {boolean}
 */
export function isKnownDeepLink(url) {
  const route = resolveDeepLink(url);
  return route !== null && route !== '/';
}

// ---------------------------------------------------------------------------
// Web deep link support (query param ?deeplink=...)
// ---------------------------------------------------------------------------

/**
 * Check the current page URL for a ?deeplink= query parameter and navigate
 * to it if present. This supports web-based deep linking (e.g., links in
 * emails that include a deeplink param).
 *
 * @param {Function} navigate - React Router navigate function
 * @returns {boolean} true if a deep link was found and processed
 */
function handleWebDeepLinkParam(navigate) {
  try {
    const params = new URLSearchParams(window.location.search);
    const deeplink = params.get('deeplink');
    if (!deeplink) return false;

    const route = deeplink.startsWith('/') ? deeplink : `/${deeplink}`;
    const resolved = resolveDeepLink(route);
    if (!resolved) return false;

    if (isAuthenticatedSync()) {
      navigate(resolved);
    } else {
      storePendingDeepLink(resolved);
    }

    // Clean the URL to remove the deeplink param
    params.delete('deeplink');
    const cleanSearch = params.toString();
    const cleanUrl = window.location.pathname + (cleanSearch ? `?${cleanSearch}` : '');
    window.history.replaceState(null, '', cleanUrl);

    return true;
  } catch (err) {
    console.warn('[DeepLinkHandler] Error processing web deep link param:', err);
    return false;
  }
}

// ---------------------------------------------------------------------------
// Main setup function
// ---------------------------------------------------------------------------

let _cleanupFn = null;

/**
 * Set up deep link handling for the app.
 *
 * On native (Capacitor): registers listeners for appUrlOpen, appRestoredResult,
 * cold launch URLs, and pushNotificationNavigation events.
 *
 * On web: checks for a ?deeplink= query parameter in the current URL.
 *
 * Handles the case where the app hasn't loaded/authenticated yet by storing
 * the deep link for later consumption via getPendingDeepLink().
 *
 * @param {Function} navigate - React Router navigate function (from useNavigate)
 * @returns {Function} Cleanup function to remove listeners
 */
export function setupDeepLinking(navigate) {
  if (!navigate) {
    console.warn('[DeepLinkHandler] setupDeepLinking called without a navigate function');
    return () => {};
  }

  // Tear down any previous listeners
  if (_cleanupFn) {
    _cleanupFn();
    _cleanupFn = null;
  }

  // Process any pending deep link from a previous cold start
  const pending = getPendingDeepLink();
  if (pending && isAuthenticatedSync()) {
    // Defer navigation slightly to avoid interfering with initial render
    setTimeout(() => navigate(pending), 0);
  }

  if (Capacitor.isNativePlatform()) {
    // Native: delegate to the full deepLinkRouter which handles
    // appUrlOpen, appRestoredResult, getLaunchUrl, and native push events
    const cleanup = initDeepLinkRouter(navigate);

    _cleanupFn = cleanup;
    return cleanup;
  }

  // Web: check for ?deeplink= query parameter
  handleWebDeepLinkParam(navigate);

  // No persistent listeners needed on web
  _cleanupFn = () => {};
  return _cleanupFn;
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

// Re-export route table for consumers that need it
export { DEEP_LINK_ROUTES };

export default {
  setupDeepLinking,
  resolveDeepLink,
  isKnownDeepLink,
  storePendingDeepLink,
  getPendingDeepLink,
  DEEP_LINK_ROUTES,
};
