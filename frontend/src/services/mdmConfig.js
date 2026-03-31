/**
 * Mobile Device Management (MDM) Configuration Service
 *
 * Reads managed app configuration pushed via MDM profiles and applies
 * enterprise policies to the Perennia AI mobile app.
 *
 * Integration: Call initMDMConfig() on app launch, before session manager
 * initialization, to apply enterprise policies first.
 *
 * iOS: Reads from UserDefaults (managed app configuration)
 * Android: Reads from RestrictionsManager
 * Web: Returns unmanaged defaults
 */
import { Capacitor, registerPlugin } from '@capacitor/core';

// Native plugin bridge — resolves to no-op stubs on web
const MDMConfigNative = registerPlugin('MDMConfig', {
  web: () => import('./mdmConfigWeb').catch(() => ({
    default: {
      getManagedConfig: async () => ({ config: {} }),
      isManagedDevice: async () => ({ managed: false }),
    },
  })).then(m => m.default),
});

// ---------------------------------------------------------------------------
// MDM key definitions
// ---------------------------------------------------------------------------

const MDM_KEYS = {
  'com.perenniaai.crm.server_url': 'string',
  'com.perenniaai.crm.organization_id': 'string',
  'com.perenniaai.crm.sso_provider': 'string',
  'com.perenniaai.crm.sso_domain': 'string',
  'com.perenniaai.crm.features_disabled': 'array',
  'com.perenniaai.crm.require_biometric': 'boolean',
  'com.perenniaai.crm.session_timeout': 'number',
  'com.perenniaai.crm.allow_screenshots': 'boolean',
  'com.perenniaai.crm.min_os_version': 'string',
  'com.perenniaai.crm.allowed_networks': 'array',
};

// Short aliases for internal use (strip the prefix)
function shortKey(fullKey) {
  return fullKey.replace('com.perenniaai.crm.', '');
}

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------

let _cachedConfig = null;
let _lastChecked = null;
let _complianceStatus = null;

// ---------------------------------------------------------------------------
// Core API
// ---------------------------------------------------------------------------

/**
 * Read managed app configuration from the native layer.
 * On iOS this reads UserDefaults keys pushed by the MDM profile.
 * On Android this reads RestrictionsManager entries.
 * On web this always returns an empty config.
 *
 * @returns {Promise<Object>} Parsed and type-validated MDM config
 */
export async function getMDMConfig() {
  if (_cachedConfig !== null) {
    return _cachedConfig;
  }

  try {
    const platform = Capacitor.getPlatform();

    if (platform === 'web') {
      _cachedConfig = {};
      _lastChecked = Date.now();
      return _cachedConfig;
    }

    const result = await MDMConfigNative.getManagedConfig();
    const raw = result?.config || {};

    // Validate and coerce types based on MDM_KEYS schema
    const validated = {};
    for (const [fullKey, expectedType] of Object.entries(MDM_KEYS)) {
      const value = raw[fullKey];
      if (value === undefined || value === null) {
        continue;
      }

      const alias = shortKey(fullKey);

      switch (expectedType) {
        case 'string':
          validated[alias] = String(value);
          break;
        case 'number': {
          const num = Number(value);
          if (!Number.isNaN(num)) {
            validated[alias] = num;
          }
          break;
        }
        case 'boolean':
          validated[alias] = value === true || value === 'true' || value === '1';
          break;
        case 'array':
          if (Array.isArray(value)) {
            validated[alias] = value;
          } else if (typeof value === 'string') {
            try {
              const parsed = JSON.parse(value);
              validated[alias] = Array.isArray(parsed) ? parsed : [value];
            } catch {
              // Comma-separated fallback
              validated[alias] = value.split(',').map(s => s.trim()).filter(Boolean);
            }
          }
          break;
        default:
          validated[alias] = value;
      }
    }

    _cachedConfig = validated;
    _lastChecked = Date.now();
    return _cachedConfig;
  } catch (err) {
    console.warn('[MDM] Failed to read managed config:', err);
    _cachedConfig = {};
    _lastChecked = Date.now();
    return _cachedConfig;
  }
}

/**
 * Check whether this device is enrolled in an MDM and has managed configuration.
 *
 * @returns {Promise<boolean>}
 */
export async function isManagedDevice() {
  try {
    const platform = Capacitor.getPlatform();
    if (platform === 'web') {
      return false;
    }

    const result = await MDMConfigNative.isManagedDevice();
    return result?.managed === true;
  } catch {
    return false;
  }
}

/**
 * Get a single MDM config value by its short key name.
 *
 * @param {string} key - Short key (e.g. 'server_url', 'session_timeout')
 * @param {*} defaultValue - Fallback if key is not present
 * @returns {Promise<*>}
 */
export async function getMDMValue(key, defaultValue = undefined) {
  const config = await getMDMConfig();
  return config[key] !== undefined ? config[key] : defaultValue;
}

// ---------------------------------------------------------------------------
// Policy enforcement
// ---------------------------------------------------------------------------

/**
 * Apply MDM-pushed restrictions to the running application.
 * Should be called once on app launch, before session manager init.
 *
 * Effects:
 *  - Overrides session timeout if configured
 *  - Disables screenshots if not allowed
 *  - Forces biometric authentication requirement
 *  - Restricts to allowed WiFi networks
 *  - Disables specified features
 *  - Overrides server URL for on-prem deployments
 *
 * @returns {Promise<Object>} Summary of applied policies
 */
export async function applyMDMPolicy() {
  const config = await getMDMConfig();
  const managed = await isManagedDevice();
  const applied = [];

  if (!managed || Object.keys(config).length === 0) {
    return { managed: false, policiesApplied: [] };
  }

  // --- Session timeout override ---
  if (config.session_timeout != null && config.session_timeout > 0) {
    const timeoutMs = config.session_timeout * 60 * 1000;
    localStorage.setItem('mdm_session_timeout', String(timeoutMs));
    applied.push(`session_timeout: ${config.session_timeout} minutes`);
  }

  // --- Screenshot restriction ---
  if (config.allow_screenshots === false) {
    localStorage.setItem('mdm_screenshots_disabled', 'true');
    // On iOS the native plugin handles UIScreen capture prevention;
    // on the web layer we prevent right-click and print
    _applyScreenshotRestriction();
    applied.push('screenshots: disabled');
  }

  // --- Biometric requirement ---
  if (config.require_biometric === true) {
    localStorage.setItem('mdm_require_biometric', 'true');
    applied.push('biometric: required');
  }

  // --- Network restrictions ---
  if (Array.isArray(config.allowed_networks) && config.allowed_networks.length > 0) {
    localStorage.setItem('mdm_allowed_networks', JSON.stringify(config.allowed_networks));
    applied.push(`allowed_networks: ${config.allowed_networks.join(', ')}`);
  }

  // --- Feature restrictions ---
  if (Array.isArray(config.features_disabled) && config.features_disabled.length > 0) {
    localStorage.setItem('mdm_features_disabled', JSON.stringify(config.features_disabled));
    applied.push(`features_disabled: ${config.features_disabled.join(', ')}`);
  }

  // --- Server URL override (on-prem / private cloud) ---
  if (config.server_url) {
    localStorage.setItem('mdm_server_url', config.server_url);
    applied.push(`server_url: ${config.server_url}`);
  }

  // --- Organization pre-set ---
  if (config.organization_id) {
    localStorage.setItem('mdm_organization_id', config.organization_id);
    applied.push(`organization_id: ${config.organization_id}`);
  }

  // --- SSO configuration ---
  if (config.sso_provider) {
    localStorage.setItem('mdm_sso_provider', config.sso_provider);
    if (config.sso_domain) {
      localStorage.setItem('mdm_sso_domain', config.sso_domain);
    }
    applied.push(`sso: ${config.sso_provider} (${config.sso_domain || 'no domain'})`);
  }

  // --- Minimum OS version check ---
  if (config.min_os_version) {
    localStorage.setItem('mdm_min_os_version', config.min_os_version);
    applied.push(`min_os_version: ${config.min_os_version}`);
  }

  console.log(`[MDM] Applied ${applied.length} policies:`, applied);

  // Update compliance after applying
  _complianceStatus = null;
  await getMDMComplianceStatus();

  return { managed: true, policiesApplied: applied };
}

// ---------------------------------------------------------------------------
// Compliance reporting
// ---------------------------------------------------------------------------

/**
 * Get compliance status of the device against MDM policy requirements.
 *
 * @returns {Promise<Object>} Compliance report
 */
export async function getMDMComplianceStatus() {
  if (_complianceStatus && _lastChecked && (Date.now() - _lastChecked < 60000)) {
    return _complianceStatus;
  }

  const config = await getMDMConfig();
  const managed = await isManagedDevice();
  const violations = [];

  if (!managed) {
    _complianceStatus = {
      isManaged: false,
      isCompliant: true,
      violations: [],
      lastChecked: Date.now(),
    };
    return _complianceStatus;
  }

  // Check minimum OS version
  if (config.min_os_version) {
    const deviceVersion = _getDeviceOSVersion();
    if (deviceVersion && _compareVersions(deviceVersion, config.min_os_version) < 0) {
      violations.push(
        `OS version ${deviceVersion} is below minimum required ${config.min_os_version}`
      );
    }
  }

  // Check biometric availability when required
  if (config.require_biometric === true) {
    const biometricAvailable = await _checkBiometricAvailability();
    if (!biometricAvailable) {
      violations.push('Biometric authentication required but not available on device');
    }
  }

  // Check network restrictions
  if (Array.isArray(config.allowed_networks) && config.allowed_networks.length > 0) {
    const networkCompliant = await _checkNetworkCompliance(config.allowed_networks);
    if (!networkCompliant) {
      violations.push('Device is not connected to an allowed network');
    }
  }

  _complianceStatus = {
    isManaged: true,
    isCompliant: violations.length === 0,
    violations,
    lastChecked: Date.now(),
  };

  _lastChecked = Date.now();
  return _complianceStatus;
}

// ---------------------------------------------------------------------------
// Feature gating helpers
// ---------------------------------------------------------------------------

/**
 * Check if a specific feature is disabled by MDM policy.
 *
 * @param {string} featureName - Feature identifier to check
 * @returns {boolean}
 */
export function isFeatureDisabledByMDM(featureName) {
  try {
    const raw = localStorage.getItem('mdm_features_disabled');
    if (!raw) return false;
    const disabled = JSON.parse(raw);
    return Array.isArray(disabled) && disabled.includes(featureName);
  } catch {
    return false;
  }
}

/**
 * Get the MDM-overridden server URL, or null if not set.
 *
 * @returns {string|null}
 */
export function getMDMServerUrl() {
  return localStorage.getItem('mdm_server_url') || null;
}

/**
 * Get the MDM-overridden session timeout in milliseconds, or null.
 *
 * @returns {number|null}
 */
export function getMDMSessionTimeout() {
  const raw = localStorage.getItem('mdm_session_timeout');
  return raw ? Number(raw) : null;
}

/**
 * Check if biometric auth is required by MDM.
 *
 * @returns {boolean}
 */
export function isBiometricRequired() {
  return localStorage.getItem('mdm_require_biometric') === 'true';
}

/**
 * Get the pre-configured organization ID, or null.
 *
 * @returns {string|null}
 */
export function getMDMOrganizationId() {
  return localStorage.getItem('mdm_organization_id') || null;
}

/**
 * Get SSO configuration from MDM, or null if not set.
 *
 * @returns {{ provider: string, domain: string|null }|null}
 */
export function getMDMSSOConfig() {
  const provider = localStorage.getItem('mdm_sso_provider');
  if (!provider) return null;
  return {
    provider,
    domain: localStorage.getItem('mdm_sso_domain') || null,
  };
}

// ---------------------------------------------------------------------------
// Initialization (call on app launch)
// ---------------------------------------------------------------------------

/**
 * Initialize MDM configuration. Call this before session manager init.
 * Reads config from native layer, applies policies, and runs compliance check.
 *
 * @returns {Promise<Object>} Policy application result
 */
export async function initMDMConfig() {
  try {
    const result = await applyMDMPolicy();
    if (result.managed) {
      console.log('[MDM] Device is managed. Policies applied:', result.policiesApplied.length);
    }
    return result;
  } catch (err) {
    console.error('[MDM] Initialization failed:', err);
    return { managed: false, policiesApplied: [], error: err.message };
  }
}

/**
 * Clear cached MDM config and force re-read on next access.
 * Useful when the app returns to foreground (MDM config may have changed).
 */
export function invalidateMDMCache() {
  _cachedConfig = null;
  _lastChecked = null;
  _complianceStatus = null;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _applyScreenshotRestriction() {
  if (Capacitor.getPlatform() === 'web') {
    return;
  }
  // CSS-based content protection for web view layer
  try {
    const style = document.createElement('style');
    style.textContent = `
      body {
        -webkit-user-select: none;
        user-select: none;
      }
      @media print {
        body { display: none !important; }
      }
    `;
    document.head.appendChild(style);
  } catch {
    // Non-critical
  }
}

function _getDeviceOSVersion() {
  try {
    const ua = navigator.userAgent;
    // iOS: "OS 17_4_1"
    const iosMatch = ua.match(/OS\s+([\d_]+)/);
    if (iosMatch) {
      return iosMatch[1].replace(/_/g, '.');
    }
    // Android: "Android 14"
    const androidMatch = ua.match(/Android\s+([\d.]+)/);
    if (androidMatch) {
      return androidMatch[1];
    }
  } catch {
    // Ignore
  }
  return null;
}

function _compareVersions(a, b) {
  const aParts = a.split('.').map(Number);
  const bParts = b.split('.').map(Number);
  const len = Math.max(aParts.length, bParts.length);
  for (let i = 0; i < len; i++) {
    const av = aParts[i] || 0;
    const bv = bParts[i] || 0;
    if (av > bv) return 1;
    if (av < bv) return -1;
  }
  return 0;
}

async function _checkBiometricAvailability() {
  try {
    // Use the Web Authentication API as a proxy check
    if (window.PublicKeyCredential) {
      const available = await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
      return available;
    }
  } catch {
    // Ignore
  }
  // On native, assume biometric is available if the device has it
  // The native plugin does the real check
  return Capacitor.getPlatform() !== 'web';
}

async function _checkNetworkCompliance(allowedNetworks) {
  // Network SSID checking requires native APIs; on the web layer we
  // cannot read the current SSID. The native plugin handles this.
  // Here we do a best-effort check: if we are on a native platform,
  // ask the native layer; otherwise assume compliant.
  try {
    if (Capacitor.getPlatform() === 'web') {
      return true;
    }
    const result = await MDMConfigNative.getCurrentNetworkSSID();
    if (result?.ssid) {
      return allowedNetworks.includes(result.ssid);
    }
    // If we cannot determine SSID, treat as non-compliant for security
    return false;
  } catch {
    // If native call fails, allow through to avoid blocking legitimate use
    return true;
  }
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export default {
  getMDMConfig,
  isManagedDevice,
  getMDMValue,
  applyMDMPolicy,
  getMDMComplianceStatus,
  isFeatureDisabledByMDM,
  getMDMServerUrl,
  getMDMSessionTimeout,
  isBiometricRequired,
  getMDMOrganizationId,
  getMDMSSOConfig,
  initMDMConfig,
  invalidateMDMCache,
  MDM_KEYS,
};
