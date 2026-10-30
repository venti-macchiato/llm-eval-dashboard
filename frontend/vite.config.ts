import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built assets land in ../static/dist and are served by FastAPI under
// /static/dist. Dev server proxies /api to the FastAPI backend.
export default defineConfig({
  plugins: [react()],
  base: "/static/dist/",
  build: {
    outDir: "../static/dist",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
