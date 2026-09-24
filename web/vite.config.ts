/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API is same-origin in production (nginx proxies /api to the api container), so the
// dev server proxies the same prefix. That keeps one code path: the app always calls /api.
const API_TARGET = process.env.AAMSX_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        // Experiment streams are WebSockets on the same prefix.
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // three and echarts are large and change rarely; splitting them keeps the app
        // chunk small enough that a code edit does not invalidate 2 MB of vendor cache.
        // Vite 8 bundles with rolldown, where the object form of `manualChunks` is gone
        // and named groups are matched by module path instead.
        codeSplitting: {
          groups: [
            { name: "three", test: /node_modules\/(three|@react-three)\// },
            { name: "echarts", test: /node_modules\/(echarts|echarts-for-react|zrender)\// },
            { name: "react", test: /node_modules\/(react|react-dom|react-router|scheduler)\// },
          ],
        },
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
