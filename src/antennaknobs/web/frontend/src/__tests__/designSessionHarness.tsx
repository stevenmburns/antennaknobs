// The one recipe for mounting the real <DesignSession> (issue #718). Every
// other component test in this suite mounts a piece PULLED OUT of
// DesignSession instead (SolveOverlays.test.tsx, ViewPicker.test.tsx,
// LayoutModeToggle.test.tsx, ViewGrid.test.tsx) — DesignSession itself owns a
// WebSocket, a fetch-backed catalog and a capabilities gate, so mounting it
// needs a stubbed fetch, seeded view prefs, and a controlled matchMedia.
// DesignSession.mobile.test.tsx worked this recipe out first (from
// newBackend.test.tsx's fetch stub); this is that recipe, generalized to also
// cover desktop and grid layout, not a reimplementation of it.
//
// Deliberately NOT covered here (future work; the seam is this function):
// no WS message injection and no solve-response simulation — nothing today
// asserts on a live solve landing, only on static mount-time placement/wiring,
// and setup.ts's InertWebSocket never calls onmessage.
import { vi } from "vitest";
import { render } from "@testing-library/react";
import { DesignSession } from "../components/session/DesignSession";
import { VIEW_PREFS_KEY, type Layout } from "../components/session/useViewPrefs";
import { VIEWS, type View } from "../lib/view";
import type { ExampleDescriptor } from "../lib/params";
import type { BackendRoster } from "../lib/backends";
import {
  SERVED_ROSTER,
  SERVED_ALIASES,
  SERVED_SLOT_SEEDS,
} from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

// A minimal but representative example descriptor — the same fixture
// DesignSession.mobile.test.tsx (and newBackend.test.tsx before it) used, so
// switching either file over to the harness changes no served data.
export const HARNESS_EXAMPLE: ExampleDescriptor = {
  name: "dipoles.probe",
  label: "Probe dipole",
  multi_feed: false,
  param_schema: [],
  result_schema: [],
  bands: [],
  meas_freq_range_mhz: null,
  default_view: "xz",
  default_freq: null,
  default_design_freq: null,
  default_backend: null,
  requires_backends: null,
  has_design_freq: true,
  variants: ["default"],
  variant_values: {},
  sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25 },
};

// The pinned set every test gets unless it asks for its own: the four
// founding views (VIEWS' defaultPinned entries) — matches what a fresh
// (never-configured) useViewPrefs store would seed, so a test that doesn't
// care about pinning still exercises the everyday shape.
const DEFAULT_PINNED: View[] = VIEWS.filter((v) => v.defaultPinned).map(
  (v) => v.id,
);

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

// A fetch-route override: given the request, return a Response to short-
// circuit the default routing, or undefined/null to fall through to the
// harness's own /capabilities, /examples, /geometry defaults (in that
// order — a route keyed "/geometry" still sees every /geometry POST, it just
// runs before the default that would otherwise answer it).
export type FetchRouteOverrides = Record<
  string,
  (url: string, init?: RequestInit) => Response | Promise<Response>
>;

export interface MountDesignSessionOptions {
  /** Force the phone/portrait branch (matchMedia matches everything) when
   * true, or the desktop tree (matchMedia never matches) when false. */
  mobile?: boolean;
  /** Desktop stage layout preset; irrelevant (never reachable) on mobile —
   * see DesignSession's `effectiveLayout` comment. */
  layout?: Layout;
  /** The desktop rail / grid / mobile carousel's resident view set. */
  pinned?: View[];
  /** Session tab id, forwarded to <DesignSession id={…} active />. */
  id?: number;
  /** /capabilities' served roster; defaults to the shared SERVED_ROSTER
   * fixture (backendFixtures.ts). */
  roster?: BackendRoster;
  /** /examples' catalog; defaults to the single HARNESS_EXAMPLE above. */
  examples?: ExampleDescriptor[];
  /** Per-path handlers tried before the built-in /capabilities, /examples
   * and /geometry defaults — e.g. to capture POST /geometry bodies, or to
   * answer a route the defaults don't know about. */
  routes?: FetchRouteOverrides;
}

// Mounts <DesignSession>: seeds the view prefs localStorage record, stubs
// matchMedia to force the requested branch, stubs fetch to serve
// /capabilities + /examples (+ whatever `routes` adds), and renders. Returns
// exactly what @testing-library/react's `render` returns — callers use its
// `container`/`rerender`/etc the same as any other render() call.
//
// Callers own teardown: call `vi.unstubAllGlobals()` in their own afterEach
// (setup.ts's per-test cleanup() handles the DOM; the fetch/matchMedia stubs
// are this function's, not setup.ts's, so unstubbing them is the caller's
// responsibility — same division DesignSession.mobile.test.tsx already had).
export function mountDesignSession(opts: MountDesignSessionOptions = {}) {
  const {
    mobile = false,
    layout = "rail",
    pinned = DEFAULT_PINNED,
    id = 1,
    roster = SERVED_ROSTER,
    examples = [HARNESS_EXAMPLE],
    routes = {},
  } = opts;

  localStorage.clear();
  localStorage.setItem(
    VIEW_PREFS_KEY,
    JSON.stringify({ pinned, seen: VIEWS.map((v) => v.id), layout }),
  );

  // Every query matches (mobile) or none does (desktop) — the session reads
  // both the phone-breakpoint query and the portrait query through the same
  // global, so this one stub decides isMobile AND orientation together, as
  // DesignSession.mobile.test.tsx established.
  vi.stubGlobal("matchMedia", () => ({
    matches: mobile,
    addEventListener() {},
    removeEventListener() {},
  }));

  vi.stubGlobal(
    "fetch",
    async (url: string, init?: RequestInit): Promise<Response> => {
      const path = String(url);
      for (const [prefix, handler] of Object.entries(routes)) {
        if (path.startsWith(prefix)) return handler(path, init);
      }
      if (path.startsWith("/capabilities"))
        return jsonResponse({
          have_pynec: true,
          backends: roster,
          model_option_specs: SERVED_OPTION_SPECS,
          backend_aliases: SERVED_ALIASES,
          default_slots: SERVED_SLOT_SEEDS,
          terrain_presets: [],
        });
      if (path.startsWith("/examples"))
        return jsonResponse({ examples, errors: [] });
      if (path.startsWith("/geometry")) return jsonResponse({ wires: [] });
      return jsonResponse({});
    },
  );

  return render(<DesignSession id={id} active />);
}
