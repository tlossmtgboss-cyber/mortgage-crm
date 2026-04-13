/**
 * OfflineIndicator — Top-of-screen banner for mobile users.
 *
 * Shows connectivity state and sync progress:
 *   - Offline:              amber banner "You're offline -- changes will sync when connected"
 *   - Online + syncing:     blue banner  "Syncing X changes..." with spinner
 *   - Online + synced:      green banner "All changes synced" (auto-dismisses after 3s)
 *   - Online + idle:        hidden
 *
 * Only renders on mobile viewports (< 768px) or Capacitor native apps.
 */
import React, { useState, useEffect, useRef } from 'react';
import { Capacitor } from '@capacitor/core';
import { useOfflineSync } from '../../hooks/useOfflineSync';
import './OfflineIndicator.css';

function isMobileViewport() {
  return Capacitor.isNativePlatform() || window.innerWidth < 768;
}

export function OfflineIndicator() {
  const { isOnline, pendingCount, isSyncing } = useOfflineSync();
  const [isMobile, setIsMobile] = useState(isMobileViewport);
  const [showSuccess, setShowSuccess] = useState(false);
  const prevPendingRef = useRef(pendingCount);
  const hideTimerRef = useRef(null);

  // Track viewport changes (e.g. orientation, resize)
  useEffect(() => {
    if (Capacitor.isNativePlatform()) return; // always mobile on native

    const handleResize = () => setIsMobile(isMobileViewport());
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Detect sync completion: had pending items -> now 0 and online
  useEffect(() => {
    const hadPending = prevPendingRef.current > 0 || isSyncing;
    prevPendingRef.current = pendingCount;

    if (hadPending && pendingCount === 0 && !isSyncing && isOnline) {
      setShowSuccess(true);
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = setTimeout(() => setShowSuccess(false), 3000);
    }

    return () => clearTimeout(hideTimerRef.current);
  }, [pendingCount, isSyncing, isOnline]);

  // Don't render on desktop
  if (!isMobile) return null;

  // Determine banner state
  let variant = null;
  let message = '';

  if (!isOnline) {
    variant = 'offline';
    message = "You're offline \u2014 changes will sync when connected";
  } else if (isSyncing && pendingCount > 0) {
    variant = 'syncing';
    message = `Syncing ${pendingCount} change${pendingCount !== 1 ? 's' : ''}...`;
  } else if (isSyncing) {
    variant = 'syncing';
    message = 'Syncing...';
  } else if (showSuccess) {
    variant = 'success';
    message = 'All changes synced';
  }

  if (!variant) return null;

  return (
    <div
      className={`offline-indicator offline-indicator--${variant}`}
      role="status"
      aria-live="polite"
    >
      {variant === 'syncing' && <span className="offline-indicator__spinner" />}
      {variant === 'success' && (
        <svg
          className="offline-indicator__icon"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      )}
      {variant === 'offline' && (
        <svg
          className="offline-indicator__icon"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="1" y1="1" x2="23" y2="23" />
          <path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55" />
          <path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39" />
          <path d="M10.71 5.05A16 16 0 0 1 22.56 9" />
          <path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88" />
          <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
          <line x1="12" y1="20" x2="12.01" y2="20" />
        </svg>
      )}
      <span className="offline-indicator__text">{message}</span>
    </div>
  );
}

export default OfflineIndicator;
