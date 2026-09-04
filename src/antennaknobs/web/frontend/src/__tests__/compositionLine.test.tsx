/**
 * The composition line (#1006 G2-7) — point 2 made visible.
 *
 * Everything before this was equivalence-gated and looked identical to a user
 * by design. This is the first change they are meant to SEE, and its job is to
 * say what an engine is made of. A line that says something FALSE about the
 * engine is therefore worse than no line: it speaks with authority.
 *
 * SNAPSHOTTED AS AN ORDERED LIST OF SEGMENTS, never a set and never one
 * joined string. Ordered because a per-item comparison cannot see a
 * reordering — that is exactly what let `degree` migrate to the bottom of the
 * panel in #1163 with 29 green assertions — and for a line whose whole point
 * is word order, a set-shaped snapshot would go green on a shuffled sentence.
 * Segments rather than a string so a diff names the axis that changed.
 */
import { describe, expect, it } from "vitest";

import { compositionLine, type BackendEntry } from "../lib/backends";
import { entry, optsWithModel, SERVED_ROSTER, SERVED_VOCAB } from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";
import { defaultOptsFor } from "../lib/backends";

const stock = (name: string) => defaultOptsFor(entry(name), SERVED_OPTION_SPECS);
const text = (name: string, opts = stock(name)) =>
  (compositionLine(entry(name), opts, SERVED_VOCAB) ?? []).map((s) =>
    s.pinned ? `${s.text}, pinned` : s.text,
  );

describe("the default line per tab", () => {
  it("bspline", () => {
    expect(text("bspline")).toEqual([
      "degree 2",
      "Galerkin",
      "reduced kernel",
      "converged quadrature",
      "dense",
      "segment gap",
    ]);
  });

  it("the b-spline trio differ in exactly ONE segment", () => {
    // #1006 point 2 in a single assertion: three tabs, one word. This is the
    // argument for the feature, so it is asserted rather than described.
    const [a, b, c] = ["bspline", "hmatrix", "arrayblock"].map((n) => text(n));
    const differing = a!.map((_, i) => i).filter((i) => !(a![i] === b![i] && b![i] === c![i]));
    expect(differing).toHaveLength(1);
    expect([a![differing[0]!], b![differing[0]!], c![differing[0]!]]).toEqual([
      "dense",
      "ACA",
      "element-block",
    ]);
  });

  it("the sinusoidal pair differ in ONE structural segment, plus its consequence", () => {
    // I first asserted "exactly one", from the design narrative rather than
    // the data, and it is TWO: `testing` and `feed_model`. The second is not
    // a second difference — it FOLLOWS from the first. Point matching has no
    // collocation RHS for a zero-width gap (momwire#212), so the
    // point-matched tab is fixed at the segment gap while its Galerkin
    // sibling is free and defaults to the point gap.
    //
    // Asserting the tidier story would have been asserting a story. The line
    // is worth having precisely because it shows the consequence too.
    const [a, b] = ["sinusoidal", "sinusoidal-galerkin"].map((n) => text(n));
    const differing = a!.map((_, i) => i).filter((i) => a![i] !== b![i]);
    expect(differing.map((i) => [a![i], b![i]])).toEqual([
      ["point-matched", "Galerkin"],
      ["segment gap", "point gap"],
    ]);

    // ...and with the free axis set to match, the STRUCTURAL difference is
    // the only one left — which is the claim that actually matters.
    const matched = text(
      "sinusoidal-galerkin",
      optsWithModel("sinusoidal-galerkin", { feed_model: "segment" }),
    );
    const structural = a!.map((_, i) => i).filter((i) => a![i] !== matched[i]);
    expect(structural.map((i) => [a![i], matched[i]])).toEqual([
      ["point-matched", "Galerkin"],
    ]);

    // The fixed-vs-free fact behind it, so the explanation cannot rot.
    expect(entry("sinusoidal").axes!.feed_model).toEqual(["segment-gap"]);
    expect(entry("sinusoidal-galerkin").axes!.feed_model).toHaveLength(2);
  });

  it("razor-2p marks its pinned axis and ONLY that one", () => {
    // The rule the design corrected: an axis is pinned iff ITS value was
    // resolved as bound, not "bound is non-empty". razor binds
    // nec5_quadrature alone — its kernel is free, and a segment reading
    // "reduced kernel, pinned" would assert a constraint the engine lacks.
    const segs = compositionLine(entry("razor-2p"), stock("razor-2p"), SERVED_VOCAB)!;
    const pinned = segs.filter((s) => s.pinned).map((s) => s.axis);
    expect(pinned).toEqual(["quadrature"]);
    expect(text("razor-2p")).toContain("two-point quadrature, pinned");
    expect(text("razor-2p")).toContain("reduced kernel");
    expect(text("razor-2p")).not.toContain("reduced kernel, pinned");
  });

  it("pynec and nec5 get NO line at all, never a fabricated one", () => {
    for (const n of ["pynec", "nec5"]) {
      const b = SERVED_ROSTER.find((x) => x.name === n) ?? entry("pynec");
      expect(compositionLine(b, stock("pynec"), SERVED_VOCAB)).toBeNull();
    }
  });
});

describe("a moved control rewrites its one segment, in place", () => {
  it("degree", () => {
    const before = text("bspline");
    const after = text("bspline", optsWithModel("bspline", { degree: 1 }));
    expect(after[0]).toBe("degree 1");
    expect(after.slice(1)).toEqual(before.slice(1));
  });

  it("kernel", () => {
    const before = text("bspline");
    const after = text("bspline", optsWithModel("bspline", { extended_kernel: true }));
    expect(after[2]).toBe("extended kernel");
    expect(after.filter((_, i) => i !== 2)).toEqual(
      before.filter((_, i) => i !== 2),
    );
  });

  it("feed model, where it is free", () => {
    const before = text("sinusoidal-galerkin");
    const after = text(
      "sinusoidal-galerkin",
      optsWithModel("sinusoidal-galerkin", { feed_model: "segment" }),
    );
    const moved = before.map((_, i) => i).filter((i) => before[i] !== after[i]);
    expect(moved).toHaveLength(1);
    expect([before[moved[0]!], after[moved[0]!]]).toEqual([
      "point gap",
      "segment gap",
    ]);
  });

  it("a PINNED axis never moves, whatever the options say", () => {
    // The pin marker only means something if the segment is actually immune.
    const before = text("razor-2p");
    const after = text("razor-2p", optsWithModel("razor-2p", { extended_kernel: true }));
    const q = (l: string[]) => l.find((x) => x.includes("quadrature"));
    expect(q(after)).toBe(q(before));
    expect(q(after)).toBe("two-point quadrature, pinned");
  });
});

describe("the line describes the ENGINE, not the deck", () => {
  it("carries no derived axis, so a design switch cannot change it", () => {
    // `ground_model` and `wire_position` are the deck's. A line that changed
    // when you switched design would be describing the wrong thing — and the
    // constraint notes, which DO change, are the right place for that.
    for (const b of SERVED_ROSTER) {
      const segs = compositionLine(b, stock(b.name), SERVED_VOCAB);
      if (!segs) continue;
      const axes = segs.map((s) => s.axis);
      expect(axes).not.toContain("ground_model");
      expect(axes).not.toContain("wire_position");
    }
  });

  it("states no axis the server did not order, and keeps that order", () => {
    for (const b of SERVED_ROSTER) {
      const segs = compositionLine(b, stock(b.name), SERVED_VOCAB);
      if (!segs) continue;
      const axes = segs.map((s) => s.axis);
      expect(axes).toEqual(SERVED_VOCAB.axes.filter((a) => axes.includes(a)));
    }
  });

  it("renders nothing rather than guessing when the vocabulary is empty", () => {
    // A server predating G2-7 serves no axes and no labels. An empty line is
    // the honest answer; a line assembled from raw momwire tokens would leak
    // internal vocabulary into a sentence.
    const empty = { axes: [], labels: {} };
    expect(compositionLine(entry("bspline"), stock("bspline"), empty)).toEqual([]);
  });

  it("skips a value the server has no phrase for", () => {
    const partial = { axes: ["basis", "testing"], labels: { testing: SERVED_VOCAB.labels.testing! } };
    const segs = compositionLine(entry("bspline"), stock("bspline"), partial)!;
    expect(segs.map((s) => s.axis)).toEqual(["testing"]);
  });
});

describe("the fixed/free/pinned kinds", () => {
  it("marks single-valued axes as the tab's identity", () => {
    const segs = compositionLine(entry("bspline"), stock("bspline"), SERVED_VOCAB)!;
    const byAxis = Object.fromEntries(segs.map((s) => [s.axis, s]));
    expect(byAxis.testing!.fixed).toBe(true);
    expect(byAxis.basis!.fixed).toBe(false);
    expect(byAxis.kernel!.fixed).toBe(false);
  });

  it("a legacy backend with null axes yields null, not an empty line", () => {
    // Empty means "described, and it said nothing"; null means "cannot be
    // asked". The component renders those differently and inferring one from
    // the other is #1103's rule.
    const legacy: BackendEntry = { ...entry("bspline"), axes: null };
    expect(compositionLine(legacy, stock("bspline"), SERVED_VOCAB)).toBeNull();
  });
});
