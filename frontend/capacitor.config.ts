import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: process.env.CAPACITOR_APP_ID || 'com.perenniaai.crm',
  appName: process.env.CAPACITOR_APP_NAME || 'Perennia AI',
  webDir: 'build',
  server: {
    ...(process.env.CAPACITOR_SERVER_URL ? { url: process.env.CAPACITOR_SERVER_URL, cleartext: true } : {}),
    allowNavigation: [
      ...(process.env.CAPACITOR_ALLOWED_DOMAINS?.split(',') || []),
      'perenniaai.com', 'app.perenniaai.com', 'api.perenniaai.com', 'www.perenniaai.com', 'localhost', '127.0.0.1',
    ],
  },
  ios: {
    contentInset: 'automatic',
    allowsLinkPreview: false,
  }
};

export default config;
