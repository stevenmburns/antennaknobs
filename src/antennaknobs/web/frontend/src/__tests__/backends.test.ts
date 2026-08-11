// Pins the backend-selection/config logic in src/lib/backends.ts. Every case
// is driven by a roster FIXTURE rather than a module constant (issue #628):
// the roster is server data now, so these test how the frontend reacts to a
// roster, not which backends exist. Pure functions with no DOM dependency —
// the suite-wide jsdom environment exists for tests that import App.tsx (its
// module-scope WS_URL reads window.location), not for these.
import { describe, it, expect } from "vitest";
import {
  BSPLINE_DEFAULT_OPTS,
  backendAllowed,
  backendDisplayLabel,
  backendSupportsGround,
  backendSupportsTerrain,
  comboInappropriate,
  defaultOptsFor,
  defaultSlots,
  EK_ENRICHMENT_REASON,
  EK_GALERKIN_REASON,
  EK_UNSUPPORTED_BACKEND,
  extendedKernelActive,
  extendedKernelRefusal,
  findBackend,
  hasBSplinePanel,
  normalizeBackend,
  slotFromSeed,
  type BackendEntry,
  type BackendOpts,
} from "../lib/backends";
import {
  backendEntry,
  backendOption,
  entry,
  ROSTER_NO_PYNEC,
  SERVED_ROSTER,
} from "./backendFixtures";

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
    const opts = defaultOptsFor(entry("sinusoidal"));
    expect(opts.schema).toEqual({ n_qp_const: 8 });
    expect(opts.nPerWire).toBe(30);
  });

  it("takes segments/wire from the entry, not a client-side table", () => {
    expect(defaultOptsFor(entry("arrayblock")).nPerWire).toBe(21);
    expect(defaultOptsFor(entry("pynec")).nPerWire).toBe(21);
    expect(
      defaultOptsFor(backendEntry({ name: "x", default_n_per_wire: 7 })).nPerWire,
    ).toBe(7);
  });

  it("attaches bespoke panel state only for the entry that names that panel", () => {
    expect(defaultOptsFor(entry("bspline")).bspline).toEqual(BSPLINE_DEFAULT_OPTS);
    expect(defaultOptsFor(entry("bspline")).feedModel).toBeUndefined();
    expect(defaultOptsFor(entry("sinusoidal-galerkin")).feedModel).toBe("segment");
    expect(defaultOptsFor(entry("sinusoidal-galerkin")).bspline).toBeUndefined();
    expect(defaultOptsFor(entry("sinusoidal")).bspline).toBeUndefined();
    expect(defaultOptsFor(entry("sinusoidal")).feedModel).toBeUndefined();
  });

  // Absence, not `false`: that is the EK card's own convention, and it is what
  // keeps a stock request byte-identical to the pre-#849 one (pinned as JSON
  // in modelOptions.test.ts).
  it("leaves the extended kernel unset on every backend (#849)", () => {
    for (const b of SERVED_ROSTER) {
      expect(defaultOptsFor(b).extendedKernel).toBeUndefined();
      expect(extendedKernelActive(b, defaultOptsFor(b))).toBe(false);
    }
  });
});

describe("extendedKernelRefusal (#849)", () => {
  const on = (name: string) => ({ ...defaultOptsFor(entry(name)), extendedKernel: true });

  it("passes every backend that momwire serves the kernel on", () => {
    for (const name of ["sinusoidal", "bspline", "hmatrix", "arrayblock"]) {
      expect(extendedKernelRefusal(entry(name), on(name))).toBeNull();
      expect(extendedKernelActive(entry(name), on(name))).toBe(true);
    }
  });

  it("refuses the Galerkin basis by name, citing momwire#246", () => {
    const b = entry("sinusoidal-galerkin");
    expect(b.name).toBe(EK_UNSUPPORTED_BACKEND); // the constant IS the roster name
    expect(extendedKernelRefusal(b, on(b.name))).toBe(EK_GALERKIN_REASON);
    expect(EK_GALERKIN_REASON).toContain("momwire#246");
    // …and it refuses whether or not the flag is set: the predicate describes
    // the backend, and the toggle greys out before anything is armed.
    expect(extendedKernelRefusal(b, defaultOptsFor(b))).toBe(EK_GALERKIN_REASON);
    expect(extendedKernelActive(b, on(b.name))).toBe(false);
  });

  it("refuses alongside singular enrichment, citing momwire#271", () => {
    const opts = on("bspline");
    opts.bspline = { ...BSPLINE_DEFAULT_OPTS, useSingularEnrichment: true };
    expect(extendedKernelRefusal(entry("bspline"), opts)).toBe(EK_ENRICHMENT_REASON);
    expect(EK_ENRICHMENT_REASON).toContain("momwire#271");
    expect(extendedKernelActive(entry("bspline"), opts)).toBe(false);
    // Enrichment off again and the same slot serves it.
    opts.bspline = { ...BSPLINE_DEFAULT_OPTS, useSingularEnrichment: false };
    expect(extendedKernelActive(entry("bspline"), opts)).toBe(true);
  });

  it("never activates on PyNEC, which takes no model_options at all", () => {
    // PyNEC's own extended-kernel support (issue #414) is a separate,
    // unexposed kwarg — this toggle must not claim to drive it.
    expect(extendedKernelActive(entry("pynec"), on("pynec"))).toBe(false);
  });

  it("serves a momwire backend the roster invented and nobody hardcoded", () => {
    const fake = backendEntry({ name: "fake-solver", label: "Fake" });
    expect(
      extendedKernelActive(fake, { ...defaultOptsFor(fake), extendedKernel: true }),
    ).toBe(true);
  });
});

describe("slotFromSeed / defaultSlots", () => {
  it("resolves the stock A/B/C seeds against the full roster", () => {
    const slots = defaultSlots(SERVED_ROSTER);
    expect(slots.A.backend).toBe(entry("bspline"));
    expect(slots.A.opts.nPerWire).toBe(15);
    expect(slots.A.opts.bspline?.degree).toBe(2);
    expect(slots.B.backend).toBe(entry("bspline"));
    expect(slots.B.opts.nPerWire).toBe(20);
    expect(slots.B.opts.bspline?.degree).toBe(1);
    expect(slots.C.backend).toBe(entry("pynec"));
  });

  it("falls back to the roster's first entry when the seeded backend is absent (#429)", () => {
    const slots = defaultSlots(ROSTER_NO_PYNEC);
    expect(slots.C.backend).toBe(ROSTER_NO_PYNEC[0]);
    expect(slots.C.opts).toEqual(defaultOptsFor(ROSTER_NO_PYNEC[0]));
  });

  it("applies the seed's deviations without mutating the entry's defaults", () => {
    slotFromSeed({ backend: "bspline", bspline: { degree: 1 } }, SERVED_ROSTER);
    expect(BSPLINE_DEFAULT_OPTS.degree).toBe(2);
  });

  it("seeds a backend the roster invented, with no seed of its own", () => {
    const fake = backendEntry({
      name: "fake-solver",
      label: "Fake",
      default_n_per_wire: 9,
      options_schema: [backendOption()],
    });
    const cfg = slotFromSeed({ backend: "fake-solver" }, [...SERVED_ROSTER, fake]);
    expect(cfg.backend).toBe(fake);
    expect(cfg.opts).toEqual({
      nPerWire: 9,
      wireRadius: 0.0005,
      schema: { n_qp_const: 8 },
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
    pynec: false,
  };

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
    const opts = defaultOptsFor(entry(name));
    opts.bspline = { ...BSPLINE_DEFAULT_OPTS, degree };
    return backendDisplayLabel(entry(name), opts);
  };

  it("carries the spline degree for every backend on the b-spline panel", () => {
    expect(withDegree("bspline", 2)).toBe("B-spline d=2");
    expect(withDegree("bspline", 1)).toBe("B-spline d=1");
    expect(withDegree("hmatrix", 2)).toBe("H-matrix (ACA) d=2");
    expect(withDegree("arrayblock", 1)).toBe("Array-block d=1");
  });

  it('suffixes "(converged)" for the sin-galerkin panel with the point feed model', () => {
    const opts = defaultOptsFor(entry("sinusoidal-galerkin"));
    expect(
      backendDisplayLabel(entry("sinusoidal-galerkin"), {
        ...opts,
        feedModel: "point",
      }),
    ).toBe("Sin-Galerkin (converged)");
  });

  it("stays plain for the sin-galerkin panel with the segment feed model", () => {
    const opts = defaultOptsFor(entry("sinusoidal-galerkin"));
    expect(backendDisplayLabel(entry("sinusoidal-galerkin"), opts)).toBe(
      "Sin-Galerkin",
    );
  });

  it("is the served label for a panel-less backend, including one nobody hardcoded", () => {
    expect(
      backendDisplayLabel(entry("sinusoidal"), defaultOptsFor(entry("sinusoidal"))),
    ).toBe("Sinusoidal");
    expect(backendDisplayLabel(entry("pynec"), defaultOptsFor(entry("pynec")))).toBe(
      "PyNEC",
    );
    const fake = backendEntry({
      name: "fake-solver",
      label: "Fake",
      options_schema: [backendOption()],
    });
    expect(backendDisplayLabel(fake, defaultOptsFor(fake))).toBe("Fake");
  });

  // The A/B story of #849 is "same basis, one slot with the kernel": if the
  // chips don't say which, the comparison is unreadable.
  it('affixes "+EK" wherever the extended kernel is in force', () => {
    const ek = (name: string, over: Partial<BackendOpts> = {}) =>
      backendDisplayLabel(entry(name), {
        ...defaultOptsFor(entry(name)),
        extendedKernel: true,
        ...over,
      });
    expect(ek("sinusoidal")).toBe("Sinusoidal +EK");
    expect(ek("bspline")).toBe("B-spline d=2 +EK");
    expect(ek("bspline", { bspline: { ...BSPLINE_DEFAULT_OPTS, degree: 1 } })).toBe(
      "B-spline d=1 +EK",
    );
    expect(ek("hmatrix")).toBe("H-matrix (ACA) d=2 +EK");
    expect(ek("arrayblock")).toBe("Array-block d=2 +EK");
  });

  it("leaves the label alone when the kernel is off or refused", () => {
    // Off: the default, and the other half of every A/B pair.
    expect(
      backendDisplayLabel(entry("bspline"), defaultOptsFor(entry("bspline"))),
    ).toBe("B-spline d=2");
    // Refused by basis — a set flag on a Galerkin slot is not a running
    // kernel, and the chip must not claim it is.
    expect(
      backendDisplayLabel(entry("sinusoidal-galerkin"), {
        ...defaultOptsFor(entry("sinusoidal-galerkin")),
        feedModel: "point",
        extendedKernel: true,
      }),
    ).toBe("Sin-Galerkin (converged)");
    // Refused by enrichment.
    expect(
      backendDisplayLabel(entry("bspline"), {
        ...defaultOptsFor(entry("bspline")),
        bspline: { ...BSPLINE_DEFAULT_OPTS, useSingularEnrichment: true },
        extendedKernel: true,
      }),
    ).toBe("B-spline d=2");
    // Never on PyNEC.
    expect(
      backendDisplayLabel(entry("pynec"), {
        ...defaultOptsFor(entry("pynec")),
        extendedKernel: true,
      }),
    ).toBe("PyNEC");
  });
});
