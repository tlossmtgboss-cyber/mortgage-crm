import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import babel from 'vite-plugin-babel';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const isProduction = mode === 'production';

  // Load env vars with both VITE_ and REACT_APP_ prefixes so they're
  // available in this config file (process.env only has system vars here).
  const env = loadEnv(mode, process.cwd(), ['VITE_', 'REACT_APP_']);

  return {
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

    // Strip console.log/debug/info/trace and debugger from production builds.
    // console.warn and console.error are preserved for production error monitoring.
    esbuild: {
      drop: isProduction ? ['debugger'] : [],
      pure: isProduction ? ['console.log', 'console.debug', 'console.info', 'console.trace'] : [],
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

    // Environment variable prefix — include REACT_APP_ for CRA backward compatibility
    envPrefix: ['VITE_', 'REACT_APP_'],

    // Define global constants (for process.env compatibility)
    // All REACT_APP_* references are replaced at build time so they don't resolve to undefined.
    // Values come from: system env vars (CI/Railway) > .env files > fallback to ''.
    define: {
      // Provide process.env.NODE_ENV for libraries that expect it
      'process.env.NODE_ENV': JSON.stringify(isProduction ? 'production' : 'development'),
      // CRA-to-Vite compatibility: map every process.env.REACT_APP_* used in src/
      'process.env.REACT_APP_API_URL': JSON.stringify(env.REACT_APP_API_URL || ''),
      'process.env.REACT_APP_API_BASE': JSON.stringify(env.REACT_APP_API_BASE || ''),
      'process.env.REACT_APP_BASE_URL': JSON.stringify(env.REACT_APP_BASE_URL || ''),
      'process.env.REACT_APP_PERENNIA_API_BASE': JSON.stringify(env.REACT_APP_PERENNIA_API_BASE || ''),
      'process.env.REACT_APP_WS_URL': JSON.stringify(env.REACT_APP_WS_URL || ''),
      'process.env.REACT_APP_ENABLE_WEBSOCKET': JSON.stringify(env.REACT_APP_ENABLE_WEBSOCKET || ''),
      'process.env.REACT_APP_GOOGLE_PLACES_API_KEY': JSON.stringify(env.REACT_APP_GOOGLE_PLACES_API_KEY || ''),
      'process.env.REACT_APP_FRED_API_KEY': JSON.stringify(env.REACT_APP_FRED_API_KEY || ''),
      'process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY': JSON.stringify(env.REACT_APP_STRIPE_PUBLISHABLE_KEY || ''),
      'process.env.REACT_APP_TURNSTILE_SITE_KEY': JSON.stringify(env.REACT_APP_TURNSTILE_SITE_KEY || ''),
      'process.env.REACT_APP_PURL_DOMAIN': JSON.stringify(env.REACT_APP_PURL_DOMAIN || ''),
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
    // CSS Modules are supported natively by Vite for *.module.css files.
    // New components should use CSS Modules; see src/styles/README.md.
    css: {
      devSourcemap: true,
      modules: {
        localsConvention: 'camelCase',
      },
    },
  };
});
