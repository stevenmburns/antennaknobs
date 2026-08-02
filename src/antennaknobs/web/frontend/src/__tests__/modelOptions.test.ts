// Pins modelOptionsForRequest's per-backend request-shape contract with the
// server (issue #642 step 2): which snake_case keys each backend sends, and
// that feed_model is sent ONLY for sinusoidal-galerkin.
import { describe, it, expect } from "vitest";
import {
  DEFAULT_BACKEND_OPTS,
  modelOptionsForRequest,
  type BSplineOpts,
  type SinGalerkinOpts,
} from "../App";

describe("modelOptionsForRequest", () => {
  it("sinusoidal-galerkin sends exactly n_qp_const and feed_model", () => {
    const opts: SinGalerkinOpts = {
      ...DEFAULT_BACKEND_OPTS["sinusoidal-galerkin"],
      nQpConst: 11,
      feedModel: "point",
    };
    const result = modelOptionsForRequest("sinusoidal-galerkin", opts);
    expect(Object.keys(result).sort()).toEqual(["feed_model", "n_qp_const"]);
    expect(result).toEqual({ n_qp_const: 11, feed_model: "point" });
  });

  it("plain sinusoidal sends exactly n_qp_const, and feed_model is ABSENT", () => {
    const opts = { ...DEFAULT_BACKEND_OPTS.sinusoidal, nQpConst: 7 };
    const result = modelOptionsForRequest("sinusoidal", opts);
    expect(Object.keys(result).sort()).toEqual(["n_qp_const"]);
    expect(result).toEqual({ n_qp_const: 7 });
    expect(result).not.toHaveProperty("feed_model");
  });

  it("bspline sends exactly the ten snake_case b-spline kwargs, values mapped from camelCase", () => {
    const opts: BSplineOpts = {
      nPerWire: 15, // not forwarded — geometry sizing, not a model kwarg
      wireRadius: 0.0005, // not forwarded
      degree: 1,
      nQpPair: 5,
      feedSmoothingFactor: 0.25,
      useSingularEnrichment: true,
      enrichmentVariant: "tikhonov",
      tikhonovLambda: 0.42,
      autoTapRatioThreshold: 0.31,
      nQpSing: 40,
      enrichmentMinK: 4,
      nQpSource: 17,
    };
    const result = modelOptionsForRequest("bspline", opts);
    expect(Object.keys(result).sort()).toEqual(
      [
        "auto_tap_ratio_threshold",
        "degree",
        "enrichment_min_k",
        "enrichment_variant",
        "feed_smoothing_factor",
        "n_qp_pair",
        "n_qp_sing",
        "n_qp_source",
        "tikhonov_lambda",
        "use_singular_enrichment",
      ].sort(),
    );
    expect(result).toEqual({
      degree: 1,
      n_qp_pair: 5,
      n_qp_source: 17,
      feed_smoothing_factor: 0.25,
      use_singular_enrichment: true,
      enrichment_variant: "tikhonov",
      tikhonov_lambda: 0.42,
      auto_tap_ratio_threshold: 0.31,
      n_qp_sing: 40,
      enrichment_min_k: 4,
    });
    expect(result).not.toHaveProperty("feed_model");
  });

  it("hmatrix and arrayblock (the rest of the b-spline family) get the same ten keys", () => {
    for (const backend of ["hmatrix", "arrayblock"] as const) {
      const opts = DEFAULT_BACKEND_OPTS[backend];
      const result = modelOptionsForRequest(backend, opts);
      expect(Object.keys(result).sort()).toEqual(
        [
          "auto_tap_ratio_threshold",
          "degree",
          "enrichment_min_k",
          "enrichment_variant",
          "feed_smoothing_factor",
          "n_qp_pair",
          "n_qp_sing",
          "n_qp_source",
          "tikhonov_lambda",
          "use_singular_enrichment",
        ].sort(),
      );
      expect(result).not.toHaveProperty("feed_model");
    }
  });

  it("pynec sends no model_options at all", () => {
    const result = modelOptionsForRequest("pynec", DEFAULT_BACKEND_OPTS.pynec);
    expect(result).toEqual({});
    expect(Object.keys(result)).toHaveLength(0);
  });
});
