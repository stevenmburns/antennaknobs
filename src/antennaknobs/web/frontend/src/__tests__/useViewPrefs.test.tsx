// Pins the view-preference model against the SHIPPED roster (unit 2 of
// docs/plan-view-rail-scaling.md): the default pin set, what the desktop rail
// derives from it, the arrow-key cycle, the NEW badge, and the localStorage
// contract — including every way the stored record can be garbage. The 6-pin
// cap needs a roster bigger than the cap itself, so it lives in
// ViewPicker.test.tsx, which mocks a larger one.
//
// Roster growth is the normal case here (|Γ| and VSWR landed while this file
// was being written), so anything sized by the roster is DERIVED from VIEWS.
// Two literals are deliberate: FOUNDING, because "the founding four are the
// defaults and later views ship unpinned" is the claim itself, and
// PRE_PICKER, which mirrors the frozen seed inside useViewPrefs.
//
// Isolation: the prefs store is module-level (one truth for every open
// session), and it drops its cache when the last subscriber unmounts, so
// Testing Library's per-test cleanup already gives each test a fresh read of
// whatever it wrote into localStorage.
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { VIEWS, type View } from "../lib/view";
import {
  PIN_CAP,
  VIEW_PREFS_KEY,
  cycleOrder,
  pinBlockedReason,
  useViewPrefs,
} from "../components/session/useViewPrefs";
import { useViewState } from "../components/session/useViewState";

const FOUNDING: View[] = ["antenna", "azimuth", "elevation", "smith"];
const ROSTER = VIEWS.map((v) => v.id);
// A deliberate mirror of useViewPrefs' SEEN_SEED (not exported: it records a
// frozen historical fact rather than offering a knob). Copying it here means a
// change to the production seed surfaces as a failure in the badge tests,
// which is exactly where the seed's meaning lives.
const PRE_PICKER: View[] = ["antenna", "azimuth", "elevation", "smith", "schematic"];
// Views that shipped after the picker did — the population the NEW badge
// exists for. Empty on the day the picker shipped, non-empty ever since.
const POST_PICKER = ROSTER.filter((id) => !PRE_PICKER.includes(id));

beforeEach(() => {
  localStorage.clear();
});

function stored() {
  return JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "null");
}

// --- 1. Defaults come from the registry metadata ----------------------------

describe("defaults", () => {
  it("pins exactly the views VIEWS marks defaultPinned", () => {
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.pinned).toEqual(FOUNDING);
  });

  it("writes nothing until the user acts", () => {
    renderHook(() => useViewPrefs());
    expect(localStorage.getItem(VIEW_PREFS_KEY)).toBeNull();
  });

  // Gate: the one intended visible change is that the schematic leaves the
  // rail. Three non-active founding views, in pin order.
  it("rails the three non-active founding views", () => {
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.railViews("antenna").map((v) => v.id)).toEqual([
      "azimuth",
      "elevation",
      "smith",
    ]);
  });

  // The seed's whole purpose, now firing for real: a first-time user is shown
  // the pre-picker roster as already-seen and every view that shipped AFTER
  // the picker as NEW. Seeding from the live VIEWS instead would badge none of
  // them, ever, for exactly the users who have never seen any of it.
  it("badges the views that shipped after the picker, and only those", () => {
    const { result } = renderHook(() => useViewPrefs());
    expect([...result.current.newIds]).toEqual(POST_PICKER);
    expect(POST_PICKER).toContain("gamma");
    expect(POST_PICKER).toContain("vswr");
    for (const id of PRE_PICKER) expect(result.current.newIds.has(id)).toBe(false);
  });
});

// --- 2. Peek ----------------------------------------------------------------

describe("peek", () => {
  it("shows every pin while an unpinned view is active, and pins nothing", () => {
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.railViews("schematic").map((v) => v.id)).toEqual(
      FOUNDING,
    );
    expect(result.current.pinned).toEqual(FOUNDING);
  });
});

// --- 3. Persistence ---------------------------------------------------------

describe("persistence", () => {
  it("round-trips a pin through storage to the next mount", () => {
    const first = renderHook(() => useViewPrefs());
    act(() => first.result.current.togglePin("schematic"));
    expect(first.result.current.pinned).toEqual([...FOUNDING, "schematic"]);
    expect(stored().pinned).toEqual([...FOUNDING, "schematic"]);
    first.unmount();

    const second = renderHook(() => useViewPrefs());
    expect(second.result.current.pinned).toEqual([...FOUNDING, "schematic"]);
  });

  it("round-trips an unpin too", () => {
    const first = renderHook(() => useViewPrefs());
    act(() => first.result.current.togglePin("smith"));
    first.unmount();
    const second = renderHook(() => useViewPrefs());
    expect(second.result.current.pinned).toEqual(["antenna", "azimuth", "elevation"]);
  });

  // The stored record is an open object of independent fields so unit 3 can
  // add `layout` without a key bump: fields it does not know must survive a
  // write from this build.
  it("stores a named-field object, not a bare array", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.togglePin("schematic"));
    const rec = stored();
    expect(Array.isArray(rec)).toBe(false);
    expect(Object.keys(rec).sort()).toEqual(["pinned", "seen"]);
  });

  it("keeps working when storage is disabled", () => {
    const spy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("storage disabled");
      });
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.togglePin("schematic"));
    expect(result.current.pinned).toContain("schematic");
    spy.mockRestore();
  });
});

// --- 4. Nothing read back from storage is trusted ---------------------------

describe("stored-record validation", () => {
  // Ids no release will ever ship — a stale pin from a REMOVED view, or a
  // hand-edited key. Asserted, not assumed: "gamma" was this file's stand-in
  // for an unknown id until the day it became a real view.
  it("uses id fixtures the registry really does not know", () => {
    for (const id of ["bogus", "no-such-view"]) expect(ROSTER).not.toContain(id);
  });

  const falls_back = [
    ["corrupt JSON", "{not json"],
    ["a bare array", '["antenna"]'],
    ["a null record", "null"],
    ["no pinned field", '{"seen":["antenna"]}'],
    ["a non-array pinned field", '{"pinned":"antenna"}'],
    ["only unknown ids", '{"pinned":["bogus","no-such-view"]}'],
    ["an empty pin set", '{"pinned":[]}'],
  ] as const;

  for (const [what, raw] of falls_back) {
    it(`falls back to the defaults on ${what}`, () => {
      localStorage.setItem(VIEW_PREFS_KEY, raw);
      const { result } = renderHook(() => useViewPrefs());
      expect(result.current.pinned).toEqual(FOUNDING);
    });
  }

  it("drops unknown ids and duplicates from a salvageable record", () => {
    localStorage.setItem(
      VIEW_PREFS_KEY,
      '{"pinned":["smith","bogus","smith","antenna"],"seen":["antenna"]}',
    );
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.pinned).toEqual(["smith", "antenna"]);
  });

  // A `seen` that sanitises to nothing is indistinguishable from an absent
  // one, so it takes the seed — which leaves the same badges a first-time
  // user gets, not a blank slate and not the whole roster.
  it("re-seeds `seen` when the stored one has nothing usable left", () => {
    localStorage.setItem(VIEW_PREFS_KEY, '{"pinned":["smith"],"seen":["bogus"]}');
    const { result } = renderHook(() => useViewPrefs());
    expect([...result.current.newIds]).toEqual(POST_PICKER);
  });

  it("honours a partial `seen` — every other view badges", () => {
    localStorage.setItem(VIEW_PREFS_KEY, '{"pinned":["smith"],"seen":["antenna"]}');
    const { result } = renderHook(() => useViewPrefs());
    expect([...result.current.newIds]).toEqual(
      ROSTER.filter((id) => id !== "antenna"),
    );
  });
});

// --- 5. The pin floor -------------------------------------------------------

describe("pin floor", () => {
  // An empty pin set is what loadPrefs reads as corruption, so it must not be
  // reachable through the UI or the stored state stops being a fixed point.
  it("refuses to unpin the last pin", () => {
    localStorage.setItem(VIEW_PREFS_KEY, '{"pinned":["smith"],"seen":["smith"]}');
    const { result } = renderHook(() => useViewPrefs());
    expect(pinBlockedReason(result.current.pinned, "smith")).toBe(
      "Keep at least one view pinned",
    );
    act(() => result.current.togglePin("smith"));
    expect(result.current.pinned).toEqual(["smith"]);
  });
});

// --- 6. Arrow-key cycling ---------------------------------------------------

// Dispatch from an ELEMENT, never window: the listener's focus guard reads
// event.target's tagName, and a real keydown always originates at an element
// (document.body when nothing is focused).
function press(key: string, target?: HTMLElement) {
  act(() => {
    (target ?? document.body).dispatchEvent(
      new KeyboardEvent("keydown", { key, bubbles: true }),
    );
  });
}

function renderCycler(pinned: View[]) {
  return renderHook(() =>
    useViewState({ currentExample: undefined, active: true, pinned }),
  );
}

describe("arrow-key cycling", () => {
  it("walks exactly the pinned views and wraps", () => {
    const { result } = renderCycler(FOUNDING);
    const seen: View[] = [];
    for (let i = 0; i < FOUNDING.length; i++) {
      press("ArrowDown");
      seen.push(result.current.view);
    }
    // Four stops return to the start; the schematic is never among them.
    expect(seen).toEqual(["azimuth", "elevation", "smith", "antenna"]);
  });

  it("cycles in PIN order, not registry order", () => {
    const { result } = renderCycler(["smith", "antenna"]);
    press("ArrowDown");
    expect(result.current.view).toBe("smith");
    press("ArrowDown");
    expect(result.current.view).toBe("antenna");
  });

  it("keeps a peeked view in the cycle so the arrows can leave it", () => {
    const { result } = renderCycler(FOUNDING);
    act(() => result.current.setView("schematic"));
    press("ArrowDown");
    expect(result.current.view).toBe("antenna");
    // …and it sits at the end of the order, so ArrowUp from the first pin
    // lands back on the peek rather than on the last pin.
    act(() => result.current.setView("antenna"));
    press("ArrowUp");
    expect(result.current.view).toBe("smith");
  });

  it("leaves the arrows alone while an input or a knob has focus", () => {
    const { result } = renderCycler(FOUNDING);
    for (const el of [
      document.createElement("input"),
      Object.assign(document.createElement("div"), { className: "knob" }),
    ]) {
      document.body.appendChild(el);
      press("ArrowDown", el);
      expect(result.current.view).toBe("antenna");
      el.remove();
    }
  });
});

describe("cycleOrder", () => {
  it("appends the active view only when it is unpinned", () => {
    expect(cycleOrder(FOUNDING, "smith")).toEqual(FOUNDING);
    expect(cycleOrder(FOUNDING, "schematic")).toEqual([...FOUNDING, "schematic"]);
  });
});

describe("the cap constant", () => {
  it("is the six the column math bought", () => {
    expect(PIN_CAP).toBe(6);
  });
});
