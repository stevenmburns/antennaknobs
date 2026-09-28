// AK#1781: the workbench and the CLI compute Z∞ with the SAME estimator.
// fixtures/zinfVectors.json is generated from the Python implementation
// (its `generator` field is the command); tests/test_zinf_vectors_1781.py
// holds the Python side to the same file. Adding a case there gates both.

import { describe, expect, it } from "vitest";
import vectors from "./fixtures/zinfVectors.json";
import { feedwiseZinf, zinfEstimate, zinfSuffix, type ZInfStatus } from "../lib/zinf";

type Case = {
  name: string;
  x: number[];
  re: number[];
  im: number[];
  expected: { re: number | null; im: number | null; p: number | null; status: ZInfStatus };
};

const CASES = (vectors as { cases: Case[] }).cases;
const REL = 1e-12;

const close = (got: number, want: number, scale: number) =>
  Math.abs(got - want) <= REL * Math.max(1, Math.abs(scale));

describe("zinfEstimate against the shared vectors", () => {
  it("covers every status", () => {
    expect(new Set(CASES.map((c) => c.expected.status))).toEqual(
      new Set(["insufficient", "converged", "asymptotic", "rough"]),
    );
  });

  for (const c of CASES) {
    it(c.name, () => {
      const got = zinfEstimate(c.x, c.re, c.im);
      const want = c.expected;
      expect(got.status).toBe(want.status);
      if (want.p == null) expect(got.p).toBeNull();
      else expect(close(got.p!, want.p, want.p)).toBe(true);
      if (want.re == null || want.im == null) {
        expect(got.re).toBeNull();
        expect(got.im).toBeNull();
      } else {
        const scale = Math.hypot(want.re, want.im);
        expect(close(got.re!, want.re, scale), `re ${got.re} vs ${want.re}`).toBe(true);
        expect(close(got.im!, want.im, scale), `im ${got.im} vs ${want.im}`).toBe(true);
      }
    });
  }
});

describe("feedwiseZinf", () => {
  it("runs the estimator per feed on complex Z, one p per feed", () => {
    const x = [10, 20, 40, 80, 160];
    // Feed 0 converges at p = 1, feed 1 at p = 2.
    const f = (p: number, k: number, zr: number, zi: number) => [
      zr + 3 * x[k] ** -p,
      zi - 2 * x[k] ** -p,
    ];
    const re = x.map((_, k) => [f(1, k, 50, 10)[0], f(2, k, 70, -5)[0]]);
    const im = x.map((_, k) => [f(1, k, 50, 10)[1], f(2, k, 70, -5)[1]]);
    const [a, b] = feedwiseZinf(x, re, im);
    expect(a.status).toBe("asymptotic");
    expect(b.status).toBe("asymptotic");
    expect(a.p).toBeCloseTo(1, 9);
    expect(b.p).toBeCloseTo(2, 9);
    expect(a.re).toBeCloseTo(50, 9);
    expect(b.im).toBeCloseTo(-5, 9);
  });
});

describe("zinfSuffix", () => {
  it("names the order, the rough fallback, or nothing", () => {
    expect(zinfSuffix("asymptotic", 0.9754)).toBe(" · p 0.98");
    expect(zinfSuffix("rough", null)).toBe(" · rough");
    expect(zinfSuffix("converged", null)).toBe("");
    expect(zinfSuffix(null, null)).toBe("");
  });
});
