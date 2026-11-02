import { useContext, useEffect, useRef } from "react";
import type { SolveResponse } from "../../lib/api";
import { usePatternScale } from "../../lib/patternScale";
import { cutDbiTop, cutDbiToFrac, cutRings } from "../../lib/refine";
import { ThemeContext } from "../hooks";
import {
  buildFarFieldCaptions,
  cutsRedrawKey,
  traceFor,
  useCutTraces,
} from "./cuts";
import { CHART_FONT, fitChartCanvas, useChartScale } from "./chartScale";
import { ghostRgb, plotColors } from "./palette";
import {
  drawDbiRings,
  drawSpoke,
  necCutSamples,
  type PolarGeom,
  strokeTrace as strokePolarTrace,
  type TraceStyle,
} from "./polar";
import type {
  FarFieldCaptions,
  FarFieldCut,
  PatternData,
  PinnedPattern,
} from "./types";

export function FarFieldChart({
  result,
  pattern,
  pinned,
  size,
  cut,
  azElevDeg,
  elevAzDeg,
  fineNorm,
  onCaptions,
}: {
  result: SolveResponse | null;
  pattern: PatternData | null;
  pinned: PinnedPattern[];
  size: number;
  cut: FarFieldCut;
  azElevDeg: number;
  elevAzDeg: number;
  /** Field-side gain norm from the dwell-triggered norm check (the pattern
   *  renormalised by its own integrated radiated power instead of the input
   *  power the live norm uses). When set, that pattern is overlaid dotted —
   *  the norm is a scalar multiplier, so it is the live trace shifted
   *  radially by 10·log10(fineNorm/liveNorm). Overlap ⇒ the solve conserves
   *  power; a visible gap ⇒ the solver's discretisation error. */
  fineNorm?: number | null | undefined;
  /** Given, the chart does NOT print its corner captions and hands them up
   *  instead, for the stage's overlay stacks to show where no control can
   *  cover them. Omitted (a thumbnail), it prints them as always. */
  onCaptions?: ((c: FarFieldCaptions) => void) | undefined;
}) {
  const theme = useContext(ThemeContext); // repaint on theme toggle (dep below)
  const [scale] = usePatternScale(); // ARRL or linear radius (dep below)
  const k = useChartScale(); // the chart scale (./chartScale)
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Server-computed cut traces for the live solve + enabled pins (issue
  // #547): synchronous when the angles match what each solve shipped with,
  // POST /cuts (debounced, cached) after the user drags a cut slider.
  // Disabled pins draw no ghost and don't stretch the radial scale.
  const enabledPins = pinned.filter((p) => p.enabled);
  const cutTraces = useCutTraces(
    cut,
    [result, ...enabledPins.map((p) => p.result)],
    azElevDeg,
    elevAzDeg,
  );
  // Draw-effect dep: see `cutsRedrawKey`. The solve identities and the dial
  // angles are already deps of their own; this covers what can change at
  // unchanged angles.
  const cutTracesKey = cutsRedrawKey(cutTraces);

  // The captions, from the same trace the draw uses. Serialised so the effect
  // below fires when a caption CHANGES, not on every render.
  const captions = buildFarFieldCaptions(
    cut,
    cutTraces[0],
    result,
    azElevDeg,
    elevAzDeg,
    !!pattern,
  );
  const captionsJson = JSON.stringify(captions);
  useEffect(() => {
    onCaptions?.(JSON.parse(captionsJson) as FarFieldCaptions);
  }, [captionsJson, onCaptions]);
  const drawCaptions = !onCaptions;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const sz = fitChartCanvas(canvas, ctx, size, k);

    const PC = plotColors();

    ctx.fillStyle = PC.bg;
    ctx.fillRect(0, 0, sz, sz);

    const cx = sz / 2;
    const cy = sz / 2;
    const R = sz / 2 - 14;

    // Azimuth cut: cone above horizon at elevation azElevDeg. With ground
    // off, the conventional setting is 0° (the xy plane). With ground on,
    // 0° is grazing and Fresnel kills the pattern, so something like 15°
    // gives a useful view — the slider lets the user pick.
    // Elevation cut: vertical great circle through azimuth bearing elevAzDeg.
    // t=0 lies at +elevAz horizon; t=π/2 is zenith; t=π is at the opposite
    // horizon; t=3π/2 is nadir (below ground, zeroed when ground is on).
    // (The NEC overlay's own geometry is polar.ts's necCutSamples.)

    // Slice every trace (live + any pinned ghosts) up front, so the radial
    // scale below can expand to fit the highest-gain lobe on screen.
    const liveTrace = traceFor(cutTraces[0], cut);
    const ghosts = enabledPins.map((p, i) => ({
      colorIdx: p.colorIdx,
      trace: traceFor(cutTraces[i + 1], cut),
    }));

    // Radial axis (lib/refine.ts, the scale from lib/patternScale.ts). Its top
    // comes from the peak of every trace DRAWN: the live lobe, the pins, the
    // norm-check overlay when shown and the NEC overlay (sampled below).
    //   arrl:   the top IS that peak, the rim of r = R_max·0.89^(−dB/3), with
    //           rings 3/6/10/20/30 dB down and the rim labelled in dBi.
    //   linear: dBi from a fixed −20 dBi floor to 1 dB above the peak (never
    //           under 11 dBi), rings at +6/0/−6/−12/−18 dBi.
    const peaks: number[] = [];
    if (liveTrace) peaks.push(liveTrace.peakDbi);
    for (const gh of ghosts) if (gh.trace) peaks.push(gh.trace.peakDbi);
    // Norm-check overlay: the norm scales the whole pattern, so switching to
    // the field-side norm shifts every dBi by this constant. null when the
    // check is off or the live result carries no norm to compare against.
    const liveNorm = result?.directivity_norm;
    const gridDeltaDb =
      fineNorm && fineNorm > 0 && liveNorm && liveNorm > 0
        ? 10 * Math.log10(fineNorm / liveNorm)
        : null;
    // Let the radial scale grow to fit the shifted overlay when it lands higher.
    if (liveTrace && gridDeltaDb != null)
      peaks.push(liveTrace.peakDbi + gridDeltaDb);
    // Clamp to [0, 1]: a lobe at/above the top sits on the rim instead of
    // drawing past R and clipping against the canvas edge. The map itself
    // lives in lib/refine.ts so the refinement planner (issue #744) judges
    // curvature against the exact geometry drawn here.
    // NEC exact-pattern overlay samples along this cut, taken BEFORE the
    // radial scale so its peak counts: on the ARRL scale the rim is the
    // highest peak drawn, and an uncounted NEC lobe peaking above the live
    // one would be flattened onto the rim, hiding the difference the overlay
    // is there to show. Bilinear interpolation off the (θ, φ) grid; null
    // marks a ray below the horizon.
    const necSamples = pattern
      ? necCutSamples(pattern, cut, azElevDeg, elevAzDeg)
      : null;
    if (necSamples)
      for (const smp of necSamples) if (smp !== null) peaks.push(smp.dbi);
    const dbiTop = cutDbiTop(peaks, scale);
    const dbiToFrac = cutDbiToFrac(dbiTop, scale);
    const geom: PolarGeom = {
      cx,
      cy,
      R,
      dbiToFrac,
      rings: cutRings(dbiTop, scale),
    };
    drawDbiRings(ctx, geom, PC);

    // Axis labels: xy cut uses world x/y around the rim; yz cut shows the
    // azimuth bearing on the horizontal pair and zenith/nadir on vertical.
    ctx.fillStyle = PC.labelDim;
    ctx.font = CHART_FONT.label;
    const cutLabel =
      cut === "xy"
        ? `az @ ${azElevDeg}° elev (dBi)`
        : `elev @ ${elevAzDeg}° az (dBi)`;
    // A thumbnail too small for both corner labels keeps the peak; the view's
    // name is printed under it anyway.
    if (drawCaptions && sz >= 220) ctx.fillText(cutLabel, 6, 14);
    ctx.fillStyle = PC.label;
    // A thumbnail (the chart that prints its own captions) has no room for
    // the axis labels: they collide with its peak and cut captions, and the
    // view's name under it already says which plot it is.
    if (!drawCaptions) {
      if (cut === "xy") {
        ctx.fillText("+x", cx + R - 14, cy + 11);
        ctx.fillText("−x", cx - R + 2, cy + 11);
        ctx.fillText("+y", cx - 8, cy - R + 12);
        ctx.fillText("−y", cx - 7, cy + R - 2);
      } else {
        ctx.fillText("zen", cx - 9, cy - R + 12);
        ctx.fillText("nad", cx - 9, cy + R - 2);
      }
    }

    // Cross-reference: a single dashed spoke showing where the *other* cut
    // slices this plot. The opposite side is implied by symmetry.
    drawSpoke(
      ctx,
      geom,
      cut === "xy"
        ? (elevAzDeg * Math.PI) / 180 // azimuth plot: elevation cut's bearing
        : (azElevDeg * Math.PI) / 180, // elevation plot: azimuth cut's elevation
      PC.spoke,
    );

    if (!result) return;

    // Terrain orientation marker: the terrain's characteristic bearing
    // (water / downhill / cliff side), so orientation reads off the chart
    // instead of being inferred from lobes — which can legitimately peak
    // toward the OTHER side (a hillside's mid-angle lobes point uphill;
    // downhill only wins below the first-lobe band).
    const terrainMarker = result.ground_terrain?.marker;
    if (terrainMarker) {
      ctx.font = CHART_FONT.label;
      if (cut === "xy") {
        // Inward tick + label at the bearing; dimmer label opposite.
        const a = (terrainMarker.bearing_deg * Math.PI) / 180;
        const ca = Math.cos(a);
        const sa = Math.sin(a);
        ctx.strokeStyle = PC.labelStrong;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(cx + ca * R, cy - sa * R);
        ctx.lineTo(cx + ca * (R - 8), cy - sa * (R - 8));
        ctx.stroke();
        const place = (label: string, dirx: number, diry: number) => {
          const tw = ctx.measureText(label).width;
          // Sit the label just inside the rim along the bearing, nudged
          // toward the centre so it doesn't collide with the axis labels.
          ctx.fillText(
            label,
            cx + dirx * (R - 24) - tw / 2,
            cy - diry * (R - 24) + 4,
          );
        };
        ctx.fillStyle = PC.labelStrong;
        place(terrainMarker.label, ca, sa);
        ctx.fillStyle = PC.labelDim;
        place(terrainMarker.opposite, -ca, -sa);
      } else {
        // Elevation cut: label which terrain side each horizon points into
        // (the right rim is the cut bearing elevAzDeg).
        const rel =
          ((((elevAzDeg - terrainMarker.bearing_deg) % 360) + 540) % 360) - 180;
        const rightLabel =
          Math.abs(rel) <= 90 ? terrainMarker.label : terrainMarker.opposite;
        const leftLabel =
          Math.abs(rel) <= 90 ? terrainMarker.opposite : terrainMarker.label;
        ctx.fillStyle = PC.labelStrong;
        ctx.fillText(
          rightLabel,
          cx + R - ctx.measureText(rightLabel).width - 2,
          cy - 5,
        );
        ctx.fillStyle = PC.labelDim;
        ctx.fillText(leftLabel, cx - R + 2, cy - 5);
      }
    }

    // Draw one dBi trace around the polar cut. Sample i sits at t = 2π·i/n —
    // the server cuts' default parameterisation — unless the trace carries
    // explicit per-sample angles, which adaptive refinement (issue #744)
    // needs because a densified cut is no longer uniform and the index no
    // longer determines the angle. The live lobe closes + fills; pinned
    // ghosts are an open dashed stroke so the live trace reads on top.
    const strokeTrace = (dbi: number[], o: TraceStyle) =>
      strokePolarTrace(ctx, geom, dbi, o);

    // Pinned ghosts first (dimmed, dashed), so the live lobe sits on top. Each
    // shares the adaptive radial scale computed above, so it tracks the cut and
    // angle sliders just like the live trace.
    for (const gh of ghosts) {
      if (!gh.trace) continue;
      strokeTrace(gh.trace.dbi, {
        stroke: `rgba(${ghostRgb(gh.colorIdx)}, 0.8)`,
        width: 1,
        dash: [5, 3],
        anglesDeg: gh.trace.anglesDeg,
      });
    }

    // Live lobe (filled).
    if (!liveTrace) return;
    strokeTrace(liveTrace.dbi, {
      stroke: `rgba(${PC.lobeRgb}, 0.9)`,
      fill: `rgba(${PC.lobeRgb}, 0.12)`,
      width: 1.5,
      anglesDeg: liveTrace.anglesDeg,
    });

    // Fine-grid norm overlay (dotted, same lobe hue): the live trace shifted
    // radially by the constant dB offset. Sits exactly on the solid lobe when
    // the adaptive grid was fine enough; a visible gap is the grid error. Drawn
    // open (no fill) so the solid lobe still reads underneath.
    if (gridDeltaDb != null) {
      strokeTrace(
        liveTrace.dbi.map((d) => d + gridDeltaDb),
        {
          stroke: `rgba(${PC.lobeRgb}, 0.85)`,
          width: 1,
          dash: [2, 2],
          anglesDeg: liveTrace.anglesDeg,
        },
      );
    }

    // NEC exact-pattern overlay (dashed cyan line) when available, drawn from
    // the samples taken above (`necSamples`); a null sample is a ray below
    // the horizon, where the line breaks rather than wrapping to the origin.
    if (pattern && necSamples) {
      ctx.beginPath();
      let started = false;
      for (const smp of necSamples) {
        if (smp === null) {
          started = false;
          continue;
        }
        const frac = dbiToFrac(smp.dbi);
        const px = cx + Math.cos(smp.t) * frac * R;
        const py = cy - Math.sin(smp.t) * frac * R;
        if (!started) {
          ctx.moveTo(px, py);
          started = true;
        } else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = `rgba(${PC.necRgb}, 0.85)`;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Legend swatch + label, bottom-right.
      if (drawCaptions) {
        ctx.fillStyle = `rgba(${PC.necRgb}, 0.9)`;
        ctx.font = CHART_FONT.label;
        const necText = "NEC rp_card";
        const necTw = ctx.measureText(necText).width;
        ctx.fillText(necText, sz - necTw - 6, sz - 6);
      }
    }

    // The corner captions below are the stage overlays' to show (see
    // `onCaptions`); a thumbnail prints them itself.
    if (!drawCaptions) return;

    // Peak dBi annotation (top-right corner).
    const peakDbi = liveTrace.peakDbi;
    ctx.fillStyle = PC.labelStrong;
    ctx.font = CHART_FONT.readout;
    const peakText = `peak ${peakDbi >= 0 ? "+" : ""}${peakDbi.toFixed(1)} dBi`;
    const tw = ctx.measureText(peakText).width;
    ctx.fillText(peakText, sz - tw - 6, 14);
    // Which FIELD this trace is, over a faceted terrain (issue #1373). Always
    // shown when there are two to choose between, never when there is one: a
    // label that appears only while the two "differ" would be a label the user
    // cannot learn, since its absence would mean both "flat ground" and "the
    // edges happen not to matter here".
    //
    // Read off the TRACE, not off the request or the ground model. During a
    // drag this is the specular field because that is what was composed; a
    // moment after the knob settles the same corner says the other thing, and
    // the only way for it to be wrong is for the server to have mislabelled
    // its own output.
    if (cutTraces[0] && result?.ground_terrain) {
      const diffracted = cutTraces[0].diffraction;
      ctx.fillStyle = diffracted ? PC.labelStrong : PC.labelDim;
      ctx.font = CHART_FONT.label;
      ctx.fillText(
        diffracted ? "with diffraction" : "specular while dragging",
        6,
        sz - 6,
      );
    }
    const frac = result?.in_medium_moment_fraction;
    if (frac != null) {
      // Issue #1341: the share of current moment below the ground plane.
      // Those currents are in the lobe, placed through the interface — the
      // label says how much of the antenna is down there, not what is
      // missing from the pattern.
      ctx.fillStyle = PC.labelDim;
      const medText = `${Math.round(frac * 100)}% of current below ground`;
      const mw = ctx.measureText(medText).width;
      ctx.fillText(medText, sz - mw - 6, 26);
    }
    // cutTracesKey stands in for the fetched trace contents (see above); the
    // other deps cover everything the draw reads directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    result,
    pattern,
    pinned,
    size,
    k,
    cut,
    azElevDeg,
    elevAzDeg,
    fineNorm,
    theme,
    scale,
    cutTracesKey,
    drawCaptions,
  ]);

  return <canvas ref={canvasRef} className="farfield" />;
}
