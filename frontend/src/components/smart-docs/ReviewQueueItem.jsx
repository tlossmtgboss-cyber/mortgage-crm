/**
 * ReviewQueueItem Component
 *
 * Renders a single item in the document review queue as a 5-column grid row:
 * Priority badge | Doc info | Meta | Claim status | Action buttons
 *
 * Props:
 *   document      {object}   — queue item from the API
 *   onClaim       {function} — (documentId) => void
 *   onRelease     {function} — (documentId) => void
 *   onAiReview    {function} — (documentId) => void
 *   onViewDetail  {function} — (documentId) => void
 *   currentUserId {string}   — logged-in user's ID for claim ownership check
 */
import React from 'react';
import './ReviewQueueItem.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(dateStr) {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatConfidence(value) {
  if (value == null) return '—';
  const pct = typeof value === 'number' && value <= 1 ? Math.round(value * 100) : Math.round(value);
  return `${pct}%`;
}

function getPriorityMod(priority) {
  switch ((priority || '').toUpperCase()) {
    case 'CRITICAL': return 'rqi__priority--critical';
    case 'HIGH':     return 'rqi__priority--high';
    case 'NORMAL':   return 'rqi__priority--normal';
    case 'LOW':      return 'rqi__priority--low';
    default:         return 'rqi__priority--normal';
  }
}

function getRowMod(priority) {
  switch ((priority || '').toUpperCase()) {
    case 'CRITICAL': return 'rqi--critical';
    case 'HIGH':     return 'rqi--high';
    default:         return '';
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ReviewQueueItem({
  document,
  onClaim,
  onRelease,
  onAiReview,
  onViewDetail,
  currentUserId,
}) {
  if (!document) return null;

  const {
    id,
    doc_type,
    borrower_name,
    loan_number,
    priority,
    uploaded_at,
    ai_confidence,
    claimed_by_id,
    claimed_by_name,
  } = document;

  const isClaimed         = Boolean(claimed_by_id);
  const isClaimedByMe     = isClaimed && String(claimed_by_id) === String(currentUserId);
  const isClaimedByOther  = isClaimed && !isClaimedByMe;

  const rowClass = [
    'rqi',
    getRowMod(priority),
    isClaimed ? 'rqi--claimed' : '',
  ]
    .filter(Boolean)
    .join(' ');

  // ---- Col 1: Priority badge -----------------------------------------------
  const priorityBadge = (
    <div className="rqi__col rqi__col--priority">
      <span className={`rqi__priority ${getPriorityMod(priority)}`}>
        {(priority || 'NORMAL').toUpperCase()}
      </span>
    </div>
  );

  // ---- Col 2: Doc info -------------------------------------------------------
  const docInfo = (
    <div className="rqi__col rqi__col--info">
      <span className="rqi__doc-type">{doc_type || 'Unknown Type'}</span>
      {borrower_name && <span className="rqi__borrower">{borrower_name}</span>}
      {loan_number   && <span className="rqi__loan-num">#{loan_number}</span>}
    </div>
  );

  // ---- Col 3: Meta -----------------------------------------------------------
  const meta = (
    <div className="rqi__col rqi__col--meta">
      {uploaded_at && (
        <span className="rqi__meta-item">
          <span className="rqi__meta-label">Uploaded</span>
          <span>{formatDate(uploaded_at)}</span>
        </span>
      )}
      {ai_confidence != null && (
        <span className="rqi__meta-item">
          <span className="rqi__meta-label">AI confidence</span>
          <span>{formatConfidence(ai_confidence)}</span>
        </span>
      )}
    </div>
  );

  // ---- Col 4: Claim status ---------------------------------------------------
  const claimStatus = (
    <div className="rqi__col rqi__col--claim">
      {isClaimedByMe && (
        <span className="rqi__claim-tag rqi__claim-tag--mine">Claimed by you</span>
      )}
      {isClaimedByOther && (
        <span className="rqi__claim-tag rqi__claim-tag--other">
          Claimed by {claimed_by_name || 'reviewer'}
        </span>
      )}
      {!isClaimed && (
        <span className="rqi__claim-tag rqi__claim-tag--open">Unclaimed</span>
      )}
    </div>
  );

  // ---- Col 5: Actions -------------------------------------------------------
  const actions = (
    <div className="rqi__col rqi__col--actions">
      {/* View detail always available */}
      <button
        className="rqi__btn rqi__btn--ghost"
        onClick={() => onViewDetail && onViewDetail(id)}
        title="View detail"
      >
        View
      </button>

      {/* Unclaimed: Claim + AI Review */}
      {!isClaimed && (
        <>
          <button
            className="rqi__btn rqi__btn--primary"
            onClick={() => onClaim && onClaim(id)}
            title="Claim this document for review"
          >
            Claim
          </button>
          <button
            className="rqi__btn rqi__btn--secondary"
            onClick={() => onAiReview && onAiReview(id)}
            title="Run AI review"
          >
            AI Review
          </button>
        </>
      )}

      {/* Claimed by me: Review + Release */}
      {isClaimedByMe && (
        <>
          <button
            className="rqi__btn rqi__btn--primary"
            onClick={() => onViewDetail && onViewDetail(id)}
            title="Review this document"
          >
            Review
          </button>
          <button
            className="rqi__btn rqi__btn--danger"
            onClick={() => onRelease && onRelease(id)}
            title="Release back to queue"
          >
            Release
          </button>
        </>
      )}
    </div>
  );

  return (
    <div className={rowClass}>
      {priorityBadge}
      {docInfo}
      {meta}
      {claimStatus}
      {actions}
    </div>
  );
}
