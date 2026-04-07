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

// Register service worker for offline support (web only, not Capacitor)
if ('serviceWorker' in navigator && !window.Capacitor) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js')
      .then(reg => console.log('SW registered:', reg.scope))
      .catch(err => console.warn('SW registration failed:', err));
  });
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
