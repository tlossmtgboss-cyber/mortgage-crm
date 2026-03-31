/**
 * SSL Certificate Pinning Service
 *
 * Enterprise security layer to prevent MITM attacks on financial data
 * flowing through the Perennia AI mobile app.
 *
 * How it works:
 * - Pins are SHA-256 hashes of the Subject Public Key Info (SPKI) of the
 *   server's TLS certificate. SPKI pinning survives certificate renewals
 *   as long as the same key pair is reused.
 * - Each domain has a primary and backup pin. The backup pin should be
 *   generated from a separate key pair stored offline, so that if the
 *   primary key is compromised, a new certificate can be issued with the
 *   backup key without requiring an app update.
 * - In development (REACT_APP_DISABLE_CERT_PINNING=true), pinning is
 *   bypassed entirely to allow local HTTPS proxies and Charles/mitmproxy.
 *
 * Integration notes:
 * - Capacitor's WKWebView does NOT expose the TLS certificate chain to
 *   JavaScript. This service is designed to work with either:
 *   (a) @capgo/capacitor-ssl-pinning plugin (recommended), or
 *   (b) A custom native Capacitor plugin (see CertificatePinning.swift).
 * - For web builds, this module is a no-op since browsers handle TLS
 *   certificate validation via the OS trust store and HSTS.
 *
 * Generating pin hashes:
 *   openssl s_client -connect api.perenniaai.com:443 -servername api.perenniaai.com < /dev/null 2>/dev/null \
 *     | openssl x509 -pubkey -noout \
 *     | openssl pkey -pubin -outform der \
 *     | openssl dgst -sha256 -binary \
 *     | openssl enc -base64
 */

import { Capacitor } from '@capacitor/core';

// ============================================================================
// CONFIGURATION
// ============================================================================

/**
 * Kill switch: disable pinning in development or when debugging network issues.
 * Set REACT_APP_DISABLE_CERT_PINNING=true in .env.local to bypass.
 */
const PINNING_DISABLED =
  process.env.REACT_APP_DISABLE_CERT_PINNING === 'true' ||
  process.env.NODE_ENV === 'development';

/**
 * Pinned domains and their expected SPKI SHA-256 hashes.
 *
 * IMPORTANT: Replace placeholder hashes before production deployment.
 * Generate real hashes with the openssl command in the module docstring.
 *
 * Include at least two pins per domain:
 *   1. Primary: hash of the current certificate's public key
 *   2. Backup: hash of a pre-generated backup key pair (stored offline)
 *
 * When rotating certificates, issue the new cert with the backup key,
 * then ship an app update that adds the next backup pin.
 */
const PINNED_DOMAINS = {
  'api.perenniaai.com': {
    pins: [
      // Primary cert pin — current production certificate SPKI hash
      // Replace with actual SPKI hash from:
      //   openssl s_client -connect api.perenniaai.com:443 -servername api.perenniaai.com < /dev/null 2>/dev/null \
      //     | openssl x509 -pubkey -noout \
      //     | openssl pkey -pubin -outform der \
      //     | openssl dgst -sha256 -binary \
      //     | openssl enc -base64
      'sha256/PLACEHOLDER_PRIMARY_PIN_HASH_API',
      // Backup cert pin — pre-generated backup key pair for rotation
      // Generate a backup key pair, store the private key offline, and pin
      // the public key hash here. When the primary cert expires or is
      // compromised, issue a new cert with the backup key.
      'sha256/PLACEHOLDER_BACKUP_PIN_HASH_API',
    ],
    includeSubdomains: true,
  },
  'app.perenniaai.com': {
    pins: [
      // Primary cert pin — current production certificate SPKI hash
      // Replace with actual SPKI hash from:
      //   openssl s_client -connect app.perenniaai.com:443 -servername app.perenniaai.com < /dev/null 2>/dev/null \
      //     | openssl x509 -pubkey -noout \
      //     | openssl pkey -pubin -outform der \
      //     | openssl dgst -sha256 -binary \
      //     | openssl enc -base64
      'sha256/PLACEHOLDER_PRIMARY_PIN_HASH_APP',
      // Backup cert pin — pre-generated backup key pair for rotation
      'sha256/PLACEHOLDER_BACKUP_PIN_HASH_APP',
    ],
    includeSubdomains: true,
  },
};

/**
 * Maximum number of pin failure reports to buffer before flushing.
 * Reports are batched to avoid flooding the backend during an active attack.
 */
const MAX_BUFFERED_REPORTS = 10;

/**
 * Interval in milliseconds between report flushes.
 */
const REPORT_FLUSH_INTERVAL_MS = 30000; // 30 seconds

/**
 * Backend endpoint for pin validation failure reports.
 */
const PIN_FAILURE_REPORT_URL = 'https://api.perenniaai.com/api/v1/security/pin-failure';


// ============================================================================
// INTERNAL STATE
// ============================================================================

let _initialized = false;
let _failureBuffer = [];
let _flushTimer = null;
let _nativePluginAvailable = false;
let _validationStats = {
  totalChecks: 0,
  passed: 0,
  failed: 0,
  skipped: 0,
};


// ============================================================================
// PIN VALIDATION
// ============================================================================

/**
 * Extract the bare hash from a pin string like "sha256/ABCDEF..."
 * @param {string} pin - Pin in "sha256/<base64>" format
 * @returns {string} The base64 hash portion
 */
function extractHash(pin) {
  if (!pin || typeof pin !== 'string') return '';
  const parts = pin.split('/');
  return parts.length === 2 ? parts[1] : pin;
}

/**
 * Get the pin configuration for a given domain.
 * If includeSubdomains is set on a parent domain, subdomains inherit the pins.
 *
 * @param {string} domain - The domain to look up (e.g., "api.perenniaai.com")
 * @returns {object|null} The pin config object or null if not pinned
 */
function getPinConfigForDomain(domain) {
  if (!domain || typeof domain !== 'string') return null;

  const normalized = domain.toLowerCase().trim();

  // Direct match
  if (PINNED_DOMAINS[normalized]) {
    return PINNED_DOMAINS[normalized];
  }

  // Check if any parent domain with includeSubdomains covers this domain
  for (const [pinnedDomain, config] of Object.entries(PINNED_DOMAINS)) {
    if (config.includeSubdomains && normalized.endsWith('.' + pinnedDomain)) {
      return config;
    }
  }

  return null;
}

/**
 * Validate a certificate chain against pinned SPKI hashes.
 *
 * This function checks whether at least one certificate in the chain
 * has an SPKI hash that matches one of the pinned hashes for the domain.
 * This is the "trust on first use" model recommended by OWASP.
 *
 * @param {string} domain - The domain being connected to
 * @param {string[]} certChainHashes - Array of SHA-256 SPKI hashes (base64)
 *   from the certificate chain, leaf first. These are typically provided by
 *   the native SSL pinning plugin.
 * @returns {{ valid: boolean, matchedPin: string|null, reason: string }}
 */
function validateCertificate(domain, certChainHashes) {
  _validationStats.totalChecks++;

  // Kill switch
  if (PINNING_DISABLED) {
    _validationStats.skipped++;
    return {
      valid: true,
      matchedPin: null,
      reason: 'pinning_disabled',
    };
  }

  // Not running on native platform — browser handles TLS
  if (!Capacitor.isNativePlatform()) {
    _validationStats.skipped++;
    return {
      valid: true,
      matchedPin: null,
      reason: 'web_platform',
    };
  }

  const config = getPinConfigForDomain(domain);

  // Domain is not pinned — allow (don't break non-pinned domains)
  if (!config) {
    _validationStats.skipped++;
    return {
      valid: true,
      matchedPin: null,
      reason: 'domain_not_pinned',
    };
  }

  // No certificate hashes provided
  if (!Array.isArray(certChainHashes) || certChainHashes.length === 0) {
    _validationStats.failed++;
    const failure = {
      valid: false,
      matchedPin: null,
      reason: 'no_cert_hashes_provided',
    };
    reportPinFailure(domain, failure.reason, []);
    return failure;
  }

  // Extract bare hashes from pin config
  const expectedHashes = config.pins.map(extractHash).filter(Boolean);

  // Check if ANY hash in the cert chain matches ANY pinned hash
  for (const certHash of certChainHashes) {
    const normalizedCertHash = certHash.trim();
    for (const expectedHash of expectedHashes) {
      if (normalizedCertHash === expectedHash) {
        _validationStats.passed++;
        return {
          valid: true,
          matchedPin: `sha256/${expectedHash}`,
          reason: 'pin_matched',
        };
      }
    }
  }

  // No match found — potential MITM
  _validationStats.failed++;
  const failure = {
    valid: false,
    matchedPin: null,
    reason: 'pin_mismatch',
  };
  reportPinFailure(domain, failure.reason, certChainHashes);
  return failure;
}


// ============================================================================
// FAILURE REPORTING
// ============================================================================

/**
 * Buffer a pin validation failure for reporting to the backend.
 * Reports are batched and flushed periodically to avoid flooding.
 *
 * @param {string} domain - The domain that failed validation
 * @param {string} reason - Why validation failed
 * @param {string[]} receivedHashes - The certificate hashes that were received
 */
function reportPinFailure(domain, reason, receivedHashes) {
  const report = {
    domain,
    reason,
    receivedHashes: (receivedHashes || []).slice(0, 5), // Limit to 5 hashes
    timestamp: new Date().toISOString(),
    platform: Capacitor.getPlatform(),
    appVersion: getAppVersion(),
  };

  console.error(
    `[CertificatePinning] PIN VALIDATION FAILED for ${domain}: ${reason}`,
    report
  );

  _failureBuffer.push(report);

  // Flush immediately if buffer is full
  if (_failureBuffer.length >= MAX_BUFFERED_REPORTS) {
    flushFailureReports();
  }
}

/**
 * Flush buffered failure reports to the backend.
 * Uses a separate fetch call (not the app's axios instance) to avoid
 * circular dependencies and to ensure reports are sent even if the
 * main API client is blocked by pin failures.
 */
async function flushFailureReports() {
  if (_failureBuffer.length === 0) return;

  const reports = [..._failureBuffer];
  _failureBuffer = [];

  try {
    // Use native fetch to avoid circular dependency with api.js
    // This request itself is NOT pin-validated to ensure delivery
    const token = localStorage.getItem('token');
    await fetch(PIN_FAILURE_REPORT_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        reports,
        deviceInfo: {
          platform: Capacitor.getPlatform(),
          isNative: Capacitor.isNativePlatform(),
        },
      }),
    });
  } catch (err) {
    // If reporting fails (e.g., network blocked by MITM), log locally.
    // Don't re-buffer to avoid infinite loops.
    console.error('[CertificatePinning] Failed to report pin failures:', err);
  }
}

/**
 * Get the app version string for failure reports.
 * @returns {string}
 */
function getAppVersion() {
  try {
    // Capacitor config appVersion or fallback
    return process.env.REACT_APP_VERSION || '1.0.0';
  } catch {
    return 'unknown';
  }
}


// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize the certificate pinning service.
 *
 * This should be called once at app startup, before any API calls.
 * On native platforms, it attempts to configure the native SSL pinning
 * plugin. On web, it's a no-op.
 *
 * @returns {Promise<{ initialized: boolean, method: string }>}
 */
async function initialize() {
  if (_initialized) {
    return { initialized: true, method: _nativePluginAvailable ? 'native' : 'javascript' };
  }

  // Only meaningful on native platforms
  if (!Capacitor.isNativePlatform()) {
    _initialized = true;
    return { initialized: true, method: 'web_noop' };
  }

  // Kill switch check
  if (PINNING_DISABLED) {
    console.warn('[CertificatePinning] Pinning is DISABLED via environment variable');
    _initialized = true;
    return { initialized: true, method: 'disabled' };
  }

  // Try to configure native SSL pinning plugin
  try {
    // Check if @capgo/capacitor-ssl-pinning or custom native plugin is available
    const { SSLPinning } = await import('@capgo/capacitor-ssl-pinning').catch(() => ({}));

    if (SSLPinning) {
      // Build pin configuration for native plugin
      const nativePins = {};
      for (const [domain, config] of Object.entries(PINNED_DOMAINS)) {
        nativePins[domain] = {
          pins: config.pins.map(extractHash),
          includeSubdomains: config.includeSubdomains,
        };
      }

      await SSLPinning.configure({
        pins: nativePins,
        reportUri: PIN_FAILURE_REPORT_URL,
      });

      _nativePluginAvailable = true;
      console.log('[CertificatePinning] Native SSL pinning configured');
    } else {
      console.warn(
        '[CertificatePinning] No native SSL pinning plugin found. ' +
        'Install @capgo/capacitor-ssl-pinning for production use. ' +
        'JavaScript-layer validation is active but cannot intercept WKWebView requests.'
      );
    }
  } catch (err) {
    console.warn('[CertificatePinning] Native plugin configuration failed:', err);
  }

  // Start periodic flush timer for failure reports
  if (_flushTimer) clearInterval(_flushTimer);
  _flushTimer = setInterval(flushFailureReports, REPORT_FLUSH_INTERVAL_MS);

  _initialized = true;

  const method = _nativePluginAvailable ? 'native' : 'javascript';
  console.log(`[CertificatePinning] Initialized with method: ${method}`);
  return { initialized: true, method };
}

/**
 * Shut down the certificate pinning service.
 * Flushes any remaining failure reports.
 */
async function destroy() {
  if (_flushTimer) {
    clearInterval(_flushTimer);
    _flushTimer = null;
  }
  await flushFailureReports();
  _initialized = false;
}


// ============================================================================
// HTTP REQUEST INTERCEPTOR
// ============================================================================

/**
 * Create an axios request interceptor that validates certificate pins.
 *
 * Usage with axios:
 *   import api from './api';
 *   import { createAxiosInterceptor } from './certificatePinning';
 *   api.interceptors.request.use(createAxiosInterceptor());
 *
 * Note: This interceptor works in conjunction with the native plugin.
 * On WKWebView, the native plugin handles actual TLS validation.
 * This interceptor provides an additional JavaScript-layer check
 * when certificate hashes are available (e.g., from CapacitorHttp).
 *
 * @returns {Function} Axios request interceptor function
 */
function createAxiosInterceptor() {
  return async (config) => {
    if (PINNING_DISABLED || !Capacitor.isNativePlatform()) {
      return config;
    }

    try {
      const url = new URL(config.baseURL || config.url || '');
      const domain = url.hostname;
      const pinConfig = getPinConfigForDomain(domain);

      if (pinConfig) {
        // Attach pin expectations to the request config.
        // The native HTTP plugin can use this for validation.
        config.headers = config.headers || {};
        config.headers['X-Expected-Pins'] = pinConfig.pins.join(',');
      }
    } catch {
      // URL parsing failed — let the request proceed
    }

    return config;
  };
}

/**
 * Create an axios response interceptor that checks for pin validation
 * results returned by the native HTTP plugin.
 *
 * @returns {{ onFulfilled: Function, onRejected: Function }}
 */
function createAxiosResponseInterceptor() {
  return {
    onFulfilled: (response) => response,
    onRejected: (error) => {
      // Check if the error is a certificate pinning failure from native plugin
      if (
        error?.message?.includes('certificate') ||
        error?.message?.includes('SSL') ||
        error?.message?.includes('pin')
      ) {
        const domain = extractDomainFromError(error);
        reportPinFailure(
          domain || 'unknown',
          'native_ssl_error',
          []
        );

        // Wrap the error with a clear message
        const pinError = new Error(
          `SSL certificate validation failed for ${domain || 'unknown domain'}. ` +
          'This may indicate a man-in-the-middle attack. ' +
          'Please check your network connection and try again.'
        );
        pinError.code = 'CERT_PIN_FAILURE';
        pinError.originalError = error;
        return Promise.reject(pinError);
      }

      return Promise.reject(error);
    },
  };
}

/**
 * Extract domain from an axios error object.
 * @param {Error} error
 * @returns {string|null}
 */
function extractDomainFromError(error) {
  try {
    const url = error?.config?.baseURL || error?.config?.url;
    if (url) {
      return new URL(url).hostname;
    }
  } catch {
    // Ignore
  }
  return null;
}


// ============================================================================
// DIAGNOSTICS
// ============================================================================

/**
 * Get current pinning configuration (sanitized for display).
 * Does not expose actual pin hashes in production.
 *
 * @returns {object} Pinning configuration summary
 */
function getConfiguration() {
  const domains = {};
  for (const [domain, config] of Object.entries(PINNED_DOMAINS)) {
    domains[domain] = {
      pinCount: config.pins.length,
      includeSubdomains: config.includeSubdomains,
      // Only show pin prefixes in non-production for debugging
      pins: PINNING_DISABLED
        ? config.pins
        : config.pins.map((p) => p.substring(0, 15) + '...'),
    };
  }

  return {
    enabled: !PINNING_DISABLED,
    initialized: _initialized,
    nativePluginAvailable: _nativePluginAvailable,
    isNative: Capacitor.isNativePlatform(),
    platform: Capacitor.getPlatform(),
    domains,
  };
}

/**
 * Get validation statistics.
 * @returns {object} Counts of checks, passes, failures, and skips
 */
function getStats() {
  return { ..._validationStats };
}

/**
 * Get the list of pinned domains.
 * @returns {string[]}
 */
function getPinnedDomains() {
  return Object.keys(PINNED_DOMAINS);
}

/**
 * Check if a specific domain has pins configured.
 * @param {string} domain
 * @returns {boolean}
 */
function isDomainPinned(domain) {
  return getPinConfigForDomain(domain) !== null;
}


// ============================================================================
// EXPORTS
// ============================================================================

export {
  // Core
  initialize,
  destroy,
  validateCertificate,

  // Configuration
  PINNED_DOMAINS,
  PINNING_DISABLED,
  getPinConfigForDomain,
  getConfiguration,
  getStats,
  getPinnedDomains,
  isDomainPinned,

  // Axios integration
  createAxiosInterceptor,
  createAxiosResponseInterceptor,

  // Reporting (exposed for testing)
  reportPinFailure,
  flushFailureReports,
};

export default {
  initialize,
  destroy,
  validateCertificate,
  getConfiguration,
  getStats,
  getPinnedDomains,
  isDomainPinned,
  createAxiosInterceptor,
  createAxiosResponseInterceptor,
};
