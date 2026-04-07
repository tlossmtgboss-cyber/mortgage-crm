/**
 * Share Extension Bridge Service
 * Perennia AI - iOS Share Extension Token Sync & Pending Upload Management
 *
 * Bridges auth tokens from the main app into the shared App Group container
 * so the iOS Share Extension can authenticate with the Perennia AI API.
 *
 * Also retrieves and manages pending uploads that were queued by the Share
 * Extension when network uploads failed.
 *
 * Usage:
 *   import { syncAuthToken, getPendingUploads, clearPendingUpload } from './shareExtensionBridge';
 *
 *   // After login or token refresh:
 *   await syncAuthToken(token);
 *
 *   // On app resume, check for pending uploads:
 *   const { uploads } = await getPendingUploads();
 */

import { Capacitor, registerPlugin } from '@capacitor/core';

const ShareExtensionBridge = registerPlugin('ShareExtensionBridge');

/**
 * Syncs the auth token to the App Group shared UserDefaults.
 * Call this after login, token refresh, and logout (pass empty string on logout).
 *
 * @param {string} token - The JWT auth token, or empty string to clear
 * @returns {Promise<{synced: boolean}>}
 */
export async function syncAuthToken(token) {
  if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== 'ios') {
    return { synced: false };
  }

  try {
    return await ShareExtensionBridge.syncAuthToken({ token: token || '' });
  } catch (err) {
    console.warn('[ShareExtensionBridge] Failed to sync auth token:', err);
    return { synced: false };
  }
}

/**
 * Returns pending uploads that were queued by the Share Extension.
 * Each upload contains: id, fileName, mimeType, loanID, borrowerID, docType, queuedAt, relativePath
 *
 * @returns {Promise<{uploads: Array}>}
 */
export async function getPendingUploads() {
  if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== 'ios') {
    return { uploads: [] };
  }

  try {
    return await ShareExtensionBridge.getPendingUploads();
  } catch (err) {
    console.warn('[ShareExtensionBridge] Failed to get pending uploads:', err);
    return { uploads: [] };
  }
}

/**
 * Removes a pending upload after it has been successfully retried.
 * Also deletes the queued file from the App Group container.
 *
 * @param {string} id - The upload ID
 * @returns {Promise<{removed: boolean}>}
 */
export async function clearPendingUpload(id) {
  if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== 'ios') {
    return { removed: false };
  }

  try {
    return await ShareExtensionBridge.clearPendingUpload({ id });
  } catch (err) {
    console.warn('[ShareExtensionBridge] Failed to clear pending upload:', err);
    return { removed: false };
  }
}
