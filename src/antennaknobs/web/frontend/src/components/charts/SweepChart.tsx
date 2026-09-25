import { useContext, useEffect, useRef, useState } from "react";
import type { FeedEntry, SweepData } from "../../lib/api";
import { gammaDbFromMag, gammaMagFromZ, vswrFromGammaMag } from "../../lib/math";
import { s11DbTop } from "../../lib/refine";
import type { SweepProgress } from "../../lib/sweep";
import {
  AUTO,
  type AxisDomain,
  axisTicks,
  bandwidthReadout,
  DEFAULT_SWR_THRESHOLD,
  formatTick,
  s11DbForSwr,
  sweepAxisDomain,
  type SweepAxisChoice,
  type SweepMode,
  swrBands,
  widenDomain,
} from "../../lib/sweepAxis";
import { ThemeContext } from "../hooks";
import { feedColor, feedSweepColor, plotColors } from "./palette";
import { SweepRangePopover } from "./SweepRangePopover";
import {
  drawSweepProgressBar,
  sweepProgressAttr,
  sweepStatusText,
} from "./sweepStatus";

// The two output views the sweep already pays for: |Γ| vs. frequency and
// VSWR vs. frequency (issue #700 unit 5, docs/plan-view-rail-scaling.md
// items 6/7). One component, precedent FarFieldChart's `cut` prop — the two
// modes differ only in the y-axis domain/ticks and which lib/math.ts
// conversion turns a swept Z into a y-value.
export type { SweepMode };

// The y axis per mode (AK#1738). gamma plots S11 in negative dB
// (20·log₁₀|Γ|), the VNA/NanoVNA convention: 0 dB at the top, a good match
// is a downward dip, anything below the floor clamps to the bottom edge.
// VSWR is linear from 1, and anything above the top pegs with an off-scale
// tick — a real SWR meter's needle pinned at the peg.
//
// The range is the viewer's (lib/sweepAxis.ts): a preset, a custom min/max,
// or Auto, which fits the sweep's dip. The fixed 1–10 / −30..0 it replaces
// was chosen for a meter's stability — an axis that rescales under the hand
// on every knob step is unreadable — so Auto keeps that: while the inputs
// are LIVE (a knob moving, a sweep streaming) it only grows, and it re-fits
// once they have been quiet for AUTO_SETTLE_MS. The refinement planner
// (lib/refine.ts) computes the same domain from the same rule.
const TITLE: Record<SweepMode, string> = { gamma: "S11 dB", vswr: "VSWR" };

// The same 500 ms as every other dwell in the app (useAnalysisRunners'
// sweep debounce and refinement dwell): the inputs have been still this long
// ⇒ the knob has settled.
export const AUTO_SETTLE_MS = 500;

// The drawn domain under Auto: grow-only while `live`, the fresh fit
// otherwise. State adjusted during render (React's documented pattern for
// state derived from changing props) — it converges in one extra render,
// since widening a domain by itself is the identity. Held per mode: the
// stage swaps VSWR for S11 on the SAME component instance, and a VSWR range
// must never be widened into an S11 one.
function useHeldDomain(
  mode: SweepMode,
  fresh: AxisDomain,
  live: boolean,
  auto: boolean,
): AxisDomain {
  const [held, setHeld] = useState<{ mode: SweepMode; dom: AxisDomain } | null>(null);
  if (!auto) {
    if (held !== null) setHeld(null);
    return fresh;
  }
  const prev = held && held.mode === mode ? held.dom : null;
  const next = live ? widenDomain(prev, fresh) : fresh;
  if (prev === null || prev.lo !== next.lo || prev.hi !== next.hi) {
    setHeld({ mode, dom: next });
  }
  return next;
}

// Whether the chart's inputs changed within the last AUTO_SETTLE_MS. Keyed on
// a signature of what Auto fits: a knob step moves the live marker and blanks
// the sweep, so a drag changes it at every solve; a streaming sweep changes
// it at every point. A freshly mounted chart starts quiet — it shows the fit,
// not a grown range from a previous life.
function useQuiet(sig: string): boolean {
  const [quietSig, setQuietSig] = useState(sig);
  useEffect(() => {
    if (quietSig === sig) return;
    const t = window.setTimeout(() => setQuietSig(sig), AUTO_SETTLE_MS);
    return () => window.clearTimeout(t);
  }, [sig, quietSig]);
  return quietSig === sig;
}

// Z -> this mode's y-value. Both modes go through gammaMagFromZ first (the
// one place |Γ| gets computed), so a bug there shows up identically in both
// charts instead of two independently-wrong formulas.
function valueFor(mode: SweepMode, re: number, im: number, z0: number): number {
  const g = gammaMagFromZ(re, im, z0);
  return mode === "gamma" ? gammaDbFromMag(g) : vswrFromGammaMag(g);
}

export function SweepChart({
  mode,
  r,
  x,
  z0,
  size,
  sweep,
  measFreqMhz,
  running,
  progress,
  settled = true,
  feeds,
  multiFeed,
  axis = AUTO,
  swrThreshold = DEFAULT_SWR_THRESHOLD,
  onAxisChange,
  onThresholdChange,
}: {
  mode: SweepMode;
  r: number;
  x: number;
  z0: number;
  size: number;
  sweep: SweepData | null;
  measFreqMhz: number;
  running: boolean;
  /** Points received by the sweep in flight (AK#1682) — see SmithChart's
   *  prop of the same name. */
  progress?: SweepProgress | null | undefined;
  /** The sweep's shape is final (issue #866). While a refinement pass is
   *  still inserting points (or was cut short mid-run), the trail renders as
   *  unconnected dots — a polyline through a still-densifying set draws
   *  transient kinks that then shift as points land. Defaults true so
   *  refinement-free call sites keep today's connected line. */
  settled?: boolean;
  /** Multi-feed geometries pass the per-feed Z list from the latest solve so
   *  the chart can mark N current points, one per port (same prop SmithChart
   *  takes for the same reason). */
  feeds?: FeedEntry[] | undefined;
  multiFeed: boolean;
  /** This chart's vertical range (AK#1738); Auto when omitted. */
  axis?: SweepAxisChoice;
  /** The SWR threshold for the line and the bandwidth readout (2:1 when
   *  omitted). The S11 chart draws the matching return-loss line. */
  swrThreshold?: number;
  /** Given, the y axis opens the range popover. Thumbnails omit both
   *  callbacks: a thumb is a button that selects its view. */
  onAxisChange?: (c: SweepAxisChoice) => void;
  onThresholdChange?: (t: number) => void;
}) {
  const theme = useContext(ThemeContext); // repaint on theme toggle (dep below)
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Pure derivation from props, computed outside the canvas effect so it's
  // available for the data-* attributes below even when there is no 2-D
  // context to draw with (jsdom in tests). This is also the one place the
  // mode's conversion runs per sample — the draw effect below reuses it
  // rather than recomputing.
  const hasSweep = !!sweep && sweep.freqs_mhz.length > 1;
  const hasMulti =
    hasSweep &&
    !!sweep!.feeds_z_re &&
    !!sweep!.feeds_z_im &&
    sweep!.feeds_z_re!.length === sweep!.freqs_mhz.length &&
    sweep!.feeds_z_re![0].length > 1;
  const nFeeds = hasSweep ? (hasMulti ? sweep!.feeds_z_re![0].length : 1) : 0;
  const zAt = (fi: number, i: number) =>
    hasMulti
      ? { re: sweep!.feeds_z_re![i][fi], im: sweep!.feeds_z_im![i][fi] }
      : { re: sweep!.z_re[i], im: sweep!.z_im[i] };
  // Feed-0 (or the legacy single trace)'s y-values, exposed for tests: a
  // mutation that swapped gamma<->vswr math changes these numbers even
  // though the DOM shape (canvas, data-mode) stays identical.
  const traceY = hasSweep
    ? sweep!.freqs_mhz.map((_, i) => {
        const z = zAt(0, i);
        return valueFor(mode, z.re, z.im, z0);
      })
    : [];

  // Current-Z marker(s): one per feed (or the single r/x pair), same
  // fallback SmithChart uses. Undefined/zero Z (no solve yet) yields no
  // marker rather than a spurious point at the origin.
  const markerPoints: Array<{ v: number; fi: number }> =
    feeds && feeds.length > 0
      ? feeds.map((f, fi) => ({ v: valueFor(mode, f.z_re, f.z_im, z0), fi }))
      : r > 0 || x !== 0
        ? [{ v: valueFor(mode, r, x, z0), fi: 0 }]
        : [];

  // Every feed's trail, in this mode's units.
  const trails: number[] = [];
  if (hasSweep) {
    for (let fi = 0; fi < nFeeds; fi++) {
      for (let i = 0; i < sweep!.freqs_mhz.length; i++) {
        const z = zAt(fi, i);
        trails.push(valueFor(mode, z.re, z.im, z0));
      }
    }
  }
  const markerVs = markerPoints.map((m) => m.v);
  // The S11 axis top ADAPTS when any drawn value crosses 0 dB (a driven
  // array's active Γ is not bounded by 1 — see s11DbTop, which is also what
  // the refinement planner uses, so axis and planner cannot drift). The rule
  // runs over every feed's trail plus the current-Z markers: whichever trace
  // carries the over-unity port pushes the top up, headroom included, and
  // the 0 dB boundary stays as a tick — the line a healthy port never
  // crosses.
  const s11Top = mode === "gamma" ? s11DbTop([...trails, ...markerVs]) : 0;
  // Auto fits the finished sweep when there is one, else the marker(s) — the
  // sweep alone, not the markers with it, so the planner (which sees only
  // the sweep) derives the same domain. Not a sweep still streaming in: its
  // first points are the band edge, whose "dip" is a mismatch, and the
  // grow-only hold would lock that in until the settle (seen in the real
  // app: a 20 → 100 → 1.5 flash). Refinement rounds add points to a
  // finished sweep, which only ever deepens the dip, so they fit as usual.
  const fitValues = hasSweep && !running ? trails : markerVs;
  const fresh = sweepAxisDomain(mode, axis, fitValues, s11Top);
  const quiet = useQuiet(
    `${mode}:${fitValues.length}:${Math.min(...fitValues).toFixed(4)}:` +
      markerVs.map((v) => v.toFixed(4)).join(","),
  );
  const dom = useHeldDomain(mode, fresh, running || !quiet, axis.kind === "auto");
  const ticks = axisTicks(dom);
  // The 0 dB line stays a tick when the S11 top grows past it, as before.
  if (mode === "gamma" && dom.hi > 0 && !ticks.includes(0)) ticks.push(0);
  if (mode === "gamma" && dom.hi > 0 && !ticks.includes(dom.hi)) ticks.push(dom.hi);

  // The threshold (AK#1738): the SWR line, or the matching S11 line, and the
  // runs of feed 0's sweep below it, their edges interpolated between the
  // straddling samples (lib/sweepAxis.ts swrBands).
  const thresholdY = mode === "vswr" ? swrThreshold : s11DbForSwr(swrThreshold);
  const bands = hasSweep
    ? swrBands(
        sweep!.freqs_mhz,
        sweep!.freqs_mhz.map((_, i) => {
          const z = zAt(0, i);
          return valueFor("vswr", z.re, z.im, z0);
        }),
        swrThreshold,
      )
    : [];
  const readout = hasSweep ? bandwidthReadout(bands, measFreqMhz, swrThreshold) : "";
  const domKey = `${dom.lo},${dom.hi}`;
  const bandsKey = bands.map((b) => `${b.lo},${b.hi}`).join(";");

  // The range popover's anchor, while it is open.
  const [menuAt, setMenuAt] = useState<{ x: number; y: number } | null>(null);

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

    // Plot rectangle: left margin fits the y-axis tick labels, bottom margin
    // fits the freq-range / status text (same corner SmithChart uses).
    const marginL = 26;
    const marginR = 8;
    const marginT = 16;
    const marginB = 20;
    const plotW = size - marginL - marginR;
    const plotH = size - marginT - marginB;

    // domain -> [0,1] -> canvas y (top = hi, bottom = lo, same sense as any
    // chart axis).
    const frac = (v: number) =>
      Math.max(0, Math.min(1, (v - dom.lo) / (dom.hi - dom.lo)));
    const yOf = (v: number) => marginT + plotH * (1 - frac(v));
    // A value at/above the domain top for VSWR means "off the chart" (a real
    // SWR meter pins its needle rather than rescaling); gamma instead GROWS
    // its top when a driven-array port crosses 0 dB (see `dom` above), so
    // nothing is ever pinned there. Below the gamma floor the trace just
    // clamps to the bottom edge — an over-deep dip is good news, not a
    // hazard worth a pinned-needle glyph.
    const offScale = (v: number) => v > dom.hi;

    ctx.strokeStyle = PC.grid;
    ctx.lineWidth = 0.6;
    ctx.fillStyle = PC.labelDim;
    ctx.font = "9px ui-monospace, monospace";
    for (const t of ticks) {
      const y = yOf(t);
      ctx.beginPath();
      ctx.moveTo(marginL, y);
      ctx.lineTo(marginL + plotW, y);
      ctx.stroke();
      ctx.fillText(formatTick(t), 2, y + 3);
    }
    // Axis frame.
    ctx.strokeStyle = PC.axis;
    ctx.lineWidth = 1;
    ctx.strokeRect(marginL, marginT, plotW, plotH);

    // Mode title, top-left (same corner SmithChart's Z0 label uses).
    ctx.fillStyle = PC.labelDim;
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText(TITLE[mode], marginL, 12);

    // The threshold line (AK#1738), dashed, labelled at its right end, drawn
    // only when it is inside the range. The band readout shares the title
    // row, right-aligned.
    if (thresholdY > dom.lo && thresholdY < dom.hi) {
      const ty = yOf(thresholdY);
      ctx.strokeStyle = `rgb(${PC.thresholdRgb})`;
      ctx.lineWidth = 0.8;
      ctx.setLineDash([5, 3]);
      ctx.beginPath();
      ctx.moveTo(marginL, ty);
      ctx.lineTo(marginL + plotW, ty);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = `rgb(${PC.thresholdRgb})`;
      ctx.font = "9px ui-monospace, monospace";
      const lbl = `${formatTick(Number(swrThreshold.toFixed(2)))}:1`;
      ctx.fillText(lbl, marginL + plotW - ctx.measureText(lbl).width - 2, ty - 3);
    }
    if (readout) {
      ctx.fillStyle = PC.labelBright;
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillText(readout, size - marginR - ctx.measureText(readout).width, 12);
    }

    // Maps a frequency to canvas x within the swept band; undefined (null)
    // when there is no band to map against. Shared by the trail, the
    // current-freq guide line, and the current-Z marker's x position so all
    // three agree about where on the axis a given frequency sits.
    const fLo = hasSweep ? sweep!.freqs_mhz[0] : null;
    const fHi = hasSweep ? sweep!.freqs_mhz[sweep!.freqs_mhz.length - 1] : null;
    const xOf = (f: number) =>
      marginL + plotW * ((f - fLo!) / ((fHi! - fLo!) || 1));

    if (hasSweep) {
      const freqs = sweep!.freqs_mhz;

      // The below-threshold band(s), shaded under the trace.
      ctx.fillStyle = `rgba(${PC.thresholdRgb}, 0.12)`;
      for (const b of bands) {
        const x0 = xOf(b.lo);
        ctx.fillRect(x0, marginT, xOf(b.hi) - x0, plotH);
      }

      // One polyline per feed, dim "trail" color (SmithChart's convention:
      // dim = sweep trail, bright = current-Z marker). Unlike the Smith
      // chart's 2-D Γ-plane locus, frequency is a natural ordering axis
      // here, so — unlike that chart's unconnected scatter — a connected
      // line is the correct read, not an artifact of interpolation. Except
      // while refinement is still densifying the set (issue #866): then the
      // line's kinks are transients about to shift, so draw honest dots and
      // connect only once `settled`.
      for (let fi = 0; fi < nFeeds; fi++) {
        if (settled) {
          ctx.strokeStyle = feedSweepColor(fi);
          ctx.lineWidth = 1.3;
          ctx.beginPath();
          let started = false;
          for (let i = 0; i < freqs.length; i++) {
            const z = zAt(fi, i);
            const v = valueFor(mode, z.re, z.im, z0);
            const px = xOf(freqs[i]);
            const py = offScale(v) ? marginT : yOf(v);
            if (!started) { ctx.moveTo(px, py); started = true; }
            else ctx.lineTo(px, py);
          }
          ctx.stroke();
        } else {
          // Same dot radius as SmithChart's unconnected trail, same color
          // grammar (off-scale samples still get the pinned-needle tick
          // below, not a dot on the frame).
          ctx.fillStyle = feedSweepColor(fi);
          for (let i = 0; i < freqs.length; i++) {
            const z = zAt(fi, i);
            const v = valueFor(mode, z.re, z.im, z0);
            if (offScale(v)) continue;
            const px = xOf(freqs[i]);
            const py = yOf(v);
            ctx.beginPath();
            ctx.arc(px, py, 1.5, 0, 2 * Math.PI);
            ctx.fill();
          }
        }

        // Off-scale samples get an upward tick at the top edge instead of a
        // dot sitting exactly on the frame — a real VSWR meter's pinned
        // needle, not a plausible-looking in-range value.
        ctx.fillStyle = feedSweepColor(fi);
        for (let i = 0; i < freqs.length; i++) {
          const z = zAt(fi, i);
          const v = valueFor(mode, z.re, z.im, z0);
          if (!offScale(v)) continue;
          const px = xOf(freqs[i]);
          ctx.beginPath();
          ctx.moveTo(px - 3, marginT + 5);
          ctx.lineTo(px + 3, marginT + 5);
          ctx.lineTo(px, marginT);
          ctx.closePath();
          ctx.fill();
        }
      }

      // Freq range label, bottom-right (same convention as SmithChart).
      ctx.fillStyle = PC.labelBright;
      ctx.font = "10px ui-monospace, monospace";
      const txt = `${fLo!.toFixed(2)} → ${fHi!.toFixed(2)} MHz`;
      ctx.fillText(txt, size - 6 - ctx.measureText(txt).width, size - 6);

      // Current-frequency guide: a dashed vertical line at measFreqMhz (only
      // meaningful inside the swept band — outside it there is nothing on
      // this axis to point at) plus a bright per-feed marker where that line
      // crosses each trail. Mirrors SmithChart's dim-trail/bright-marker
      // grammar, projected onto a frequency x-axis instead of the Γ-plane.
      if (measFreqMhz >= fLo! && measFreqMhz <= fHi!) {
        const gx = xOf(measFreqMhz);
        ctx.strokeStyle = PC.spoke;
        ctx.lineWidth = 0.8;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(gx, marginT);
        ctx.lineTo(gx, marginT + plotH);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // Current-Z marker(s): bright dot per feed at the measured frequency
    // (or centered if outside the swept band / no sweep at all — the
    // reading is still valid, it just has nowhere better to sit on this
    // axis than the plot's horizontal middle).
    if (markerPoints.length > 0) {
      const inBand = hasSweep && measFreqMhz >= fLo! && measFreqMhz <= fHi!;
      const gx = inBand ? xOf(measFreqMhz) : marginL + plotW / 2;
      for (const m of markerPoints) {
        const py = offScale(m.v) ? marginT : yOf(m.v);
        ctx.fillStyle = feedColor(m.fi);
        ctx.beginPath();
        ctx.arc(gx, py, 3.5, 0, 2 * Math.PI);
        ctx.fill();
        ctx.strokeStyle = `rgba(${PC.bgRgb}, 0.85)`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }

    const status = sweepStatusText(running, progress);
    if (status) {
      ctx.fillStyle = PC.label;
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillText(status, marginL, size - 6);
    }
    drawSweepProgressBar(ctx, progress, size, PC.label);
    // multiFeed isn't read directly (nFeeds/hasMulti already derive the same
    // thing from the sweep payload's own shape) but is kept as a dep so a
    // descriptor flip that changes it without changing the sweep shape still
    // redraws — same reasoning as SmithChart's identical comment.
    //
    // dom/hasSweep/hasMulti/nFeeds/traceY/markerPoints are pure functions of
    // the props already listed, not separate state — omitted here (as
    // opposed to listed like SmithChart's locals) because they're fresh
    // array/object literals every render; listing them would defeat the
    // memoization this dep array exists for. mode is listed directly since
    // it's the one prop dom/valueFor key off that isn't otherwise present.
    //
    // domKey/bandsKey/readout/swrThreshold stand in for the domain, the
    // bands and the threshold line (AK#1738): strings, so an unchanged range
    // does not redraw.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, r, x, z0, size, sweep, measFreqMhz, running, progress, settled, feeds, multiFeed, theme, domKey, bandsKey, readout, swrThreshold]);

  const title =
    mode === "vswr" ? "VSWR range and SWR threshold" : "S11 range and SWR threshold";
  return (
    <div className="sweep-chart" style={{ width: size, height: size }}>
      <canvas
        ref={canvasRef}
        className={`sweep sweep-${mode}`}
        data-mode={mode}
        data-settled={settled ? "1" : "0"}
        data-progress={sweepProgressAttr(progress)}
        data-points={hasSweep ? sweep!.freqs_mhz.length : 0}
        data-feeds={nFeeds}
        data-y-values={traceY.map((v) => v.toFixed(4)).join(",")}
        data-current={markerPoints.length > 0 ? markerPoints[0].v.toFixed(4) : ""}
        data-y-lo={dom.lo}
        data-y-hi={dom.hi}
        data-axis={axis.kind}
        data-bands={bands.length}
        data-readout={readout}
      />
      {/* The y axis is the range control (AK#1738): a transparent button over
          the tick-label strip, the whole plot height. Stage charts only. */}
      {onAxisChange && (
        <button
          type="button"
          className="sweep-axis-btn"
          style={{ top: 16, height: size - 16 - 20 }}
          aria-label={title}
          title={`${title} (${axis.kind === "auto" ? "Auto" : "fixed"})`}
          aria-haspopup="dialog"
          aria-expanded={menuAt !== null}
          onClick={(e) => setMenuAt({ x: e.clientX + 8, y: e.clientY - 8 })}
        />
      )}
      {onAxisChange && menuAt && (
        <SweepRangePopover
          mode={mode}
          at={menuAt}
          choice={axis}
          drawn={dom}
          threshold={swrThreshold}
          onChoice={onAxisChange}
          onThreshold={(t) => onThresholdChange?.(t)}
          onClose={() => setMenuAt(null)}
        />
      )}
    </div>
  );
}
