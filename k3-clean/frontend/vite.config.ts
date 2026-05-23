import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/orchestrate": "http://localhost:8716",
      "/sessions":    "http://localhost:8716",
      "/languages":   "http://localhost:8716",
      "/workflows":   "http://localhost:8716",
      "/providers":   "http://localhost:8716",
      "/mcp":         "http://localhost:8716",
      "/health":      "http://localhost:8716",
    },
  },
});
