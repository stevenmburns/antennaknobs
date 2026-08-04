// The mobile carousel's index arithmetic, away from React (#700 unit 4).
//
// Both functions here answer the same question — "which page is the user on,
// now that pages are `pinned ++ [Info]`?" — and every hard case of the unit is
// a statement about one of them, so they are pinned as pure values rather than
// inferred from a rendered carousel. jsdom has no layout and therefore no real
// scroll-snap, which is the other half of the reason: the DOM cannot answer
// "which page snapped" here at all. MobileCarousel.test.tsx drives the same
// mappings through the hook with a stubbed scroll geometry.
import { describe, it, expect } from "vitest";
import { VIEW_META, mobileScreens, type View } from "../lib/view";
import { reconcileCarousel } from "../components/session/useMobileCarousel";

const ids = (pinned: View[]) => mobileScreens(pinned).map((s) => s.id);

// Deliberately NOT registry order: pin order is page order, and a mapping that
// quietly re-sorted into registry order would still pass a same-order fixture.
const TWO: View[] = ["smith", "antenna"];
const FOUR: View[] = ["smith", "antenna", "vswr", "azimuth"];
const SIX: View[] = ["smith", "antenna", "vswr", "azimuth", "schematic", "gamma"];

describe("mobileScreens", () => {
  it.each([
    ["2 pins", TWO],
    ["4 pins", FOUR],
    ["6 pins", SIX],
  ])("pages %s in pin order with Info trailing", (_name, pinned) => {
    expect(ids(pinned)).toEqual([...pinned, "info"]);
    // Info is the LAST page at every pin count — its index is pinned.length,
    // which is why nothing may compare against the registry's length.
    expect(ids(pinned).indexOf("info")).toBe(pinned.length);
  });

  it("labels the chart pages from the registry", () => {
    expect(mobileScreens(FOUR).map((s) => s.label)).toEqual([
      ...FOUR.map((id) => VIEW_META[id].label),
      "Info",
    ]);
  });

  it("still has a page and a dot at the pin floor of one", () => {
    expect(ids(["gamma"])).toEqual(["gamma", "info"]);
  });
});

describe("reconcileCarousel", () => {
  // Hard case 1: `view` has no page. Stored prefs changed under a parked
  // `view`, or the desktop handed one over that it was peeking. index 0 is
  // what a fresh mobile tree holds, so this reads as "snap to the first pin".
  it("snaps a view with no page onto the first pinned page", () => {
    expect(reconcileCarousel(FOUR, FOUR, 0, "elevation")).toEqual({
      index: 0,
      view: "smith",
    });
  });

  // Hard case 2: the page under the thumb was unpinned from the open sheet.
  it("holds the slot when the current page is unpinned, adopting its successor", () => {
    const after: View[] = ["smith", "vswr", "azimuth"]; // antenna dropped
    expect(reconcileCarousel(FOUR, after, 1, "antenna")).toEqual({
      index: 1,
      view: "vswr",
    });
  });

  it("clamps when the unpinned page was the last one", () => {
    const after: View[] = ["smith", "antenna", "vswr"]; // azimuth dropped
    expect(reconcileCarousel(FOUR, after, 3, "azimuth")).toEqual({
      index: 2,
      view: "vswr",
    });
  });

  it("lands on the only remaining page at the floor", () => {
    expect(reconcileCarousel(TWO, ["antenna"], 0, "smith")).toEqual({
      index: 0,
      view: "antenna",
    });
  });

  // Hard case 3: pinning appends, so the page under the thumb must not move.
  it("leaves the current page exactly where it is when a pin is appended", () => {
    const after: View[] = [...TWO, "schematic"];
    expect(reconcileCarousel(TWO, after, 1, "antenna")).toEqual({
      index: 1,
      view: "antenna",
    });
  });

  it("follows the current view when an EARLIER page is unpinned", () => {
    const after: View[] = ["antenna", "vswr", "azimuth"]; // smith dropped
    expect(reconcileCarousel(FOUR, after, 2, "vswr")).toEqual({
      index: 1,
      view: "vswr",
    });
  });

  // Hard case 4: Info's index is pinned.length, so it moves with every pin —
  // and a user parked there must stay parked, not get shunted onto a chart.
  describe("parked on Info", () => {
    it("follows Info to its new index when a pin is appended", () => {
      const after: View[] = [...TWO, "schematic"];
      expect(reconcileCarousel(TWO, after, 2, "antenna")).toEqual({
        index: 3,
        view: "antenna",
      });
    });

    it("follows Info back when some other page is unpinned", () => {
      const after: View[] = ["smith", "vswr", "azimuth"];
      expect(reconcileCarousel(FOUR, after, 4, "azimuth")).toEqual({
        index: 3,
        view: "azimuth",
      });
    });

    it("re-parks `view` on the last page when the parked one is unpinned", () => {
      const after: View[] = ["smith", "antenna", "vswr"];
      expect(reconcileCarousel(FOUR, after, 4, "azimuth")).toEqual({
        index: 3,
        view: "vswr",
      });
    });

    it("keeps Info reachable at the floor of one pin", () => {
      expect(reconcileCarousel(TWO, ["antenna"], 2, "smith")).toEqual({
        index: 1,
        view: "antenna",
      });
    });
  });
});
