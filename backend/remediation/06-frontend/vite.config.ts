/**
 * 06-frontend/vite.config.ts
 *
 * Vite config with aggressive code-splitting, bundle analysis, and size budgets.
 * Targets: initial load <12MB raw / ~3MB gzipped. Route chunks lazy-load on match.
 *
 * Drop-in: frontend/vite.config.ts
 */

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { visualizer } from "rollup-plugin-visualizer";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const isAnalyze = mode === "analyze";
  const isProd = mode === "production" || isAnalyze;

  return {
    plugins: [
      react({
        babel: {
          // SWC-like plugin chain: remove dev-only code in prod
          plugins: isProd
            ? [["babel-plugin-transform-remove-console", { exclude: ["error", "warn"] }]]
            : [],
        },
      }),
      isAnalyze &&
        visualizer({
          filename: "dist/stats.html",
          open: false,
          gzipSize: true,
          brotliSize: true,
          template: "treemap",
        }),
    ].filter(Boolean),

    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },

    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: env.VITE_API_PROXY || "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },

    build: {
      target: "es2022",
      sourcemap: isProd ? "hidden" : true,
      cssCodeSplit: true,
      chunkSizeWarningLimit: 800, // KB — warn per chunk, not total

      rollupOptions: {
        output: {
          // Long-term caching: content hash in filename
          entryFileNames: "assets/[name]-[hash].js",
          chunkFileNames: "assets/[name]-[hash].js",
          assetFileNames: "assets/[name]-[hash][extname]",

          manualChunks(id: string) {
            // --- node_modules chunking --------------------------------------
            if (id.includes("node_modules")) {
              // React ecosystem — shared everywhere, one chunk
              if (
                id.includes("react/") ||
                id.includes("react-dom") ||
                id.includes("react-router") ||
                id.includes("scheduler")
              ) {
                return "vendor-react";
              }
              // UI libs
              if (
                id.includes("@radix-ui") ||
                id.includes("framer-motion") ||
                id.includes("lucide-react") ||
                id.includes("sonner")
              ) {
                return "vendor-ui";
              }
              // Data / state
              if (
                id.includes("zustand") ||
                id.includes("@tanstack/react-query") ||
                id.includes("immer") ||
                id.includes("zod")
              ) {
                return "vendor-data";
              }
              // Heavy libs loaded only by specific features — own chunks
              if (id.includes("three") || id.includes("@react-three")) {
                return "vendor-three";
              }
              if (id.includes("recharts") || id.includes("d3")) {
                return "vendor-charts";
              }
              if (id.includes("gsap")) {
                return "vendor-gsap";
              }
              if (id.includes("pdfjs") || id.includes("react-pdf")) {
                return "vendor-pdf";
              }
              if (id.includes("monaco") || id.includes("codemirror")) {
                return "vendor-editor";
              }
              // Everything else — generic vendor
              return "vendor-misc";
            }

            // --- app chunking by route area --------------------------------
            const src = id.replace(/\\/g, "/");

            if (src.includes("/src/features/pipeline/")) return "app-pipeline";
            if (src.includes("/src/features/ai/") || src.includes("/src/features/aria/"))
              return "app-ai";
            if (src.includes("/src/features/voice/") || src.includes("/src/features/call-intelligence/"))
              return "app-voice";
            if (src.includes("/src/features/borrower-portal/")) return "app-borrower";
            if (src.includes("/src/features/admin/") || src.includes("/src/features/settings/"))
              return "app-admin";
            if (src.includes("/src/features/documents/") || src.includes("/src/features/guidelines/"))
              return "app-docs";

            // Default: main bundle
            return undefined;
          },
        },
      },

      // Minification
      minify: "esbuild",
      cssMinify: "lightningcss",

      // Size budget — CI fails if exceeded
      // Enforced separately in scripts/size-check.mjs
    },

    // Optimize deps used everywhere so they're pre-bundled in dev
    optimizeDeps: {
      include: [
        "react",
        "react-dom",
        "react-router-dom",
        "zustand",
        "immer",
        "@tanstack/react-query",
      ],
    },
  };
});
