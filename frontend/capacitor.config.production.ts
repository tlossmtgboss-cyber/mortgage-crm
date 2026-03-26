import type { CapacitorConfig } from '@capacitor/cli';

// Production configuration - uses bundled web assets (no dev server)
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
  }
};

export default config;
