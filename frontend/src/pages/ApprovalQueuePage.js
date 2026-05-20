import React from 'react';
import ApprovalQueue from '../components/ApprovalQueue';

/**
 * Standalone page wrapper for the ApprovalQueue component.
 * Provides the full-page layout with header when accessed via /approval-queue route.
 */
function ApprovalQueuePage() {
  return <ApprovalQueue embedded={false} />;
}

export default ApprovalQueuePage;
