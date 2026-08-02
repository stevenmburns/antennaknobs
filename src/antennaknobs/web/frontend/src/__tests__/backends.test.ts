// Pins the backend-selection/config logic in App.tsx's backend-config block
// (issue #642 step 2). These are pure functions with no DOM dependency; the
// jsdom environment is only here because importing "../App" evaluates the
// module's WS_URL, which reads window.location.
import { describe, it, expect } from "vitest";
import {
  BACKEND_ORDER,
  DEFAULT_BACKEND_OPTS,
  backendAllowed,
  backendDisplayLabel,
  backendSupportsGround,
  backendSupportsTerrain,
  comboInappropriate,
  isBSplineFamily,
  normalizeBackend,
  resolveBackend,
  resolveSlotConfig,
  selectableBackends,
  type Backend,
  type BSplineOpts,
  type SinGalerkinOpts,
  type SlotConfig,
} from "../lib/backends";

describe("normalizeBackend", () => {
  it("maps the retired 'triangular' name to bspline", () => {
    expect(normalizeBackend("triangular")).toBe("bspline");
  });

  it("passes through every current backend name unchanged", () => {
    for (const b of BACKEND_ORDER) {
      expect(normalizeBackend(b)).toBe(b);
    }
  });

  it("maps an unrecognized string to null", () => {
    expect(normalizeBackend("quadratic")).toBeNull();
    expect(normalizeBackend("")).toBeNull();
  });

  it("maps null and undefined to null", () => {
    expect(normalizeBackend(null)).toBeNull();
    expect(normalizeBackend(undefined)).toBeNull();
  });
});

describe("resolveBackend", () => {
  it("falls back pynec to sinusoidal when pynec-accel is absent", () => {
    expect(resolveBackend("pynec", false)).toBe("sinusoidal");
  });

  it("keeps pynec when pynec-accel is present", () => {
    expect(resolveBackend("pynec", true)).toBe("pynec");
  });

  it("leaves every non-pynec backend unaffected by the flag", () => {
    for (const b of BACKEND_ORDER.filter((x) => x !== "pynec")) {
      expect(resolveBackend(b, false)).toBe(b);
      expect(resolveBackend(b, true)).toBe(b);
    }
  });
});

describe("selectableBackends", () => {
  it("returns the full BACKEND_ORDER, in order, when pynec is available", () => {
    expect(selectableBackends(true)).toEqual(BACKEND_ORDER);
  });

  it("drops pynec but preserves order when pynec is unavailable", () => {
    expect(selectableBackends(false)).toEqual(
      BACKEND_ORDER.filter((b) => b !== "pynec"),
    );
  });
});

describe("resolveSlotConfig", () => {
  it("returns the SAME object reference when no swap is needed", () => {
    const cfg: SlotConfig = {
      backend: "bspline",
      opts: { ...DEFAULT_BACKEND_OPTS.bspline },
    };
    expect(resolveSlotConfig(cfg, false)).toBe(cfg);
    // pynec unaffected when the flag says it's available, too.
    const pynecCfg: SlotConfig = {
      backend: "pynec",
      opts: { ...DEFAULT_BACKEND_OPTS.pynec },
    };
    expect(resolveSlotConfig(pynecCfg, true)).toBe(pynecCfg);
  });

  it("swaps an unavailable pynec slot to sinusoidal, preserving nPerWire/wireRadius", () => {
    // Non-default sizing so preservation is actually exercised, not just
    // coincidentally equal to the sinusoidal defaults.
    const cfg: SlotConfig = {
      backend: "pynec",
      opts: { nPerWire: 99, wireRadius: 0.0123 },
    };
    expect(resolveSlotConfig(cfg, false)).toEqual({
      backend: "sinusoidal",
      opts: {
        ...DEFAULT_BACKEND_OPTS.sinusoidal,
        nPerWire: 99,
        wireRadius: 0.0123,
      },
    });
  });
});

describe("comboInappropriate", () => {
  // Full 6 (backend) x 3 (rec) matrix.
  const cases: [Backend, Backend | null, boolean][] = [
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
    expect(comboInappropriate(b, rec)).toBe(expected);
  });
});

describe("backendAllowed", () => {
  it("allows every backend when required is null or undefined", () => {
    for (const b of BACKEND_ORDER) {
      expect(backendAllowed(b, null)).toBe(true);
      expect(backendAllowed(b, undefined)).toBe(true);
    }
  });

  it("restricts to exactly the members of a given allowlist", () => {
    const required = ["bspline"];
    for (const b of BACKEND_ORDER) {
      expect(backendAllowed(b, required)).toBe(b === "bspline");
    }
  });

  it("supports a multi-backend allowlist (junction-port designs)", () => {
    const required = ["bspline", "sinusoidal-galerkin"];
    for (const b of BACKEND_ORDER) {
      expect(backendAllowed(b, required)).toBe(required.includes(b));
    }
  });
});

describe("isBSplineFamily / backendSupportsGround / backendSupportsTerrain", () => {
  const bsplineFamily: Record<Backend, boolean> = {
    sinusoidal: false,
    "sinusoidal-galerkin": false,
    bspline: true,
    hmatrix: true,
    arrayblock: true,
    pynec: false,
  };

  it.each(BACKEND_ORDER)("isBSplineFamily(%s)", (b) => {
    expect(isBSplineFamily(b)).toBe(bsplineFamily[b]);
  });

  // Current behavior: sinusoidal, sinusoidal-galerkin, the b-spline family,
  // and pynec are the entire Backend union, so both predicates are true for
  // every backend today — see the final report for a note on this.
  it.each(BACKEND_ORDER)("backendSupportsGround(%s) is true", (b) => {
    expect(backendSupportsGround(b)).toBe(true);
  });

  it.each(BACKEND_ORDER)("backendSupportsTerrain(%s) is true", (b) => {
    expect(backendSupportsTerrain(b)).toBe(true);
  });
});

describe("backendDisplayLabel", () => {
  const bsplineOpts = (degree: 1 | 2): BSplineOpts => ({
    ...DEFAULT_BACKEND_OPTS.bspline,
    degree,
  });

  it("carries the spline degree for every b-spline-family backend", () => {
    expect(backendDisplayLabel("bspline", bsplineOpts(2))).toBe("B-spline d=2");
    expect(backendDisplayLabel("bspline", bsplineOpts(1))).toBe("B-spline d=1");
    expect(backendDisplayLabel("hmatrix", bsplineOpts(2))).toBe(
      "H-matrix (ACA) d=2",
    );
    expect(backendDisplayLabel("arrayblock", bsplineOpts(1))).toBe(
      "Array-block d=1",
    );
  });

  it('suffixes "(converged)" for sinusoidal-galerkin with the point feed model', () => {
    const opts: SinGalerkinOpts = {
      ...DEFAULT_BACKEND_OPTS["sinusoidal-galerkin"],
      feedModel: "point",
    };
    expect(backendDisplayLabel("sinusoidal-galerkin", opts)).toBe(
      "Sin-Galerkin (converged)",
    );
  });

  it("stays plain for sinusoidal-galerkin with the segment feed model", () => {
    const opts: SinGalerkinOpts = {
      ...DEFAULT_BACKEND_OPTS["sinusoidal-galerkin"],
      feedModel: "segment",
    };
    expect(backendDisplayLabel("sinusoidal-galerkin", opts)).toBe(
      "Sin-Galerkin",
    );
  });

  it("stays plain for sinusoidal and pynec", () => {
    expect(
      backendDisplayLabel("sinusoidal", DEFAULT_BACKEND_OPTS.sinusoidal),
    ).toBe("Sinusoidal");
    expect(backendDisplayLabel("pynec", DEFAULT_BACKEND_OPTS.pynec)).toBe(
      "PyNEC",
    );
  });
});
