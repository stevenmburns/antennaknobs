import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";
import { ZPARAM_PLOT_MARGIN, zparamChartSize } from "../../lib/zparamLayout";
import { useChartScale } from "../charts/chartScale";

// The Z-vs-parameter view's desktop stage (AC6LA, QRZ #166): the sweep bar
// pinned to the chart's upper-left and the solve readout to its lower-left,
// at every window size and browser zoom.
//
// They used to float at the SLIDE's corners (top-right and bottom-left)
// while the chart was a centred square of at most 720 px, so where they fell
// on the chart depended on the window: off to the sides of a big one, and on
// a small or zoomed-in one the bar covered the R Ω / X Ω titles and the
// readout the R axis's and the x axis's labels. Now both live INSIDE the
// chart's own box:
//
//   - the bar sits in the page flow above the plot, its left edge on the
//     chart's, and the chart gives up exactly the bar's measured height (not
//     a guess), so the bar never covers the plot. The bar wraps at the BOX's
//     width, not the chart's: were its height a function of the chart's
//     size, a short box would spiral (a smaller chart wraps the bar taller,
//     which shrinks the chart again) down to the 160 px floor. A bar wider
//     than the chart simply runs on past its right edge;
//   - the readout is absolute in the plot's box, at its lower-left corner
//     just inside the axes (the chart's own margins, in CSS px, so zoom moves
//     nothing), so it never covers an axis label. The sweep's advisory and
//     refusal stack above it there.
//
// Measured from the element boxes, never from viewport offsets.

function useBoxSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [wh, setWh] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      setWh((cur) => (cur.w === r.width && cur.h === r.height ? cur : { w: r.width, h: r.height }));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, ...wh };
}

export function ZParamStage({
  size,
  fallbackHead,
  header,
  chart,
  overlays,
  readout,
}: {
  /** The square the stage would give any chart (useSlideSize / the grid's
   *  cell size): the width bound. */
  size: number;
  /** What the chart gives up before the bar is measured. */
  fallbackHead: number;
  header: ReactNode;
  chart: (size: number) => ReactNode;
  /** The sweep's advisory and refusal: over the plot, above the readout. */
  overlays?: ReactNode;
  /** The floating solve readout, when this view is the rail's primary. */
  readout?: ReactNode;
}) {
  const { ref: boxRef, w: boxW, h: boxH } = useBoxSize<HTMLDivElement>();
  const { ref: headRef, h: headH } = useBoxSize<HTMLDivElement>();
  const s = zparamChartSize(size, boxH, headH, fallbackHead);
  // The canvas's margins on screen: logical px times the chart scale
  // (../charts/chartScale), which the chart draws them at.
  const k = useChartScale();
  const M = ZPARAM_PLOT_MARGIN;
  const plotVars = {
    "--zparam-plot-l": `${M.l * k}px`,
    "--zparam-plot-r": `${M.r * k}px`,
    "--zparam-plot-t": `${M.t * k}px`,
    "--zparam-plot-b": `${M.b * k}px`,
  } as CSSProperties;
  return (
    <div className="zparam-fit" ref={boxRef}>
      <div className="zparam-area" data-chart-size={s}>
        <div
          className="zparam-head"
          ref={headRef}
          style={boxW > 0 ? { maxWidth: Math.max(160, boxW - 16) } : undefined}
        >
          {header}
        </div>
        <div className="zparam-plot" style={plotVars}>
          {chart(s)}
          {overlays}
          {readout}
        </div>
      </div>
    </div>
  );
}
