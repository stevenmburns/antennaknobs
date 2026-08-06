import { useEffect, useRef, useState } from "react";
import { type ExampleDescriptor } from "../../lib/params";
import { type Projection, type View } from "../../lib/view";
import { cycleOrder, gridCells, gridFix, type Layout } from "./useViewPrefs";

// Which output view is on screen and how it is drawn: the two far-field cut
// angles, the selected view + camera projection, the antenna-canvas display
// toggles, the per-example camera reset and the arrow-key view cycler (#642
// seam 5b-3). Called from the component at the cut-angle states' old position,
// which keeps the camera-reset effect exactly where it was; the arrow-key
// listener moves up with it, ahead of the linked-design-freq and mobile
// carousel effects it shares no state with.
export function useViewState({
  currentExample,
  active,
  pinned,
  layout = "rail",
  setLayout,
}: {
  currentExample: ExampleDescriptor | undefined;
  active: boolean;
  // The user's pinned views (useViewPrefs). The arrow keys cycle these plus
  // the active view, not the whole registry — see cycleOrder.
  pinned: View[];
  // Unit 3 (docs/plan-view-rail-scaling.md "Layout modes"): grid mode's
  // arrows cycle the displayed cells only (gridCells), not pinned ∪ active
  // — a ring that walked onto pin #5 would vanish. Chosen as the seam here
  // (rather than a generic `cycle` override list) because the displayed set
  // is already fully determined by `pinned`, which this hook already takes;
  // a second, separately-passed list could disagree with it. Defaults to
  // "rail" so this stays a pure addition — every existing call keeps
  // cycling pinned ∪ active exactly as before.
  layout?: Layout;
  // Only the grid-mode off-grid-peek fix (see the effect below) ever calls
  // this. Omit it and that one branch is simply inert.
  setLayout?: (l: Layout) => void;
}) {
  // Far-field cut angles. The azimuth plot slices the pattern at elevation
  // `azElevDeg`; the elevation plot slices the vertical plane at azimuth
  // bearing `elevAzDeg` (0° = +x). Defaults give the conventional views.
  const [azElevDeg, setAzElevDeg] = useState(15);
  // Default elevation-cut azimuth is 0° (+x) for every geometry: Yagi,
  // moxon, and hexbeam beam +x; the inverted V now runs its arms along
  // ±y so its broadside lobe also peaks at ±x.
  const [elevAzDeg, setElevAzDeg] = useState(0);

  const [view, setView] = useState<View>("antenna");

  // Keeps the grid-mode focus ring on a displayed cell — see gridFix's own
  // comment for the full decision table. `wasGridRef` tracks the layout as
  // of the last time this effect ran, which is how gridFix tells "just
  // entered grid" from "already in grid, view just changed under it" apart;
  // it is updated on every run regardless of which branch (or no branch)
  // fires, so it always reflects the PREVIOUS render's layout.
  const wasGridRef = useRef(layout === "grid");
  useEffect(() => {
    const fix = gridFix(layout, wasGridRef.current, view, pinned);
    wasGridRef.current = layout === "grid";
    if (!fix) return;
    if ("view" in fix) setView(fix.view);
    else setLayout?.("rail");
  }, [layout, view, pinned, setLayout]);

  const [cameraProjection, setCameraProjection] = useState<Projection>("xy");
  // When the user switches antennas, reset the camera to that example's
  // natural starting view (declared on the backend via default_view).
  // Explicit user override sticks until the next geometry change.
  //
  // A deferred (user) design reports default_view === null — its real view is
  // auto-detected and arrives with the first geometry preview (handled where
  // the preview lands, below). Holding the current camera until then avoids
  // snapping to a wrong provisional view and flipping when the preview arrives.
  useEffect(() => {
    if (currentExample?.default_view) {
      // Sets the camera to the new antenna's declared default view on an
      // actual antenna switch; the user's later pick must survive re-renders
      // (#768).
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCameraProjection(currentExample.default_view);
    }
    // Keyed on the name, not currentExample.default_view directly: a value
    // change for the same example (e.g. a data refresh) must not override
    // the user's camera pick — only an actual antenna switch should.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentExample?.name]);

  // Antenna-canvas current visualization is split into two independent
  // toggles: the per-segment current-magnitude heatmap (wire color/width)
  // and the |I| envelope curve overlay. Either or both can be turned off;
  // the wires and feed marker are always drawn.
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [showEnvelope, setShowEnvelope] = useState(false);
  // Wire labels and feed names can crowd dense geometries (and PyNEC returns
  // many more wires than the momwire engines), so let them be toggled. Wire
  // labels default OFF — they're the noisiest, especially on PyNEC.
  const [showWireLabels, setShowWireLabels] = useState(false);
  const [showFeedNames, setShowFeedNames] = useState(true);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      // Don't hijack arrows while a knob (e.g. the cut-angle dials) or a real
      // field is focused — those consume arrows to turn/edit their own value.
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.tagName === "SELECT" ||
          t.isContentEditable ||
          t.classList.contains("knob"))
      ) {
        return;
      }
      // Grid mode cycles the displayed cells only (unit 3's "Keyboard"
      // section); rail mode keeps unit 2's pinned ∪ active cycle untouched.
      const order = layout === "grid" ? gridCells(pinned) : cycleOrder(pinned, view);
      const idx = order.indexOf(view);
      const next =
        e.key === "ArrowDown"
          ? (idx + 1) % order.length
          : (idx - 1 + order.length) % order.length;
      setView(order[next]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, active, pinned, layout]);

  return {
    azElevDeg,
    setAzElevDeg,
    elevAzDeg,
    setElevAzDeg,
    view,
    setView,
    cameraProjection,
    setCameraProjection,
    showHeatmap,
    setShowHeatmap,
    showEnvelope,
    setShowEnvelope,
    showWireLabels,
    setShowWireLabels,
    showFeedNames,
    setShowFeedNames,
  };
}
