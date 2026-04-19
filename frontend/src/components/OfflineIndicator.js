import React, { useState, useEffect, useCallback } from 'react';
import { Capacitor } from '@capacitor/core';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import './OfflineIndicator.css';

export function OfflineIndicator() {
  const { isOnline } = useNetworkStatus();
  const isNative = Capacitor.isNativePlatform();
  const [dismissed, setDismissed] = useState(false);
  const [showReconnected, setShowReconnected] = useState(false);
  const [wasOffline, setWasOffline] = useState(false);

  // Track offline-to-online transitions
  useEffect(() => {
    if (!isOnline) {
      setWasOffline(true);
      setDismissed(false); // Reset dismiss when going offline again
    } else if (wasOffline && isOnline) {
      // Just came back online
      setShowReconnected(true);
      setWasOffline(false);
      const timer = setTimeout(() => setShowReconnected(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [isOnline, wasOffline]);

  const handleDismiss = useCallback(() => {
    setDismissed(true);
  }, []);

  // Show reconnected toast briefly
  if (showReconnected) {
    return (
      <div
        className="offline-indicator offline-indicator--reconnected visible"
        role="status"
        aria-live="polite"
      >
        <span className="offline-indicator__dot offline-indicator__dot--online" />
        Back online
      </div>
    );
  }

  // Show offline banner (unless dismissed)
  if (dismissed || isOnline) {
    return null;
  }

  return (
    <div
      className="offline-indicator visible"
      role="alert"
      aria-live="assertive"
    >
      <span className="offline-indicator__dot" />
      <span className="offline-indicator__message">
        {isNative
          ? "You're offline \u2014 changes will sync when reconnected"
          : "You're offline \u2014 showing cached data"}
      </span>
      <button
        className="offline-indicator__dismiss"
        onClick={handleDismiss}
        aria-label="Dismiss offline notification"
        type="button"
      >
        &times;
      </button>
    </div>
  );
}

export default OfflineIndicator;
