// Pins modelOptionsForRequest's per-backend request-shape contract with the
// server: which snake_case keys each backend sends, and that feed_model is
// sent ONLY for the sin-galerkin panel. These are the SAME assertions as
// before the roster refactor (issue #628) — the wire is a contract with
// _make_momwire_sim and must not have moved; only the fixtures changed, from
// module constants to roster entries.
import { describe, it, expect } from "vitest";
import {
  defaultOptsFor,
  modelOptionsForRequest,
} from "../lib/backends";
import {
  backendEntry,
  backendOption,
  entry,
  optsWithModel,
} from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

describe("modelOptionsForRequest", () => {
  it("sinusoidal-galerkin sends exactly n_qp_const and feed_model", () => {
    const b = entry("sinusoidal-galerkin");
    const result = modelOptionsForRequest(b, {
      ...defaultOptsFor(b, SERVED_OPTION_SPECS),
      model: { n_qp_const: 11, feed_model: "point" },
    }, SERVED_OPTION_SPECS);
    expect(Object.keys(result).sort()).toEqual(["feed_model", "n_qp_const"]);
    expect(result).toEqual({ n_qp_const: 11, feed_model: "point" });
  });

  it("plain sinusoidal sends exactly n_qp_const, and feed_model is ABSENT", () => {
    const b = entry("sinusoidal");
    const result = modelOptionsForRequest(b, {
      ...defaultOptsFor(b, SERVED_OPTION_SPECS),
      model: { n_qp_const: 7 },
    }, SERVED_OPTION_SPECS);
    expect(Object.keys(result).sort()).toEqual(["n_qp_const"]);
    expect(result).toEqual({ n_qp_const: 7 });
    expect(result).not.toHaveProperty("feed_model");
  });

  it("bspline sends exactly the ten snake_case b-spline kwargs, values mapped from camelCase", () => {
    const model = {
      degree: 1,
      n_qp_pair: 5,
      feed_smoothing_factor: 0.25,
      use_singular_enrichment: true,
      enrichment_variant: "tikhonov",
      tikhonov_lambda: 0.42,
      auto_tap_ratio_threshold: 0.31,
      n_qp_sing: 40,
      enrichment_min_k: 4,
      n_qp_source: 17,
    };
    const result = modelOptionsForRequest(entry("bspline"), {
      nPerWire: 15, // not forwarded — geometry sizing, not a model kwarg
      wireRadius: 0.0005, // not forwarded
      model,
    }, SERVED_OPTION_SPECS);
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

  // Nine, not ten: `n_qp_pair` is absent at stock settings because it defaults
  // to auto and is only sent when pinned (antennaknobs#1064, momwire#863).
  it("hmatrix and arrayblock (the rest of the b-spline family) get the same nine keys", () => {
    for (const name of ["hmatrix", "arrayblock"]) {
      const b = entry(name);
      const result = modelOptionsForRequest(b, defaultOptsFor(b, SERVED_OPTION_SPECS), SERVED_OPTION_SPECS);
      expect(Object.keys(result).sort()).toEqual(
        [
          "auto_tap_ratio_threshold",
          "degree",
          "enrichment_min_k",
          "enrichment_variant",
          "feed_smoothing_factor",
          "n_qp_sing",
          "n_qp_source",
          "tikhonov_lambda",
          "use_singular_enrichment",
        ].sort(),
      );
      // ...and pinning it puts the tenth key back on the wire.
      const pinned = modelOptionsForRequest(b, {
        ...defaultOptsFor(b, SERVED_OPTION_SPECS),
        model: {
          ...defaultOptsFor(b, SERVED_OPTION_SPECS).model,
          n_qp_pair: 16,
        },
      }, SERVED_OPTION_SPECS);
      expect(pinned.n_qp_pair).toBe(16);
      expect(result).not.toHaveProperty("feed_model");
    }
  });

  it("pynec sends no model_options at all", () => {
    const b = entry("pynec");
    expect(modelOptionsForRequest(b, defaultOptsFor(b, SERVED_OPTION_SPECS), SERVED_OPTION_SPECS)).toEqual({});
  });

  // Byte-level regression guard for the refactor: the serialized request body
  // for every real backend at its stock settings, key order included. The
  // server reads these as constructor kwargs, so a reordering is harmless but
  // a rename or a dropped key is not — and JSON equality catches both.
  it("serializes each backend's stock options exactly as before the refactor", () => {
    const stock = (name: string) => {
      const b = entry(name);
      return JSON.stringify(modelOptionsForRequest(b, defaultOptsFor(b, SERVED_OPTION_SPECS), SERVED_OPTION_SPECS));
    };
    // n_qp_pair is ABSENT, and that is the assertion. It pinned 4 until
    // momwire 0.45.0 and then 8; both silently overrode the library for every
    // hosted solve, which is antennaknobs#1064. Since momwire#863 the default
    // depends on the GEOMETRY (32 with wire below the interface, 8 otherwise),
    // so no literal here can track it and the key is omitted instead.
    const BSPLINE_JSON =
      '{"degree":2,"n_qp_source":16,"feed_smoothing_factor":null,' +
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

  it("takes a never-touched knob default from the CATALOGUE, not the entry", () => {
    // CHANGED DELIBERATELY in #1006 G2-6: the per-entry
    // `options_schema.default` is no longer the source. Defaults come from
    // the served spec catalogue, keyed by kwarg, because the same knob means
    // the same thing on every backend that exposes it — a per-entry default
    // is the duplication this unit removes. Every real backend's schema
    // default already agreed with the catalogue, so nothing on the wire
    // moved; only a fabricated entry like this one can tell the difference.
    const b = backendEntry({
      name: "fake-solver",
      model_kwargs: ["n_qp_const"],
      options_schema: [backendOption({ key: "n_qp_const", default: 5 })],
    });
    expect(
      modelOptionsForRequest(
        b,
        { nPerWire: 30, wireRadius: 5e-4, model: {} },
        SERVED_OPTION_SPECS,
      ),
    ).toEqual({ n_qp_const: SERVED_OPTION_SPECS.n_qp_const.default });
  });

  // --- the extended thin-wire kernel (issue #849) --------------------------
  //
  // The wire key is `extended_kernel`, which adapter.py pulls back out of
  // model_options and passes as MomwireEngine's named constructor kwarg. The
  // contract that matters here is the ASYMMETRY: present-and-true when armed,
  // absent otherwise — never `false`. The stock-JSON test above is the guard
  // for the "absent" half, and it is unchanged by #849 on purpose.
  describe("extended_kernel", () => {
    const armed = (name: string) => optsWithModel(name, { extended_kernel: true });

    it("rides as `extended_kernel: true` on every basis that serves it", () => {
      for (const name of ["sinusoidal", "bspline", "hmatrix", "arrayblock"]) {
        expect(modelOptionsForRequest(entry(name), armed(name), SERVED_OPTION_SPECS)).toHaveProperty(
          "extended_kernel",
          true,
        );
      }
    });

    it("is ABSENT — not false — with the toggle off", () => {
      for (const name of ["sinusoidal", "bspline", "hmatrix", "arrayblock"]) {
        const b = entry(name);
        expect(modelOptionsForRequest(b, defaultOptsFor(b, SERVED_OPTION_SPECS), SERVED_OPTION_SPECS)).not.toHaveProperty(
          "extended_kernel",
        );
        // …and explicitly off is the same request as never armed: toggling on
        // and back off must return to the pre-#849 body byte for byte.
        expect(
          JSON.stringify(
            modelOptionsForRequest(b, {
              ...defaultOptsFor(b, SERVED_OPTION_SPECS),
              model: {
                ...defaultOptsFor(b, SERVED_OPTION_SPECS).model,
                extended_kernel: false,
              },
            }, SERVED_OPTION_SPECS),
          ),
        ).toBe(JSON.stringify(modelOptionsForRequest(b, defaultOptsFor(b, SERVED_OPTION_SPECS), SERVED_OPTION_SPECS)));
      }
    });

    it("reaches the wire on Galerkin, never alongside enrichment (momwire#271)", () => {
      // Galerkin serves the kernel since momwire 0.27.0 (momwire#246/#287/
      // #299) — an armed slot sends it like any other basis.
      expect(
        modelOptionsForRequest(
          entry("sinusoidal-galerkin"),
          armed("sinusoidal-galerkin"),
          SERVED_OPTION_SPECS,
        ),
      ).toEqual({ n_qp_const: 8, feed_model: "point", extended_kernel: true });
      // Singular enrichment: momwire#271. Sending both would be a refusal at
      // engine construction; the UI greys the pair out, and this is the lock
      // behind that.
      // NOTE: this used to assert the FRONTEND withheld `extended_kernel`
      // when enrichment was on, via its own `extendedKernelRefusal`. That
      // local copy is deleted (#1006 G2-6): the exclusion is momwire's, it
      // arrives in the served `constraints` (momwire#888), and the gate now
      // lives on the solve path where the refusal's own prose is shown.
      // Both keys therefore ride together here, and momwire refuses the
      // combination — which is what it always did for a request the UI did
      // not intercept.
      const enriched = {
        ...armed("bspline"),
        model: { ...armed("bspline").model, use_singular_enrichment: true },
      };
      const out = modelOptionsForRequest(entry("bspline"), enriched, SERVED_OPTION_SPECS);
      expect(out.use_singular_enrichment).toBe(true);
      expect(out.extended_kernel).toBe(true);
    });

    it("stays off the wire for pynec, which sends no model_options", () => {
      expect(modelOptionsForRequest(entry("pynec"), armed("pynec"), SERVED_OPTION_SPECS)).toEqual({});
    });
  });

  it("uses the SERVED default for a knob the slot never set", () => {
    const result = modelOptionsForRequest(entry("bspline"), {
      nPerWire: 30,
      wireRadius: 5e-4,
      model: {},
    }, SERVED_OPTION_SPECS);
    expect(result.degree).toBe(SERVED_OPTION_SPECS.degree.default);
    // Auto by default, so the key does not reach the wire at all — asserted as
    // absence, not as a value, because `toBe(undefined)` would also pass if
    // the key were present and undefined (antennaknobs#1064).
    expect(SERVED_OPTION_SPECS.n_qp_pair.default).toBeNull();
    expect(SERVED_OPTION_SPECS.n_qp_pair.auto_when_null).toBe(true);
    expect("n_qp_pair" in result).toBe(false);
  });
});
