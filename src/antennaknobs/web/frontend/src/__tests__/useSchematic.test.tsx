// Pins the fetch discipline of the schematic hook
// (src/components/session/useSchematic.ts, issue #652): the 250 ms debounce
// that coalesces a knob drag into one POST, the stale-display policy (a knob
// tweak keeps the previous drawing up until the refetch lands; a design
// switch clears it immediately — another antenna's feed chain on screen is
// misinformation), the available/unavailable state split, and the inactive-
// session gate. fetch is stubbed per test; fake timers drive the debounce.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useSchematic } from "../components/session/useSchematic";
import type { SolveRequest } from "../lib/api";

const REQ = { geometry: "x" } as unknown as SolveRequest;

function respond(body: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn(() => respond({ available: true, svg: "<svg one/>" }));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

type HookProps = { active: boolean; geometry: string; requestKey: string };

function renderSchematic(initial: Partial<HookProps> = {}) {
  return renderHook(
    (p: HookProps) => useSchematic({ ...p, buildRequest: () => REQ }),
    {
      initialProps: {
        active: true,
        geometry: "dipoles.invvee_coax_station",
        requestKey: "k1",
        ...initial,
      },
    },
  );
}

// Run the debounce out and let the stubbed response's promise chain settle.
async function settle() {
  await act(async () => {
    vi.advanceTimersByTime(250);
    await Promise.resolve();
  });
}

// --- 1. debounce -------------------------------------------------------------

describe("debounce", () => {
  it("does not fetch before the debounce elapses", async () => {
    renderSchematic();
    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("coalesces rapid requestKey changes into one POST", async () => {
    const { rerender } = renderSchematic();
    rerender({
      active: true,
      geometry: "dipoles.invvee_coax_station",
      requestKey: "k2",
    });
    rerender({
      active: true,
      geometry: "dipoles.invvee_coax_station",
      requestKey: "k3",
    });
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

// --- 2. state split ----------------------------------------------------------

describe("response handling", () => {
  it("an available response lands the svg and stays not-unavailable", async () => {
    const { result } = renderSchematic();
    await settle();
    expect(result.current.schematicSvg).toBe("<svg one/>");
    expect(result.current.schematicUnavailable).toBe(false);
  });

  it("a no-network response clears the svg and flags unavailable", async () => {
    fetchMock.mockImplementation(() => respond({ available: false }));
    const { result } = renderSchematic();
    await settle();
    expect(result.current.schematicSvg).toBeNull();
    expect(result.current.schematicUnavailable).toBe(true);
  });
});

// --- 3. stale-display policy -------------------------------------------------

describe("stale-display policy", () => {
  it("a knob tweak keeps the old drawing up until the refetch lands", async () => {
    const { result, rerender } = renderSchematic();
    await settle();
    expect(result.current.schematicSvg).toBe("<svg one/>");

    fetchMock.mockImplementation(() =>
      respond({ available: true, svg: "<svg two/>" }),
    );
    rerender({
      active: true,
      geometry: "dipoles.invvee_coax_station",
      requestKey: "k2",
    });
    // Debounce still pending: the previous drawing must not flash away.
    expect(result.current.schematicSvg).toBe("<svg one/>");
    await settle();
    expect(result.current.schematicSvg).toBe("<svg two/>");
  });

  it("a design switch clears the drawing immediately", async () => {
    const { result, rerender } = renderSchematic();
    await settle();
    expect(result.current.schematicSvg).toBe("<svg one/>");

    rerender({ active: true, geometry: "dipoles.invvee", requestKey: "k2" });
    // Before any response: another design's chain must not stay on screen,
    // and the empty state must not claim "no feed circuit" yet either.
    expect(result.current.schematicSvg).toBeNull();
    expect(result.current.schematicUnavailable).toBe(false);
  });
});

// --- 4. inactive gate --------------------------------------------------------

describe("inactive sessions", () => {
  it("does not fetch while the session tab is inactive", async () => {
    renderSchematic({ active: false });
    await settle();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not fetch before a design is selected (geometry \"\")", async () => {
    renderSchematic({ geometry: "" });
    await settle();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
