/**
 * Perennia AI — Service Worker
 *
 * Provides offline support with smart caching strategies:
 * - Cache-first for static assets (JS, CSS, fonts, images)
 * - Network-first with 24-hour cache fallback for key API endpoints
 * - Never caches POST/PATCH/DELETE or auth endpoints
 * - Enforces cache size limits (max 100 API responses)
 * - Cleans up expired entries on activation
 * - Safe inside Capacitor/WKWebView (no-ops gracefully)
 */

const CACHE_VERSION = 'v2';
const STATIC_CACHE = 'perennia-static-' + CACHE_VERSION;
const API_CACHE = 'perennia-api-' + CACHE_VERSION;

// Max age for cached API responses (24 hours)
const API_CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000;

// Max number of API responses to keep in cache
const API_CACHE_MAX_ENTRIES = 100;

// API paths eligible for network-first caching (GET only)
const CACHEABLE_API_PATHS = [
  '/api/v1/mobile/dashboard',
  '/api/v1/mobile/pipeline',
  '/api/v1/mobile/tasks',
  '/api/v1/mobile/notifications',
  '/api/v1/leads/',
  '/api/v1/loans/',
  '/api/v1/scheduler/appointments',
  '/api/v1/pipeline/metrics',
  '/api/v1/dashboard/summary',
  '/api/v1/rate-alerts',
  '/api/v1/rate-monitor/alerts',
  '/api/v1/tasks',
  '/api/v1/notifications',
];

// Paths that must never be cached
const NEVER_CACHE_PREFIXES = [
  '/api/v1/auth/',
];

// Extensions treated as static assets
const STATIC_EXTENSIONS = [
  '.js', '.css', '.woff', '.woff2', '.ttf', '.otf', '.eot',
  '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',
];

// -------------------------------------------------------------------
// Native platform guard — avoid running caching logic in iOS WKWebView
// where service workers behave unpredictably.
// -------------------------------------------------------------------

function isNativeWebView() {
  // Check common Capacitor/Cordova/WKWebView markers.
  // self.location is available in SW scope; Capacitor apps load from
  // capacitor:// or ionic:// schemes, or localhost with a native user-agent.
  // The safest signal: if the origin uses a non-http scheme we're native.
  if (
    typeof self !== 'undefined' &&
    self.location &&
    !self.location.protocol.startsWith('http')
  ) {
    return true;
  }
  return false;
}

// -------------------------------------------------------------------
// Install — precache nothing, just activate immediately
// -------------------------------------------------------------------

self.addEventListener('install', (event) => {
  console.log('[SW] Installing');
  self.skipWaiting();
});

// -------------------------------------------------------------------
// Activate — claim clients, delete old caches, clean expired entries
// -------------------------------------------------------------------

self.addEventListener('activate', (event) => {
  console.log('[SW] Activating');
  const currentCaches = [STATIC_CACHE, API_CACHE];
  event.waitUntil(
    Promise.all([
      // 1. Delete old cache versions
      caches.keys().then((keys) =>
        Promise.all(
          keys
            .filter((key) => !currentCaches.includes(key))
            .map((key) => {
              console.log('[SW] Deleting old cache:', key);
              return caches.delete(key);
            })
        )
      ),
      // 2. Evict expired API entries from current cache
      evictExpiredEntries(),
      // 3. Enforce size limit on API cache
      enforceApiCacheSizeLimit(),
    ]).then(() => self.clients.claim())
  );
});

// -------------------------------------------------------------------
// Fetch handler
// -------------------------------------------------------------------

self.addEventListener('fetch', (event) => {
  // Skip entirely in native iOS WebView
  if (isNativeWebView()) return;

  const url = new URL(event.request.url);

  // Only handle same-origin HTTP(S) GET requests
  if (!url.protocol.startsWith('http')) return;
  if (url.origin !== self.location.origin) return;
  if (event.request.method !== 'GET') return;

  // Never cache auth endpoints or other blacklisted paths
  if (isNeverCachePath(url.pathname)) return;

  // API requests — network-first with cache fallback
  if (isCacheableApiPath(url.pathname)) {
    event.respondWith(networkFirstWithExpiry(event.request));
    return;
  }

  // Static assets — cache-first
  if (isStaticAsset(url.pathname)) {
    event.respondWith(cacheFirstStatic(event.request));
    return;
  }

  // Everything else (HTML, etc.) — go to network, no caching
  // The no-cache meta tags on index.html handle freshness
});

// -------------------------------------------------------------------
// Strategy: network-first with 24-hour expiry for API responses
// -------------------------------------------------------------------

async function networkFirstWithExpiry(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(API_CACHE);
      // Store response with a timestamp header for expiry checking
      const cloned = response.clone();
      const headers = new Headers(cloned.headers);
      headers.set('x-sw-cached-at', Date.now().toString());
      const timestampedResponse = new Response(await cloned.blob(), {
        status: cloned.status,
        statusText: cloned.statusText,
        headers: headers,
      });
      await cache.put(request, timestampedResponse);
      // Enforce size limit after adding a new entry
      enforceApiCacheSizeLimit();
    }
    return response;
  } catch (error) {
    // Network failed — try cache
    const cached = await caches.match(request);
    if (cached) {
      const cachedAt = parseInt(cached.headers.get('x-sw-cached-at') || '0', 10);
      const age = Date.now() - cachedAt;
      if (age < API_CACHE_MAX_AGE_MS) {
        console.log('[SW] Serving cached API response:', request.url);
        return cached;
      }
      // Expired but still better than nothing when offline
      console.log('[SW] Serving expired cached API response:', request.url);
      return cached;
    }
    // No cache available — return offline error
    return new Response(
      JSON.stringify({
        error: 'You are offline and no cached data is available.',
        offline: true,
      }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }
    );
  }
}

// -------------------------------------------------------------------
// Strategy: cache-first for static assets
// -------------------------------------------------------------------

async function cacheFirstStatic(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    return new Response('', { status: 503, statusText: 'Offline' });
  }
}

// -------------------------------------------------------------------
// Cache maintenance — evict expired entries
// -------------------------------------------------------------------

async function evictExpiredEntries() {
  try {
    const cache = await caches.open(API_CACHE);
    const requests = await cache.keys();
    const now = Date.now();

    await Promise.all(
      requests.map(async (request) => {
        const response = await cache.match(request);
        if (!response) return;
        const cachedAt = parseInt(response.headers.get('x-sw-cached-at') || '0', 10);
        if (cachedAt > 0 && (now - cachedAt) > API_CACHE_MAX_AGE_MS) {
          console.log('[SW] Evicting expired cache entry:', request.url);
          await cache.delete(request);
        }
      })
    );
  } catch (error) {
    console.warn('[SW] Error evicting expired entries:', error);
  }
}

// -------------------------------------------------------------------
// Cache maintenance — enforce max entry count (LRU-ish: oldest first)
// -------------------------------------------------------------------

async function enforceApiCacheSizeLimit() {
  try {
    const cache = await caches.open(API_CACHE);
    const requests = await cache.keys();

    if (requests.length <= API_CACHE_MAX_ENTRIES) return;

    // Build list with timestamps so we can evict oldest
    const entries = await Promise.all(
      requests.map(async (request) => {
        const response = await cache.match(request);
        const cachedAt = parseInt(
          (response && response.headers.get('x-sw-cached-at')) || '0',
          10
        );
        return { request, cachedAt };
      })
    );

    // Sort oldest-first
    entries.sort((a, b) => a.cachedAt - b.cachedAt);

    // Delete oldest entries until we're at the limit
    const toRemove = entries.length - API_CACHE_MAX_ENTRIES;
    for (let i = 0; i < toRemove; i++) {
      console.log('[SW] Evicting cache entry (over limit):', entries[i].request.url);
      await cache.delete(entries[i].request);
    }
  } catch (error) {
    console.warn('[SW] Error enforcing cache size limit:', error);
  }
}

// -------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------

function isCacheableApiPath(pathname) {
  return CACHEABLE_API_PATHS.some((path) => pathname.startsWith(path));
}

function isNeverCachePath(pathname) {
  return NEVER_CACHE_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isStaticAsset(pathname) {
  return STATIC_EXTENSIONS.some((ext) => pathname.endsWith(ext));
}
