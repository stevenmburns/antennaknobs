// Pins the backend-selection/config logic in src/lib/backends.ts. Every case
// is driven by a roster FIXTURE rather than a module constant (issue #628):
// the roster is server data now, so these test how the frontend reacts to a
// roster, not which backends exist. Pure functions with no DOM dependency —
// the suite-wide jsdom environment exists for tests that import App.tsx (its
// module-scope WS_URL reads window.location), not for these.
import { describe, it, expect } from "vitest";
import {
  backendAllowed,
  backendDisplayLabel,
  backendSupportsGround,
  backendSupportsTerrain,
  comboInappropriate,
  defaultOptsFor,
  defaultSlots,
  extendedKernelActive,
  findBackend,
  hasBSplinePanel,
  normalizeBackend,
  slotFromSeed,
  type BackendEntry,
} from "../lib/backends";
import {
  backendEntry,
  backendOption,
  entry,
  optsWithModel,
  ROSTER_NO_PYNEC,
  SERVED_ROSTER,
} from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const NAMES = SERVED_ROSTER.map((b) => b.name);

describe("normalizeBackend", () => {
  it("maps the retired 'triangular' name to the bspline entry", () => {
    expect(normalizeBackend("triangular", SERVED_ROSTER)).toBe(entry("bspline"));
  });

  it("resolves every served name to its own entry", () => {
    for (const b of SERVED_ROSTER) {
      expect(normalizeBackend(b.name, SERVED_ROSTER)).toBe(b);
    }
  });

  it("maps a name the roster doesn't carry to null", () => {
    expect(normalizeBackend("quadratic", SERVED_ROSTER)).toBeNull();
    expect(normalizeBackend("", SERVED_ROSTER)).toBeNull();
    // The #429 case is now roster membership: no entry, no recommendation.
    expect(normalizeBackend("pynec", ROSTER_NO_PYNEC)).toBeNull();
  });

  it("maps null and undefined to null", () => {
    expect(normalizeBackend(null, SERVED_ROSTER)).toBeNull();
    expect(normalizeBackend(undefined, SERVED_ROSTER)).toBeNull();
  });

  it("resolves a name the fixture roster invented, with no frontend list to update", () => {
    const roster = [...SERVED_ROSTER, backendEntry({ name: "fake-solver", label: "Fake" })];
    expect(normalizeBackend("fake-solver", roster)?.label).toBe("Fake");
  });
});

describe("findBackend", () => {
  it("returns the entry for a served name and null otherwise", () => {
    expect(findBackend(SERVED_ROSTER, "hmatrix")).toBe(entry("hmatrix"));
    expect(findBackend(SERVED_ROSTER, "nope")).toBeNull();
    expect(findBackend(SERVED_ROSTER, null)).toBeNull();
  });
});

describe("defaultOptsFor", () => {
  it("seeds the served generic knobs under their own (wire) keys", () => {
    const opts = defaultOptsFor(entry("sinusoidal"), SERVED_OPTION_SPECS);
    // Keyed by the SERVER's kwarg names, defaults from the SERVED catalogue —
    // this used to be `opts.schema` beside a panel-shaped `opts.bspline`.
    // `feed_model` is deliberately ABSENT: `SinusoidalSolver` accepts the
    // kwarg and refuses the value "point" (momwire#212), so the server does
    // not EXPOSE it here. Its Galerkin sibling does — asserted below.
    expect(opts.model).toEqual({ n_qp_const: 8, extended_kernel: false });
    expect(
      defaultOptsFor(entry("sinusoidal-galerkin"), SERVED_OPTION_SPECS).model
        .feed_model,
    ).toBe("point");
    expect(opts.nPerWire).toBe(30);
  });

  it("takes segments/wire from the entry, not a client-side table", () => {
    expect(defaultOptsFor(entry("arrayblock"), SERVED_OPTION_SPECS).nPerWire).toBe(21);
    expect(defaultOptsFor(entry("pynec"), SERVED_OPTION_SPECS).nPerWire).toBe(21);
    expect(
      defaultOptsFor(backendEntry({ name: "x", default_n_per_wire: 7 }), SERVED_OPTION_SPECS).nPerWire,
    ).toBe(7);
  });

  it("seeds exactly the kwargs the backend ACCEPTS, and no others", () => {
    // The b-spline family takes twelve knobs and NOT n_qp_const; the
    // sinusoidal family takes three and DOES. That asymmetry is the server's
    // measurement (test_backend_model_kwargs_1006.py) and it is the fact the
    // `panel` hint could never express, since it named a panel rather than a
    // set of knobs.
    const bspline = defaultOptsFor(entry("bspline"), SERVED_OPTION_SPECS).model;
    expect(Object.keys(bspline)).toContain("degree");
    expect(Object.keys(bspline)).not.toContain("n_qp_const");
    const sin = defaultOptsFor(entry("sinusoidal"), SERVED_OPTION_SPECS).model;
    expect(Object.keys(sin)).toContain("n_qp_const");
    expect(Object.keys(sin)).not.toContain("degree");
    // pynec takes none at all — an empty map, not a guess at some.
    expect(defaultOptsFor(entry("pynec"), SERVED_OPTION_SPECS).model).toEqual({});
  });


  // Absence, not `false`: that is the EK card's own convention, and it is what
  // keeps a stock request byte-identical to the pre-#849 one (pinned as JSON
  // in modelOptions.test.ts).
  it("leaves the extended kernel unset on every backend (#849)", () => {
    for (const b of SERVED_ROSTER) {
      // False in the map, ABSENT from the wire — `modelOptionsForRequest`
      // deletes it unless in force, which is what keeps a kernel-off request
      // byte-identical to the pre-#849 one.
      expect(defaultOptsFor(b, SERVED_OPTION_SPECS).model.extended_kernel).not.toBe(true);
      expect(extendedKernelActive(b, defaultOptsFor(b, SERVED_OPTION_SPECS))).toBe(false);
    }
  });
});

// `extendedKernelRefusal` and `EK_ENRICHMENT_REASON` are GONE (#1006 G2-6).
//
// They were a hand-written copy of momwire's refusal and a DRIFTED one: they
// cited momwire#271 where momwire's own `_ENRICHMENT_EXTENDED_KERNEL_REFUSAL`
// cites momwire#249 follow-up C, and gave one reason where it gives three.
// The tests here asserted that copy — including `expect(EK_ENRICHMENT_REASON)
// .toContain("momwire#271")`, which pinned the WRONG issue number in place.
//
// momwire#888 added the served coupling row, so the exclusion now arrives
// through `constraints` like every other refusal and is exercised by
// `designRefusal` in backendAxisControls.test.ts. Nothing is untested; the
// test moved to where the fact now lives.


describe("slotFromSeed / defaultSlots", () => {
  it("resolves the stock A/B/C seeds against the full roster", () => {
    const slots = defaultSlots(SERVED_ROSTER, SERVED_OPTION_SPECS);
    expect(slots.A.backend).toBe(entry("bspline"));
    expect(slots.A.opts.nPerWire).toBe(15);
    expect(slots.A.opts.model.degree).toBe(2);
    expect(slots.B.backend).toBe(entry("bspline"));
    expect(slots.B.opts.nPerWire).toBe(20);
    expect(slots.B.opts.model.degree).toBe(1);
    expect(slots.C.backend).toBe(entry("pynec"));
  });

  it("falls back to the roster's first entry when the seeded backend is absent (#429)", () => {
    const slots = defaultSlots(ROSTER_NO_PYNEC, SERVED_OPTION_SPECS);
    expect(slots.C.backend).toBe(ROSTER_NO_PYNEC[0]);
    expect(slots.C.opts).toEqual(
      defaultOptsFor(ROSTER_NO_PYNEC[0], SERVED_OPTION_SPECS),
    );
  });

  it("applies the seed's deviations without mutating the served defaults", () => {
    const seeded = slotFromSeed(
      { backend: "bspline", model: { degree: 1 } },
      SERVED_ROSTER,
      SERVED_OPTION_SPECS,
    );
    expect(seeded.opts.model.degree).toBe(1);
    // The catalogue is shared across every slot, so a seed that wrote through
    // to it would silently re-default every OTHER slot.
    expect(SERVED_OPTION_SPECS.degree.default).toBe(2);
    expect(
      defaultOptsFor(entry("bspline"), SERVED_OPTION_SPECS).model.degree,
    ).toBe(2);
  });

  it("ignores a seed naming a kwarg the backend does not accept", () => {
    // A seed is a preset, not an override: putting an unaccepted kwarg on the
    // wire means the hosted sanitiser drops it and a local install raises
    // TypeError, neither of which the user asked for.
    const seeded = slotFromSeed(
      { backend: "sinusoidal", model: { degree: 1 } },
      SERVED_ROSTER,
      SERVED_OPTION_SPECS,
    );
    expect(seeded.opts.model.degree).toBeUndefined();
  });

  it("seeds a backend the roster invented, with no seed of its own", () => {
    const fake = backendEntry({
      name: "fake-solver",
      label: "Fake",
      default_n_per_wire: 9,
      model_kwargs: ["n_qp_const"],
      options_schema: [backendOption()],
    });
    const cfg = slotFromSeed(
      { backend: "fake-solver" },
      [...SERVED_ROSTER, fake],
      SERVED_OPTION_SPECS,
    );
    expect(cfg.backend).toBe(fake);
    expect(cfg.opts).toEqual({
      nPerWire: 9,
      wireRadius: 0.0005,
      model: { n_qp_const: SERVED_OPTION_SPECS.n_qp_const.default },
    });
  });
});

describe("comboInappropriate", () => {
  // Full 6 (backend) x 3 (recommendation) matrix, by name for readability —
  // the function itself only ever reads the two capability flags.
  const cases: [string, string | null, boolean][] = [
    ["sinusoidal", "arrayblock", true],
    ["sinusoidal", "sinusoidal", false],
    ["sinusoidal", null, false],

    ["sinusoidal-galerkin", "arrayblock", true],
    ["sinusoidal-galerkin", "sinusoidal", true],
    ["sinusoidal-galerkin", null, false],

    ["bspline", "arrayblock", true],
    ["bspline", "sinusoidal", true],
    ["bspline", null, false],

    ["hmatrix", "arrayblock", false],
    ["hmatrix", "sinusoidal", true],
    ["hmatrix", null, true],

    ["arrayblock", "arrayblock", false],
    ["arrayblock", "sinusoidal", true],
    ["arrayblock", null, true],

    ["pynec", "arrayblock", true],
    ["pynec", "sinusoidal", false],
    ["pynec", null, false],
  ];

  it.each(cases)("comboInappropriate(%s, %s) === %s", (b, rec, expected) => {
    expect(
      comboInappropriate(entry(b), rec === null ? null : entry(rec)),
    ).toBe(expected);
  });

  it("reads the flags, not the names: a fake accelerator behaves like arrayblock", () => {
    const fake = backendEntry({ name: "fake-accel", accelerator: true, dense_family: true });
    expect(comboInappropriate(fake, null)).toBe(true);
    expect(comboInappropriate(fake, entry("arrayblock"))).toBe(false);
    expect(comboInappropriate(entry("sinusoidal"), fake)).toBe(true);
  });
});

describe("backendAllowed", () => {
  it("allows every backend when required is null or undefined", () => {
    for (const b of SERVED_ROSTER) {
      expect(backendAllowed(b, null)).toBe(true);
      expect(backendAllowed(b, undefined)).toBe(true);
    }
  });

  it("restricts to exactly the members of a given allowlist", () => {
    const required = ["bspline"];
    for (const b of SERVED_ROSTER) {
      expect(backendAllowed(b, required)).toBe(b.name === "bspline");
    }
  });

  it("supports a multi-backend allowlist (junction-port designs)", () => {
    const required = ["bspline", "sinusoidal-galerkin"];
    for (const b of SERVED_ROSTER) {
      expect(backendAllowed(b, required)).toBe(required.includes(b.name));
    }
  });
});

describe("hasBSplinePanel / backendSupportsGround / backendSupportsTerrain", () => {
  const bsplinePanel: Record<string, boolean> = {
    sinusoidal: false,
    "sinusoidal-galerkin": false,
    bspline: true,
    hmatrix: true,
    arrayblock: true,
    "razor-2p": false,
    pynec: false,
  };

  // The table is keyed by name while the cases come from the roster, so a
  // roster row with no key here looks up `undefined` — and would PASS for any
  // backend whose helper also answered undefined. That is not hypothetical:
  // `razor-2p` was missing from the fixture AND from this table, so the tab
  // was uncovered in a suite that looks like it iterates everything.
  it("has an expectation for every served backend", () => {
    expect(Object.keys(bsplinePanel).sort()).toEqual([...NAMES].sort());
  });

  it.each(NAMES)("hasBSplinePanel(%s)", (name) => {
    expect(hasBSplinePanel(entry(name))).toBe(bsplinePanel[name]);
  });

  // Every solver the server currently registers models a ground, so the flag
  // is true across the served roster — but it is now DATA, and a roster entry
  // carrying false is honoured without any frontend change (see below and
  // GroundPanel.noGround.test.tsx).
  it.each(NAMES)("backendSupportsGround(%s) is true", (name) => {
    expect(backendSupportsGround(entry(name))).toBe(true);
    expect(backendSupportsTerrain(entry(name))).toBe(true);
  });

  it("reports a served supports_ground: false backend as ground-less", () => {
    const groundless: BackendEntry = backendEntry({
      name: "future-solver",
      supports_ground: false,
    });
    expect(backendSupportsGround(groundless)).toBe(false);
    expect(backendSupportsTerrain(groundless)).toBe(false);
  });
});

describe("backendDisplayLabel", () => {
  const withDegree = (name: string, degree: 1 | 2) => {
    return backendDisplayLabel(entry(name), optsWithModel(name, { degree }));
  };

  it("carries the spline degree for every backend on the b-spline panel", () => {
    expect(withDegree("bspline", 2)).toBe("B-spline d=2");
    expect(withDegree("bspline", 1)).toBe("B-spline d=1");
    expect(withDegree("hmatrix", 2)).toBe("H-matrix (ACA) d=2");
    expect(withDegree("arrayblock", 1)).toBe("Array-block d=1");
  });

  it('suffixes "(NEC gap)" for the sin-galerkin panel with the segment feed model', () => {
    expect(
      backendDisplayLabel(
        entry("sinusoidal-galerkin"),
        optsWithModel("sinusoidal-galerkin", { feed_model: "segment" }),
      ),
    ).toBe("Sin-Galerkin (NEC gap)");
  });

  // The chip marks the DEVIATION, and which value that is flipped with
  // momwire#654: the point gap is the solver's default now, so a plain chip
  // is the converged one.
  it("stays plain for the sin-galerkin panel with the default point feed model", () => {
    const opts = defaultOptsFor(entry("sinusoidal-galerkin"), SERVED_OPTION_SPECS);
    expect(opts.model.feed_model).toBe("point");
    expect(backendDisplayLabel(entry("sinusoidal-galerkin"), opts)).toBe(
      "Sin-Galerkin",
    );
  });

  it("is the served label for a panel-less backend, including one nobody hardcoded", () => {
    expect(
      backendDisplayLabel(entry("sinusoidal"), defaultOptsFor(entry("sinusoidal"), SERVED_OPTION_SPECS)),
    ).toBe("Sinusoidal");
    expect(backendDisplayLabel(entry("pynec"), defaultOptsFor(entry("pynec"), SERVED_OPTION_SPECS))).toBe(
      "PyNEC",
    );
    const fake = backendEntry({
      name: "fake-solver",
      label: "Fake",
      options_schema: [backendOption()],
    });
    expect(backendDisplayLabel(fake, defaultOptsFor(fake, SERVED_OPTION_SPECS))).toBe("Fake");
  });

  // The A/B story of #849 is "same basis, one slot with the kernel": if the
  // chips don't say which, the comparison is unreadable.
  it('affixes "+EK" wherever the extended kernel is in force', () => {
    const ek = (name: string, over: Record<string, unknown> = {}) =>
      backendDisplayLabel(
        entry(name),
        optsWithModel(name, { extended_kernel: true, ...over }),
      );
    expect(ek("sinusoidal")).toBe("Sinusoidal +EK");
    expect(ek("bspline")).toBe("B-spline d=2 +EK");
    expect(ek("bspline", { degree: 1 })).toBe("B-spline d=1 +EK");
    expect(ek("hmatrix")).toBe("H-matrix (ACA) d=2 +EK");
    expect(ek("arrayblock")).toBe("Array-block d=2 +EK");
  });

  it("leaves the label alone when the kernel is off or refused", () => {
    // Off: the default, and the other half of every A/B pair.
    expect(
      backendDisplayLabel(entry("bspline"), defaultOptsFor(entry("bspline"), SERVED_OPTION_SPECS)),
    ).toBe("B-spline d=2");
    // Served on Galerkin since momwire 0.27.0 — the flag on that slot IS a
    // running kernel now, and the chip says so.
    expect(
      backendDisplayLabel(
        entry("sinusoidal-galerkin"),
        optsWithModel("sinusoidal-galerkin", {
          feed_model: "segment",
          extended_kernel: true,
        }),
      ),
    ).toBe("Sin-Galerkin (NEC gap) +EK");
    // NOTE: the enrichment case used to appear here, asserting the chip
    // stayed plain because the frontend's own `extendedKernelRefusal` vetoed
    // the kernel. That local veto is deleted (#1006 G2-6) — the exclusion is
    // momwire's and travels in `constraints` — so the chip now reflects what
    // the user asked for, and the refusal is surfaced by `designRefusal` on
    // the solve path rather than by silently rewriting the label.
    // Never on PyNEC.
    expect(
      backendDisplayLabel(entry("pynec"), {
        ...defaultOptsFor(entry("pynec"), SERVED_OPTION_SPECS),
        model: { extended_kernel: true },
      }),
    ).toBe("PyNEC");
  });
});
