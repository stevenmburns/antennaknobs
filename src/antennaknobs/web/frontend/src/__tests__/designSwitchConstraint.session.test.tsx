/**
 * The cross-axis constraint is LIVE, through a real <DesignSession> (#1006 G2-5).
 *
 * The question this answers is Steve's: what happens when you set an engine on
 * one design and then switch designs? The whole point of #1006 point 4 is that
 * the answer is recomputed, not remembered. A check made when the engine was
 * picked would still be showing the FIRST design's verdict, and the user would
 * meet momwire's refusal as an error dialog after the solve instead of as a
 * greyed control before it.
 *
 * The sequence, which is the test:
 *
 *   sin-Galerkin + extended kernel on a UNIFORM design   -> solving
 *   switch to the stepped-radius design (elt_whip)       -> withheld, and the
 *                                                           gate quotes
 *                                                           momwire's sentence
 *   switch back                                          -> clears
 *
 * The last step is the one that matters most and the one a naive
 * implementation fails: a gate that latches is indistinguishable from a live
 * one until you go back.
 *
 * MUTATION-CHECKED, and the result is worth writing down because one of the
 * three mutations did NOT fail:
 *
 *   - `steppedJunctionNote` ignoring the design's flag      -> both tests fail
 *   - `designRefusal` remembering its first non-null answer
 *     (a one-time check going stale — the exact bug)        -> both tests fail
 *   - the solve effect latching on `solverWarning`          -> STILL PASSES
 *
 * The third survives because DesignSession already clears `solverWarning` on
 * every antenna switch for the combo warning ("drop any combo warning from the
 * prior design"), so that particular latch cannot be observed. That is defence
 * in depth rather than a hole in this test — the derivation-level latch, which
 * is the failure mode #1006 point 4 is actually about, is caught. Recorded so
 * the next person to mutate this file does not conclude from the third result
 * that step (3) proves nothing.
 *
 * WHY elt_whip. It is the ONLY design in the catalog with a stepped-radius
 * junction — pinned Python-side by
 * test_design_constraints_1006.py::test_exactly_one_catalog_design_is_stepped,
 * which also fails if a second one appears. The descriptors below carry the
 * `has_stepped_radius_junction` the server measures for it.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DesignSession } from "../components/session/DesignSession";
import type { ExampleDescriptor } from "../lib/params";
import {
  SERVED_ROSTER,
  SERVED_ALIASES,
  SERVED_SLOT_SEEDS,
} from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const BASE: Omit<ExampleDescriptor, "name" | "label"> = {
  multi_feed: false,
  param_schema: [],
  result_schema: [],
  bands: [],
  meas_freq_range_mhz: null,
  default_view: "xz",
  default_freq: null,
  default_design_freq: null,
  default_backend: null,
  requires_backends: null,
  has_design_freq: true,
  variants: ["default"],
  variant_values: {},
  sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25 },
};

// The uniform control deck. Its junctions (if any) join equal radii, so the
// extended kernel is fine here — which is what makes the switch a measurement
// rather than a comparison against a design that could never solve.
const UNIFORM: ExampleDescriptor = {
  ...BASE,
  name: "dipoles.probe",
  label: "Probe dipole",
  has_stepped_radius_junction: false,
  has_buried_wire: false,
};

// The case Steve hit reviewing G2-7: a buried deck on an accelerated
// backend. It takes the OPTION path (`backendOptsAllowed` — the served
// solve_strategy x wire_position row), NOT `requires_backends`, which is
// exactly why the soft overlay's `!backendDisallowed` guard did not exclude
// it and both overlays rendered.
const BURIED: ExampleDescriptor = {
  ...BASE,
  name: "verticals.buried_radial_vertical",
  label: "buried radial vertical",
  has_stepped_radius_junction: false,
  has_buried_wire: true,
};

// A vertex-port design: RESTRICTED to a backend allowlist, which is the
// other state the switch has to survive. Steve's repro used this one.
const RESTRICTED: ExampleDescriptor = {
  ...BASE,
  name: "dipoles.invvee_apex",
  label: "invvee apex",
  requires_backends: [
    "bspline",
    "sinusoidal-galerkin",
    "hmatrix",
    "arrayblock",
    "nec5",
  ],
  // A single-element design recommends the dense solver, so an accelerator
  // here is "overkill" and the SOFT mismatch overlay shows. That state before
  // the switch is what Steve's repro starts from and what my earlier tests
  // omitted.
  default_backend: "bspline",
  has_stepped_radius_junction: false,
  has_buried_wire: false,
};

const STEPPED: ExampleDescriptor = {
  ...BASE,
  name: "verticals.elt_whip",
  label: "elt whip",
  has_stepped_radius_junction: true,
  has_buried_wire: false,
};

// momwire's own sentence, as the roster serves it. Matched on a distinctive
// fragment rather than in full: the assertion is that the REFUSAL PROSE
// reaches the user, and pinning every word here would just be a second copy
// of a string this repo deliberately never retypes.
const REFUSAL_FRAGMENT = /radius step at a junction/i;

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  }));
  vi.stubGlobal("fetch", async (url: string) => {
    const path = String(url);
    if (path.startsWith("/capabilities"))
      return jsonResponse({
        have_pynec: true,
        backends: SERVED_ROSTER,
        model_option_specs: SERVED_OPTION_SPECS,
        backend_aliases: SERVED_ALIASES,
        default_slots: SERVED_SLOT_SEEDS,
        terrain_presets: [],
      });
    if (path.startsWith("/examples"))
      return jsonResponse({
        examples: [UNIFORM, STEPPED, BURIED, RESTRICTED],
        errors: [],
      });
    if (path.startsWith("/geometry")) return jsonResponse({ wires: [] });
    return jsonResponse({});
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

type User = ReturnType<typeof userEvent.setup>;

async function selectDesign(user: User, label: string) {
  const box = screen.getByRole("combobox", { name: "antenna" });
  await user.clear(box);
  await user.type(box, label);
  await user.click(await screen.findByRole("option", { name: new RegExp(label, "i") }));
}

/** Put slot A on sinusoidal-Galerkin with the extended kernel armed. */
async function armSinGalerkinEK(user: User) {
  await user.click(screen.getByRole("button", { name: "Slot A options" }));
  await user.click(screen.getByRole("tab", { name: /Sin-Galerkin/ }));
  await user.click(screen.getByRole("checkbox", { name: /extended kernel \(EK\)/ }));
  await user.click(screen.getByRole("button", { name: "Close" }));
}

function gate() {
  return screen.queryByRole("alertdialog", {
    name: "Solver option unavailable for this design",
  });
}

describe("switching design re-answers the cross-axis constraint", () => {
  it("gates on the stepped deck and clears when you switch back", async () => {
    const user = userEvent.setup();
    render(<DesignSession id={1} active />);
    await screen.findByRole("tab", { name: /Solver slot A/ });

    await selectDesign(user, "Probe dipole");
    await armSinGalerkinEK(user);

    // (1) The uniform design solves: the same backend and the same option,
    // and no gate. Without this the test could pass on a gate that is always
    // on.
    await waitFor(() => expect(gate()).toBeNull());

    // (2) Switch to the stepped deck. Nothing about the SLOT changed — same
    // solver, same kernel flag — so a gate appearing here can only be the
    // design being re-consulted.
    await selectDesign(user, "elt whip");
    const shown = await screen.findByRole("alertdialog", {
      name: "Solver option unavailable for this design",
    });
    expect(shown.textContent).toMatch(REFUSAL_FRAGMENT);
    // momwire's issue travels with the sentence, so a user can read the
    // primary source rather than take the UI's word for it.
    expect(shown.textContent).toMatch(/momwire#398/);
    // The CONDITION is rendered too. Without it this reads as "the extended
    // kernel refuses junctions", which is false and would send the user to
    // the wrong workaround — uniform-radius junctions are the common case.
    expect(shown.textContent).toMatch(/radius step at the junction/i);

    // (3) …and back. A latched gate passes step (2) and fails here.
    await selectDesign(user, "Probe dipole");
    await waitFor(() => expect(gate()).toBeNull());
  });

  it("does not gate the same design when the kernel is off", async () => {
    // The other two thirds of the condition. The stepped deck is perfectly
    // solvable at the reduced kernel, and greying it out unconditionally
    // would be a worse bug than not gating at all.
    const user = userEvent.setup();
    render(<DesignSession id={1} active />);
    await screen.findByRole("tab", { name: /Solver slot A/ });

    await selectDesign(user, "elt whip");
    await user.click(screen.getByRole("button", { name: "Slot A options" }));
    await user.click(screen.getByRole("tab", { name: /Sin-Galerkin/ }));
    await user.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => expect(gate()).toBeNull());
  });
});


describe("a buried deck on an accelerated backend shows ONE overlay", () => {
  it("does not stack the soft mismatch on top of the hard refusal", async () => {
    // Found by Steve in the running app, not by any gate here. Two overlays
    // rendered and the top one offered "Solve anyway" — an override for a
    // combination momwire RAISES on. The soft overlay excluded
    // `backendDisallowed` but not `optionRefusal`, and this deck reaches the
    // gate through the second.
    const user = userEvent.setup();
    render(<DesignSession id={1} active />);
    await screen.findByRole("tab", { name: /Solver slot A/ });

    await selectDesign(user, "buried radial vertical");
    await user.click(screen.getByRole("button", { name: "Slot A options" }));
    await user.click(screen.getByRole("tab", { name: /Array-block/ }));
    await user.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() =>
      expect(
        screen.getByRole("alertdialog", {
          name: "Solver option unavailable for this design",
        }),
      ).toBeTruthy(),
    );
    // ONE dialog, and no override — the user's way out is a different
    // solver or a different option, not a button that asks anyway.
    expect(screen.getAllByRole("alertdialog")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /solve anyway/i })).toBeNull();
    // ...and momwire's own sentence is what it says.
    expect(
      screen.getByRole("alertdialog").textContent,
    ).toMatch(/wire below the ground plane/i);
  });
});


describe("switching TO a buried design withholds the solve", () => {
  it("gates when the backend was chosen on a design that allowed it", async () => {
    // THE ORDER IS THE BUG. Picking an accelerated backend while a buried
    // design is loaded is now prevented by the modal (the tab is disabled),
    // so the only way to reach the bad state is the other order: choose the
    // backend on a design that allows it, THEN switch. Found in review; the
    // solve fired and the banner showed
    // "ValueError: ArrayBlockSolver cannot solve this design's buried geometry".
    const user = userEvent.setup();
    render(<DesignSession id={1} active />);
    await screen.findByRole("tab", { name: /Solver slot A/ });

    await selectDesign(user, "Probe dipole");
    await user.click(screen.getByRole("button", { name: "Slot A options" }));
    await user.click(screen.getByRole("tab", { name: /Array-block/ }));
    await user.click(screen.getByRole("button", { name: "Close" }));
    // Allowed here: nothing withheld on an above-ground deck.
    await waitFor(() => expect(gate()).toBeNull());

    await selectDesign(user, "buried radial vertical");

    // ONE overlay, momwire's own sentence, and no override.
    const shown = await screen.findByRole("alertdialog");
    expect(screen.getAllByRole("alertdialog")).toHaveLength(1);
    expect(shown.textContent).toMatch(/buried|below the ground plane/i);
    expect(screen.queryByRole("button", { name: /solve anyway/i })).toBeNull();
  });
});


describe("Steve's exact repro: restricted design, slot B, then switch", () => {
  it("withholds when slot B's backend cannot take the new design", async () => {
    const user = userEvent.setup();
    render(<DesignSession id={1} active />);
    await screen.findByRole("tab", { name: /Solver slot A/ });

    // Slot B, Array-block, on a design whose allowlist permits it.
    await selectDesign(user, "invvee apex");
    await user.click(screen.getByRole("tab", { name: /Solver slot B/ }));
    await user.click(screen.getByRole("button", { name: "Slot B options" }));
    await user.click(screen.getByRole("tab", { name: /Array-block/ }));
    await user.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(gate()).toBeNull());

    // ...then switch to a deck it cannot take at all.
    await selectDesign(user, "buried radial vertical");

    const shown = await screen.findByRole("alertdialog");
    expect(screen.getAllByRole("alertdialog")).toHaveLength(1);
    expect(shown.textContent).toMatch(/buried|below the ground plane/i);
    expect(screen.queryByRole("button", { name: /solve anyway/i })).toBeNull();
  });
});


describe("switching AWAY from a showing soft mismatch (Steve's instrumented repro)", () => {
  it("keeps the hard gate up and sends nothing", async () => {
    // TIMELINE FROM THE BROWSER: the hard gate fired correctly, was removed
    // 24 ms later with nothing clicked, and a solve went out —
    // "ValueError: ArrayBlockSolver cannot solve this design's buried
    // geometry". So the gate is right and something clears it a tick later.
    //
    // The soft overlay must be SHOWING and unapproved before the switch;
    // starting from a design with no overlay is why the two earlier tests
    // here pass.
    const user = userEvent.setup();
    render(<DesignSession id={1} active />);
    await screen.findByRole("tab", { name: /Solver slot A/ });

    await selectDesign(user, "invvee apex");
    await user.click(screen.getByRole("tab", { name: /Solver slot B/ }));
    await user.click(screen.getByRole("button", { name: "Slot B options" }));
    await user.click(screen.getByRole("tab", { name: /Array-block/ }));
    await user.click(screen.getByRole("button", { name: "Close" }));

    // The soft overlay is up and NOT approved.
    await screen.findByRole("alertdialog", { name: "Solver mismatch" });

    await selectDesign(user, "buried radial vertical");

    // Let every effect settle — the browser saw the gate appear and vanish
    // within two ticks, so an immediate assertion would pass on the flash.
    await waitFor(() =>
      expect(
        screen.queryByRole("alertdialog", { name: "Solver mismatch" }),
      ).toBeNull(),
    );
    await new Promise((r) => setTimeout(r, 50));

    expect(
      screen.getByRole("alertdialog", {
        name: "Solver option unavailable for this design",
      }),
    ).toBeTruthy();
    expect(screen.getAllByRole("alertdialog")).toHaveLength(1);
  });
});
