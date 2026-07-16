import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev-server proxy. Instead of enumerating every backend route (which meant a
// new route silently 404'd into the SPA fallback until someone remembered to
// add it here — this bit us repeatedly), we proxy *everything* to the backend
// and bypass only the requests Vite must serve itself: the SPA document, its
// own dev-client internals (/@vite, /@react-refresh, /@fs, /@id), app source
// under /src, pre-bundled deps under /node_modules, and any static asset (a
// path with a file extension). Everything else — every extensionless GET and
// every non-GET — is a backend API call and is forwarded automatically, so new
// JSON routes need no change here.
//
// The app WebSocket stays an explicit entry: it's the only upgrade route, and
// keeping it separate leaves Vite's own HMR socket untouched.
export default defineConfig({
  plugins: [react()],
  // Build the production bundle straight into the `web` Python package
  // (web/static), so it ships as package data in the antennaknobs wheel and
  // server.py can mount it at "/". emptyOutDir is required because the target
  // is outside this Vite root (web/frontend).
  build: {
    outDir: "../static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/ws": { target: "ws://127.0.0.1:8000", ws: true, changeOrigin: true },
      "/": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        // Propagate client aborts upstream. http-proxy does NOT reliably
        // destroy its backend request when the browser goes away mid-stream
        // (closed tab during an NDJSON sweep): the upstream socket lingers,
        // the backend's request.is_disconnected() stays false, and a
        // benchmark-mesh sweep grinds on for tens of minutes against a dead
        // client (found in the #382 acceptance pass — five zombie proxied
        // streams kept a whip sweep+converge+norm-check burning after the
        // tab closed). Production doesn't route through this proxy; only
        // the dev loop needs the hand-off.
        configure(proxy) {
          proxy.on("proxyReq", (proxyReq, req, res) => {
            res.on("close", () => {
              if (!res.writableFinished) proxyReq.destroy();
            });
          });
        },
        bypass(req) {
          const url = req.url || "";
          // Only GETs can be Vite-owned; any other method is an API call.
          if (req.method === "GET") {
            const accept = req.headers.accept || "";
            if (
              accept.includes("text/html") || // SPA document / navigations
              url === "/" ||
              url.startsWith("/@") || // /@vite, /@react-refresh, /@fs, /@id
              url.startsWith("/src/") || // app source modules
              url.startsWith("/node_modules/") || // pre-bundled deps
              /\.\w+($|\?)/.test(url) // static assets: .js/.css/.svg/...
            ) {
              return url; // let Vite serve it
            }
          }
          return undefined; // forward to the backend
        },
      },
    },
  },
});
