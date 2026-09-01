// Pins modelOptionsForRequest's per-backend request-shape contract with the
// server: which snake_case keys each backend sends, and that feed_model is
// sent ONLY for the sin-galerkin panel. These are the SAME assertions as
// before the roster refactor (issue #628) — the wire is a contract with
// _make_momwire_sim and must not have moved; only the fixtures changed, from
// module constants to roster entries.
import { describe, it, expect } from "vitest";
import {
  BSPLINE_DEFAULT_OPTS,
  defaultOptsFor,
  modelOptionsForRequest,
  type BSplineOpts,
} from "../lib/backends";
import { backendEntry, backendOption, entry } from "./backendFixtures";

describe("modelOptionsForRequest", () => {
  it("sinusoidal-galerkin sends exactly n_qp_const and feed_model", () => {
    const b = entry("sinusoidal-galerkin");
    const result = modelOptionsForRequest(b, {
      ...defaultOptsFor(b),
      schema: { n_qp_const: 11 },
      feedModel: "point",
    });
    expect(Object.keys(result).sort()).toEqual(["feed_model", "n_qp_const"]);
    expect(result).toEqual({ n_qp_const: 11, feed_model: "point" });
  });

  it("plain sinusoidal sends exactly n_qp_const, and feed_model is ABSENT", () => {
    const b = entry("sinusoidal");
    const result = modelOptionsForRequest(b, {
      ...defaultOptsFor(b),
      schema: { n_qp_const: 7 },
    });
    expect(Object.keys(result).sort()).toEqual(["n_qp_const"]);
    expect(result).toEqual({ n_qp_const: 7 });
    expect(result).not.toHaveProperty("feed_model");
  });

  it("bspline sends exactly the ten snake_case b-spline kwargs, values mapped from camelCase", () => {
    const bspline: BSplineOpts = {
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
    const result = modelOptionsForRequest(entry("bspline"), {
      nPerWire: 15, // not forwarded — geometry sizing, not a model kwarg
      wireRadius: 0.0005, // not forwarded
      schema: {},
      bspline,
    });
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
    for (const name of ["hmatrix", "arrayblock"]) {
      const b = entry(name);
      const result = modelOptionsForRequest(b, defaultOptsFor(b));
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
    const b = entry("pynec");
    expect(modelOptionsForRequest(b, defaultOptsFor(b))).toEqual({});
  });

  // Byte-level regression guard for the refactor: the serialized request body
  // for every real backend at its stock settings, key order included. The
  // server reads these as constructor kwargs, so a reordering is harmless but
  // a rename or a dropped key is not — and JSON equality catches both.
  it("serializes each backend's stock options exactly as before the refactor", () => {
    const stock = (name: string) => {
      const b = entry(name);
      return JSON.stringify(modelOptionsForRequest(b, defaultOptsFor(b)));
    };
    // n_qp_pair is 8, not the 4 this pinned until momwire 0.45.0: momwire#758
    // raised its own cross-edge default and this value is sent
    // unconditionally, so leaving it at 4 would have silently overridden the
    // library for every hosted solve (antennaknobs#1064).
    const BSPLINE_JSON =
      '{"degree":2,"n_qp_pair":8,"n_qp_source":16,"feed_smoothing_factor":null,' +
      '"use_singular_enrichment":false,"enrichment_variant":"raw",' +
      '"tikhonov_lambda":0.1,"auto_tap_ratio_threshold":0.3,"n_qp_sing":32,' +
      '"enrichment_min_k":3}';
    expect(stock("sinusoidal")).toBe('{"n_qp_const":8}');
    // "point" since momwire#654 made it the solver's default — the wire
    // format still carries the value explicitly, so a request says which
    // source ran regardless of which momwire the server has.
    expect(stock("sinusoidal-galerkin")).toBe(
      '{"n_qp_const":8,"feed_model":"point"}',
    );
    expect(stock("bspline")).toBe(BSPLINE_JSON);
    expect(stock("hmatrix")).toBe(BSPLINE_JSON);
    expect(stock("arrayblock")).toBe(BSPLINE_JSON);
    expect(stock("pynec")).toBe("{}");
  });

  it("falls back to the served default for a knob the slot has never touched", () => {
    const b = backendEntry({
      name: "fake-solver",
      options_schema: [backendOption({ key: "n_qp_const", default: 5 })],
    });
    expect(modelOptionsForRequest(b, { nPerWire: 30, wireRadius: 5e-4, schema: {} })).toEqual({
      n_qp_const: 5,
    });
  });

  // --- the extended thin-wire kernel (issue #849) --------------------------
  //
  // The wire key is `extended_kernel`, which adapter.py pulls back out of
  // model_options and passes as MomwireEngine's named constructor kwarg. The
  // contract that matters here is the ASYMMETRY: present-and-true when armed,
  // absent otherwise — never `false`. The stock-JSON test above is the guard
  // for the "absent" half, and it is unchanged by #849 on purpose.
  describe("extended_kernel", () => {
    const armed = (name: string) => ({
      ...defaultOptsFor(entry(name)),
      extendedKernel: true,
    });

    it("rides as `extended_kernel: true` on every basis that serves it", () => {
      for (const name of ["sinusoidal", "bspline", "hmatrix", "arrayblock"]) {
        expect(modelOptionsForRequest(entry(name), armed(name))).toHaveProperty(
          "extended_kernel",
          true,
        );
      }
    });

    it("is ABSENT — not false — with the toggle off", () => {
      for (const name of ["sinusoidal", "bspline", "hmatrix", "arrayblock"]) {
        const b = entry(name);
        expect(modelOptionsForRequest(b, defaultOptsFor(b))).not.toHaveProperty(
          "extended_kernel",
        );
        // …and explicitly off is the same request as never armed: toggling on
        // and back off must return to the pre-#849 body byte for byte.
        expect(
          JSON.stringify(
            modelOptionsForRequest(b, {
              ...defaultOptsFor(b),
              extendedKernel: false,
            }),
          ),
        ).toBe(JSON.stringify(modelOptionsForRequest(b, defaultOptsFor(b))));
      }
    });

    it("reaches the wire on Galerkin, never alongside enrichment (momwire#271)", () => {
      // Galerkin serves the kernel since momwire 0.27.0 (momwire#246/#287/
      // #299) — an armed slot sends it like any other basis.
      expect(
        modelOptionsForRequest(
          entry("sinusoidal-galerkin"),
          armed("sinusoidal-galerkin"),
        ),
      ).toEqual({ n_qp_const: 8, feed_model: "point", extended_kernel: true });
      // Singular enrichment: momwire#271. Sending both would be a refusal at
      // engine construction; the UI greys the pair out, and this is the lock
      // behind that.
      const enriched = {
        ...armed("bspline"),
        bspline: { ...BSPLINE_DEFAULT_OPTS, useSingularEnrichment: true },
      };
      const out = modelOptionsForRequest(entry("bspline"), enriched);
      expect(out.use_singular_enrichment).toBe(true);
      expect(out).not.toHaveProperty("extended_kernel");
    });

    it("stays off the wire for pynec, which sends no model_options", () => {
      expect(modelOptionsForRequest(entry("pynec"), armed("pynec"))).toEqual({});
    });
  });

  it("uses the panel's own defaults when a b-spline slot carries no panel state", () => {
    const result = modelOptionsForRequest(entry("bspline"), {
      nPerWire: 30,
      wireRadius: 5e-4,
      schema: {},
    });
    expect(result.degree).toBe(BSPLINE_DEFAULT_OPTS.degree);
    expect(result.n_qp_pair).toBe(BSPLINE_DEFAULT_OPTS.nQpPair);
  });
});
