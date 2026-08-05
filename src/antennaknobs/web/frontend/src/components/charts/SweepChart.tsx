import { useContext, useEffect, useRef } from "react";
import type { FeedEntry, SweepData } from "../../lib/api";
import { gammaDbFromMag, gammaMagFromZ, vswrFromGammaMag } from "../../lib/math";
import { ThemeContext } from "../hooks";
import { feedColor, feedSweepColor, plotColors } from "./palette";

// The two output views the sweep already pays for: |Γ| vs. frequency and
// VSWR vs. frequency (issue #700 unit 5, docs/plan-view-rail-scaling.md
// items 6/7). One component, precedent FarFieldChart's `cut` prop — the two
// modes differ only in the y-axis domain/ticks and which lib/math.ts
// conversion turns a swept Z into a y-value.
export type SweepMode = "gamma" | "vswr";

// y-domain per mode. gamma plots S11 in negative dB (20·log₁₀|Γ|), the
// VNA/NanoVNA convention: 0 dB at the top, a good match is a downward dip
// toward −30; anything deeper clamps to the bottom edge (below −30 dB the
// match is beyond caring, and beyond most VNAs' honesty). VSWR is unbounded
// as |Γ| → 1; the ham-instrument convention is a linear 1..10 scale with an
// off-scale indication for anything hotter — matching a real SWR meter's
// needle pinned at the peg rather than a y-axis that silently rescales
// every time a knob drags through a bad match.
const DOMAIN: Record<SweepMode, { lo: number; hi: number; ticks: number[]; title: string }> = {
  gamma: { lo: -30, hi: 0, ticks: [-30, -20, -10, 0], title: "S11 dB" },
  vswr: { lo: 1, hi: 10, ticks: [1, 2, 4, 6, 8, 10], title: "VSWR" },
};

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
  feeds,
  multiFeed,
}: {
  mode: SweepMode;
  r: number;
  x: number;
  z0: number;
  size: number;
  sweep: SweepData | null;
  measFreqMhz: number;
  running: boolean;
  /** Multi-feed geometries pass the per-feed Z list from the latest solve so
   *  the chart can mark N current points, one per port (same prop SmithChart
   *  takes for the same reason). */
  feeds?: FeedEntry[] | undefined;
  multiFeed: boolean;
}) {
  const theme = useContext(ThemeContext); // repaint on theme toggle (dep below)
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dom = DOMAIN[mode];

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
    // SWR meter pins its needle rather than rescaling); gamma never needs
    // this since S11 ≤ 0 dB for anything passive. Below the gamma floor the
    // trace just clamps to the bottom edge — an over-deep dip is good news,
    // not a hazard worth a pinned-needle glyph.
    const offScale = (v: number) => v > dom.hi;

    ctx.strokeStyle = PC.grid;
    ctx.lineWidth = 0.6;
    ctx.fillStyle = PC.labelDim;
    ctx.font = "9px ui-monospace, monospace";
    for (const t of dom.ticks) {
      const y = yOf(t);
      ctx.beginPath();
      ctx.moveTo(marginL, y);
      ctx.lineTo(marginL + plotW, y);
      ctx.stroke();
      ctx.fillText(t.toFixed(0), 2, y + 3);
    }
    // Axis frame.
    ctx.strokeStyle = PC.axis;
    ctx.lineWidth = 1;
    ctx.strokeRect(marginL, marginT, plotW, plotH);

    // Mode title, top-left (same corner SmithChart's Z0 label uses).
    ctx.fillStyle = PC.labelDim;
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText(dom.title, marginL, 12);

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

      // One polyline per feed, dim "trail" color (SmithChart's convention:
      // dim = sweep trail, bright = current-Z marker). Unlike the Smith
      // chart's 2-D Γ-plane locus, frequency is a natural ordering axis
      // here, so — unlike that chart's unconnected scatter — a connected
      // line is the correct read, not an artifact of interpolation.
      for (let fi = 0; fi < nFeeds; fi++) {
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

    if (running) {
      ctx.fillStyle = PC.label;
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillText("sweeping…", marginL, size - 6);
    }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, r, x, z0, size, sweep, measFreqMhz, running, feeds, multiFeed, theme]);

  return (
    <canvas
      ref={canvasRef}
      className={`sweep sweep-${mode}`}
      data-mode={mode}
      data-points={hasSweep ? sweep!.freqs_mhz.length : 0}
      data-feeds={nFeeds}
      data-y-values={traceY.map((v) => v.toFixed(4)).join(",")}
      data-current={markerPoints.length > 0 ? markerPoints[0].v.toFixed(4) : ""}
    />
  );
}
