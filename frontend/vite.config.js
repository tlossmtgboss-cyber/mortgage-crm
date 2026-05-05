import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import babel from 'vite-plugin-babel';
import path from 'path';

// https://vitejs.dev/config/
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

  // Build output directory (matches CRA's default)
  build: {
    outDir: 'build',
    sourcemap: false,
    // Strip console.log/warn/info from production builds (keep console.error)
    minify: 'esbuild',
    // Rollup options for chunking
    rollupOptions: {
      // Native-only Capacitor plugins — not available in web builds
      external: ['@capgo/capacitor-ssl-pinning'],
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          mui: ['@mui/material', '@mui/icons-material'],
          charts: ['recharts'],
        },
      },
    },
  },

  // Dev server configuration
  server: {
    port: 3000,
    open: true,
    // Proxy API calls to backend
    proxy: {
      '/api': {
        target: 'https://api.perenniaai.com',
        changeOrigin: true,
        secure: true,
      },
      '/token': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },

  // Preview server (for production build testing)
  preview: {
    port: 3000,
  },

  // Resolve aliases for cleaner imports
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@capgo/capacitor-ssl-pinning': path.resolve(__dirname, './src/stubs/capacitor-ssl-pinning.js'),
    },
  },

  // Environment variable prefix (Vite uses VITE_ by default)
  envPrefix: ['VITE_'],

  esbuild: {
    drop: process.env.NODE_ENV === 'production' ? ['debugger'] : [],
    pure: process.env.NODE_ENV === 'production' ? ['console.log', 'console.info', 'console.debug', 'console.trace'] : [],
  },

  // Define global constants (for process.env compatibility)
  define: {
    // Provide process.env.NODE_ENV for libraries that expect it
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'development'),
  },

  // Optimize dependencies
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-router-dom',
      '@mui/material',
      '@emotion/react',
      '@emotion/styled',
      'axios',
      '@tanstack/react-query',
    ],
    exclude: ['@capgo/capacitor-ssl-pinning'],
    esbuildOptions: {
      // Handle JSX in .js files (CRA compatibility)
      loader: {
        '.js': 'jsx',
      },
    },
  },

  // CSS configuration
  css: {
    devSourcemap: true,
  },
});
