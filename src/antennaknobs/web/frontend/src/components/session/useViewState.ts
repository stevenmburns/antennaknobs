import { useEffect, useState } from "react";
import { type ExampleDescriptor } from "../../lib/params";
import { VIEWS, type Projection, type View } from "../../lib/view";

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
}: {
  currentExample: ExampleDescriptor | undefined;
  active: boolean;
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
      setCameraProjection(currentExample.default_view);
    }
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
      const idx = VIEWS.findIndex((v) => v.id === view);
      const next = e.key === "ArrowDown" ? (idx + 1) % VIEWS.length : (idx - 1 + VIEWS.length) % VIEWS.length;
      setView(VIEWS[next].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, active]);

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
