import { useContext, useEffect, useRef } from "react";
import type { SolveResponse } from "../../lib/api";
import { cutDbiToFrac } from "../../lib/refine";
import type { CombinedFill } from "../../lib/view";
import { ThemeContext } from "../hooks";
import {
  combinedDbiTop,
  combinedTraces,
  effectiveFocus,
  LIVE_ENTITY,
} from "./combined";
import { buildFarFieldCaptions, cutsRedrawKey, useCutTraces } from "./cuts";
import { plotColors } from "./palette";
import { drawDbiRings, drawSpoke, type PolarGeom, strokeTrace } from "./polar";
import type {
  FarFieldCaptions,
  FarFieldCut,
  PatternData,
  PinnedPattern,
} from "./types";

// The combined Az + El view (AK#1730): both principal cuts overlaid on one
// polar plot, EZNEC's combined 2D plot.
//
// Both cuts share the one polar parameter the server already uses, so neither
// needs remapping: the azimuth trace is the full circle at its angle (0° = +x
// on the right), and the elevation trace is t = elevation angle (0° = the cut
// bearing's horizon on the right, 90° = zenith at the top, 180° = the opposite
// horizon). The two right-hand rims therefore mean different directions, which
// is the convention of the plot this copies.
//
// Colour = cut: azimuth in the live lobe's hue, elevation in its own token.
// Pinned traces keep their cut's hue, dashed, thinner and dimmer; which pin
// is which comes from the legend, which can focus one entity and dim the rest.
// The trace model (what is drawn, and on what scale) is in ./combined.

export function CombinedPatternChart({
  result,
  pattern,
  pinned,
  size,
  azElevDeg,
  elevAzDeg,
  fill,
  focus,
  onCaptions,
}: {
  result: SolveResponse | null;
  /** Only to report `necOverlay` the way the one-cut charts do, so the two
   *  kinds of chart on one grid hand up identical captions. Not drawn. */
  pattern: PatternData | null;
  pinned: PinnedPattern[];
  size: number;
  azElevDeg: number;
  elevAzDeg: number;
  fill: CombinedFill;
  /** LIVE_ENTITY or a pin id: that entity's traces draw at full strength and
   *  everything else dims. Null draws everything normally. */
  focus: string | null;
  /** Given (the stage), the chart hands its captions up, one per cut, and
   *  prints its rim labels. Omitted (a thumbnail), it draws the bare plot. */
  onCaptions?: ((c: FarFieldCaptions) => void) | undefined;
}) {
  const theme = useContext(ThemeContext);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const enabledPins = pinned.filter((p) => p.enabled);
  const cutTraces = useCutTraces(
    "both",
    [result, ...enabledPins.map((p) => p.result)],
    azElevDeg,
    elevAzDeg,
  );
  const cutTracesKey = cutsRedrawKey(cutTraces);
  const focused = effectiveFocus(focus, enabledPins);

  const captionsJson = JSON.stringify(
    (["xy", "yz"] as const).map((cut) =>
      buildFarFieldCaptions(
        cut,
        cutTraces[0],
        result,
        azElevDeg,
        elevAzDeg,
        !!pattern,
      ),
    ),
  );
  useEffect(() => {
    if (!onCaptions) return;
    for (const c of JSON.parse(captionsJson) as FarFieldCaptions[]) onCaptions(c);
  }, [captionsJson, onCaptions]);
  const stage = !!onCaptions;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(size * dpr);
    canvas.height = Math.floor(size * dpr);
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const PC = plotColors();
    ctx.fillStyle = PC.bg;
    ctx.fillRect(0, 0, size, size);

    const cx = size / 2;
    const cy = size / 2;
    const R = size / 2 - 14;

    const traces = combinedTraces(cutTraces, enabledPins);
    const geom: PolarGeom = {
      cx,
      cy,
      R,
      dbiToFrac: cutDbiToFrac(combinedDbiTop(traces)),
    };
    drawDbiRings(ctx, geom, PC);

    // Faint 30° spokes: with two cuts on one plot the angle is read off the
    // plot far more than on a single cut, where the peak caption says it.
    ctx.strokeStyle = PC.axisFaint;
    ctx.lineWidth = 0.6;
    for (let a = 30; a < 360; a += 30) {
      if (a % 90 === 0) continue; // the axes are already drawn
      const t = (a * Math.PI) / 180;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(t) * R, cy - Math.sin(t) * R);
      ctx.stroke();
    }

    // Rim labels: the angles both cuts share (azimuth from +x, elevation from
    // the cut bearing's horizon). A thumbnail has no room for them.
    if (stage) {
      ctx.fillStyle = PC.label;
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillText("0°", cx + R - 16, cy + 12);
      ctx.fillText("90°", cx + 3, cy - R + 11);
      ctx.fillText("180°", cx - R + 2, cy + 12);
    }

    // The cut-angle spoke: where the azimuth cut sits on the elevation trace.
    drawSpoke(ctx, geom, (azElevDeg * Math.PI) / 180, PC.spoke);

    if (!result) return;

    const elevRgb = PC.elevRgb;
    const rgbOf = (cut: FarFieldCut) => (cut === "xy" ? PC.lobeRgb : elevRgb);

    // Terrain: which side each HORIZON of the elevation trace looks into, in
    // the elevation hue, since it is the elevation trace's horizons it names
    // (the azimuth trace's rim is bearings, and 0° there is +x).
    const terrainMarker = result.ground_terrain?.marker;
    if (terrainMarker && stage) {
      const rel =
        ((((elevAzDeg - terrainMarker.bearing_deg) % 360) + 540) % 360) - 180;
      const toward = Math.abs(rel) <= 90;
      const rightLabel = toward ? terrainMarker.label : terrainMarker.opposite;
      const leftLabel = toward ? terrainMarker.opposite : terrainMarker.label;
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillStyle = `rgba(${elevRgb}, 0.95)`;
      ctx.fillText(
        rightLabel,
        cx + R - ctx.measureText(rightLabel).width - 2,
        cy - 5,
      );
      ctx.fillStyle = `rgba(${elevRgb}, 0.6)`;
      ctx.fillText(leftLabel, cx - R + 2, cy - 5);
    }

    // With a focus, the focused entity draws at full strength (a focused pin
    // at the live pair's weight, so it can be traced), the rest at a ghost.
    const dimmed = (entity: string) => focused != null && entity !== focused;
    const liveElev = traces.find(
      (t) => t.entity === LIVE_ENTITY && t.cut === "yz",
    );
    // The elevation half-lobe's fill goes down first, under every stroke.
    // Below the horizon an over-ground trace sits on the floor, so filling the
    // closed trace fills the half-lobe above it.
    if (fill === "elevation" && liveElev) {
      strokeTrace(ctx, geom, liveElev.dbi, {
        stroke: null,
        fill: `rgba(${elevRgb}, ${dimmed(LIVE_ENTITY) ? 0.05 : 0.14})`,
        width: 0,
        anglesDeg: liveElev.anglesDeg,
      });
    }
    for (const t of traces) {
      const strong = focused != null && t.entity === focused;
      const alpha = dimmed(t.entity) ? 0.18 : t.pinned && !strong ? 0.6 : 0.95;
      strokeTrace(ctx, geom, t.dbi, {
        stroke: `rgba(${rgbOf(t.cut)}, ${alpha})`,
        width: t.pinned ? (strong ? 1.5 : 1) : 1.5,
        ...(t.pinned ? { dash: [5, 3] } : {}),
        anglesDeg: t.anglesDeg,
      });
    }
    // cutTracesKey stands in for the fetched trace contents (FarFieldChart's
    // draw effect has the same note).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    result,
    pinned,
    size,
    azElevDeg,
    elevAzDeg,
    fill,
    focused,
    theme,
    cutTracesKey,
    stage,
  ]);

  // data-fill surfaces the one prop that leaves no other DOM trace, for the
  // registry's dispatch test.
  return <canvas ref={canvasRef} className="farfield" data-fill={fill} />;
}
