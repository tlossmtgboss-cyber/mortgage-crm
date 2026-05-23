import React from 'react';
import ReactDOM from 'react-dom/client';
import './setupConsole'; // Disable console.log in production
import './index.css';
import App from './App';
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

// Initialize certificate pinning (native only — no-op on web)
import certificatePinning from './services/certificatePinning';

certificatePinning.initialize().then((result) => {
  if (result?.method !== 'web_noop' && result?.method !== 'disabled') {
    console.info('[Security] Certificate pinning active:', result.method);
  }
}).catch((err) => {
  console.error('[Security] Certificate pinning failed:', err);
});

// Initialize in-memory token store (loads from Preferences/localStorage)
import { initialize as initTokenStore } from './utils/tokenStore';
initTokenStore();

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);

// In dev mode, unregister any stale service worker to prevent cached chunk conflicts.
// In production, register for offline support and push notifications.
if (import.meta.env.DEV) {
  serviceWorkerRegistration.unregister();
} else {
  serviceWorkerRegistration.register({
    onUpdate: (registration) => {
      console.log('[App] New version available — will activate on next reload');
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
