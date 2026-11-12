import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // In development the page is served by Vite (port 5173) and the API by
    // `koopjeskompas serve` (port 8000). Forwarding /api makes them one origin
    // to the browser, as CloudFront will in production (PLAN.md §9.3), so the
    // API needs no CORS setup.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    unstubGlobals: true, // undo vi.stubGlobal("fetch", ...) after each test
    unstubEnvs: true, // and vi.stubEnv("VITE_API_BASE_URL", ...)
  },
});
