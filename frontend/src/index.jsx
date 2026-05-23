import React from 'react';
import ReactDOM from 'react-dom/client';
import './setupConsole'; // Disable console.log in production
import './index.css';
// Import from modular App.jsx (routes, layouts, and providers are now separate modules)
import App from './App.jsx';
import ErrorBoundary from './ErrorBoundary';
import * as serviceWorkerRegistration from './serviceWorkerRegistration';

// Global handler for chunk load errors (stale cache after deployment)
window.addEventListener('error', (event) => {
  if (event.message && (event.message.includes('Loading chunk') || event.message.includes('Loading CSS chunk'))) {
    window.location.reload();
  }
});

// Handle unhandled promise rejections for dynamic imports
window.addEventListener('unhandledrejection', (event) => {
  if (event.reason && event.reason.message &&
      (event.reason.message.includes('Loading chunk') || event.reason.message.includes('Loading CSS chunk'))) {
    window.location.reload();
  }
});

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
// Register service worker for offline support and push notifications (production only).
// In dev mode, unregister any leftover SW to prevent stale chunk caching.
if (import.meta.env.DEV) {
  serviceWorkerRegistration.unregister();
} else {
serviceWorkerRegistration.register({
  onUpdate: (registration) => {
    // New version available — user will get it on next reload
    console.log('[App] New version available');
  },
  onSuccess: () => {
    console.log('[App] Offline support ready');
  },
  onMutationQueued: (data) => {
    console.log('[App] Change saved offline:', data.method, data.url);
  },
  onSyncComplete: (data) => {
    console.log('[App] Offline changes synced, remaining:', data.remaining);
  },
});
}

/* Trigger rebuild - Sat Nov 15 07:18:33 EST 2025 */
// Force rebuild $(date)
// Trigger deployment 1767495280
// Force Vercel rebuild 1737406200
