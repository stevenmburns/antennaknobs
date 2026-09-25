import { useContext, useEffect, useRef } from "react";
import type { SolveResponse } from "../../lib/api";
import { cutDbiTop, cutDbiToFrac } from "../../lib/refine";
import { ThemeContext } from "../hooks";
import {
  buildFarFieldCaptions,
  cutsRedrawKey,
  traceFor,
  useCutTraces,
} from "./cuts";
import { ghostRgb, plotColors } from "./palette";
import {
  drawDbiRings,
  drawSpoke,
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

    // Azimuth cut: cone above horizon at elevation azElevDeg. With ground
    // off, the conventional setting is 0° (the xy plane). With ground on,
    // 0° is grazing and Fresnel kills the pattern, so something like 15°
    // gives a useful view — the slider lets the user pick.
    const azElevRad = (azElevDeg * Math.PI) / 180;
    const azSinT = Math.cos(azElevRad); // sin(polar θ from +z) = cos(elevation)
    const azCosT = Math.sin(azElevRad); // cos(polar θ) = sin(elevation)
    // Elevation cut: vertical great circle through azimuth bearing elevAzDeg.
    // t=0 lies at +elevAz horizon; t=π/2 is zenith; t=π is at the opposite
    // horizon; t=3π/2 is nadir (below ground, zeroed when ground is on).
    const elevAzRad = (elevAzDeg * Math.PI) / 180;
    const elevAzCos = Math.cos(elevAzRad);
    const elevAzSin = Math.sin(elevAzRad);

    // Slice every trace (live + any pinned ghosts) up front, so the radial
    // scale below can expand to fit the highest-gain lobe on screen.
    const liveTrace = traceFor(cutTraces[0], cut);
    const ghosts = enabledPins.map((p, i) => ({
      colorIdx: p.colorIdx,
      trace: traceFor(cutTraces[i + 1], cut),
    }));

    // Radial axis: absolute directivity in dBi. Origin is a fixed −20 dBi
    // floor. The outer edge is +10 dBi by default, but expands to fit the peak
    // of the highest-gain trace (plus 1 dB headroom) so a high-gain array's
    // lobe renders in full instead of drawing past the edge and clipping — the
    // thumbnails escaped this only because their tiny radius left slack inside
    // the margin. Labeled rings sit at +6/0/−6/−12/−18 (all inside any top).
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
    const dbiTop = cutDbiTop(peaks);
    const dbiToFrac = cutDbiToFrac(dbiTop);
    const geom: PolarGeom = { cx, cy, R, dbiToFrac };
    drawDbiRings(ctx, geom, PC);

    // Axis labels: xy cut uses world x/y around the rim; yz cut shows the
    // azimuth bearing on the horizontal pair and zenith/nadir on vertical.
    ctx.fillStyle = PC.labelDim;
    ctx.font = "10px ui-monospace, monospace";
    const cutLabel =
      cut === "xy"
        ? `az @ ${azElevDeg}° elev (dBi)`
        : `elev @ ${elevAzDeg}° az (dBi)`;
    // A thumbnail too small for both corner labels keeps the peak; the view's
    // name is printed under it anyway.
    if (drawCaptions && size >= 220) ctx.fillText(cutLabel, 6, 14);
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
      ctx.font = "10px ui-monospace, monospace";
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

    // NEC exact-pattern overlay (dashed cyan line) when available. Bilinear
    // interpolation off the (θ, φ) grid; rays below horizon are skipped so
    // the line breaks at the ground rather than wrapping to the origin.
    if (pattern) {
      const N_DIR = 180; // drawing resolution for the interpolated overlay
      const nt = pattern.theta_deg.length;
      const np_ = pattern.phi_deg.length;
      const dTheta = pattern.theta_deg[1] - pattern.theta_deg[0];
      const dPhi = pattern.phi_deg[1] - pattern.phi_deg[0];
      const clip = (g: number) => (g < -100 ? -100 : g);

      ctx.beginPath();
      let started = false;
      for (let pi = 0; pi <= N_DIR; pi++) {
        const t = (2 * Math.PI * pi) / N_DIR;
        const ct = Math.cos(t);
        const st = Math.sin(t);
        const rx = cut === "xy" ? azSinT * ct : elevAzCos * ct;
        const ry = cut === "xy" ? azSinT * st : elevAzSin * ct;
        const rz = cut === "xy" ? azCosT : st;
        if (rz < -1e-9) {
          started = false;
          continue;
        }

        const thetaDeg =
          (Math.acos(Math.max(-1, Math.min(1, rz))) * 180) / Math.PI;
        let phiRad = Math.atan2(ry, rx);
        if (phiRad < 0) phiRad += 2 * Math.PI;
        const phiDeg = (phiRad * 180) / Math.PI;

        const tf = Math.max(0, Math.min(nt - 1, thetaDeg / dTheta));
        const pf = Math.max(0, Math.min(np_ - 1, phiDeg / dPhi));
        const t0 = Math.floor(tf),
          t1 = Math.min(nt - 1, t0 + 1);
        const p0 = Math.floor(pf),
          p1 = Math.min(np_ - 1, p0 + 1);
        const ft = tf - t0,
          fp = pf - p0;
        const g00 = clip(pattern.gain_dbi[t0][p0]);
        const g01 = clip(pattern.gain_dbi[t0][p1]);
        const g10 = clip(pattern.gain_dbi[t1][p0]);
        const g11 = clip(pattern.gain_dbi[t1][p1]);
        const dBi =
          g00 * (1 - ft) * (1 - fp) +
          g01 * (1 - ft) * fp +
          g10 * ft * (1 - fp) +
          g11 * ft * fp;

        const frac = dbiToFrac(dBi);
        const px = cx + Math.cos(t) * frac * R;
        const py = cy - Math.sin(t) * frac * R;
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
        ctx.font = "10px ui-monospace, monospace";
        const necText = "NEC rp_card";
        const necTw = ctx.measureText(necText).width;
        ctx.fillText(necText, size - necTw - 6, size - 6);
      }
    }

    // The corner captions below are the stage overlays' to show (see
    // `onCaptions`); a thumbnail prints them itself.
    if (!drawCaptions) return;

    // Peak dBi annotation (top-right corner).
    const peakDbi = liveTrace.peakDbi;
    ctx.fillStyle = PC.labelStrong;
    ctx.font = "10px ui-monospace, monospace";
    const peakText = `peak ${peakDbi >= 0 ? "+" : ""}${peakDbi.toFixed(1)} dBi`;
    const tw = ctx.measureText(peakText).width;
    ctx.fillText(peakText, size - tw - 6, 14);
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
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillText(
        diffracted ? "with diffraction" : "specular while dragging",
        6,
        size - 6,
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
      ctx.fillText(medText, size - mw - 6, 26);
    }
    // cutTracesKey stands in for the fetched trace contents (see above); the
    // other deps cover everything the draw reads directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    result,
    pattern,
    pinned,
    size,
    cut,
    azElevDeg,
    elevAzDeg,
    fineNorm,
    theme,
    cutTracesKey,
    drawCaptions,
  ]);

  return <canvas ref={canvasRef} className="farfield" />;
}
