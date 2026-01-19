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

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
/* Trigger rebuild - Sat Nov 15 07:18:33 EST 2025 */
// Force rebuild $(date)
// Trigger deployment 1767495280
// Force Vercel rebuild 1768858234
