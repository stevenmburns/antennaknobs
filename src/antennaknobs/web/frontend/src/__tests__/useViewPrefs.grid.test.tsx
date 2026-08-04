// Unit 3 of docs/plan-view-rail-scaling.md ("Layout modes"): the `layout`
// field useViewPrefs.test.tsx's comments promised room for, plus the pure
// grid-shape helpers (gridCells/gridShape/gridFix) that decide what grid
// mode shows and how it recovers when the focus ring drifts off-grid.
//
// A separate file rather than additions to useViewPrefs.test.tsx: that file
// is the pre-existing baseline this arc must keep passing UNEDITED (its
// exact-keys assertion is what proves the sparse-write design below is
// correct), so anything new lives here instead.
import { describe, it, expect, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { type View } from "../lib/view";
import {
  VIEW_PREFS_KEY,
  gridCells,
  gridFix,
  gridShape,
  useViewPrefs,
} from "../components/session/useViewPrefs";

const FOUNDING: View[] = ["antenna", "azimuth", "elevation", "smith"];

beforeEach(() => {
  localStorage.clear();
});

function stored() {
  return JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "null");
}

// --- 1. Defaults --------------------------------------------------------

describe("layout defaults", () => {
  it("is rail with no stored state", () => {
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.layout).toBe("rail");
  });

  it("writes nothing extra until setLayout is called", () => {
    renderHook(() => useViewPrefs());
    expect(localStorage.getItem(VIEW_PREFS_KEY)).toBeNull();
  });
});

// --- 2. Persistence + sparse write --------------------------------------

describe("layout persistence", () => {
  it("round-trips a grid pick through storage to the next mount", () => {
    const first = renderHook(() => useViewPrefs());
    act(() => first.result.current.setLayout("grid"));
    expect(first.result.current.layout).toBe("grid");
    expect(stored().layout).toBe("grid");
    first.unmount();

    const second = renderHook(() => useViewPrefs());
    expect(second.result.current.layout).toBe("grid");
  });

  it("round-trips back to rail too", () => {
    const first = renderHook(() => useViewPrefs());
    act(() => first.result.current.setLayout("grid"));
    act(() => first.result.current.setLayout("rail"));
    first.unmount();
    const second = renderHook(() => useViewPrefs());
    expect(second.result.current.layout).toBe("rail");
  });

  // The whole point of the sparse write (see useViewPrefs.ts's ViewPrefs
  // comment): a pin/unpin that never touches layout must not grow the
  // stored record's key set, or useViewPrefs.test.tsx's pre-unit-3
  // exact-keys assertion (["pinned","seen"]) would break on THIS build even
  // though that test file is untouched.
  it("omits `layout` from storage while it is rail (togglePin only)", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.togglePin("schematic"));
    const rec = stored();
    expect(Object.keys(rec).sort()).toEqual(["pinned", "seen"]);
  });

  it("includes `layout` once it is grid, even from an unrelated pin toggle", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.setLayout("grid"));
    act(() => result.current.togglePin("schematic"));
    const rec = stored();
    expect(Object.keys(rec).sort()).toEqual(["layout", "pinned", "seen"]);
    expect(rec.layout).toBe("grid");
  });

  it("drops the key again on a return to rail", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.setLayout("grid"));
    act(() => result.current.setLayout("rail"));
    expect(Object.keys(stored()).sort()).toEqual(["pinned", "seen"]);
  });
});

// --- 3. Corrupt / unknown values fall back to rail ----------------------

describe("layout validation", () => {
  const cases = [
    ["absent", '{"pinned":["antenna"],"seen":["antenna"]}'],
    ["wrong type", '{"pinned":["antenna"],"seen":["antenna"],"layout":3}'],
    ["unknown string", '{"pinned":["antenna"],"seen":["antenna"],"layout":"list"}'],
    ["null", '{"pinned":["antenna"],"seen":["antenna"],"layout":null}'],
  ] as const;

  for (const [what, raw] of cases) {
    it(`falls back to rail on a ${what} layout field`, () => {
      localStorage.setItem(VIEW_PREFS_KEY, raw);
      const { result } = renderHook(() => useViewPrefs());
      expect(result.current.layout).toBe("rail");
    });
  }

  it("still recovers the good pinned/seen fields alongside a bad layout", () => {
    localStorage.setItem(
      VIEW_PREFS_KEY,
      '{"pinned":["smith"],"seen":["smith"],"layout":"bogus"}',
    );
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.pinned).toEqual(["smith"]);
    expect(result.current.layout).toBe("rail");
  });

  it("honours a stored grid value", () => {
    localStorage.setItem(
      VIEW_PREFS_KEY,
      '{"pinned":["smith"],"seen":["smith"],"layout":"grid"}',
    );
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.layout).toBe("grid");
  });
});

// --- 4. gridCells / gridShape --------------------------------------------

describe("gridCells", () => {
  it("shows the first ≤4 pins, in pin order — mutation target: order", () => {
    expect(gridCells(["smith", "antenna"])).toEqual(["smith", "antenna"]);
    expect(gridCells(["elevation", "antenna", "azimuth", "smith"])).toEqual([
      "elevation",
      "antenna",
      "azimuth",
      "smith",
    ]);
  });

  it("never shows a 5th or 6th pin", () => {
    const six: View[] = [
      "antenna",
      "azimuth",
      "elevation",
      "smith",
      "schematic",
      "gamma",
    ];
    expect(gridCells(six)).toEqual(FOUNDING);
    expect(gridCells(six)).toHaveLength(4);
  });

  it("passes a single pin through unchanged", () => {
    expect(gridCells(["smith"])).toEqual(["smith"]);
  });
});

describe("gridShape", () => {
  it("is 1x1 for one cell", () => {
    expect(gridShape(1)).toEqual({ rows: 1, cols: 1 });
  });
  it("is 1x2 for two cells", () => {
    expect(gridShape(2)).toEqual({ rows: 1, cols: 2 });
  });
  it("is 2x2 for three cells (the 4th slot is the hint)", () => {
    expect(gridShape(3)).toEqual({ rows: 2, cols: 2 });
  });
  it("is 2x2 for four cells", () => {
    expect(gridShape(4)).toEqual({ rows: 2, cols: 2 });
  });
});

// --- 5. gridFix — the off-grid recovery decision table -------------------

describe("gridFix", () => {
  it("is a no-op outside grid mode", () => {
    expect(gridFix("rail", false, "schematic", FOUNDING)).toBeNull();
  });

  it("is a no-op when the ring is already on a displayed cell", () => {
    expect(gridFix("grid", true, "smith", FOUNDING)).toBeNull();
  });

  it("snaps to cell 1 when ENTERING grid with a peeked view active", () => {
    // wasGrid=false ⇒ just switched rail→grid; "schematic" is unpinned.
    expect(gridFix("grid", false, "schematic", FOUNDING)).toEqual({
      view: "antenna",
    });
  });

  it("snaps to cell 1 when ENTERING grid with pin #5 active", () => {
    const sixPins = [...FOUNDING, "schematic", "gamma"] as View[];
    expect(gridFix("grid", false, "gamma", sixPins)).toEqual({
      view: "antenna",
    });
  });

  it("snaps to cell 1 when ALREADY in grid and a pinned off-grid view (pin #5) is picked", () => {
    const sixPins = [...FOUNDING, "schematic", "gamma"] as View[];
    // wasGrid=true ⇒ grid did not just start; the picker activated "gamma".
    expect(gridFix("grid", true, "gamma", sixPins)).toEqual({
      view: "antenna",
    });
  });

  // The one branch mutation probe 4(b) targets: drop this and the peek stays
  // stranded on a nonexistent cell instead of falling back to rail.
  it("leaves grid for rail when ALREADY in grid and an unpinned peek is picked", () => {
    expect(gridFix("grid", true, "schematic", FOUNDING)).toEqual({
      layout: "rail",
    });
  });
});
