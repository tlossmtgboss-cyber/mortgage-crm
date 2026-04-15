import React from 'react';
import ReactDOM from 'react-dom/client';
import './setupConsole'; // Disable console.log in production
import './index.css';
import App from './App';
import ErrorBoundary from './ErrorBoundary';

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

// Register service worker for offline support (web only, not Capacitor native)
// WKWebView on iOS doesn't support service workers and will crash/error
const isNative = window.Capacitor?.isNativePlatform?.() || window.Capacitor?.isNative;
if (!isNative && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js')
      .then(reg => console.log('SW registered:', reg.scope))
      .catch(err => console.warn('SW registration failed:', err));
  });
}

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
