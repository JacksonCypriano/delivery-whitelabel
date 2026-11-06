import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/static/merchant/" : "/",
  build: {
    outDir: "../static/merchant",
    emptyOutDir: true,
    manifest: true,
    rollupOptions: { input: "src/main.tsx" },
  },
  test: {
    maxWorkers: 1,
    fileParallelism: false,
    testTimeout: 15000,
  },
  server: {
    allowedHosts: [".lvh.me", "localhost"],
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
      "/media": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
}));
