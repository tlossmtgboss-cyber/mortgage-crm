/**
 * useBiometricLogin Hook
 *
 * Enables Face ID / Touch ID login for the mobile app.
 * Securely stores credentials and allows quick biometric authentication.
 */

import { useState, useEffect, useCallback } from 'react';
import { biometrics, isNative } from '../services/nativeServices';

const CREDENTIAL_SERVER = 'com.perenniaai.crm';

export function useBiometricLogin() {
  const [isAvailable, setIsAvailable] = useState(false);
  const [biometryType, setBiometryType] = useState('none'); // 'faceId', 'touchId', 'fingerprint', 'none'
  const [hasStoredCredentials, setHasStoredCredentials] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Check availability on mount
  useEffect(() => {
    async function checkAvailability() {
      if (!isNative) {
        setIsLoading(false);
        return;
      }

      try {
        const result = await biometrics.isAvailable();
        setIsAvailable(result.available);
        setBiometryType(result.biometryType);

        // Check if we have stored credentials
        if (result.available) {
          const creds = await biometrics.getCredentials(CREDENTIAL_SERVER);
          setHasStoredCredentials(!!creds);
        }
      } catch (error) {
        console.error('Error checking biometric availability:', error);
      } finally {
        setIsLoading(false);
      }
    }

    checkAvailability();
  }, []);

  /**
   * Enable biometric login by storing credentials
   */
  const enableBiometricLogin = useCallback(async (email, password) => {
    if (!isAvailable) return false;

    try {
      // First authenticate to confirm user wants to enable
      const authenticated = await biometrics.authenticate(
        getBiometricPrompt('Enable biometric login')
      );

      if (!authenticated) return false;

      // Store credentials
      const stored = await biometrics.storeCredentials(CREDENTIAL_SERVER, email, password);
      setHasStoredCredentials(stored);
      return stored;
    } catch (error) {
      console.error('Error enabling biometric login:', error);
      return false;
    }
  }, [isAvailable]);

  /**
   * Authenticate and retrieve stored credentials
   */
  const authenticateWithBiometrics = useCallback(async () => {
    if (!isAvailable || !hasStoredCredentials) return null;

    try {
      // Authenticate with biometrics
      const authenticated = await biometrics.authenticate(
        getBiometricPrompt('Log in to Perennia AI')
      );

      if (!authenticated) return null;

      // Get stored credentials
      const credentials = await biometrics.getCredentials(CREDENTIAL_SERVER);
      return credentials;
    } catch (error) {
      console.error('Error authenticating with biometrics:', error);
      return null;
    }
  }, [isAvailable, hasStoredCredentials]);

  /**
   * Disable biometric login by removing stored credentials
   */
  const disableBiometricLogin = useCallback(async () => {
    try {
      await biometrics.deleteCredentials(CREDENTIAL_SERVER);
      setHasStoredCredentials(false);
      return true;
    } catch (error) {
      console.error('Error disabling biometric login:', error);
      return false;
    }
  }, []);

  /**
   * Get appropriate prompt text based on biometry type
   */
  function getBiometricPrompt(action) {
    switch (biometryType) {
      case 'faceId':
        return `${action} with Face ID`;
      case 'touchId':
        return `${action} with Touch ID`;
      case 'fingerprint':
        return `${action} with fingerprint`;
      default:
        return action;
    }
  }

  /**
   * Get display name for the biometry type
   */
  const biometryDisplayName = biometryType === 'faceId' ? 'Face ID'
    : biometryType === 'touchId' ? 'Touch ID'
    : biometryType === 'fingerprint' ? 'Fingerprint'
    : 'Biometrics';

  return {
    // State
    isAvailable,
    biometryType,
    biometryDisplayName,
    hasStoredCredentials,
    isLoading,
    isNative,

    // Actions
    enableBiometricLogin,
    authenticateWithBiometrics,
    disableBiometricLogin,
  };
}

export default useBiometricLogin;
