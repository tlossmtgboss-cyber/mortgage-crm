/**
 * Perennia AI — DEPRECATED Service Worker
 *
 * This file existed as a duplicate of service-worker.js. All offline support
 * is now consolidated in service-worker.js, registered via
 * serviceWorkerRegistration.js from main.jsx.
 *
 * This stub self-unregisters so any browser that cached it will clean up
 * and let service-worker.js take over on the next page load.
 */

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    self.registration.unregister().then(() => {
      console.log('[sw.js] Deprecated service worker unregistered. service-worker.js is now active.');
      return self.clients.matchAll();
    }).then((clients) => {
      // Notify clients so the new SW registration can take over
      clients.forEach((client) => client.navigate(client.url));
    })
  );
});
