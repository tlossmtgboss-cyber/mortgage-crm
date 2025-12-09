import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.perenniaai.crm',
  appName: 'Perennia AI',
  webDir: 'build',
  server: {
    // Allow the app to make requests to the Railway backend
    allowNavigation: ['mortgage-crm-production-7a9a.up.railway.app'],
  },
  ios: {
    contentInset: 'automatic',
    allowsLinkPreview: true,
  }
};

export default config;
