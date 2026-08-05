import { defineConfig } from "vitest/config";

// Separate from vite.config.ts (not merged via `test:` there) because the app
// config's `defineConfig` comes from "vite", which has no `test` field in its
// type — merging would need switching that import to "vitest/config" for a
// dev/build config that otherwise has nothing to do with tests.
export default defineConfig({
  test: {
    // App.tsx computes WS_URL from window.location at module scope (issue
    // #642), so importing it from a Node environment throws before any test
    // runs. jsdom supplies window/document without starting a real browser.
    environment: "jsdom",
    // src-wide, not src/__tests__ only: a co-located test next to its
    // component used to be silently ignored — never run, never reported,
    // green CI (#735). The __tests__ layout keeps working verbatim.
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    // No `globals: true` — tests import describe/it/expect explicitly so
    // they typecheck under tsc without adding vitest's ambient types to
    // tsconfig (npm run build's tsc --noEmit covers all of src/).
    //
    // That choice costs Testing Library its auto-cleanup: RTL only registers
    // its own afterEach when it finds one on globalThis at import time, which
    // without `globals` is never. setup.ts registers it explicitly instead —
    // without it, mounted components from earlier tests stay in document.body
    // and getBy* queries hit duplicate matches.
    setupFiles: ["src/__tests__/setup.ts"],
    // `npm run test:coverage` only (#736) — not part of CI's plain `npm test`,
    // which stays fast. No thresholds: this is a first measurement to find
    // gaps (see the issue), not a gate to enforce yet.
    coverage: {
      provider: "v8",
      include: ["src/**"],
      exclude: ["src/__tests__/**", "src/**/*.config.ts"],
    },
  },
});
