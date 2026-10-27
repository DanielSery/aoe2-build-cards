import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative so the built site works from a subdirectory as well as a root.
// The dev server hands /api to the replay reader (replays/server.py), which
// serves the built app itself and needs no proxy.
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8030" } },
});
