import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({ plugins: [react()], base: "/static/public/", build: {
  outDir: "../static/public", emptyOutDir: true, manifest: true,
  rollupOptions: { input: "src/public/client.tsx" },
} });
