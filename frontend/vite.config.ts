/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Version compiled into the frontend; the image build passes the same APP_VERSION as
  // to the backend, so both report one version (spec 5.7)
  define: { __APP_VERSION__: JSON.stringify(process.env.APP_VERSION ?? "dev") },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    // Listen on all interfaces, so the dev server is reachable from outside the
    // container (forwarded port, or the host's IP address)
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    watch: { ignored: ["**/dist/**", "**/coverage/**"] },
    // Development: the backend runs separately (uvicorn on port 8000)
    proxy: { "/api": "http://localhost:8000" },
  },
  build: { outDir: "dist" },
  test: {
    environment: "jsdom",
    // One jsdom per worker instead of one per test file; each file still runs isolated
    pool: "vmThreads",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    reporters: ["default", "./src/test/req-reporter.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/test/**", "src/api/schema.d.ts", "src/main.tsx", "src/**/*.test.{ts,tsx}"],
      thresholds: { lines: 80 },
    },
  },
});
