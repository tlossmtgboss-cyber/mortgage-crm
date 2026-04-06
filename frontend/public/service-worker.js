/* Perennia AI — Service Worker for Offline Support */
/* Caches app shell, handles API fallback, queues offline mutations, push notifications */

const CACHE_NAME = 'perennia-v1';
const API_CACHE_NAME = 'perennia-api-v1';
const OFFLINE_QUEUE_DB = 'perennia-offline-queue';
const OFFLINE_QUEUE_STORE = 'mutations';
const DB_VERSION = 1;

const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
];

// API paths that should be cached for offline read access
const CACHEABLE_API_PATHS = [
  '/api/v1/leads',
  '/api/v1/loans',
  '/api/v1/pipeline',
  '/api/v1/tasks',
  '/api/v1/contacts',
  '/api/v1/users/me',
  '/api/v1/notifications',
];

// HTTP methods that represent mutations (queue when offline)
const MUTATION_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE'];

// ─── IndexedDB helpers for offline mutation queue ────────────────────────────

function openOfflineDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(OFFLINE_QUEUE_DB, DB_VERSION);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(OFFLINE_QUEUE_STORE)) {
        const store = db.createObjectStore(OFFLINE_QUEUE_STORE, {
          keyPath: 'id',
          autoIncrement: true,
        });
        store.createIndex('timestamp', 'timestamp', { unique: false });
        store.createIndex('url', 'url', { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function enqueueOfflineMutation(request) {
  try {
    const body = await request.clone().text();
    const mutation = {
      url: request.url,
      method: request.method,
      headers: Object.fromEntries(request.headers.entries()),
      body: body || null,
      timestamp: Date.now(),
    };

    const db = await openOfflineDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readwrite');
      const store = tx.objectStore(OFFLINE_QUEUE_STORE);
      const addRequest = store.add(mutation);
      addRequest.onsuccess = () => resolve(addRequest.result);
      addRequest.onerror = () => reject(addRequest.error);
      tx.oncomplete = () => db.close();
    });
  } catch (error) {
    console.error('[SW] Failed to queue offline mutation:', error);
  }
}

async function getOfflineMutations() {
  const db = await openOfflineDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readonly');
    const store = tx.objectStore(OFFLINE_QUEUE_STORE);
    const getAll = store.getAll();
    getAll.onsuccess = () => resolve(getAll.result);
    getAll.onerror = () => reject(getAll.error);
    tx.oncomplete = () => db.close();
  });
}

async function clearOfflineMutation(id) {
  const db = await openOfflineDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readwrite');
    const store = tx.objectStore(OFFLINE_QUEUE_STORE);
    const deleteRequest = store.delete(id);
    deleteRequest.onsuccess = () => resolve();
    deleteRequest.onerror = () => reject(deleteRequest.error);
    tx.oncomplete = () => db.close();
  });
}

// ─── Offline mutation sync ──────────────────────────────────────────────────

async function syncOfflineMutations() {
  let mutations;
  try {
    mutations = await getOfflineMutations();
  } catch (error) {
    console.error('[SW] Failed to read offline queue:', error);
    return;
  }

  if (!mutations || mutations.length === 0) return;

  console.log(`[SW] Syncing ${mutations.length} offline mutation(s)...`);

  for (const mutation of mutations) {
    try {
      const fetchOptions = {
        method: mutation.method,
        headers: mutation.headers,
      };
      // Only attach body for methods that support it
      if (mutation.body && MUTATION_METHODS.includes(mutation.method)) {
        fetchOptions.body = mutation.body;
      }

      const response = await fetch(mutation.url, fetchOptions);

      if (response.ok || response.status === 409) {
        // Success or conflict (already applied) — remove from queue
        await clearOfflineMutation(mutation.id);
        console.log(`[SW] Synced mutation ${mutation.id}: ${mutation.method} ${mutation.url}`);
      } else if (response.status >= 500) {
        // Server error — stop retrying, will try again next sync
        console.warn(`[SW] Server error syncing mutation ${mutation.id}, will retry later`);
        break;
      } else {
        // Client error (4xx) — remove from queue, cannot be retried
        await clearOfflineMutation(mutation.id);
        console.warn(`[SW] Mutation ${mutation.id} failed with ${response.status}, discarding`);
      }
    } catch (error) {
      // Network still down — stop retrying
      console.warn('[SW] Still offline, stopping sync');
      break;
    }
  }

  // Notify all clients about sync completion
  const clients = await self.clients.matchAll();
  for (const client of clients) {
    client.postMessage({
      type: 'OFFLINE_SYNC_COMPLETE',
      remaining: (await getOfflineMutations()).length,
    });
  }
}

// ─── Install ────────────────────────────────────────────────────────────────

self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker...');
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// ─── Activate ───────────────────────────────────────────────────────────────

self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker...');
  const validCaches = [CACHE_NAME, API_CACHE_NAME];
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => !validCaches.includes(k)).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ─── Fetch strategies ───────────────────────────────────────────────────────

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    // Cache successful GET responses for offline fallback
    if (request.method === 'GET' && response.ok) {
      const cache = await caches.open(API_CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    // Network failed — try cache
    const cached = await caches.match(request);
    if (cached) return cached;
    // No cache — return offline error
    return new Response(
      JSON.stringify({ error: 'You are offline', offline: true }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }
    );
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    // For navigation requests, return the cached index.html (SPA fallback)
    if (request.mode === 'navigate') {
      const fallback = await caches.match('/index.html');
      if (fallback) return fallback;
    }
    return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
  }
}

// ─── Fetch handler ──────────────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-HTTP(S) requests
  if (!url.protocol.startsWith('http')) return;

  // Skip cross-origin requests (CDN assets, analytics, etc.)
  if (url.origin !== self.location.origin) return;

  // API calls
  if (url.pathname.startsWith('/api/')) {
    // Mutations: queue if offline
    if (MUTATION_METHODS.includes(event.request.method)) {
      event.respondWith(handleMutation(event.request));
      return;
    }
    // GET: network-first with cache fallback
    event.respondWith(networkFirst(event.request));
    return;
  }

  // Static assets and navigation: cache-first
  event.respondWith(cacheFirst(event.request));
});

async function handleMutation(request) {
  try {
    const response = await fetch(request.clone());
    return response;
  } catch (error) {
    // Offline — queue the mutation for later sync
    await enqueueOfflineMutation(request);

    // Notify the client that mutation was queued
    const clients = await self.clients.matchAll();
    for (const client of clients) {
      client.postMessage({
        type: 'MUTATION_QUEUED',
        url: request.url,
        method: request.method,
      });
    }

    return new Response(
      JSON.stringify({
        queued: true,
        message: 'Your change has been saved offline and will sync when you reconnect.',
      }),
      {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }
    );
  }
}

// ─── Background sync (when browser supports it) ────────────────────────────

self.addEventListener('sync', (event) => {
  if (event.tag === 'offline-mutations') {
    event.waitUntil(syncOfflineMutations());
  }
});

// ─── Push notifications ─────────────────────────────────────────────────────

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data ? event.data.text() : 'You have a new update' };
  }

  const options = {
    body: data.body || 'You have a new update',
    icon: data.icon || '/favicon.ico',
    badge: '/favicon.ico',
    tag: data.tag || 'perennia-notification',
    data: {
      url: data.url || '/',
      type: data.type || 'general',
      entityId: data.entityId || null,
    },
    actions: data.actions || [],
    requireInteraction: data.requireInteraction || false,
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'Perennia AI', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl = event.notification.data?.url || '/';

  // Handle action button clicks
  if (event.action) {
    // Action-specific handling can be added here
    console.log(`[SW] Notification action clicked: ${event.action}`);
  }

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Focus existing window if available
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      // Open new window if none found
      return self.clients.openWindow(targetUrl);
    })
  );
});

// ─── Message handler (for client communication) ─────────────────────────────

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }

  if (event.data && event.data.type === 'SYNC_NOW') {
    event.waitUntil(syncOfflineMutations());
  }

  if (event.data && event.data.type === 'GET_QUEUE_STATUS') {
    event.waitUntil(
      getOfflineMutations().then((mutations) => {
        event.source.postMessage({
          type: 'QUEUE_STATUS',
          count: mutations.length,
          mutations: mutations.map((m) => ({
            id: m.id,
            url: m.url,
            method: m.method,
            timestamp: m.timestamp,
          })),
        });
      })
    );
  }
});
