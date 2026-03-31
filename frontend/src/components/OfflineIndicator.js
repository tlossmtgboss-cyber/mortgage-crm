import React from 'react';
import { Capacitor } from '@capacitor/core';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import './OfflineIndicator.css';

export function OfflineIndicator() {
  const { isOnline } = useNetworkStatus();
  const isNative = Capacitor.isNativePlatform();

  return (
    <div
      className={`offline-indicator ${!isOnline ? 'visible' : ''}`}
      role="status"
      aria-live="polite"
    >
      <span className="offline-indicator__dot" />
      {isNative
        ? "You're offline \u2014 changes will sync when reconnected"
        : "You're offline \u2014 showing cached data"}
    </div>
  );
}

export default OfflineIndicator;
