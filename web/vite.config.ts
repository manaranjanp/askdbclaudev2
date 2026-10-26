import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI backend runs on port 8000 (uvicorn default).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
