/**
 * LegacyPortalRedirect
 *
 * Phase 0 of the portal consolidation. Dead token-based portal routes
 * (`/portal/active/:token`, `/portal/ultimate/token/:token`) pointed at
 * abandoned portal components with zero inbound link generation. This redirects
 * those stale links into the live token entry point (`/borrower-portal/:token`)
 * so any links already sitting in borrower inboxes keep working after the dead
 * components are deleted.
 *
 * loanId-based legacy routes use the existing `LoanPortalRedirect` instead,
 * which resolves loanId -> portal via GET /api/portal/by-loan/{loanId}.
 */
import React from 'react';
import { Navigate, useParams } from 'react-router-dom';

export default function LegacyPortalRedirect() {
  const { token } = useParams();
  return <Navigate to={`/borrower-portal/${encodeURIComponent(token)}`} replace />;
}
