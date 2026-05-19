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
    },
  },
  // Handle JSX in .js files (CRA compatibility)
  esbuild: {
    loader: 'jsx',
    include: /\.[jt]sx?$/,
  },
});
