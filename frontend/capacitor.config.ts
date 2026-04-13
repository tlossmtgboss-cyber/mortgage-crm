import type { CapacitorConfig } from '@capacitor/cli';

// Capacitor configuration — used for all builds (development and production).
// Single source of truth for app identity, server settings, and plugin options.
const config: CapacitorConfig = {
  appId: 'com.perenniaai.crm',
  appName: 'Perennia AI',
  webDir: 'build',
  server: {
    url: 'https://app.perenniaai.com',
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
