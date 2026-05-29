/**
 * LegacyPortalRedirect tests.
 *
 * Phase 0 of the portal consolidation: dead token-based portal routes
 * (/portal/active/:token, /portal/ultimate/token/:token) must redirect into
 * the live token entry point (/borrower-portal/:token) instead of mounting an
 * abandoned portal component. This guards stale links already in borrower
 * inboxes before the dead components are deleted in a later phase.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useParams } from 'react-router-dom';
import LegacyPortalRedirect from '../LegacyPortalRedirect';

// Lands on the redirect destination and reports back the resolved :token.
function TokenProbe({ onResolve }) {
  const { token } = useParams();
  onResolve(token);
  return <div>LIVE PORTAL</div>;
}

function renderAt(initialPath, onResolve = () => {}) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/portal/active/:token" element={<LegacyPortalRedirect />} />
        <Route path="/portal/ultimate/token/:token" element={<LegacyPortalRedirect />} />
        <Route path="/borrower-portal/:token" element={<TokenProbe onResolve={onResolve} />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('LegacyPortalRedirect', () => {
  it('redirects /portal/active/:token to /borrower-portal/:token', () => {
    renderAt('/portal/active/tok_abc123');
    expect(screen.getByText('LIVE PORTAL')).toBeInTheDocument();
  });

  it('redirects /portal/ultimate/token/:token to /borrower-portal/:token', () => {
    renderAt('/portal/ultimate/token/tok_xyz789');
    expect(screen.getByText('LIVE PORTAL')).toBeInTheDocument();
  });

  it('preserves the token value through the redirect', () => {
    let captured = null;
    renderAt('/portal/active/tok_KEEPME', (t) => { captured = t; });
    expect(captured).toBe('tok_KEEPME');
  });
});
