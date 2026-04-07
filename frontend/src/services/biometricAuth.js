/**
 * Biometric Authentication Service
 * Perennia AI - Login-flow biometric integration via capacitor-native-biometric
 *
 * Provides a high-level API for biometric login:
 *   - Check device biometric capability (Face ID, Touch ID, fingerprint)
 *   - Store refresh token + email after successful password login
 *   - Authenticate with biometric and retrieve stored credentials
 *   - Clear credentials on logout or password change
 *   - React hook for biometric auth state
 *
 * Usage:
 *   import { checkBiometricAvailability, authenticateWithBiometric, useBiometricAuth } from './biometricAuth';
 *
 *   // Check availability
 *   const { available, biometryType } = await checkBiometricAvailability();
 *
 *   // Store after password login
 *   await storeCredentials(email, refreshToken);
 *
 *   // Biometric login
 *   const { success, email, refreshToken } = await authenticateWithBiometric();
 *
 *   // React hook
 *   const { available, biometryType, hasCredentials, loading } = useBiometricAuth();
 */

import { useState, useEffect } from 'react';
import { Capacitor } from '@capacitor/core';
import { NativeBiometric } from 'capacitor-native-biometric';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SERVER = 'api.perenniaai.com';

// ---------------------------------------------------------------------------
// Availability
// ---------------------------------------------------------------------------

/**
 * Check if biometric auth is available on this device.
 * Returns immediately with { available: false } on web platforms.
 *
 * @returns {Promise<{available: boolean, biometryType: string|number}>}
 *   biometryType: 1=Touch ID, 2=Face ID, 3=Iris, 4=Multiple, 'none' if unavailable
 */
export async function checkBiometricAvailability() {
  if (!Capacitor.isNativePlatform()) {
    return { available: false, biometryType: 'none' };
  }
  try {
    const result = await NativeBiometric.isAvailable();
    return {
      available: result.isAvailable,
      biometryType: result.biometryType, // 1=Touch ID, 2=Face ID, 3=Iris, 4=Multiple
    };
  } catch {
    return { available: false, biometryType: 'none' };
  }
}

// ---------------------------------------------------------------------------
// Display Helpers
// ---------------------------------------------------------------------------

/**
 * Get human-readable biometry name for UI display.
 *
 * @param {number|string} type - biometryType from checkBiometricAvailability
 * @returns {string} 'Touch ID', 'Face ID', 'Iris', or 'Biometric'
 */
export function getBiometryName(type) {
  switch (type) {
    case 1: return 'Touch ID';
    case 2: return 'Face ID';
    case 3: return 'Iris';
    default: return 'Biometric';
  }
}

// ---------------------------------------------------------------------------
// Credential Storage
// ---------------------------------------------------------------------------

/**
 * Store credentials in the OS keychain after a successful password login.
 * The refresh token is stored as the "password" field, keyed to the API server.
 *
 * @param {string} email - User's email address
 * @param {string} refreshToken - JWT refresh token from the auth API
 * @returns {Promise<boolean>} true if stored successfully
 */
export async function storeCredentials(email, refreshToken) {
  if (!Capacitor.isNativePlatform()) return false;
  try {
    await NativeBiometric.setCredentials({
      username: email,
      password: refreshToken,
      server: SERVER,
    });
    return true;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Biometric Authentication
// ---------------------------------------------------------------------------

/**
 * Verify the user's identity via biometric and retrieve stored credentials.
 * This is the main "biometric login" flow — prompts Face ID / Touch ID,
 * then returns the stored email + refresh token on success.
 *
 * @returns {Promise<{success: boolean, email?: string, refreshToken?: string, error?: string}>}
 */
export async function authenticateWithBiometric() {
  try {
    await NativeBiometric.verifyIdentity({
      reason: 'Log in to Perennia AI',
      title: 'Perennia AI',
      subtitle: 'Verify your identity',
      description: 'Place your finger on the sensor or look at the camera',
    });

    const credentials = await NativeBiometric.getCredentials({ server: SERVER });
    return {
      success: true,
      email: credentials.username,
      refreshToken: credentials.password,
    };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// ---------------------------------------------------------------------------
// Credential Queries
// ---------------------------------------------------------------------------

/**
 * Check if the user has previously stored biometric credentials.
 * Does NOT prompt for biometric verification — just checks the keychain.
 *
 * @returns {Promise<boolean>} true if credentials exist for this server
 */
export async function hasBiometricCredentials() {
  if (!Capacitor.isNativePlatform()) return false;
  try {
    const creds = await NativeBiometric.getCredentials({ server: SERVER });
    return !!(creds?.username && creds?.password);
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Credential Cleanup
// ---------------------------------------------------------------------------

/**
 * Clear stored biometric credentials.
 * Call this on logout, password change, or account deletion.
 */
export async function clearBiometricCredentials() {
  if (!Capacitor.isNativePlatform()) return;
  try {
    await NativeBiometric.deleteCredentials({ server: SERVER });
  } catch {
    /* ignore if no credentials stored */
  }
}

// ---------------------------------------------------------------------------
// React Hook
// ---------------------------------------------------------------------------

/**
 * React hook that provides the current biometric auth state.
 * Checks availability and stored credentials on mount.
 *
 * @returns {{
 *   available: boolean,
 *   biometryType: number|string,
 *   hasCredentials: boolean,
 *   loading: boolean,
 * }}
 */
export function useBiometricAuth() {
  const [state, setState] = useState({
    available: false,
    biometryType: 'none',
    hasCredentials: false,
    loading: true,
  });

  useEffect(() => {
    let mounted = true;
    async function check() {
      const avail = await checkBiometricAvailability();
      const hasCreds = await hasBiometricCredentials();
      if (mounted) {
        setState({
          available: avail.available,
          biometryType: avail.biometryType,
          hasCredentials: hasCreds,
          loading: false,
        });
      }
    }
    check();
    return () => {
      mounted = false;
    };
  }, []);

  return state;
}

// ---------------------------------------------------------------------------
// Default Export
// ---------------------------------------------------------------------------

export default {
  checkBiometricAvailability,
  getBiometryName,
  storeCredentials,
  authenticateWithBiometric,
  hasBiometricCredentials,
  clearBiometricCredentials,
  useBiometricAuth,
};
