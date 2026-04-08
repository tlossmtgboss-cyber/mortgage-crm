/**
 * pinnedFetch.js — Certificate-pinned HTTP adapter for iOS
 *
 * On native iOS, routes all API requests through the PinnedFetch Capacitor
 * plugin, which uses a URLSession with SPKI certificate pinning. This closes
 * the WKWebView gap where JS fetch()/XHR bypasses cert pinning.
 *
 * On web/Android, falls through to the default axios adapter.
 *
 * Usage: Set as the axios adapter for the api instance:
 *   import { pinnedAdapter } from '../utils/pinnedFetch';
 *   const api = axios.create({ adapter: pinnedAdapter });
 */

import { Capacitor, registerPlugin } from '@capacitor/core';

const PinnedFetch = Capacitor.isNativePlatform()
  ? registerPlugin('PinnedFetch')
  : null;

/**
 * Axios adapter that routes requests through the native pinned URLSession.
 * Falls back to the default adapter on non-native platforms.
 */
export function pinnedAdapter(config) {
  if (!PinnedFetch) {
    // Not on native — use default axios behavior
    return null;
  }

  return new Promise(async (resolve, reject) => {
    try {
      // Build the full URL
      const baseURL = config.baseURL || '';
      const url = config.url?.startsWith('http')
        ? config.url
        : `${baseURL}${config.url}`;

      // Serialize headers
      const headers = {};
      if (config.headers) {
        for (const [key, value] of Object.entries(config.headers)) {
          if (value != null) headers[key] = String(value);
        }
      }

      // Serialize body
      let body = null;
      if (config.data != null) {
        body = typeof config.data === 'string'
          ? config.data
          : JSON.stringify(config.data);
      }

      const result = await PinnedFetch.request({
        url,
        method: (config.method || 'GET').toUpperCase(),
        headers,
        body,
        timeout: (config.timeout || 30000) / 1000, // axios uses ms, plugin uses seconds
      });

      // Build an axios-compatible response
      const response = {
        data: result.data,
        status: result.status,
        statusText: `${result.status}`,
        headers: result.headers || {},
        config,
        request: {},
      };

      // Axios treats 2xx as success, others go to error interceptor
      if (result.status >= 200 && result.status < 300) {
        resolve(response);
      } else {
        const error = new Error(`Request failed with status ${result.status}`);
        error.response = response;
        error.config = config;
        error.isAxiosError = true;
        reject(error);
      }
    } catch (err) {
      // Plugin-level error (pinning failure, network error)
      const error = new Error(err.message || 'Pinned request failed');
      error.config = config;
      error.code = err.code || 'PINNING_ERROR';
      error.isAxiosError = true;
      reject(error);
    }
  });
}
