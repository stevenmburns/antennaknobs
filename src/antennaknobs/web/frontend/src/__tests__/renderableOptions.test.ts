/**
 * THE OFFERED-VS-SENT RULE, as a test (#1006 G2-6).
 *
 * The rule, from `lib/backends.ts`:
 *
 *   1. `model_kwargs` says what may be SENT.
 *   2. Where an axis exists, the axis decides whether a control is OFFERED.
 *   3. Where no axis exists, `model_kwargs` drives.
 *
 * Rule 2 is the one a generic renderer drops by accident, and dropping it is a
 * behaviour CHANGE dressed as a refactor. The two cases below are the ones
 * that would actually ship wrong: `bspline` accepts `feed_model` and has never
 * offered a feed-model control, and `razor-2p` accepts `degree` while its
 * basis axis holds only "tent".
 */
import { describe, expect, it } from "vitest";

import {
  renderableOptions,
  specShown,
  type BackendEntry,
  type ModelOptionSpecs,
} from "../lib/backends";
import { entry } from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const SPECS: ModelOptionSpecs = SERVED_OPTION_SPECS;

describe("rule 2 — an axis governs whether its kwarg is offered", () => {
  it("does NOT offer feed_model on bspline, which accepts the kwarg", () => {
    const b = entry("bspline");
    // Both halves of the trap, asserted so neither can drift silently:
    expect(b.model_kwargs).toContain("feed_model");
    expect(b.axes!.feed_model).toEqual(["segment-gap"]);
    expect(renderableOptions(b, SPECS)).not.toContain("feed_model");
  });

  it("DOES offer feed_model on sinusoidal-galerkin, which has the choice", () => {
    // The other side of the same rule — without this, "never offer
    // feed_model" would pass and be wrong.
    const b = entry("sinusoidal-galerkin");
    expect(b.axes!.feed_model).toEqual(["point-gap", "segment-gap"]);
    expect(renderableOptions(b, SPECS)).toContain("feed_model");
  });

  it("does NOT offer degree on razor-2p, which accepts the kwarg", () => {
    const b = entry("razor-2p");
    expect(b.model_kwargs).toContain("degree");
    expect(b.axes!.basis).toEqual(["tent"]);
    expect(renderableOptions(b, SPECS)).not.toContain("degree");
  });

  it("DOES offer degree on bspline, whose basis axis has two values", () => {
    expect(renderableOptions(entry("bspline"), SPECS)).toContain("degree");
  });
});

describe("rule 3 — a kwarg no axis governs is driven by the kwarg list", () => {
  it("offers the quadrature and enrichment knobs on the bspline family", () => {
    const got = renderableOptions(entry("bspline"), SPECS);
    for (const k of [
      "n_qp_pair",
      "n_qp_source",
      "n_qp_sing",
      "feed_smoothing_factor",
      "use_singular_enrichment",
      "enrichment_variant",
      "tikhonov_lambda",
      "auto_tap_ratio_threshold",
      "enrichment_min_k",
    ]) {
      expect(got).toContain(k);
    }
  });

  it("offers n_qp_const on the sinusoidal family and NOT on the bspline one", () => {
    // The asymmetry that looks like a mistake, pinned on both sides.
    expect(renderableOptions(entry("sinusoidal"), SPECS)).toContain("n_qp_const");
    expect(renderableOptions(entry("bspline"), SPECS)).not.toContain("n_qp_const");
  });

  it("offers nothing for a backend that takes no kwargs", () => {
    expect(renderableOptions(entry("pynec"), SPECS)).toEqual([]);
  });
});

describe("a momwire that cannot describe its axes keeps its knobs", () => {
  it("falls back to the kwarg list rather than hiding every axis knob", () => {
    // `axes: null` is the RELEASED momwire (the pointer runs ahead of the pin).
    // Applying rule 2 with an empty `axisControls` would hide `degree` — a
    // control that momwire has always shown — so the fallback is what stops
    // this refactor regressing every installed user.
    const legacy: BackendEntry = { ...entry("bspline"), axes: null };
    const got = renderableOptions(legacy, SPECS);
    expect(got).toContain("degree");
    // ...and it still cannot invent a knob the backend does not accept.
    expect(got).not.toContain("n_qp_const");
  });
});

describe("specShown — pure UI gating, evaluated against live values", () => {
  it("hides the enrichment sub-form until enrichment is on", () => {
    const variant = SPECS.enrichment_variant;
    expect(variant.shown_when).toBe("use_singular_enrichment");
    expect(specShown(variant, { use_singular_enrichment: false })).toBe(false);
    expect(specShown(variant, { use_singular_enrichment: true })).toBe(true);
  });

  it("shows an ungated spec regardless of values", () => {
    expect(SPECS.degree.shown_when).toBeNull();
    expect(specShown(SPECS.degree, {})).toBe(true);
  });

  it("never encodes a REFUSAL — the EK exclusion is not a shown_when", () => {
    // momwire#888 put that exclusion in the served constraints where it
    // belongs. A `shown_when: "not extended_kernel"` here would be the
    // retyped-prose failure one layer up, and the Python side asserts the
    // same thing from its end.
    for (const spec of Object.values(SPECS)) {
      expect(spec.shown_when).not.toBe("extended_kernel");
    }
  });
});
