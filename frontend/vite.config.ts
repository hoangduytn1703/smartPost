import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = "http://127.0.0.1:8500";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5180,
    proxy: { "/api": api, "/files": api },
  },
});
