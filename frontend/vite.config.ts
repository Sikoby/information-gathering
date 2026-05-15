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
  build: {
    outDir: "dist",
  },
  server: {
    port: 5173,
    proxy: {
      "^/[^/]+/state$": { target: "http://localhost:8765", changeOrigin: true },
      "^/[^/]+/events$": { target: "http://localhost:8765", changeOrigin: true },
    },
  },
});
