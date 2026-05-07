/**
 * Device Integrity Service
 * Perennia AI - Jailbreak/Root Detection & Compromised Device Policy
 *
 * Provides multi-layer integrity checks:
 *   1. Web-detectable checks (iframe, debug tools, screen capture)
 *   2. Native checks via Capacitor plugin (jailbreak file paths, sandbox,
 *      URL schemes, dyld injection, fork detection)
 *
 * Usage:
 *   import { checkDeviceIntegrity, useDeviceIntegrity } from './deviceIntegrity';
 *
 *   // Direct check
 *   const result = await checkDeviceIntegrity();
 *
 *   // React hook
 *   const { integrity, isLoading } = useDeviceIntegrity();
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { getToken } from '../utils/tokenStore';

// ---------------------------------------------------------------------------
// Native plugin bridge (only available on iOS/Android, no-ops on web)
// ---------------------------------------------------------------------------

const DeviceIntegrity = registerPlugin('DeviceIntegrity');

// ---------------------------------------------------------------------------
// Policy Configuration
// ---------------------------------------------------------------------------

export const INTEGRITY_POLICY = {
  /** If true, compromised devices get a warning but can still use the app.
   *  If false, compromised devices are blocked from restricted features. */
  allowCompromisedDevice: false,

  /** Show a non-dismissible warning overlay when compromised */
  showWarning: true,

  /** Features to disable on compromised devices */
  restrictFeatures: ['biometric', 'document_upload', 'payment'],

  /** Report integrity results to the backend for audit logging */
  reportToServer: true,

  /** Backend endpoint for integrity reports */
  reportEndpoint: '/api/v1/security/device-integrity',

  /** How often to re-check (in minutes). 0 = only on launch. */
  recheckIntervalMinutes: 0,
};

// ---------------------------------------------------------------------------
// Web-Layer Checks (run on all platforms)
// ---------------------------------------------------------------------------

/**
 * Detect if the app is running inside an iframe (potential phishing/clickjacking).
 */
function checkIframe() {
  try {
    if (window.self !== window.top) {
      return 'iframe_detected';
    }
  } catch (e) {
    // Cross-origin iframe blocks access to window.top
    return 'cross_origin_iframe';
  }
  return null;
}

/**
 * Detect common mobile/web debugging tools injected into the page.
 * Eruda and vConsole are commonly used to inspect hybrid app traffic.
 */
function checkDebugTools() {
  const reasons = [];

  // Eruda (mobile debug console)
  if (typeof window.eruda !== 'undefined') {
    reasons.push('debug_tool:eruda');
  }

  // vConsole (Tencent mobile debug panel)
  if (typeof window.VConsole !== 'undefined' || typeof window.__vconsole !== 'undefined') {
    reasons.push('debug_tool:vconsole');
  }

  // Check for Weinre (remote debug)
  if (typeof window.__weinre !== 'undefined') {
    reasons.push('debug_tool:weinre');
  }

  // Check if devtools are open via debugger timing trick.
  // This is imperfect but provides a signal.
  try {
    const threshold = 100; // ms
    const before = performance.now();
    // The debugger statement pauses execution only when devtools are open
    // eslint-disable-next-line no-debugger
    debugger;
    const after = performance.now();
    if (after - before > threshold) {
      reasons.push('devtools_open');
    }
  } catch (e) {
    // Ignore - some environments throw on debugger
  }

  return reasons;
}

/**
 * Check for suspicious global overrides that may indicate browser extension
 * tampering or man-in-the-browser attacks.
 */
function checkSuspiciousOverrides() {
  const reasons = [];

  // Check if fetch or XMLHttpRequest have been monkey-patched
  // (common in proxy/intercept extensions)
  try {
    const nativeFetch = window.fetch.toString();
    if (!nativeFetch.includes('[native code]') && !nativeFetch.includes('function fetch()')) {
      reasons.push('fetch_override');
    }
  } catch (e) {
    // Ignore
  }

  // Check for Proxy on common crypto APIs (indicates interception)
  try {
    if (window.crypto && window.crypto.subtle) {
      const subtleStr = window.crypto.subtle.toString();
      if (subtleStr.includes('Proxy')) {
        reasons.push('crypto_api_proxy');
      }
    }
  } catch (e) {
    // Ignore
  }

  return reasons;
}

/**
 * Detect if screen is being recorded/captured (limited browser support).
 * Uses the Screen Capture API detection where available.
 */
async function checkScreenCapture() {
  const reasons = [];

  try {
    // navigator.mediaDevices.getDisplayMedia is used for screen capture.
    // We cannot detect active capture, but we can check if the
    // Display Capture API has been used by checking active media streams.
    if (typeof navigator.mediaDevices !== 'undefined') {
      // Check for active screen capture tracks
      // Note: This only works if the capture was initiated from this page
      const devices = await navigator.mediaDevices.enumerateDevices();
      const hasScreenCapture = devices.some(
        (d) => d.kind === 'videoinput' && d.label.toLowerCase().includes('screen')
      );
      if (hasScreenCapture) {
        reasons.push('screen_capture_device');
      }
    }
  } catch (e) {
    // Permission denied or API not available - this is fine
  }

  return reasons;
}

// ---------------------------------------------------------------------------
// Native Checks (call Capacitor plugin when available)
// ---------------------------------------------------------------------------

/**
 * Call the native DeviceIntegrity plugin for platform-specific checks.
 * Returns empty result on web where the plugin is not available.
 */
async function checkNativeIntegrity() {
  const isNative = Capacitor.isNativePlatform();

  if (!isNative) {
    return {
      isCompromised: false,
      reasons: [],
      riskLevel: 'safe',
      platform: 'web',
      checkCount: 0,
    };
  }

  try {
    const result = await DeviceIntegrity.checkIntegrity();
    return result;
  } catch (error) {
    console.error('Native integrity check failed:', error);
    // If the native plugin call itself fails, treat as unknown
    // rather than compromised to avoid false positives
    return {
      isCompromised: false,
      reasons: ['native_check_unavailable'],
      riskLevel: 'safe',
      platform: Capacitor.getPlatform(),
      checkCount: 0,
      error: error.message,
    };
  }
}

// ---------------------------------------------------------------------------
// Main Check Function
// ---------------------------------------------------------------------------

/**
 * Perform a comprehensive device integrity check.
 *
 * @returns {Promise<{
 *   isCompromised: boolean,
 *   reasons: string[],
 *   riskLevel: 'safe' | 'warning' | 'critical',
 *   timestamp: string,
 *   platform: string,
 * }>}
 */
export async function checkDeviceIntegrity() {
  const allReasons = [];

  // --- Web-layer checks (all platforms) ---
  const iframeResult = checkIframe();
  if (iframeResult) allReasons.push(iframeResult);

  const debugResults = checkDebugTools();
  allReasons.push(...debugResults);

  const overrideResults = checkSuspiciousOverrides();
  allReasons.push(...overrideResults);

  const screenResults = await checkScreenCapture();
  allReasons.push(...screenResults);

  // --- Native-layer checks (iOS/Android only) ---
  const nativeResult = await checkNativeIntegrity();
  if (nativeResult.reasons) {
    allReasons.push(...nativeResult.reasons);
  }

  // --- Aggregate result ---
  const isCompromised = allReasons.length > 0;

  let riskLevel = 'safe';
  if (nativeResult.riskLevel === 'critical' || allReasons.length >= 3) {
    riskLevel = 'critical';
  } else if (isCompromised) {
    riskLevel = 'warning';
  }

  const result = {
    isCompromised,
    reasons: allReasons,
    riskLevel,
    timestamp: new Date().toISOString(),
    platform: Capacitor.getPlatform(),
  };

  // Report to server if configured
  if (INTEGRITY_POLICY.reportToServer && isCompromised) {
    reportIntegrityResult(result).catch((err) => {
      console.error('Failed to report integrity result:', err);
    });
  }

  return result;
}

// ---------------------------------------------------------------------------
// Feature Restriction Helper
// ---------------------------------------------------------------------------

/**
 * Check if a specific feature should be restricted based on the last
 * integrity check result.
 *
 * @param {string} featureName - One of: 'biometric', 'document_upload', 'payment'
 * @param {{ isCompromised: boolean, riskLevel: string }} integrityResult
 * @returns {boolean} true if the feature should be blocked
 */
export function isFeatureRestricted(featureName, integrityResult) {
  if (!integrityResult || !integrityResult.isCompromised) {
    return false;
  }

  if (INTEGRITY_POLICY.allowCompromisedDevice) {
    return false;
  }

  return INTEGRITY_POLICY.restrictFeatures.includes(featureName);
}

// ---------------------------------------------------------------------------
// Server Reporting
// ---------------------------------------------------------------------------

/**
 * Report integrity check results to the backend for audit logging.
 * Fire-and-forget; failures are logged but not surfaced to the user.
 */
async function reportIntegrityResult(result) {
  try {
    const token = getToken();
    if (!token) return;

    await fetch(INTEGRITY_POLICY.reportEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        isCompromised: result.isCompromised,
        reasons: result.reasons,
        riskLevel: result.riskLevel,
        platform: result.platform,
        timestamp: result.timestamp,
        appVersion: import.meta.env.VITE_APP_VERSION || 'unknown',
      }),
    });
  } catch (error) {
    // Silent fail - integrity reporting should never break the app
    console.warn('Integrity report failed:', error.message);
  }
}

// ---------------------------------------------------------------------------
// Warning Message
// ---------------------------------------------------------------------------

export const COMPROMISED_DEVICE_MESSAGE =
  'This device appears to be modified. For security, some features are ' +
  'restricted. Contact support if you believe this is an error.';

export const COMPROMISED_DEVICE_TITLE = 'Device Security Warning';

// ---------------------------------------------------------------------------
// React Hook
// ---------------------------------------------------------------------------

/**
 * React hook for device integrity checks.
 * Runs on mount (app launch) and optionally on a recurring interval.
 *
 * @returns {{
 *   integrity: { isCompromised: boolean, reasons: string[], riskLevel: string } | null,
 *   isLoading: boolean,
 *   error: string | null,
 *   recheck: () => Promise<void>,
 *   isFeatureAllowed: (featureName: string) => boolean,
 * }}
 */
export function useDeviceIntegrity() {
  const [integrity, setIntegrity] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const runCheck = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const result = await checkDeviceIntegrity();
      setIntegrity(result);
    } catch (err) {
      console.error('Device integrity check error:', err);
      setError(err.message);
      // On error, default to safe to avoid false lockouts
      setIntegrity({
        isCompromised: false,
        reasons: ['check_error'],
        riskLevel: 'safe',
        timestamp: new Date().toISOString(),
        platform: Capacitor.getPlatform(),
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Run on mount
    runCheck();

    // Set up recurring check if configured
    const intervalMinutes = INTEGRITY_POLICY.recheckIntervalMinutes;
    if (intervalMinutes > 0) {
      intervalRef.current = setInterval(runCheck, intervalMinutes * 60 * 1000);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [runCheck]);

  const isFeatureAllowed = useCallback(
    (featureName) => {
      if (!integrity) return true; // Allow while loading
      return !isFeatureRestricted(featureName, integrity);
    },
    [integrity]
  );

  return {
    integrity,
    isLoading,
    error,
    recheck: runCheck,
    isFeatureAllowed,
  };
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export default {
  checkDeviceIntegrity,
  isFeatureRestricted,
  useDeviceIntegrity,
  INTEGRITY_POLICY,
  COMPROMISED_DEVICE_MESSAGE,
  COMPROMISED_DEVICE_TITLE,
};
