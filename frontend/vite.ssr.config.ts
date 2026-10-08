import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({ plugins: [react()], ssr: { noExternal: true }, build: {
  ssr: "src/public/server.mjs", outDir: "../public-ssr", emptyOutDir: true,
  rollupOptions: { output: { entryFileNames: "server.mjs" } },
} });
