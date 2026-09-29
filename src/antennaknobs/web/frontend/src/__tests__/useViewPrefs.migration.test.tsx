// The stored rail preferences of a viewer from before AK#1757 step 5 unit 3,
// which folded the standalone Smith, VSWR and S11 views into the analysis
// chart (`zparam`). Steve's ruling (2026-09-28): a stored pin naming a
// removed view maps onto the chart rather than resetting —
//   smith -> the default frequency-sweep Smith chart,
//   vswr  -> a band-SWR chart on the Swr view,
//   gamma -> the same on the S11 view —
// deterministically, keeping the viewer's other pins where they were, and
// never making two cells of one chart. The payloads below are the shapes
// useViewPrefs actually wrote (sparse: layout, readoutCollapsed and the
// sweep axes only when off their defaults).
//
// Mutation notes (run by hand, 2026-09-28):
//   - the map dropped (a removed id read as unknown and discarded, as before
//     unit 3): 7 of the 11 here fail, every one where a removed id must take
//     a place or name a view. The grid-of-four one survives it, since that
//     grid already held zparam and Smith is the default view anyway: the
//     brief's worst case is benign even unmapped;
//   - the view taken from the LAST removed id instead of the first: the
//     grid-of-four and "collapses repeats" tests fail.
import { describe, it, expect, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { VIEW_PREFS_KEY, useViewPrefs } from "../components/session/useViewPrefs";

beforeEach(() => {
  localStorage.clear();
});

function seed(rec: Record<string, unknown>) {
  localStorage.setItem(VIEW_PREFS_KEY, JSON.stringify(rec));
}
const stored = () => JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "null");

describe("stored pins that name a removed view", () => {
  it("a grid of four (smith, vswr, gamma, zparam) becomes one chart cell, on Smith", () => {
    seed({
      pinned: ["smith", "vswr", "gamma", "zparam"],
      seen: ["antenna", "azimuth", "elevation", "smith", "schematic", "gamma", "vswr", "zparam"],
      layout: "grid",
      sweepAxes: { vswr: { kind: "rho" } },
      swrThreshold: 1.5,
    });
    const { result } = renderHook(() => useViewPrefs());
    // One chart, not four cells of it; nothing else was pinned to keep.
    expect(result.current.pinned).toEqual(["zparam"]);
    expect(result.current.layout).toBe("grid");
    // smith came first, so the chart opens as the Smith view did.
    expect(result.current.chartView).toBe("Smith");
    // The VSWR view's scale and threshold are the chart's seeds now.
    expect(result.current.sweepAxes.vswr).toEqual({ kind: "rho" });
    expect(result.current.swrThreshold).toBe(1.5);
    // The chart is not NEW to someone who had seen the Smith view.
    expect(result.current.newIds.has("zparam")).toBe(false);
  });

  it("the everyday stored set: smith's place is the chart's, on the Smith view", () => {
    seed({ pinned: ["antenna", "azimuth", "elevation", "smith"], seen: ["antenna", "smith"] });
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.pinned).toEqual(["antenna", "azimuth", "elevation", "zparam"]);
    expect(result.current.chartView).toBe("Smith");
    // Seen as the Smith view was: the chart is not NEW.
    expect(result.current.newIds.has("zparam")).toBe(false);
  });

  it("vswr is a chart on the Swr view, gamma one on S11, each at the removed pin's place", () => {
    seed({ pinned: ["antenna", "vswr", "azimuth", "schematic"], seen: ["antenna"] });
    const a = renderHook(() => useViewPrefs());
    expect(a.result.current.pinned).toEqual(["antenna", "zparam", "azimuth", "schematic"]);
    expect(a.result.current.chartView).toBe("Swr");
    a.unmount();

    seed({ pinned: ["gamma", "files"], seen: ["antenna"] });
    const b = renderHook(() => useViewPrefs());
    expect(b.result.current.pinned).toEqual(["zparam", "files"]);
    expect(b.result.current.chartView).toBe("S11");
  });

  it("keeps every other pin, in order, and collapses repeats to the first place", () => {
    seed({
      pinned: ["antenna", "gamma", "azimuth", "smith", "combined", "vswr"],
      seen: ["antenna"],
    });
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.pinned).toEqual(["antenna", "zparam", "azimuth", "combined"]);
    // The first removed id decides the view: gamma.
    expect(result.current.chartView).toBe("S11");
  });

  it("a zparam pin ahead of a removed one keeps its place; the removed one still names the view", () => {
    seed({ pinned: ["zparam", "antenna", "vswr"], seen: ["antenna"] });
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.pinned).toEqual(["zparam", "antenna"]);
    expect(result.current.chartView).toBe("Swr");
  });

  it("no removed id: the chart opens on Smith, and a stored record reads unchanged", () => {
    seed({ pinned: ["antenna", "zparam"], seen: ["antenna"] });
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.pinned).toEqual(["antenna", "zparam"]);
    expect(result.current.chartView).toBe("Smith");
  });

  it("the Smith view's readout choice carries to the chart; VSWR's and S11's are dropped", () => {
    seed({
      pinned: ["smith", "antenna"],
      seen: ["antenna"],
      readoutCollapsed: { smith: true, vswr: true, gamma: false, antenna: true },
    });
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.isReadoutCollapsed("zparam")).toBe(true);
    expect(result.current.isReadoutCollapsed("antenna")).toBe(true);
  });
});

describe("the migrated record, once written", () => {
  it("keeps the chart's view after the old ids are gone, and nothing else is written", () => {
    seed({ pinned: ["antenna", "vswr"], seen: ["antenna", "azimuth"] });
    const first = renderHook(() => useViewPrefs());
    // Any write (here, a layout flip) persists the migrated record.
    act(() => first.result.current.setLayout("grid"));
    const rec = stored();
    expect(rec.pinned).toEqual(["antenna", "zparam"]);
    expect(rec.chartView).toBe("Swr");
    expect(JSON.stringify(rec)).not.toMatch(/"vswr"|"smith"|"gamma"/);
    first.unmount();
    // The next load has no removed id left, and still opens on Swr.
    const second = renderHook(() => useViewPrefs());
    expect(second.result.current.chartView).toBe("Swr");
    expect(second.result.current.pinned).toEqual(["antenna", "zparam"]);
  });

  it("the default Smith view is never written (sparse, like every other field)", () => {
    seed({ pinned: ["antenna", "smith"], seen: ["antenna"] });
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.setLayout("grid"));
    expect(stored()).toEqual({ pinned: ["antenna", "zparam"], seen: ["antenna"], layout: "grid" });
  });

  it("unpinning the chart forgets the migrated view; pinning it again opens on Smith", () => {
    seed({ pinned: ["antenna", "gamma"], seen: ["antenna"] });
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.chartView).toBe("S11");
    act(() => result.current.togglePin("zparam"));
    expect(result.current.chartView).toBe("Smith");
    act(() => result.current.togglePin("zparam"));
    expect(result.current.pinned).toEqual(["antenna", "zparam"]);
    expect(result.current.chartView).toBe("Smith");
    expect(stored().chartView).toBeUndefined();
  });

  it("a garbage chartView reads as Smith without condemning the record", () => {
    seed({ pinned: ["antenna", "zparam"], seen: ["antenna"], chartView: "Rx" });
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.pinned).toEqual(["antenna", "zparam"]);
    expect(result.current.chartView).toBe("Smith");
  });
});
