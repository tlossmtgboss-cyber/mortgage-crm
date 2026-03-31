/**
 * Web platform stub for MDMConfig native plugin.
 * Returns unmanaged defaults since MDM is not applicable on web.
 */
const MDMConfigWeb = {
  async getManagedConfig() {
    return { config: {} };
  },

  async isManagedDevice() {
    return { managed: false, enrollmentInfo: { hasManagedConfig: false, hasFallbackKeys: false, isSupervised: false } };
  },

  async getCurrentNetworkSSID() {
    return { ssid: null };
  },

  async checkBiometricAvailability() {
    return { available: false, biometryType: 'none' };
  },

  async getDeviceInfo() {
    return {
      osVersion: '',
      model: 'web',
      deviceName: 'browser',
      systemName: navigator.platform || 'web',
      identifierForVendor: '',
    };
  },

  async setScreenshotPrevention() {
    return { enabled: false };
  },
};

export default MDMConfigWeb;
