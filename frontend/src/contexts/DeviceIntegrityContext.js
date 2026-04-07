/**
 * Device Integrity Context
 * Perennia AI - Provides device integrity state to the component tree
 *
 * Wraps the useDeviceIntegrity hook result and exposes it via React context
 * so any component can check feature restrictions without re-running checks.
 */

import React, { createContext, useContext, useState, useCallback } from 'react';
import { checkDeviceIntegrity, isFeatureRestricted } from '../services/deviceIntegrity';
import { reportDeviceIntegrity } from '../services/securityService';

const DeviceIntegrityContext = createContext(null);

/**
 * Hook to access device integrity state from context.
 *
 * @returns {{
 *   integrity: Object | null,
 *   isFeatureAllowed: (featureName: string) => boolean,
 *   runCheck: () => Promise<Object>,
 * }}
 */
export function useDeviceIntegrityContext() {
  const context = useContext(DeviceIntegrityContext);
  if (!context) {
    // Return safe defaults if used outside provider (e.g. public pages)
    return {
      integrity: null,
      isFeatureAllowed: () => true,
      runCheck: async () => null,
    };
  }
  return context;
}

/**
 * Provider component. Add near the top of the component tree.
 */
export function DeviceIntegrityProvider({ children }) {
  const [integrity, setIntegrity] = useState(null);

  const runCheck = useCallback(async () => {
    try {
      const result = await checkDeviceIntegrity();
      setIntegrity(result);

      // Report to backend if compromised
      if (result.isCompromised) {
        reportDeviceIntegrity(result);
      }

      return result;
    } catch (err) {
      console.error('Device integrity check error:', err);
      const safeResult = {
        isCompromised: false,
        reasons: ['check_error'],
        riskLevel: 'safe',
        timestamp: new Date().toISOString(),
        platform: 'unknown',
      };
      setIntegrity(safeResult);
      return safeResult;
    }
  }, []);

  const isFeatureAllowed = useCallback(
    (featureName) => {
      if (!integrity) return true; // Allow while no check has run
      return !isFeatureRestricted(featureName, integrity);
    },
    [integrity]
  );

  const value = { integrity, isFeatureAllowed, runCheck };

  return (
    <DeviceIntegrityContext.Provider value={value}>
      {children}
    </DeviceIntegrityContext.Provider>
  );
}

export default DeviceIntegrityContext;
