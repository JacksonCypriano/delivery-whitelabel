import { defineConfig } from "vite";
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
  server: {
    allowedHosts: [".lvh.me", "localhost"],
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
      "/media": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
}));
