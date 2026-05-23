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
  // @ig/ui is a workspace package consumed as source.
  optimizeDeps: {
    exclude: ["@ig/ui"],
  },
  build: {
    outDir: "dist",
  },
  server: {
    port: 5174,
    proxy: {
      "/api": { target: "http://localhost:8770", changeOrigin: true },
      "/healthz": { target: "http://localhost:8770", changeOrigin: true },
    },
  },
});
