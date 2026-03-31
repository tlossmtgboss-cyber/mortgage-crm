/**
 * App Version Check Service
 *
 * Checks the backend for minimum/recommended app versions and returns
 * update status so the UI can show a forced-update modal, optional
 * banner, or maintenance screen.
 *
 * Only runs inside a Capacitor native shell — the web app is always
 * on the latest deploy and never needs a version gate.
 */
import { Capacitor } from '@capacitor/core';
import { App as CapApp } from '@capacitor/app';
import { API_BASE_URL } from './api';

// ---------------------------------------------------------------------------
// Semver helpers
// ---------------------------------------------------------------------------

/**
 * Parse a version string "1.2.3" into [major, minor, patch].
 * Missing or non-numeric segments default to 0.
 */
function parseSemver(version) {
  const parts = (version || '0.0.0').split('.').map(Number);
  return [parts[0] || 0, parts[1] || 0, parts[2] || 0];
}

/**
 * Return true if version a < version b (strict semver comparison).
 */
function versionLessThan(a, b) {
  const pa = parseSemver(a);
  const pb = parseSemver(b);
  for (let i = 0; i < 3; i++) {
    if (pa[i] < pb[i]) return true;
    if (pa[i] > pb[i]) return false;
  }
  return false;
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** Cached result so multiple callers don't trigger duplicate fetches. */
let _cachedResult = null;

/** In-flight promise (deduplication). */
let _pendingCheck = null;

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Result shape returned by checkForUpdate():
 * {
 *   needsForceUpdate: boolean,
 *   updateAvailable:  boolean,
 *   maintenanceMode:  boolean,
 *   maintenanceMessage: string,
 *   currentVersion:   string,    // client version
 *   recommendedVersion: string,  // server recommended
 *   updateUrl:        string,    // store deep-link
 *   changelog:        string,
 * }
 */

/**
 * Check the backend for version requirements.
 *
 * Safe to call from anywhere — it short-circuits instantly on web,
 * deduplicates concurrent calls, and caches the result for the
 * lifetime of the app session.
 *
 * @param {object} [options]
 * @param {boolean} [options.force=false]  Bypass the cache.
 * @returns {Promise<object>} Update status object.
 */
export async function checkForUpdate({ force = false } = {}) {
  // Web builds are always current — skip entirely.
  if (!Capacitor.isNativePlatform()) {
    return _noUpdateNeeded('0.0.0');
  }

  // Return cached result unless forced.
  if (_cachedResult && !force) {
    return _cachedResult;
  }

  // Deduplicate concurrent calls.
  if (_pendingCheck) {
    return _pendingCheck;
  }

  _pendingCheck = _performCheck();

  try {
    _cachedResult = await _pendingCheck;
    return _cachedResult;
  } finally {
    _pendingCheck = null;
  }
}

/**
 * Clear the cached version check result.
 * Useful when the app returns to the foreground after being backgrounded
 * for a long time.
 */
export function clearVersionCache() {
  _cachedResult = null;
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

async function _performCheck() {
  let clientVersion = '0.0.0';
  let clientBuild = '0';

  try {
    const info = await CapApp.getInfo();
    clientVersion = info.version || '0.0.0';     // CFBundleShortVersionString
    clientBuild = info.build || '0';              // CFBundleVersion
  } catch {
    // Fallback — should only happen in dev or if Capacitor plugin is missing.
    console.warn('[VersionCheck] Could not read app info from Capacitor.');
  }

  const platform = Capacitor.getPlatform(); // 'ios' | 'android' | 'web'

  try {
    const url = new URL('/api/v1/app/version-check', API_BASE_URL);
    url.searchParams.set('platform', platform);
    url.searchParams.set('version', clientVersion);
    url.searchParams.set('build', clientBuild);

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      // Short timeout — this must not block app startup for long.
      signal: AbortSignal.timeout ? AbortSignal.timeout(8000) : undefined,
    });

    if (!response.ok) {
      console.warn(`[VersionCheck] Server returned ${response.status}`);
      return _noUpdateNeeded(clientVersion);
    }

    const data = await response.json();

    return {
      needsForceUpdate: !!data.force_update,
      updateAvailable: !!data.update_available,
      maintenanceMode: !!data.maintenance_mode,
      maintenanceMessage: data.maintenance_message || '',
      currentVersion: clientVersion,
      minimumVersion: data.minimum_version || '0.0.0',
      recommendedVersion: data.recommended_version || clientVersion,
      updateUrl: data.update_url || '',
      changelog: data.changelog || '',
    };
  } catch (err) {
    // Network error, timeout, or parse failure — fail open so we don't
    // lock users out of the app when the server is unreachable.
    console.warn('[VersionCheck] Check failed, failing open:', err.message);
    return _noUpdateNeeded(clientVersion);
  }
}

function _noUpdateNeeded(clientVersion) {
  return {
    needsForceUpdate: false,
    updateAvailable: false,
    maintenanceMode: false,
    maintenanceMessage: '',
    currentVersion: clientVersion,
    minimumVersion: '0.0.0',
    recommendedVersion: clientVersion,
    updateUrl: '',
    changelog: '',
  };
}

// Re-export helpers for tests
export { parseSemver, versionLessThan };
