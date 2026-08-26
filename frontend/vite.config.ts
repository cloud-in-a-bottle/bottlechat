import { defineConfig } from "vite";
import solidPlugin from "vite-plugin-solid";

// `just dev` runs the backend on 8000.  The router isn't in the loop locally, so the proxy
// forges the header it would inject — dev only, never in a built asset.
const apiTarget = `http://127.0.0.1:${process.env.VITE_API_PORT || "8000"}`;
const devOwnerHeaders = { "x-openhost-is-owner": "true" };

export default defineConfig({
  plugins: [solidPlugin()],
  build: {
    target: "es2022",
    sourcemap: true,
  },
  server: {
    proxy: {
      "/api": { target: apiTarget, headers: devOwnerHeaders },
      "/share": { target: apiTarget, headers: devOwnerHeaders },
      "/health": { target: apiTarget, headers: devOwnerHeaders },
    },
  },
});
