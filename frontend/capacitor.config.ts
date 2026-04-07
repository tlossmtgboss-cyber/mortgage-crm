import type { CapacitorConfig } from '@capacitor/cli';

// Canonical Capacitor configuration — used for both development and production builds.
// The separate capacitor.config.production.ts is no longer needed; this file is the
// single source of truth for app identity, server settings, and plugin options.
const config: CapacitorConfig = {
  appId: 'com.perenniaai.crm',
  appName: 'Perennia AI',
  webDir: 'build',
  server: {
    // Production: no dev server URL, uses bundled assets
    // Only allow navigation to production domains
    allowNavigation: [
      'perenniaai.com',
      'app.perenniaai.com',
      'api.perenniaai.com',
      'www.perenniaai.com'
    ],
  },
  ios: {
    contentInset: 'automatic',
    allowsLinkPreview: false,
  },
  plugins: {
    Keyboard: {
      resize: 'body',
      resizeOnFullScreen: true,
    },
  },
};

export default config;
