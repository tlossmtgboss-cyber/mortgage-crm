/**
 * MDM Configuration Context
 * Perennia AI - Provides MDM-pushed enterprise policies to the component tree
 *
 * Initializes MDM config on mount and exposes policy values via React context.
 * Components can use the useMDMConfig() hook to read MDM restrictions.
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { App as CapApp } from '@capacitor/app';
import {
  initMDMConfig,
  invalidateMDMCache,
  isFeatureDisabledByMDM,
  getMDMServerUrl,
  getMDMSessionTimeout,
  isBiometricRequired,
  getMDMOrganizationId,
  getMDMSSOConfig,
} from '../services/mdmConfig';

// Native plugin bridge for DLP / VPN status queries
const MDMConfigNative = registerPlugin('MDMConfig', {
  web: () =>
    Promise.resolve({
      getDLPStatus: async () => ({
        clipboardAllowed: true,
        vpnRequired: false,
        vpnConnected: false,
        isCompliant: true,
      }),
      checkClipboardPolicy: async () => ({ allowed: true }),
    }),
});

const MDMConfigContext = createContext(null);

/**
 * Hook to access MDM configuration from context.
 *
 * @returns {{
 *   isManaged: boolean,
 *   isLoading: boolean,
 *   policiesApplied: string[],
 *   requireBiometric: boolean,
 *   sessionTimeout: number | null,
 *   featuresDisabled: string[],
 *   serverUrl: string | null,
 *   organizationId: string | null,
 *   ssoConfig: { provider: string, domain: string | null } | null,
 *   clipboardAllowed: boolean,
 *   vpnRequired: boolean,
 *   vpnConnected: boolean,
 *   isFeatureDisabled: (featureName: string) => boolean,
 *   checkClipboardPolicy: () => Promise<boolean>,
 *   refresh: () => Promise<void>,
 * }}
 */
export function useMDMConfig() {
  const context = useContext(MDMConfigContext);
  if (!context) {
    // Safe defaults when used outside provider
    return {
      isManaged: false,
      isLoading: false,
      policiesApplied: [],
      requireBiometric: false,
      sessionTimeout: null,
      featuresDisabled: [],
      serverUrl: null,
      organizationId: null,
      ssoConfig: null,
      clipboardAllowed: true,
      vpnRequired: false,
      vpnConnected: false,
      isFeatureDisabled: () => false,
      checkClipboardPolicy: async () => true,
      refresh: async () => {},
    };
  }
  return context;
}

/**
 * Provider component. Must be placed near the top of the app tree,
 * before session manager initialization so MDM policies take effect first.
 */
export function MDMConfigProvider({ children }) {
  const [isManaged, setIsManaged] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [policiesApplied, setPoliciesApplied] = useState([]);
  const [requireBiometric, setRequireBiometric] = useState(false);
  const [sessionTimeout, setSessionTimeout] = useState(null);
  const [featuresDisabled, setFeaturesDisabled] = useState([]);
  const [serverUrl, setServerUrl] = useState(null);
  const [organizationId, setOrganizationId] = useState(null);
  const [ssoConfig, setSsoConfig] = useState(null);
  const [clipboardAllowed, setClipboardAllowed] = useState(true);
  const [vpnRequired, setVpnRequired] = useState(false);
  const [vpnConnected, setVpnConnected] = useState(false);

  const loadConfig = useCallback(async () => {
    try {
      setIsLoading(true);
      const result = await initMDMConfig();

      setIsManaged(result.managed || false);
      setPoliciesApplied(result.policiesApplied || []);

      // Read applied policy values from localStorage (set by applyMDMPolicy)
      setRequireBiometric(isBiometricRequired());
      setSessionTimeout(getMDMSessionTimeout());
      setServerUrl(getMDMServerUrl());
      setOrganizationId(getMDMOrganizationId());
      setSsoConfig(getMDMSSOConfig());

      // Read features_disabled
      try {
        const raw = localStorage.getItem('mdm_features_disabled');
        setFeaturesDisabled(raw ? JSON.parse(raw) : []);
      } catch {
        setFeaturesDisabled([]);
      }

      // Read DLP / VPN policy status from native layer
      if (Capacitor.isNativePlatform()) {
        try {
          const dlp = await MDMConfigNative.getDLPStatus();
          setClipboardAllowed(dlp.clipboardAllowed ?? true);
          setVpnRequired(dlp.vpnRequired ?? false);
          setVpnConnected(dlp.vpnConnected ?? false);
        } catch (dlpErr) {
          console.warn('[MDMConfigContext] DLP status check failed:', dlpErr);
        }
      }
    } catch (err) {
      console.error('[MDMConfigContext] Initialization failed:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initialize on mount
  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // Re-read MDM config when app returns to foreground (config may have changed)
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    const listener = CapApp.addListener('appStateChange', ({ isActive }) => {
      if (isActive) {
        invalidateMDMCache();
        loadConfig();
      }
    });

    return () => {
      listener.then((l) => l.remove());
    };
  }, [loadConfig]);

  const isFeatureDisabled = useCallback(
    (featureName) => {
      return featuresDisabled.includes(featureName) || isFeatureDisabledByMDM(featureName);
    },
    [featuresDisabled]
  );

  const checkClipboardPolicy = useCallback(async () => {
    if (!Capacitor.isNativePlatform()) return true;
    try {
      const result = await MDMConfigNative.checkClipboardPolicy();
      return result?.allowed !== false;
    } catch {
      return true;
    }
  }, []);

  const refresh = useCallback(async () => {
    invalidateMDMCache();
    await loadConfig();
  }, [loadConfig]);

  const value = {
    isManaged,
    isLoading,
    policiesApplied,
    requireBiometric,
    sessionTimeout,
    featuresDisabled,
    serverUrl,
    organizationId,
    ssoConfig,
    clipboardAllowed,
    vpnRequired,
    vpnConnected,
    isFeatureDisabled,
    checkClipboardPolicy,
    refresh,
  };

  return (
    <MDMConfigContext.Provider value={value}>
      {children}
    </MDMConfigContext.Provider>
  );
}

export default MDMConfigContext;
