/**
 * Deep Link Router for Perennia AI Mobile App
 *
 * Parses incoming deep link URLs (universal links, custom scheme) and
 * maps them to internal React Router paths.  Provides an auth gate that
 * queues navigation when the user is not yet logged in.
 *
 * Usage (from App.jsx):
 *   import { initDeepLinkRouter } from './services/deepLinkRouter';
 *   // inside your component, after you have a navigate function:
 *   useEffect(() => initDeepLinkRouter(navigate), [navigate]);
 */

import { Capacitor } from '@capacitor/core';
import { App as CapApp } from '@capacitor/app';
import { isAuthenticatedSync } from '../utils/auth';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Domains that Perennia AI universal links can arrive on. */
const KNOWN_HOSTS = [
  'app.perenniaai.com',
  'www.perenniaai.com',
  'perenniaai.com',
];

/** Custom URL scheme used for push-notification deep links. */
const CUSTOM_SCHEME = 'perenniaai';

/**
 * DEEP_LINK_ROUTES
 *
 * Each entry maps a URL pattern to its internal React Router path.
 *   pattern  - Express-style path with :param placeholders
 *   resolve  - function(params, query) => internal route string
 *   authRequired - whether the user must be logged in (default true)
 *
 * Order matters: first match wins.  More specific patterns should come
 * before less specific ones (e.g. /smart-docs/client/:id before /smart-docs).
 */
export const DEEP_LINK_ROUTES = [
  // Loans
  {
    pattern: '/loans/:id',
    resolve: (p) => `/loans/${p.id}`,
    authRequired: true,
  },
  // Leads
  {
    pattern: '/leads/:id',
    resolve: (p) => `/leads/${p.id}`,
    authRequired: true,
  },
  // Tasks — individual task IDs land on the tasks list
  {
    pattern: '/tasks/:id',
    resolve: () => '/tasks',
    authRequired: true,
  },
  {
    pattern: '/tasks',
    resolve: () => '/tasks',
    authRequired: true,
  },
  // Calendar
  {
    pattern: '/calendar',
    resolve: () => '/calendar',
    authRequired: true,
  },
  // Notifications — mobile notification center
  {
    pattern: '/notifications',
    resolve: () => '/notifications',
    authRequired: true,
  },
  // Pipeline — MobilePipelineView (maps to efficiency dashboard)
  {
    pattern: '/pipeline',
    resolve: () => '/efficiency',
    authRequired: true,
  },
  // Smart Docs
  {
    pattern: '/smart-docs/review/:id',
    resolve: (p) => `/smart-docs/client/${p.id}`,
    authRequired: true,
  },
  {
    pattern: '/smart-docs/client/:loanId',
    resolve: (p) => `/smart-docs/client/${p.loanId}`,
    authRequired: true,
  },
  {
    pattern: '/smart-docs',
    resolve: () => '/smart-docs',
    authRequired: true,
  },
  // Dashboard
  {
    pattern: '/dashboard',
    resolve: () => '/dashboard',
    authRequired: true,
  },
  // Workflow
  {
    pattern: '/workflow/:stage',
    resolve: (p) => `/workflow/${p.stage}`,
    authRequired: true,
  },
  {
    pattern: '/workflow',
    resolve: () => '/workflow',
    authRequired: true,
  },
  // Settings
  {
    pattern: '/settings',
    resolve: () => '/settings',
    authRequired: true,
  },

  // -----------------------------------------------------------------------
  // Public routes (no auth gate)
  // -----------------------------------------------------------------------

  // Borrower application with token
  {
    pattern: '/apply/:token',
    resolve: (p) => `/apply/${p.token}`,
    authRequired: false,
  },
  // Public booking pages
  {
    pattern: '/book/:slug',
    resolve: (p) => `/book/${p.slug}`,
    authRequired: false,
  },
  // Portal (public borrower portal)
  {
    pattern: '/portal/:token',
    resolve: (p) => `/portal/${p.token}`,
    authRequired: false,
  },
  // Signing session
  {
    pattern: '/sign/:token',
    resolve: (p) => `/sign/${p.token}`,
    authRequired: false,
  },
  // Borrower portal by token
  {
    pattern: '/borrower-portal/:token',
    resolve: (p) => `/borrower-portal/${p.token}`,
    authRequired: false,
  },
];

// ---------------------------------------------------------------------------
// Pending route (auth gate)
// ---------------------------------------------------------------------------

const PENDING_ROUTE_KEY = 'perennia_pending_deep_link';

/**
 * Store a route to navigate to after the user logs in.
 */
function storePendingRoute(route) {
  try {
    sessionStorage.setItem(PENDING_ROUTE_KEY, route);
  } catch (_) {
    // sessionStorage may be unavailable in some contexts
  }
}

/**
 * Consume (read and clear) any pending deep link route.
 * Call this after successful login to redirect the user.
 *
 * @returns {string|null}
 */
export function consumePendingDeepLink() {
  try {
    const route = sessionStorage.getItem(PENDING_ROUTE_KEY);
    if (route) {
      sessionStorage.removeItem(PENDING_ROUTE_KEY);
    }
    return route || null;
  } catch (_) {
    return null;
  }
}

// ---------------------------------------------------------------------------
// URL parsing
// ---------------------------------------------------------------------------

/**
 * Parse a deep link URL string into { route, params, query }.
 *
 * Handles:
 *  - Universal links: https://app.perenniaai.com/loans/123
 *  - Custom scheme:   perenniaai://notification?type=loan&id=123
 *  - Bare paths:      /loans/123
 *
 * @param {string} urlString
 * @returns {{ route: string|null, params: Record<string,string>, query: Record<string,string> }}
 */
export function parseDeepLink(urlString) {
  if (!urlString) {
    return { route: null, params: {}, query: {} };
  }

  let pathname = '';
  let queryParams = {};

  try {
    // Handle custom scheme (perenniaai://...)
    if (urlString.startsWith(`${CUSTOM_SCHEME}://`)) {
      // Replace custom scheme with https so URL constructor can parse it
      const normalized = urlString.replace(`${CUSTOM_SCHEME}://`, 'https://deeplink.local/');
      const url = new URL(normalized);
      pathname = url.pathname;
      queryParams = Object.fromEntries(url.searchParams.entries());

      // For notification-style deep links (perenniaai://notification?type=loan&id=123),
      // the "host" becomes the action type.  Map known notification types to routes.
      const action = urlString.split('://')[1]?.split('?')[0]?.split('/')[0];
      if (action === 'notification' || action === 'open') {
        const resolved = resolveNotificationLink(queryParams);
        if (resolved) {
          return resolved;
        }
      }
    } else if (urlString.startsWith('/')) {
      // Bare path
      const withHost = `https://deeplink.local${urlString}`;
      const url = new URL(withHost);
      pathname = url.pathname;
      queryParams = Object.fromEntries(url.searchParams.entries());
    } else {
      // Universal link (https://app.perenniaai.com/...)
      const url = new URL(urlString);
      // Only process links for our known hosts
      if (!KNOWN_HOSTS.includes(url.hostname) && url.hostname !== 'localhost') {
        console.log('[DeepLink] Ignoring URL with unknown host:', url.hostname);
        return { route: null, params: {}, query: {} };
      }
      pathname = url.pathname;
      queryParams = Object.fromEntries(url.searchParams.entries());
    }
  } catch (e) {
    console.error('[DeepLink] Failed to parse URL:', urlString, e);
    return { route: null, params: {}, query: {} };
  }

  // Normalize: strip trailing slash, ensure leading slash
  pathname = pathname.replace(/\/+$/, '') || '/';
  if (!pathname.startsWith('/')) {
    pathname = '/' + pathname;
  }

  // Match against route table
  const match = matchRoute(pathname);
  if (match) {
    return {
      route: match.route,
      params: { ...match.params, ...queryParams },
      query: queryParams,
    };
  }

  // No match in our table — pass through the raw pathname
  // (React Router will handle 404 / redirect as appropriate)
  console.log('[DeepLink] No route match, passing through:', pathname);
  return { route: pathname, params: queryParams, query: queryParams };
}

// ---------------------------------------------------------------------------
// Route matching
// ---------------------------------------------------------------------------

/**
 * Match a pathname against DEEP_LINK_ROUTES.
 *
 * @param {string} pathname  e.g. "/loans/abc-123"
 * @returns {{ route: string, params: Record<string,string>, authRequired: boolean } | null}
 */
function matchRoute(pathname) {
  for (const entry of DEEP_LINK_ROUTES) {
    const params = matchPattern(entry.pattern, pathname);
    if (params !== null) {
      const route = entry.resolve(params);
      return { route, params, authRequired: entry.authRequired };
    }
  }
  return null;
}

/**
 * Match an Express-style pattern against a pathname.
 * Returns extracted params on match, or null on mismatch.
 *
 * Examples:
 *   matchPattern('/loans/:id', '/loans/123')  => { id: '123' }
 *   matchPattern('/tasks',      '/tasks')      => {}
 *   matchPattern('/loans/:id', '/leads/123')  => null
 */
function matchPattern(pattern, pathname) {
  const patternParts = pattern.split('/').filter(Boolean);
  const pathParts = pathname.split('/').filter(Boolean);

  if (patternParts.length !== pathParts.length) {
    return null;
  }

  const params = {};
  for (let i = 0; i < patternParts.length; i++) {
    const pat = patternParts[i];
    const val = pathParts[i];

    if (pat.startsWith(':')) {
      params[pat.slice(1)] = decodeURIComponent(val);
    } else if (pat !== val) {
      return null;
    }
  }

  return params;
}

// ---------------------------------------------------------------------------
// Notification deep-link resolver
// ---------------------------------------------------------------------------

/**
 * Resolve notification-style deep links like:
 *   perenniaai://notification?type=loan&id=123
 *   perenniaai://open?type=lead&id=456
 *
 * @param {Record<string,string>} query
 * @returns {{ route: string, params: Record<string,string>, query: Record<string,string> } | null}
 */
function resolveNotificationLink(query) {
  const { type, id } = query;
  if (!type) return null;

  const typeRouteMap = {
    loan: id ? `/loans/${id}` : '/loans',
    lead: id ? `/leads/${id}` : '/leads',
    task: '/tasks',
    calendar: '/calendar',
    document: id ? `/smart-docs/client/${id}` : '/smart-docs',
    smart_docs: id ? `/smart-docs/client/${id}` : '/smart-docs',
    workflow: id ? `/workflow/${id}` : '/workflow',
    pipeline: '/efficiency',
    notification: '/notifications',
  };

  const route = typeRouteMap[type];
  if (!route) return null;

  return {
    route,
    params: { ...query },
    query,
  };
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

/** Tracks active listener cleanup functions */
let _cleanup = null;

/**
 * Initialize the deep link router.
 *
 * Call this once from App.jsx (inside a useEffect) with the React Router
 * `navigate` function.  Returns a cleanup function that removes all
 * Capacitor listeners.
 *
 * @param {Function} navigate - React Router navigate function
 * @returns {Function} cleanup function
 */
export function initDeepLinkRouter(navigate) {
  // Only initialize on native platforms
  if (!Capacitor.isNativePlatform()) {
    return () => {};
  }

  // Tear down any previous listeners (safety for HMR / re-mounts)
  if (_cleanup) {
    _cleanup();
    _cleanup = null;
  }

  const listeners = [];

  /**
   * Handle a deep link URL string.
   */
  function handleDeepLink(urlString) {
    console.log('[DeepLink] Received:', urlString);

    const { route, params } = parseDeepLink(urlString);
    if (!route || route === '/') {
      console.log('[DeepLink] No actionable route from URL');
      return;
    }

    console.log('[DeepLink] Resolved route:', route, 'params:', params);

    // Check auth gate
    const match = matchRoute(route) || matchRoute(urlString);
    const authRequired = match ? match.authRequired : true;

    if (authRequired && !isAuthenticatedSync()) {
      console.log('[DeepLink] User not authenticated, storing pending route:', route);
      storePendingRoute(route);
      navigate('/login');
      return;
    }

    navigate(route);
  }

  // Listen for appUrlOpen — fires when the app is already running
  // and a universal link / custom scheme URL is opened.
  const urlOpenPromise = CapApp.addListener('appUrlOpen', (event) => {
    try {
      handleDeepLink(event.url);
    } catch (e) {
      console.error('[DeepLink] Error handling appUrlOpen:', e);
    }
  });
  listeners.push(urlOpenPromise);

  // Listen for appRestoredResult — fires on cold start when the app was
  // launched via a deep link and the activity/view was restored.
  const restoredPromise = CapApp.addListener('appRestoredResult', (data) => {
    try {
      if (data && data.url) {
        console.log('[DeepLink] Restored result with URL:', data.url);
        handleDeepLink(data.url);
      }
    } catch (e) {
      console.error('[DeepLink] Error handling appRestoredResult:', e);
    }
  });
  listeners.push(restoredPromise);

  // Check if the app was cold-launched via a deep link by querying
  // the launch URL (getLaunchUrl).
  CapApp.getLaunchUrl().then((result) => {
    if (result && result.url) {
      console.log('[DeepLink] Cold launch URL:', result.url);
      handleDeepLink(result.url);
    }
  }).catch((e) => {
    // getLaunchUrl may not be available on all platforms
    console.log('[DeepLink] getLaunchUrl not available:', e.message || e);
  });

  // Build cleanup function
  _cleanup = () => {
    for (const p of listeners) {
      p.then((handle) => handle.remove()).catch(() => {});
    }
  };

  return _cleanup;
}
