/**
 * POSTestPage — dev-only test harness for the POS borrower application.
 *
 * Accessible at /pos-test in local dev. Sets up a mock PURL token in
 * localStorage and renders the full POS experience without requiring
 * a real magic link. The backend routes are proxied through Vite to
 * the production API (or local backend if running).
 *
 * DO NOT deploy this to production.
 */
import React, { useEffect, useState } from 'react';
import { POSContainer } from '../../features/pos';

const DEV_MOCK_TOKEN = 'purl_live_dev_test_token_00000000';

export default function POSTestPage() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Set mock PURL token so the API client picks it up
    localStorage.setItem('perennia_purl_token', DEV_MOCK_TOKEN);

    // Also set on window for the fallback path
    window.__PURL_TOKEN__ = DEV_MOCK_TOKEN;

    setReady(true);

    return () => {
      // Cleanup on unmount
      localStorage.removeItem('perennia_purl_token');
      delete window.__PURL_TOKEN__;
    };
  }, []);

  if (!ready) return <div style={{ padding: 40 }}>Setting up test environment...</div>;

  return (
    <div style={{ minHeight: '100vh', background: '#f5f7fa' }}>
      <div style={{
        background: '#ff6b35',
        color: '#fff',
        padding: '8px 20px',
        fontSize: 13,
        fontWeight: 600,
        textAlign: 'center',
        letterSpacing: '0.5px',
      }}>
        DEV TEST MODE — POS Borrower Application
      </div>
      <POSContainer />
    </div>
  );
}
