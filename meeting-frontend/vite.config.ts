import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  // @ig/ui is a workspace package consumed as source — keep it out of the
  // dependency pre-bundler so Vite transpiles its .tsx directly.
  optimizeDeps: {
    exclude: ["@ig/ui"],
  },
  build: {
    outDir: "dist",
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8771", changeOrigin: true },
      "/healthz": { target: "http://localhost:8771", changeOrigin: true },
    },
  },
});
