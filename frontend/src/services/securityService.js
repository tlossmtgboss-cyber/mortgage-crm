/**
 * Security Service
 * Perennia AI - Device integrity and security event reporting
 *
 * Fire-and-forget reporting to the backend for audit logging.
 */

import { API_BASE_URL } from './api';
import { getToken } from '../utils/tokenStore';

/**
 * Report device integrity check results to the backend.
 * Fire-and-forget: failures are logged but never surfaced to the user.
 *
 * @param {Object} result - Integrity check result from checkDeviceIntegrity()
 * @param {boolean} result.isCompromised
 * @param {string[]} result.reasons
 * @param {string} result.riskLevel - 'safe' | 'warning' | 'critical'
 * @param {string} result.platform
 * @param {string} result.timestamp
 */
export async function reportDeviceIntegrity(result) {
  try {
    const token = getToken();
    if (!token) return;

    await fetch(`${API_BASE_URL}/api/v1/security/device-integrity`, {
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
  } catch {
    // Fire-and-forget: integrity reporting should never break the app
  }
}

/**
 * Report a generic security event to the backend.
 *
 * @param {string} eventType - e.g. 'biometric_required', 'mdm_policy_applied'
 * @param {Object} details - Additional context
 */
export async function reportSecurityEvent(eventType, details = {}) {
  try {
    const token = getToken();
    if (!token) return;

    await fetch(`${API_BASE_URL}/api/v1/security/events`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        event_type: eventType,
        details,
        timestamp: new Date().toISOString(),
      }),
    });
  } catch {
    // Fire-and-forget
  }
}
