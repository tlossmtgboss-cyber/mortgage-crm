import React from 'react';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import './OfflineIndicator.css';

export function OfflineIndicator() {
  const { isOnline } = useNetworkStatus();

  return (
    <div className={`offline-indicator ${!isOnline ? 'visible' : ''}`}>
      <span className="offline-indicator__dot" />
      You're offline — showing cached data
    </div>
  );
}

export default OfflineIndicator;
