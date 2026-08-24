import { useContext, useEffect, useRef } from "react";
import { reflectionCoefficient } from "../../lib/format";
import type { ConvergeData, FeedEntry, MeasuredData, SweepData } from "../../lib/api";
import { ThemeContext } from "../hooks";
import { feedColor, feedSweepColor, plotColors } from "./palette";

export function SmithChart({
  r,
  x,
  z0,
  size,
  sweep,
  converge,
  measured,
  measFreqMhz,
  running,
  convergeRunning,
  feeds,
  multiFeed,
  connectSweep = false,
  trial = false,
  trialFeeds,
  trialWorstFeed,
}: {
  r: number;
  x: number;
  z0: number;
  size: number;
  sweep: SweepData | null;
  converge: ConvergeData | null;
  /** Uploaded VNA measurement drawn against the modeled locus (issue #595). */
  measured: MeasuredData | null;
  measFreqMhz: number;
  running: boolean;
  convergeRunning: boolean;
  /** Multi-feed geometries pass the per-feed Z list from the latest
   *  solve so the chart can also render N centre dots, one per port. */
  feeds?: FeedEntry[] | undefined;
  /** From the example descriptor's `multi_feed` flag — drives the
   *  per-feed summary rows. Decoupled from feeds[].length so the chart
   *  reflects antenna type rather than guessing from response shape. */
  multiFeed: boolean;
  /** Draw the sweep trail as a CONNECTED locus instead of a point cloud.
   *  On when adaptive resolution (issue #744) is on: the merged sweep is
   *  sorted by frequency and refinement has smoothed the display-space
   *  curvature, so a polyline finally reads as the curve it is — the
   *  original objection to lines here ("sparse samples make a piecewise
   *  polyline read as artificial kinks") is exactly what refinement
   *  removes. Off (refinement disabled) keeps the honest dot cloud. */
  connectSweep?: boolean;
  /** `r`/`x` are a PROPOSED point (a streamed optimizer eval, #773), not a
   *  settled solve: draw a hollow ring and ignore `feeds`, which still holds
   *  the previous solve's per-port dots. */
  trial?: boolean;
  /** The proposed point's OWN per-feed table (#789), when the proposer has
   *  one. Distinct from `feeds` because they disagree during a run: these are
   *  this eval's impedances, `feeds` is the last settled solve's. Absent on a
   *  single-feed design, where `r`/`x` already are the whole story. */
  trialFeeds?: Array<{ z_re: number; z_im: number }> | undefined;
  /** Which entry of `trialFeeds` the minimax objective is currently chasing
   *  (#785). That ring is drawn bright and the rest dimmed — without it eight
   *  equal rings say "something is moving" but not what is being optimised. */
  trialWorstFeed?: number | undefined;
}) {
  const theme = useContext(ThemeContext); // repaint on theme toggle (dep below)
  const canvasRef = useRef<HTMLCanvasElement>(null);

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

    const cx = size / 2;
    const cy = size / 2;
    const R = size / 2 - 10;

    ctx.fillStyle = PC.bg;
    ctx.fillRect(0, 0, size, size);

    // Constant-r circles in the Γ plane.
    // Each maps to a circle: center = (r/(r+1), 0), radius = 1/(r+1).
    const rCircles: { r: number; label?: string }[] = [
      { r: 0.2 },
      { r: 0.5, label: "0.5" },
      { r: 1, label: "1" },
      { r: 2, label: "2" },
      { r: 5 },
    ];
    ctx.strokeStyle = PC.grid;
    ctx.lineWidth = 0.6;
    for (const { r: rn } of rCircles) {
      const cxN = rn / (rn + 1);
      const radN = 1 / (rn + 1);
      ctx.beginPath();
      ctx.arc(cx + cxN * R, cy, radN * R, 0, 2 * Math.PI);
      ctx.stroke();
    }

    // Constant-x arcs: center = (1, 1/x), radius = 1/|x|. Clip to unit disk.
    const xArcs = [0.2, 0.5, 1, 2, 5];
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, 2 * Math.PI);
    ctx.clip();
    for (const xn of xArcs) {
      const arcCx = cx + R;
      const rad = (1 / xn) * R;
      // Inductive (X > 0)
      ctx.beginPath();
      ctx.arc(arcCx, cy - (1 / xn) * R, rad, 0, 2 * Math.PI);
      ctx.stroke();
      // Capacitive (X < 0)
      ctx.beginPath();
      ctx.arc(arcCx, cy + (1 / xn) * R, rad, 0, 2 * Math.PI);
      ctx.stroke();
    }
    ctx.restore();

    // Real axis
    ctx.strokeStyle = PC.axis;
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.moveTo(cx - R, cy);
    ctx.lineTo(cx + R, cy);
    ctx.stroke();

    // Outer boundary (|Γ| = 1)
    ctx.strokeStyle = PC.axis;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, 2 * Math.PI);
    ctx.stroke();

    // Z0 label at center
    ctx.fillStyle = PC.labelDim;
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText(`Z₀ = ${z0}`, 6, 14);

    // Reactance sign labels.
    ctx.fillStyle = PC.labelDim;
    ctx.fillText("+jX", cx + R - 24, cy - R + 14);
    ctx.fillText("−jX", cx + R - 24, cy + R - 4);

    // Sweep locus: one colored trajectory per feed (or just the primary
    // for single-feed geometries). Multi-feed geometries (bowtie) ship
    // per-feed Z arrays via sweep.feeds_z_re / feeds_z_im; when present
    // we render one color-distinct trajectory per port instead of the
    // single legacy blue locus. No connecting line — sparse samples
    // make a piecewise polyline read as artificial kinks.
    if (sweep && sweep.freqs_mhz.length > 1) {
      const hasMulti =
        !!sweep.feeds_z_re &&
        !!sweep.feeds_z_im &&
        sweep.feeds_z_re.length === sweep.freqs_mhz.length &&
        sweep.feeds_z_re[0].length > 1;
      const nFeeds = hasMulti ? sweep.feeds_z_re![0].length : 1;

      // Z accessor per (feed index, sample index). Single-feed falls
      // back to the top-level z_re/z_im (same as before this change).
      const zAt = (fi: number, i: number) =>
        hasMulti
          ? { re: sweep.feeds_z_re![i][fi], im: sweep.feeds_z_im![i][fi] }
          : { re: sweep.z_re[i], im: sweep.z_im[i] };

      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, 2 * Math.PI);
      ctx.clip();
      for (let fi = 0; fi < nFeeds; fi++) {
        // Darkened color so the sweep trail reads underneath the bright
        // current-Z primary marker (drawn later, full color). Same
        // convention for single- and multi-feed so the chart's visual
        // grammar is uniform.
        if (connectSweep) {
          // Connected locus (adaptive resolution on): freqs_mhz arrives
          // sorted (mergeSweepPoints re-sorts on every refinement round),
          // so drawing in array order IS drawing in frequency order — no
          // chord ever jumps across the chart.
          ctx.strokeStyle = feedSweepColor(fi);
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          for (let i = 0; i < sweep.freqs_mhz.length; i++) {
            const z = zAt(fi, i);
            const g = reflectionCoefficient(z.re, z.im, z0);
            const px = cx + g.gRe * R;
            const py = cy - g.gIm * R;
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          }
          ctx.stroke();
        } else {
          ctx.fillStyle = feedSweepColor(fi);
          for (let i = 0; i < sweep.freqs_mhz.length; i++) {
            const z = zAt(fi, i);
            const g = reflectionCoefficient(z.re, z.im, z0);
            const px = cx + g.gRe * R;
            const py = cy - g.gIm * R;
            ctx.beginPath();
            ctx.arc(px, py, 1.5, 0, 2 * Math.PI);
            ctx.fill();
          }
        }
      }
      ctx.restore();

      // Endpoint markers per feed (low-freq filled, high-freq hollow) —
      // also drawn in the darkened sweep color so they stay part of the
      // trail and don't compete with the bright current-Z marker.
      const drawEndpoint = (fi: number, idx: number, filled: boolean) => {
        const z = zAt(fi, idx);
        const g = reflectionCoefficient(z.re, z.im, z0);
        const px = cx + g.gRe * R;
        const py = cy - g.gIm * R;
        const col = feedSweepColor(fi);
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = col;
        ctx.fillStyle = filled ? col : `rgba(${PC.bgRgb}, 0.95)`;
        ctx.beginPath();
        ctx.arc(px, py, 3, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
      };
      for (let fi = 0; fi < nFeeds; fi++) {
        drawEndpoint(fi, 0, true);
        drawEndpoint(fi, sweep.freqs_mhz.length - 1, false);
      }

      // Frequency anchor (issue #719): measFreqMhz reached the chart only as
      // a redraw dependency — the Γ-plane had nothing that actually pointed
      // at "this frequency." Ring the sweep-trail point nearest measFreqMhz,
      // found by a plain min-|Δf| scan rather than assuming freqs_mhz is
      // sorted or uniformly spaced (it isn't, for a log sweep) — and with no
      // special-casing for measFreqMhz outside the swept band: the endpoint
      // simply wins that comparison, which is the correct answer there too.
      // Drawn in the neutral "ink" color (PC.labelStrong) rather than a feed
      // color or the violet spoke/measured family, since it needs to read as
      // "pointing at the trail" and not be mistaken for another feed or the
      // measured-overlay locus. Hollow (stroke only, no fill) and larger
      // than both the endpoint dots (r=3) and the bright current-Z marker
      // (r=4, drawn later/on top) so it reads as a ring around a point
      // rather than a competing dot.
      let nearestIdx = 0;
      let nearestDiff = Math.abs(sweep.freqs_mhz[0] - measFreqMhz);
      for (let i = 1; i < sweep.freqs_mhz.length; i++) {
        const diff = Math.abs(sweep.freqs_mhz[i] - measFreqMhz);
        if (diff < nearestDiff) {
          nearestDiff = diff;
          nearestIdx = i;
        }
      }
      ctx.strokeStyle = PC.labelStrong;
      ctx.lineWidth = 1.4;
      for (let fi = 0; fi < nFeeds; fi++) {
        const z = zAt(fi, nearestIdx);
        const g = reflectionCoefficient(z.re, z.im, z0);
        const px = cx + g.gRe * R;
        const py = cy - g.gIm * R;
        ctx.beginPath();
        ctx.arc(px, py, 6, 0, 2 * Math.PI);
        ctx.stroke();
      }

      // Freq range label across the bottom of the panel.
      ctx.fillStyle = PC.labelBright;
      ctx.font = "10px ui-monospace, monospace";
      const fLoTxt = sweep.freqs_mhz[0].toFixed(2);
      const fHiTxt = sweep.freqs_mhz[sweep.freqs_mhz.length - 1].toFixed(2);
      const txt = `${fLoTxt} → ${fHiTxt} MHz`;
      ctx.fillText(txt, size - 6 - ctx.measureText(txt).width, size - 6);

    }

    // Measured overlay (issue #595): the locus a VNA actually saw, against the
    // one the model predicts. The measurement arrives as impedance and goes
    // through the same reflectionCoefficient() as the solved Z, so the file's
    // own calibration reference is absorbed by the conversion — a 75 Ω
    // measurement lands correctly on a 50 Ω chart with no special case.
    if (measured && measured.freqs_mhz.length > 0) {
      // Clip to the swept band so both loci span the same frequencies (the CLI
      // overlay applies the same rule). With no sweep on screen there is
      // nothing to clip against, so the whole measurement is drawn.
      const mf = measured.freqs_mhz;
      const swept = sweep && sweep.freqs_mhz.length > 1;
      const fLo = swept ? sweep!.freqs_mhz[0] : -Infinity;
      const fHi = swept ? sweep!.freqs_mhz[sweep!.freqs_mhz.length - 1] : Infinity;
      const idx: number[] = [];
      for (let i = 0; i < mf.length; i++) {
        if (mf[i] >= fLo && mf[i] <= fHi) idx.push(i);
      }
      const mGamma = (i: number) =>
        reflectionCoefficient(measured.z_re[i], measured.z_im[i], z0);
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillStyle = PC.measured;
      if (idx.length === 0) {
        // Disjoint bands. Say so — the user picked a file and would otherwise
        // see the chart not change at all.
        const txt = `measured ${mf[0].toFixed(2)}–${mf[mf.length - 1].toFixed(2)} MHz: outside the sweep`;
        ctx.fillText(txt, size - 6 - ctx.measureText(txt).width, size - 20);
      } else {
        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, R, 0, 2 * Math.PI);
        ctx.clip();
        // Dashed, to read as "other source" next to the solid convergence
        // trail and the scattered sweep dots.
        ctx.setLineDash([4, 3]);
        ctx.strokeStyle = PC.measured;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        for (let k = 0; k < idx.length; k++) {
          const g = mGamma(idx[k]);
          const px = cx + g.gRe * R;
          const py = cy - g.gIm * R;
          if (k === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();

        // Endpoint markers matching the sweep trail's grammar: low-frequency
        // end filled, high-frequency end hollow, so the locus has a direction.
        for (const [k, filled] of [[0, true], [idx.length - 1, false]] as const) {
          const g = mGamma(idx[k]);
          ctx.lineWidth = 1.2;
          ctx.strokeStyle = PC.measured;
          ctx.fillStyle = filled ? PC.measured : `rgba(${PC.bgRgb}, 0.95)`;
          ctx.beginPath();
          ctx.arc(cx + g.gRe * R, cy - g.gIm * R, 3, 0, 2 * Math.PI);
          ctx.fill();
          ctx.stroke();
        }

        // Label above the sweep's freq-range line, with the span actually
        // drawn — which is the measurement's own band when it is narrower than
        // the sweep, and says as much when the file reaches past it.
        ctx.fillStyle = PC.measured;
        const dLo = mf[idx[0]].toFixed(2);
        const dHi = mf[idx[idx.length - 1]].toFixed(2);
        const partial = idx.length < mf.length ? " (clipped)" : "";
        const txt = `measured: ${measured.label}  ${dLo} → ${dHi} MHz${partial}`;
        ctx.fillText(txt, size - 6 - ctx.measureText(txt).width, size - 20);
      }
    }

    if (running) {
      ctx.fillStyle = PC.label;
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillText("sweeping…", 6, size - 6);
    }

    // Convergence locus: Z(N) trajectory as N increases, drawn as a
    // connected polyline per feed so the sequence direction reads as
    // motion (vs. the freq sweep's unconnected scatter). Each feed gets
    // its own bright color from the feed palette — the line shape
    // distinguishes the convergence trail from the scattered freq-sweep
    // dots, and the bright-vs-dim brightness distinguishes the bright
    // current-Z marker from the trail's interior dots. Smallest-N point
    // gets a hollow ring; largest-N gets a filled disc; Richardson-
    // extrapolated Z* gets a diamond (primary feed only).
    if (converge && converge.n_values.length >= 1) {
      const cHasMulti =
        !!converge.feeds_z_re &&
        !!converge.feeds_z_im &&
        converge.feeds_z_re.length === converge.n_values.length &&
        converge.feeds_z_re[0].length > 1;
      const cNFeeds = cHasMulti ? converge.feeds_z_re![0].length : 1;
      const czAt = (fi: number, i: number) =>
        cHasMulti
          ? { re: converge.feeds_z_re![i][fi], im: converge.feeds_z_im![i][fi] }
          : { re: converge.z_re[i], im: converge.z_im[i] };

      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, 2 * Math.PI);
      ctx.clip();
      for (let fi = 0; fi < cNFeeds; fi++) {
        ctx.strokeStyle = feedColor(fi);
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        for (let i = 0; i < converge.n_values.length; i++) {
          const z = czAt(fi, i);
          const g = reflectionCoefficient(z.re, z.im, z0);
          const px = cx + g.gRe * R;
          const py = cy - g.gIm * R;
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }
        ctx.stroke();

        // Per-N dots along the trajectory.
        ctx.fillStyle = feedColor(fi);
        for (let i = 0; i < converge.n_values.length; i++) {
          const z = czAt(fi, i);
          const g = reflectionCoefficient(z.re, z.im, z0);
          const px = cx + g.gRe * R;
          const py = cy - g.gIm * R;
          ctx.beginPath();
          ctx.arc(px, py, 1.8, 0, 2 * Math.PI);
          ctx.fill();
        }
      }
      ctx.restore();

      // Endpoint markers per feed: smallest-N hollow, largest-N filled.
      const drawNEndpoint = (fi: number, idx: number, filled: boolean) => {
        const z = czAt(fi, idx);
        const g = reflectionCoefficient(z.re, z.im, z0);
        const px = cx + g.gRe * R;
        const py = cy - g.gIm * R;
        const col = feedColor(fi);
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = col;
        ctx.fillStyle = filled ? col : `rgba(${PC.bgRgb}, 0.95)`;
        ctx.beginPath();
        ctx.arc(px, py, 3, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
      };
      for (let fi = 0; fi < cNFeeds; fi++) {
        drawNEndpoint(fi, 0, false);
        drawNEndpoint(fi, converge.n_values.length - 1, true);
      }

      // Richardson Z* markers — one diamond per feed, each in the
      // matching bright feed color so the user can tell which trail
      // extrapolates to which Z*. The diamond shape distinguishes the
      // extrapolated value from the actual sampled per-N dots (small
      // circles) and from the current-Z marker (larger outlined dot).
      const drawExtrap = (
        fi: number,
        zRe: number | null,
        zIm: number | null,
      ) => {
        if (zRe == null || zIm == null) return;
        const ge = reflectionCoefficient(zRe, zIm, z0);
        // Clip to the unit Smith disc — Richardson on a not-yet-converging
        // series can fly outside |Γ|=1 in early frames.
        const gMag = Math.hypot(ge.gRe, ge.gIm);
        const k = gMag > 0.98 ? 0.98 / gMag : 1;
        const px = cx + ge.gRe * R * k;
        const py = cy - ge.gIm * R * k;
        ctx.save();
        ctx.translate(px, py);
        ctx.rotate(Math.PI / 4);
        ctx.fillStyle = feedColor(fi);
        ctx.strokeStyle = feedColor(fi, 1.0);
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.rect(-4, -4, 8, 8);
        ctx.fill();
        ctx.stroke();
        ctx.restore();
      };
      if (cHasMulti && converge.feeds_z_re_extrap && converge.feeds_z_im_extrap) {
        for (let fi = 0; fi < cNFeeds; fi++) {
          drawExtrap(
            fi,
            converge.feeds_z_re_extrap[fi],
            converge.feeds_z_im_extrap[fi],
          );
        }
      } else {
        drawExtrap(0, converge.z_re_extrap, converge.z_im_extrap);
      }

    }
    if (convergeRunning) {
      ctx.fillStyle = PC.label;
      ctx.font = "10px ui-monospace, monospace";
      // Stack under the freq-sweep status if both are running.
      const yOff = running ? 18 : 6;
      ctx.fillText("converging…", 6, size - yOff);
    }

    // Current impedance marker(s). One bright dot per feed in the
    // matching feed color, with a thin dark outline for visibility on
    // top of the sweep cloud. Single- and multi-feed share this code
    // path so the chart's visual grammar is uniform: dim color = trail
    // (freq sweep), bright = "you are here." The previous golden +
    // glow + line-from-centre treatment for single-feed is gone —
    // single-feed and feed-0-of-multi-feed now look identical.
    // `trial` overrides the feed list rather than joining it: a proposed
    // point is a proposed port table, while `feeds` still holds the LAST
    // SOLVE's per-port dots. Letting those win would leave a multi-feed
    // design showing stale dots and no trial point at all — the frozen-dot
    // bug this prop exists to fix, hiding in the multi-feed branch.
    //
    // `trialFeeds` is the same override one level finer (#789): a multi-feed
    // proposer sends every port's Z, so the run draws the array coming into
    // balance rather than feed 0 alone, which the minimax objective may not
    // even be the one chasing. Falls back to r/x when the proposer has no
    // table — single-feed designs, and any other source of a trial point.
    const markerPoints: Array<{ re: number; im: number; fi: number }> = trial
      ? trialFeeds && trialFeeds.length > 0
        ? trialFeeds.map((f, fi) => ({ re: f.z_re, im: f.z_im, fi }))
        : r > 0 || x !== 0
          ? [{ re: r, im: x, fi: 0 }]
          : []
      : feeds && feeds.length > 0
        ? feeds.map((f, fi) => ({ re: f.z_re, im: f.z_im, fi }))
        : r > 0 || x !== 0
          ? [{ re: r, im: x, fi: 0 }]
          : [];
    // The bright ring goes LAST so nothing paints over it. Measured on
    // arrays.bowtiearray2x4: the array is symmetric, so its 8 feeds are 4
    // exactly-coincident PAIRS inside a ~15 px cluster on a 300 px chart —
    // the rings do not scatter, they stack. In feed order the worst feed is
    // whichever the search says, so half the time a dim 0.32-alpha stroke
    // landed on top of the bright one and muddied the only mark that says
    // which feed is holding the array back.
    const drawOrder =
      trial && trialWorstFeed !== undefined
        ? [
            ...markerPoints.filter((m) => m.fi !== trialWorstFeed),
            ...markerPoints.filter((m) => m.fi === trialWorstFeed),
          ]
        : markerPoints;
    for (const m of drawOrder) {
      if (m.re <= 0 && m.im === 0) continue;
      const { gRe, gIm } = reflectionCoefficient(m.re, m.im, z0);
      const px = cx + gRe * R;
      const py = cy - gIm * R;
      if (trial) {
        // Hollow ring, not a filled dot. The chart's grammar is already
        // filled = settled / hollow = the other end of a trail, so a ring
        // reads as "being tried" rather than "this is your antenna" — which
        // matters because nothing else on the chart has caught up yet: the
        // sweep locus and any measured overlay still describe the geometry
        // as it was before the run started.
        //
        // With a table of rings, the one the objective is driving is bright
        // and full-width and the rest recede (#789). Eight equal rings
        // wandering per eval read as chaos; one bright ring among seven
        // faint ones reads as "this is the feed holding the array back",
        // which is exactly what a minimax run is doing.
        const isWorst =
          markerPoints.length === 1 ||
          trialWorstFeed === undefined ||
          m.fi === trialWorstFeed;
        ctx.strokeStyle = feedColor(m.fi, isWorst ? 0.85 : 0.32);
        ctx.lineWidth = isWorst ? 2 : 1.25;
        ctx.beginPath();
        ctx.arc(px, py, isWorst ? 5 : 3.5, 0, 2 * Math.PI);
        ctx.stroke();
        continue;
      }
      ctx.fillStyle = feedColor(m.fi);
      ctx.beginPath();
      ctx.arc(px, py, 4, 0, 2 * Math.PI);
      ctx.fill();
      ctx.strokeStyle = `rgba(${PC.bgRgb}, 0.85)`;
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Top-left summary: one row per feed (when multi-feed) or one row
    // total (single-feed). Each row gets:
    //   [dim swatch][bright swatch]  feed N  Z* ≈ R + jX Ω
    // Both swatches encode the per-feed color (dim = freq-sweep trail,
    // bright = current-Z marker / convergence trail). Z* tacks on
    // inline in the matching bright color when ≥3 converge samples
    // have come in, so each trail has its own visibly-colored Z*
    // readout next to its swatch — replacing the old single purple
    // Z* line that only tracked feeds[0].
    const summaryFeeds: Array<{
      fi: number;
      extrapRe: number | null;
      extrapIm: number | null;
    }> = [];
    if (multiFeed && feeds && feeds.length > 1) {
      for (let fi = 0; fi < feeds.length; fi++) {
        const re = converge?.feeds_z_re_extrap?.[fi] ?? null;
        const im = converge?.feeds_z_im_extrap?.[fi] ?? null;
        summaryFeeds.push({ fi, extrapRe: re, extrapIm: im });
      }
    } else if (converge && converge.n_values.length >= 1) {
      summaryFeeds.push({
        fi: 0,
        extrapRe: converge.z_re_extrap,
        extrapIm: converge.z_im_extrap,
      });
    } else if (feeds && feeds.length === 1) {
      // Sweep-only single-feed run: show the swatch row so the colors
      // on the chart are explained even without a converge.
      summaryFeeds.push({ fi: 0, extrapRe: null, extrapIm: null });
    }
    if (summaryFeeds.length > 0) {
      ctx.font = "10px ui-monospace, monospace";
      for (let row = 0; row < summaryFeeds.length; row++) {
        const { fi, extrapRe, extrapIm } = summaryFeeds[row];
        const ly = 12 + row * 14;
        // Dim swatch (sweep trail color).
        ctx.fillStyle = feedSweepColor(fi);
        ctx.beginPath();
        ctx.arc(12, ly, 3, 0, 2 * Math.PI);
        ctx.fill();
        // Bright swatch (current-Z / convergence-trail color).
        ctx.fillStyle = feedColor(fi);
        ctx.beginPath();
        ctx.arc(20, ly, 3, 0, 2 * Math.PI);
        ctx.fill();
        // Feed label + inline Z* (when extrap available). Text color
        // matches the bright feed color so the row's color identity
        // ties back to the chart trails for that feed.
        ctx.fillStyle = feedColor(fi);
        let txt =
          summaryFeeds.length > 1 ? `feed ${fi}` : "";
        if (extrapRe != null && extrapIm != null) {
          const sign = extrapIm >= 0 ? "+" : "−";
          const zText = `Z* ≈ ${extrapRe.toFixed(2)} ${sign} j${Math.abs(extrapIm).toFixed(2)} Ω`;
          txt = txt ? `${txt}  ${zText}` : zText;
        }
        if (txt) ctx.fillText(txt, 28, ly + 3);
      }
    }

    // Bottom-left: N-range stays neutral since it's per-converge not
    // per-feed. Sits above the converging / sweeping status indicators.
    if (converge && converge.n_values.length >= 1) {
      const nLo = converge.n_values[0];
      const nHi = converge.n_values[converge.n_values.length - 1];
      ctx.fillStyle = PC.labelBright;
      ctx.font = "10px ui-monospace, monospace";
      const baseY = running && convergeRunning ? size - 30
        : running || convergeRunning ? size - 18
        : size - 6;
      ctx.fillText(`N: ${nLo} → ${nHi}`, 6, baseY);
    }

    // Center match marker
    ctx.strokeStyle = PC.centerMark;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 4, cy);
    ctx.lineTo(cx + 4, cy);
    ctx.moveTo(cx, cy - 4);
    ctx.lineTo(cx, cy + 4);
    ctx.stroke();
    // multiFeed is captured in the closure; without it in the deps the
    // chart wouldn't redraw when the descriptor flag flips from its
    // initial false to the real /examples value (true for bowtie /
    // hexbeam_5band) — the user saw only one Z* annotation in the
    // legend because the closure stayed wedged on the single-feed branch.
    // `trial` is in the deps for the same reason: it decides both the marker
    // shape and whether `feeds` is consulted at all, so a stale closure would
    // leave the last trial ring on screen after a run settled. `trialFeeds`
    // and `trialWorstFeed` likewise carry the whole per-eval picture (#789):
    // r/x still change every frame on a multi-feed run, but they are only
    // feed 0, so a run where feed 0 sat still would freeze every ring.
  }, [r, x, z0, size, sweep, converge, measured, measFreqMhz, running, convergeRunning, feeds, multiFeed, connectSweep, trial, trialFeeds, trialWorstFeed, theme]);

  // data-connect mirrors the trail mode (locus vs. dot cloud) for tests —
  // canvas pixels are invisible to jsdom, the attribute is not (the same
  // seam SweepChart's data-* attributes provide).
  return (
    <canvas ref={canvasRef} className="smith" data-connect={connectSweep ? "1" : "0"} />
  );
}
