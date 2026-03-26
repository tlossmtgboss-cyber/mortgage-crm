import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.perenniaai.crm',
  appName: 'Perennia AI',
  webDir: 'build',
  server: {
    ...(process.env.CAPACITOR_SERVER_URL ? { url: process.env.CAPACITOR_SERVER_URL } : {}),
    allowNavigation: ['perenniaai.com', 'app.perenniaai.com', 'api.perenniaai.com', 'www.perenniaai.com', 'localhost', '127.0.0.1'],
  },
  ios: {
    contentInset: 'automatic',
    allowsLinkPreview: false,
  }
};

export default config;
