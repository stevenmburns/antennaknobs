// Vitest setup for the component tests (see vitest.config.ts `setupFiles`).
//
// Testing Library normally unmounts between tests by registering its own
// afterEach at import time, but it looks for that hook on globalThis and this
// suite runs without `globals: true`. Verified empirically: without the hook
// below a component mounted in one test is still in document.body during the
// next, so getBy* queries throw on duplicate matches. Registering it here
// rather than per test file keeps the guarantee unconditional — a new
// component test cannot forget it.
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(cleanup);

// --- jsdom gap-fillers (issue #728) ----------------------------------------
//
// jsdom implements neither ResizeObserver nor matchMedia and its canvas
// element has no 2-D context, so any component that measures itself
// (useSlideSize/useGridCellSize/useThumbColumnSize in components/hooks.ts),
// checks a media query (useIsMobile), or draws a chart throws unless
// something fills the gap. A real network WebSocket is also wrong in a test
// process — DesignSession opens one on mount (useSolveChannel).
//
// These four used to be stubbed per test file with `vi.stubGlobal`. Two
// failure modes follow from that (#728). The one that actually bit, in
// #726's CI run and as the load-sensitive "phantom flake": a stub torn down
// by the file's own afterEach `vi.unstubAllGlobals()` while a late React
// passive-effect flush was still pending — the effect then ran against an
// UNDEFINED global (DesignSession.mobile.test.tsx's ResizeObserver, timing-
// dependent, worse under CPU load). And the latent one: vitest workers host
// several files per process, so a file that forgot its own stub could pass
// locally off a co-hosted sibling's leak and fail under CI's different
// packing. Unconditional defaults here close both at once — after any
// unstub, the global falls back to a WORKING default, never to undefined,
// and no file's pass/fail depends on its worker neighbors. The suite is
// safe under `--sequence.shuffle` either way.
//
// Plain assignment, not `vi.stubGlobal` — deliberately. Per-file `afterEach`
// hooks commonly call `vi.unstubAllGlobals()` (to drop THEIR OWN behavioral
// stubs, e.g. `fetch`) and/or `vi.restoreAllMocks()` (to drop THEIR OWN
// spies). Both only undo their respective vitest API (stubGlobal / spyOn), so
// a plain `globalThis.x = ...` here is invisible to both and keeps holding
// for every test in the suite. A file that needs different behavior (a
// recording canvas context, a matchMedia that DOES match a breakpoint)
// overrides the property directly or via its own `vi.stubGlobal` in its own
// `beforeEach` — that's a per-file override of this default, not a fight
// with it, and `vi.unstubAllGlobals()`/reassignment on the next test falls
// straight back to what's set here.

class InertResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = InertResizeObserver as unknown as typeof ResizeObserver;

// Never-matching by default, so the desktop tree renders in every test that
// never thinks about layout at all. The mobile-specific tests
// (DesignSession.mobile.test.tsx) override this per-file with a MATCHING
// stub to force the phone branch — that override is behavioral (it decides
// which branch renders), not a gap-fill, so it stays local to that file.
globalThis.matchMedia = (() => ({
  matches: false,
  addEventListener() {},
  removeEventListener() {},
})) as unknown as typeof window.matchMedia;

// null is the answer every chart/canvas test that isn't inspecting drawn
// output wants: "no 2-D context available, render your no-crash fallback."
// SmithChart.test.tsx DOES assert on what got drawn, so it overrides this
// per-render with its own recording context — a plain reassignment, not a
// spy, so a sibling file's `vi.restoreAllMocks()` can't touch it either way.
HTMLCanvasElement.prototype.getContext = (() =>
  null) as unknown as typeof HTMLCanvasElement.prototype.getContext;

// jsdom's own WebSocket (where present) would attempt a real connection.
// Nothing in this suite asserts on send()/readyState, so an inert stub that
// never opens is the correct default for every test that mounts
// <DesignSession>.
class InertWebSocket {
  static OPEN = 1;
  readyState = 0;
  close() {}
  send() {}
}
globalThis.WebSocket = InertWebSocket as unknown as typeof WebSocket;
