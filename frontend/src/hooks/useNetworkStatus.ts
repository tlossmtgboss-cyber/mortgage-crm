/**
 * useNetworkStatus — Detects online/offline state.
 * Uses @capacitor/network on native, navigator.onLine on web.
 */
import { useState, useEffect } from 'react';
import { Capacitor } from '@capacitor/core';

export interface NetworkStatus {
  isOnline: boolean;
  connectionType: string;
}

export function useNetworkStatus(): NetworkStatus {
  const [isOnline, setIsOnline] = useState<boolean>(true);
  const [connectionType, setConnectionType] = useState<string>('unknown');

  useEffect(() => {
    if (Capacitor.isNativePlatform()) {
      let listener: Promise<{ remove: () => void }> | undefined;
      import('@capacitor/network').then(({ Network }) => {
        Network.getStatus().then((status) => {
          setIsOnline(status.connected);
          setConnectionType(status.connectionType);
        });

        listener = Network.addListener('networkStatusChange', (status) => {
          setIsOnline(status.connected);
          setConnectionType(status.connectionType);
        });
      });

      return () => {
        if (listener) listener.then((l) => l.remove());
      };
    } else {
      const handleOnline = (): void => setIsOnline(true);
      const handleOffline = (): void => setIsOnline(false);
      setIsOnline(navigator.onLine);

      window.addEventListener('online', handleOnline);
      window.addEventListener('offline', handleOffline);
      return () => {
        window.removeEventListener('online', handleOnline);
        window.removeEventListener('offline', handleOffline);
      };
    }
  }, []);

  return { isOnline, connectionType };
}

export default useNetworkStatus;
