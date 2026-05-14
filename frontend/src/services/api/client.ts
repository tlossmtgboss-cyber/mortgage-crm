/**
 * Axios instance setup, base URL detection, and mobile app identification.
 */
import axios from 'axios';
import { Capacitor } from '@capacitor/core';
import { pinnedAdapter } from '../../utils/pinnedFetch';

// Detect native mobile app FIRST — Capacitor serves from localhost,
// so we must check isNativePlatform() before the hostname check.
export const isNativeApp = Capacitor.isNativePlatform();
const isLocalhost = !isNativeApp && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

export const API_BASE_URL = (import.meta as any).env.VITE_API_URL || (
  isNativeApp
    ? 'https://api.perenniaai.com'  // Native iOS/Android — always production
    : isLocalhost
      ? 'http://localhost:8000'
      : 'https://api.perenniaai.com' // Production web
);

// Create axios instance with mobile app identification
// On native iOS, route through certificate-pinned URLSession
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 second timeout
  headers: {
    'Content-Type': 'application/json',
    // Identify mobile app requests to bypass IP blocking middleware
    ...(isNativeApp && { 'X-Mobile-App': 'capacitor-ios' }),
  },
  ...(isNativeApp && { adapter: pinnedAdapter }),
});

export default api;
