import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import babel from 'vite-plugin-babel';
import path from 'path';

export default defineConfig({
  plugins: [
    // Babel plugin to handle JSX in .js files (CRA compatibility)
    babel({
      filter: /\.[jt]sx?$/,
      babelConfig: {
        presets: [
          ['@babel/preset-react', { runtime: 'automatic' }],
          ['@babel/preset-typescript', { isTSX: true, allExtensions: true }],
        ],
      },
    }),
    react(),
  ],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.js', './src/test/setup.js'],
    include: ['src/**/*.{test,spec}.{js,jsx,ts,tsx}'],
    exclude: [
      'node_modules/',
      'src/__tests__/EstimateComparison*',  // Needs msw v2 migration
    ],
    coverage: {
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/setupTests.js',
        'src/mocks/',
      ],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // Native-only Capacitor plugin — not installed for web/test builds.
      // vite.config.js aliases this to the web stub for production builds;
      // mirror it here so Vitest's import-analysis can resolve the dynamic
      // import in certificatePinning.js instead of failing to collect tests.
      '@capgo/capacitor-ssl-pinning': path.resolve(__dirname, './src/stubs/capacitor-ssl-pinning.js'),
    },
  },
  // Handle JSX in .js files (CRA compatibility)
  esbuild: {
    loader: 'jsx',
    include: /\.[jt]sx?$/,
  },
});
