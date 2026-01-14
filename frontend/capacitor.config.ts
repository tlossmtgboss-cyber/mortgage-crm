import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.perenniaai.crm',
  appName: 'Perennia AI',
  webDir: 'build',
  server: {
    // For development: point to local dev server
    url: 'http://192.168.1.240:3000',
    cleartext: true,
    // Allow the app to make requests to the production backend
    allowNavigation: ['perenniaai.com', 'api.perenniaai.com', 'www.perenniaai.com', 'localhost', '127.0.0.1', '192.168.1.240'],
  },
  ios: {
    contentInset: 'automatic',
    allowsLinkPreview: true,
  }
};

export default config;
