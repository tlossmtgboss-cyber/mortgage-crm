/**
 * OfflineSyncStatus — Compact banner that shows offline mutation queue status.
 *
 * Positioned directly above the MobileBottomNav.
 *
 * States:
 *   - "3 changes pending sync"    (amber)   — offline with queued mutations
 *   - "Syncing..."                 (blue)    — processing the queue
 *   - "All synced"                 (green)   — queue drained, auto-hides after 3s
 *   - "2 changes failed"           (red)     — permanent failures, shows Retry button
 *   - "Offline"                    (gray)    — offline with empty queue
 *   - hidden                                 — online with nothing to report
 */
import React, { useState, useEffect, useRef } from 'react';
import useOfflineMutation from '../../hooks/useOfflineMutation';
import './OfflineSyncStatus.css';

// SVG icons (inline to avoid dependency)
const CheckIcon = () => (
  <span className="offline-sync-icon">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  </span>
);

const AlertIcon = () => (
  <span className="offline-sync-icon">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  </span>
);

const CloudOffIcon = () => (
  <span className="offline-sync-icon">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="1" y1="1" x2="23" y2="23" />
      <path d="M7.73 7.73A6 6 0 0 0 6 18h7" />
      <path d="M20.5 16.77A4.5 4.5 0 0 0 18 9h-1.26A8 8 0 0 0 11 4.06" />
    </svg>
  </span>
);

export function OfflineSyncStatus() {
  const { isOnline, isSyncing, queueStatus, retryFailed, syncNow } = useOfflineMutation();

  // Track "all synced" auto-hide timer
  const [showSuccess, setShowSuccess] = useState(false);
  const prevPendingRef = useRef(0);
  const hideTimerRef = useRef(null);

  // Detect transition: had pending items -> now all resolved
  useEffect(() => {
    const hadPending = prevPendingRef.current > 0;
    const nowClear =
      queueStatus.pending === 0 &&
      queueStatus.syncing === 0 &&
      queueStatus.failed === 0 &&
      queueStatus.conflict === 0;

    if (hadPending && nowClear && isOnline) {
      setShowSuccess(true);
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = setTimeout(() => setShowSuccess(false), 3000);
    }

    prevPendingRef.current = queueStatus.pending + queueStatus.syncing;

    return () => clearTimeout(hideTimerRef.current);
  }, [queueStatus, isOnline]);

  // Determine banner state
  const pendingCount = queueStatus.pending + queueStatus.conflict;
  const failedCount = queueStatus.failed;
  const totalActionable = pendingCount + failedCount + queueStatus.syncing;

  // Decide visibility and variant
  let variant = null; // null = hidden
  let message = '';
  let icon = null;
  let showRetry = false;

  if (isSyncing || queueStatus.syncing > 0) {
    variant = 'syncing';
    message = 'Syncing...';
    icon = <span className="offline-sync-spinner" />;
  } else if (failedCount > 0) {
    variant = 'failed';
    message = `${failedCount} change${failedCount !== 1 ? 's' : ''} failed`;
    icon = <AlertIcon />;
    showRetry = true;
  } else if (!isOnline && pendingCount > 0) {
    variant = 'pending';
    message = `${pendingCount} change${pendingCount !== 1 ? 's' : ''} pending sync`;
    icon = <CloudOffIcon />;
  } else if (!isOnline && totalActionable === 0) {
    variant = 'offline';
    message = 'Offline';
    icon = <CloudOffIcon />;
  } else if (showSuccess) {
    variant = 'success';
    message = 'All synced';
    icon = <CheckIcon />;
  } else if (isOnline && pendingCount > 0) {
    // Online but items haven't started syncing yet
    variant = 'pending';
    message = `${pendingCount} change${pendingCount !== 1 ? 's' : ''} pending sync`;
    icon = <CloudOffIcon />;
  }
  // else: variant stays null => banner hidden

  const hidden = variant === null;

  const handleRetry = async () => {
    await retryFailed();
    if (isOnline) {
      syncNow();
    }
  };

  return (
    <div
      className={`offline-sync-banner offline-sync-banner--${variant || 'hidden'} ${hidden ? 'offline-sync-banner--hidden' : ''}`}
      role="status"
      aria-live="polite"
      aria-hidden={hidden}
    >
      {icon}
      <span>{message}</span>
      {showRetry && (
        <button className="offline-sync-retry" onClick={handleRetry} type="button">
          Retry
        </button>
      )}
    </div>
  );
}

export default OfflineSyncStatus;
