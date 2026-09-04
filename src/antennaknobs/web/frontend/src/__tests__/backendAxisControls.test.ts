/**
 * The control rule and the design-dependent constraints (issue #1006 G2-5).
 *
 * The rule under test, from `lib/backends.ts`:
 *
 *   an axis is a CONTROL iff it is multi-valued in `axes`
 *                      AND not pinned by this preset's `bound`
 *                      AND (hosted) its kwarg is on the model-options allowlist.
 *
 * Three different things — the class, the preset, host policy — and the tests
 * below keep them apart, because collapsing them is how `razor-2p` would grow
 * a quadrature control that makes its own tab name a lie.
 *
 * The constraint predicates are LIVE derived state: they take the current
 * design, so they recompute when the user switches design. That is the whole
 * point (Steve's question was "what happens when I set an engine on one design
 * and switch designs"), so every test here varies the design rather than only
 * the backend.
 */
import { describe, expect, it } from "vitest";

import { SERVED_ROSTER, entry } from "./backendFixtures";
import {
  axisControls,
  backendOptsAllowed,
  steppedJunctionNote,
  type BackendConstraint,
  type BackendEntry,
  type BackendOpts,
} from "../lib/backends";

const BASE: BackendEntry = {
  name: "bspline",
  label: "B-spline",
  kind: "momwire",
  supports_ground: true,
  options_schema: [],
  panel: "bspline",
  default_n_per_wire: 30,
  accelerator: false,
  dense_family: true,
  axes: {
    basis: ["bspline-1", "bspline-2"],
    testing: ["galerkin"],
    kernel: ["reduced", "extended"],
    solve_strategy: ["dense"],
    ground_model: ["free", "pec", "refl-coef", "sommerfeld"],
    wire_position: ["above", "buried", "contact"],
  },
  bound: {},
  constraints: [],
};

const BURIED_CONSTRAINT: BackendConstraint = {
  axis: "kernel",
  value: "extended",
  forbids_axis: "wire_position",
  forbids_value: "buried",
  forbids_is_axis: true,
  condition: null,
  reason: "extended_kernel=True + a wire below the ground plane is not served…",
  issue: "momwire#553",
};

const STEP_CONSTRAINT: BackendConstraint = {
  axis: "kernel",
  value: "extended",
  forbids_axis: "junction_ports",
  forbids_value: "True",
  forbids_is_axis: false,
  condition: "a radius step at the junction",
  reason: "extended_kernel=True with a radius step at a junction is not…",
  issue: "momwire#398",
};

// Only the model map matters to these predicates; nPerWire/wireRadius are
// geometry and never reach them.
const OPTS = (model: Record<string, unknown> = {}): BackendOpts =>
  ({ model }) as BackendOpts;

describe("axisControls — the class, the preset, and host policy are different", () => {
  it("offers only the multi-valued axes", () => {
    // testing/solve_strategy are single-valued: they are what the TAB is,
    // not a control on it. That is #1006 point 2 falling out — the preset
    // picks the point, the controls are the axes it left free.
    expect(axisControls(BASE)).toEqual(["basis", "kernel"]);
  });

  it("drops an axis this PRESET pins, even though the class offers both", () => {
    // razor-2p's shape: the class can take either quadrature, the preset
    // binds one. A control here would let a user flip `razor-2p` into the
    // Gauss-Legendre lane and leave the tab's name describing something else.
    const razor: BackendEntry = {
      ...BASE,
      name: "razor-2p",
      axes: { ...BASE.axes, quadrature: ["converged", "nec5"] },
      bound: { nec5_quadrature: true },
    };
    expect(axisControls(razor)).not.toContain("quadrature");
    // ...and the row still SAYS the class can do both, which is the
    // distinction the payload keeps deliberately separable.
    expect(razor.axes!.quadrature).toEqual(["converged", "nec5"]);
  });

  it("says nothing for a backend that cannot describe itself", () => {
    // `axes: null` is "cannot be asked" — pynec/nec5, or a momwire predating
    // the axis vocabulary. Zero controls, not a guess at some.
    expect(axisControls({ ...BASE, axes: null })).toEqual([]);
  });
});

describe("backendOptsAllowed — live, and design-dependent", () => {
  it("permits the extended kernel on a design that is not buried", () => {
    const b = { ...BASE, constraints: [BURIED_CONSTRAINT] };
    expect(
      backendOptsAllowed(b, OPTS({ extended_kernel: true }), { buried: false }),
    ).toBeNull();
  });

  it("refuses the same options once the DESIGN changes to a buried one", () => {
    // The switch-design case in miniature: same backend, same options, and
    // the answer flips because the design did. A one-time check at engine
    // selection would still be reporting the first answer.
    const b = { ...BASE, constraints: [BURIED_CONSTRAINT] };
    const opts = OPTS({ extended_kernel: true });
    expect(backendOptsAllowed(b, opts, { buried: false })).toBeNull();
    const hit = backendOptsAllowed(b, opts, { buried: true });
    expect(hit).not.toBeNull();
    expect(hit!.reason).toBe(BURIED_CONSTRAINT.reason);
  });

  it("does not fire when the user has not asked for the extended kernel", () => {
    // The constraint is on a VALUE of the kernel axis, not on the axis. A
    // buried design is perfectly solvable here at the reduced kernel, and
    // greying the whole tab would be wrong.
    const b = { ...BASE, constraints: [BURIED_CONSTRAINT] };
    expect(
      backendOptsAllowed(b, OPTS({ extended_kernel: false }), { buried: true }),
    ).toBeNull();
  });

  it("ignores rows whose forbidden side is a keyword, not an axis", () => {
    // Served for API consumers and the inventory; not renderable as a cell.
    const b = { ...BASE, constraints: [STEP_CONSTRAINT] };
    expect(
      backendOptsAllowed(b, OPTS({ extended_kernel: true }), {
        has_stepped_radius_junction: true,
      }),
    ).toBeNull();
  });

  it("answers null when the backend cannot be asked at all", () => {
    expect(
      backendOptsAllowed({ ...BASE, constraints: null }, OPTS({ extended_kernel: true }), {
        buried: true,
      }),
    ).toBeNull();
  });
});

describe("steppedJunctionNote — the note, and it needs all three", () => {
  const b = { ...BASE, constraints: [STEP_CONSTRAINT] };

  it("fires only with the kernel selected AND a stepped design", () => {
    expect(
      steppedJunctionNote(b, OPTS({ extended_kernel: true }), {
        has_stepped_radius_junction: true,
      }),
    ).not.toBeNull();
    expect(
      steppedJunctionNote(b, OPTS({ extended_kernel: false }), {
        has_stepped_radius_junction: true,
      }),
    ).toBeNull();
    expect(
      steppedJunctionNote(b, OPTS({ extended_kernel: true }), {
        has_stepped_radius_junction: false,
      }),
    ).toBeNull();
  });

  it("carries momwire's own sentence and its condition, not a paraphrase", () => {
    const note = steppedJunctionNote(b, OPTS({ extended_kernel: true }), {
      has_stepped_radius_junction: true,
    })!;
    expect(note.reason).toBe(STEP_CONSTRAINT.reason);
    // The condition is what stops this reading as "the extended kernel
    // refuses junctions", which is false and would send a user to the wrong
    // workaround — uniform-radius junctions are the common case.
    expect(note.condition).toBe("a radius step at the junction");
  });
});

describe("axisControls over the SERVED roster — the per-tab lists, pinned", () => {
  // The lists from the G2-5 design message, asserted against the fixture that
  // mirrors the real payload. Written as EQUALITY per tab, not as
  // `toContain`, because the failure this guards is an axis LEAKING IN — a new
  // derived axis, or an axis that stops being pinned — and a containment check
  // cannot see an extra element.
  const EXPECTED: Record<string, string[]> = {
    sinusoidal: ["kernel"],
    "sinusoidal-galerkin": ["feed_model", "kernel"],
    bspline: ["basis", "kernel"],
    hmatrix: ["basis", "kernel"],
    arrayblock: ["basis", "kernel"],
    "razor-2p": ["kernel"],
    pynec: [],
  };

  it("has an expectation for every served backend", () => {
    // Same guard as backends.test.ts: the cases below come from the table, so
    // a roster row absent from it would simply never be tested.
    expect(Object.keys(EXPECTED).sort()).toEqual(
      SERVED_ROSTER.map((b) => b.name).sort(),
    );
  });

  it.each(Object.keys(EXPECTED))("axisControls(%s)", (name) => {
    expect(axisControls(entry(name))).toEqual(EXPECTED[name]);
  });

  it("keeps the derived axes out even though they are multi-valued", () => {
    // The fourth clause, measured against the real payload rather than a
    // hand-built row: every momwire tab offers four grounds and at least two
    // wire positions, so both axes clear the multi-valued bar on every one of
    // them and ONLY the derived-axis clause keeps them out. Drop that clause
    // and all six lists above grow by two.
    for (const b of SERVED_ROSTER) {
      if (!b.axes) continue;
      expect(b.axes.ground_model!.length).toBeGreaterThan(1);
      expect(b.axes.wire_position!.length).toBeGreaterThan(1);
      expect(axisControls(b)).not.toContain("ground_model");
      expect(axisControls(b)).not.toContain("wire_position");
    }
  });

  it("drops quadrature ONLY on the tab that pins it", () => {
    // razor-2p is the only preset with a non-empty `bound`, and the only tab
    // whose class offers two quadratures. Both halves are asserted so the
    // razor expectation above cannot pass because the axis is single-valued
    // everywhere — which is what would happen if `bound` stopped being served.
    const razor = entry("razor-2p");
    expect(razor.axes!.quadrature).toEqual(["converged", "nec5"]);
    expect(razor.bound).toEqual({ nec5_quadrature: true });
    const unpinned = { ...razor, bound: {} };
    expect(axisControls(unpinned)).toContain("quadrature");
  });
});
