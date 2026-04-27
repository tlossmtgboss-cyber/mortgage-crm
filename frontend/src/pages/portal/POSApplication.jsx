/**
 * POSApplication — page wrapper for the borrower portal.
 *
 * Mount this under your existing PortalContainer. It pulls the loan_id
 * from the route, falling back to the borrower's primary loan if none is
 * specified. The actual UI lives in the POSContainer feature component.
 *
 * Example route registration:
 *
 *   <Route path="/portal/application" element={<POSApplication />} />
 *   <Route path="/portal/loans/:loanId/application" element={<POSApplication />} />
 *
 * If your portal is JSX (not TSX), this file works as-is — TypeScript
 * annotations are minimal.
 */
import React from 'react';
import { useParams } from 'react-router-dom';

import { POSContainer } from '../../features/pos';

export default function POSApplication() {
  const { loanId } = useParams();
  const parsed = loanId ? Number(loanId) : undefined;

  return (
    <div className="portal-page portal-page--pos">
      <POSContainer loanId={Number.isFinite(parsed) ? parsed : undefined} />
    </div>
  );
}
