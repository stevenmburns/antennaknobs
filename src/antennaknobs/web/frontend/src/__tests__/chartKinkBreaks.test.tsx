// AK#1969 at the charts: a connected sweep leaves out the segments meeting at
// an unresolved corner and dots its samples there, on the Smith chart and the
// VSWR/S11 chart alike; a smooth well-sampled sweep is one line with no dots.
import { afterEach, describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { SmithChart } from "../components/charts/SmithChart";
import { SweepChart } from "../components/charts/SweepChart";
import type { SweepData } from "../lib/api";

type Op = { op: string; args: number[] };

function recorder() {
  const ops: Op[] = [];
  const ctx = new Proxy(
    {},
    {
      get: (_t, prop) => {
        if (prop === "measureText") return () => ({ width: 10 });
        return (...args: unknown[]) =>
          ops.push({
            op: String(prop),
            args: args.filter((a): a is number => typeof a === "number"),
          });
      },
      set: () => true,
    },
  ) as unknown as CanvasRenderingContext2D;
  return { ctx, ops };
}

const real = HTMLCanvasElement.prototype.getContext;
afterEach(() => {
  HTMLCanvasElement.prototype.getContext = real;
});

function drawWith(el: React.ReactElement): Op[] {
  const rec = recorder();
  HTMLCanvasElement.prototype.getContext = (() => rec.ctx) as unknown as HTMLCanvasElement["getContext"];
  render(el);
  return rec.ops;
}

const near = (a: number, b: number) => Math.abs(a - b) < 1e-6;
const dotsAt = (ops: Op[], pts: { x: number; y: number }[]) =>
  pts.filter((p) =>
    ops.some((o) => o.op === "arc" && near(o.args[0], p.x) && near(o.args[1], p.y) && o.args[2] === 1.5),
  ).length;
const linesTo = (ops: Op[], pts: { x: number; y: number }[]) =>
  pts.filter((p) =>
    ops.some((o) => o.op === "lineTo" && near(o.args[0], p.x) && near(o.args[1], p.y)),
  ).length;

// --- Smith chart ------------------------------------------------------------

const Z0 = 50;
const SIZE = 220;
const R = SIZE / 2 - 10;

/** A locus circling Γ = 0 at |Γ| = 0.6, `stepDeg` per sample: a remote tuner
 *  plus a window line rotates this fast (the doublet_autotuner report). */
function loop(stepDeg: number): { sweep: SweepData; screen: { x: number; y: number }[] } {
  const freqs: number[] = [];
  const zr: number[] = [];
  const zi: number[] = [];
  const screen: { x: number; y: number }[] = [];
  for (let k = 0, a = 0; a <= 320 + 1e-9; k++, a += stepDeg) {
    const t = (a * Math.PI) / 180;
    const g = { re: 0.6 * Math.cos(t), im: 0.6 * Math.sin(t) };
    // Z = Z0 (1 + Γ) / (1 − Γ)
    const nr = 1 + g.re;
    const ni = g.im;
    const dr = 1 - g.re;
    const di = -g.im;
    const den = dr * dr + di * di;
    zr.push((Z0 * (nr * dr + ni * di)) / den);
    zi.push((Z0 * (ni * dr - nr * di)) / den);
    freqs.push(14 + 0.001 * k);
    screen.push({ x: SIZE / 2 + g.re * R, y: SIZE / 2 - g.im * R });
  }
  return { sweep: { freqs_mhz: freqs, z_re: zr, z_im: zi }, screen };
}

function smith(sweep: SweepData): Op[] {
  return drawWith(
    <SmithChart
      r={0}
      x={0}
      z0={Z0}
      size={SIZE}
      sweep={sweep}
      paramSweep={null}
      measured={null}
      measFreqMhz={14}
      running={false}
      paramSweepRunning={false}
      multiFeed={false}
      connectSweep
    />,
  );
}

describe("Smith chart, connected sweep", () => {
  it("a coarse fast-rotating locus is dots, not chords", () => {
    const { sweep, screen } = loop(40);
    const ops = smith(sweep);
    // Every interior vertex turns 40°: no segment survives, every sample dots.
    expect(linesTo(ops, screen)).toBe(0);
    expect(dotsAt(ops, screen)).toBe(screen.length);
  });

  it("a well-sampled locus is one line with no dots", () => {
    const { sweep, screen } = loop(1);
    const ops = smith(sweep);
    expect(linesTo(ops, screen.slice(1))).toBe(screen.length - 1);
    expect(dotsAt(ops, screen)).toBe(0);
  });
});

// --- VSWR chart -------------------------------------------------------------

describe("VSWR chart", () => {
  const BASE = {
    mode: "vswr" as const,
    r: 0,
    x: 0,
    z0: 50,
    size: 236,
    measFreqMhz: 14.2,
    running: false,
    multiFeed: false,
  };
  const freqs = Array.from({ length: 21 }, (_, i) => 13.7 + i * 0.05);

  it("a zigzag between samples breaks and dots; a smooth sweep does not", () => {
    // Alternating reactance: VSWR jumps up and down sample to sample.
    const zig: SweepData = {
      freqs_mhz: freqs,
      z_re: freqs.map(() => 50),
      z_im: freqs.map((_, i) => (i % 2 ? 40 : 0)),
    };
    const smooth: SweepData = {
      freqs_mhz: freqs,
      z_re: freqs.map((f) => 50 + 20 * (f - 13.7)),
      z_im: freqs.map(() => 0),
    };
    const arcs = (ops: Op[]) => ops.filter((o) => o.op === "arc" && o.args[2] === 1.5).length;
    expect(arcs(drawWith(<SweepChart {...BASE} sweep={zig} />))).toBeGreaterThan(10);
    expect(arcs(drawWith(<SweepChart {...BASE} sweep={smooth} />))).toBe(0);
  });
});
