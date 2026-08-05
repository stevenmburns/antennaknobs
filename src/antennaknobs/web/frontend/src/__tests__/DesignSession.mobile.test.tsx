// The wiring MobileCarousel.test.tsx cannot see: that the REAL session's
// mobile tree derives its carousel pages and its dots from the same pinned
// list (#700 unit 4). One mount, three facts — page count, page identity, and
// the "⋯" affordance's presence — because everything about how those pages
// behave is already pinned at the hook and component level.
//
// The stub set is newBackend.test.tsx's, with matchMedia flipped to MATCH the
// phone breakpoint so the session renders its mobile branch instead of the
// stage.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DesignSession } from "../components/session/DesignSession";
import { VIEW_META, VIEWS, type View } from "../lib/view";
import { VIEW_PREFS_KEY } from "../components/session/useViewPrefs";
import type { ExampleDescriptor } from "../lib/params";
import { SERVED_ROSTER } from "./backendFixtures";

const PINNED: View[] = ["smith", "antenna", "gamma"];

const EXAMPLE: ExampleDescriptor = {
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

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(
    VIEW_PREFS_KEY,
    JSON.stringify({ pinned: PINNED, seen: VIEWS.map((v) => v.id) }),
  );
  // getContext/ResizeObserver/WebSocket provide-only defaults now live in
  // setup.ts (#728) — every component test gets them unconditionally.
  //
  // matchMedia stays here: setup.ts's default never matches, but this
  // session is on a phone, in portrait, so every query must match to force
  // the mobile branch. That's behavioral (it decides which tree renders),
  // not a gap-fill, so it's a per-file override rather than a migration.
  vi.stubGlobal("matchMedia", () => ({
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  }));
  vi.stubGlobal("fetch", async (url: string) => {
    const path = String(url);
    if (path.startsWith("/capabilities"))
      return jsonResponse({
        have_pynec: true,
        backends: SERVED_ROSTER,
        terrain_presets: [],
      });
    if (path.startsWith("/examples"))
      return jsonResponse({ examples: [EXAMPLE], errors: [] });
    if (path.startsWith("/geometry")) return jsonResponse({ wires: [] });
    return jsonResponse({});
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the session's mobile tree", () => {
  it("carries one carousel page and one dot per pinned view, plus Info", async () => {
    const { container } = render(<DesignSession id={1} active />);
    await waitFor(() =>
      expect(container.querySelector(".mobile-carousel")).not.toBeNull(),
    );

    // Pages: the pinned views in pin order, then the Info screen — NOT the
    // registry, which is four views longer here.
    const pages = container.querySelectorAll(".mobile-screen");
    expect(pages).toHaveLength(PINNED.length + 1);
    expect(pages[pages.length - 1].classList).toContain("mobile-screen-info");

    // Dots: the same list, from the same derivation.
    expect(
      screen.getAllByRole("button", { name: /^Show / }).map((b) => b.getAttribute("title")),
    ).toEqual([...PINNED.map((id) => VIEW_META[id].label), "Info"]);

    // The roster the pages were drawn from is one tap away.
    expect(screen.getByRole("button", { name: "All views" })).toBeTruthy();
  });
});
