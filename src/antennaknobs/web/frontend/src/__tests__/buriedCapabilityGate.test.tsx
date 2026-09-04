/**
 * A backend that cannot take a buried deck says so (found in review).
 *
 * THE GATE HAD TWO SHAPES AND NEEDED THREE. `backendOptsAllowed` and
 * `steppedJunctionNote` both answer "which COMBINATIONS are refused" — they
 * read `COUPLINGS`, which is right, because a coupling is a pair. But a
 * solver with no buried fill refuses the DECK, whatever else is set. momwire
 * declares that as a single-cell capability (`buried`), `COUPLINGS` rightly
 * does not name it, and so nothing gated on it at all:
 *
 *   razor-2p + a buried design -> no overlay, the solve fired, and the user
 *   got "ValueError: RazorSolver cannot solve this design's buried geometry"
 *   in the error banner.
 *
 * The capability was SERVED since #1108 and untyped in the client until now,
 * which is a large part of why: the fact was on the wire and invisible.
 *
 * `buried: null` is "cannot be asked" and must never be read as "cannot"
 * (#1103). pynec and nec5 answer null because AK has no MEASURED fact about
 * their buried scope — a sentence in a docstring is not a capability, and
 * encoding one as if it were is how a guess becomes a gate.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { BackendConfigModal } from "../components/backend/BackendConfigModal";
import {
  capabilityRefusal,
  designRefusal,
  defaultOptsFor,
  type BackendEntry,
} from "../lib/backends";
import { entry, SERVED_ROSTER,
  SERVED_VOCAB,
} from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const BURIED = { buried: true, has_stepped_radius_junction: false };
const ABOVE = { buried: false, has_stepped_radius_junction: false };

/** The served capability, as momwire reports it. */
const withBuried = (name: string, buried: boolean | null, reason: string | null) =>
  ({ ...entry(name), buried, buried_refusal: reason }) as BackendEntry;

describe("capabilityRefusal — the deck, not a combination", () => {
  it("refuses a buried deck on a solver with no buried fill", () => {
    const razor = withBuried("razor-2p", false, "RazorSolver has no buried fill…");
    const hit = capabilityRefusal(razor, BURIED);
    expect(hit).not.toBeNull();
    expect(hit!.reason).toContain("no buried fill");
  });

  it("says nothing on a deck that is not buried", () => {
    const razor = withBuried("razor-2p", false, "RazorSolver has no buried fill…");
    expect(capabilityRefusal(razor, ABOVE)).toBeNull();
  });

  it("says nothing for a solver that DOES serve buried", () => {
    // bspline is the one that can. Without this, "refuse everything on a
    // buried deck" would pass every other test here.
    expect(capabilityRefusal(withBuried("bspline", true, null), BURIED)).toBeNull();
  });

  it("treats null as CANNOT BE ASKED, never as cannot", () => {
    // #1103's rule, and the one answer that must never be inferred. pynec and
    // nec5 are null: AK has no measured fact about their buried scope.
    expect(capabilityRefusal(withBuried("pynec", null, null), BURIED)).toBeNull();
  });

  it("says nothing when the capability is false but no prose came with it", () => {
    // A gate with no sentence would have to invent one, and an invented
    // refusal is worse than an ungated solve: the user is told something
    // nobody measured.
    expect(capabilityRefusal(withBuried("razor-2p", false, null), BURIED)).toBeNull();
  });
});

describe("designRefusal checks the deck BEFORE the options", () => {
  it("reports the deck-level refusal, not a narrower option one", () => {
    // arrayblock on a buried deck hits BOTH: the capability (no buried fill)
    // and the served coupling (element-block x buried). The deck-level answer
    // is the useful one — "this solver cannot take this design" tells the
    // user to change solver, where the option-level sentence invites them to
    // change an option that will not help.
    const ab = withBuried("arrayblock", false, "this deck has a wire below the ground plane…");
    const hit = designRefusal(ab, defaultOptsFor(ab, SERVED_OPTION_SPECS), BURIED);
    expect(hit!.forbids_axis).toBe("backend");
  });

  it("still reports option-level refusals when the deck is fine", () => {
    const b = entry("bspline");
    const opts = defaultOptsFor(b, SERVED_OPTION_SPECS);
    expect(designRefusal(b, opts, ABOVE)).toBeNull();
  });
});

describe("the tab itself says it cannot take this deck", () => {
  // Found in review: Array-block on a buried design looked ordinary in the
  // picker, and gated only after the user selected it and closed the modal.
  // A refusal you can only discover by choosing the thing is discovered late.
  const roster = SERVED_ROSTER.map((b) =>
    b.name === "arrayblock" || b.name === "razor-2p"
      ? ({ ...b, buried: false, buried_refusal: `${b.label} has no buried fill…` } as BackendEntry)
      : ({ ...b, buried: b.name === "bspline" ? true : null } as BackendEntry),
  );

  const mount = (design: Record<string, unknown>) =>
    render(
      <BackendConfigModal
        slot="A"
        backend={entry("bspline")}
        backends={roster}
        requiredBackends={null}
        design={design}
        specs={SERVED_OPTION_SPECS}
        vocab={SERVED_VOCAB}
        designRefusalNote={null}
        suggestConvergedFeed={false}
        opts={defaultOptsFor(entry("bspline"), SERVED_OPTION_SPECS)}
        onChangeBackend={vi.fn()}
        onPatch={vi.fn()}
        onReset={vi.fn()}
        onClose={vi.fn()}
      />,
    );

  it("greys the refusing tabs on a buried design, with momwire's sentence", () => {
    mount(BURIED);
    const ab = screen.getByRole("tab", { name: "Array-block" }) as HTMLButtonElement;
    expect(ab.disabled).toBe(true);
    expect(ab.title).toContain("no buried fill");
    const razor = screen.getByRole("tab", { name: "Razor (2-point)" }) as HTMLButtonElement;
    expect(razor.disabled).toBe(true);
  });

  it("leaves the tab that CAN take it enabled", () => {
    // Without this, greying everything would satisfy the test above.
    mount(BURIED);
    expect(
      (screen.getByRole("tab", { name: "B-spline" }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("greys nothing on an above-ground design", () => {
    mount(ABOVE);
    for (const name of ["Array-block", "Razor (2-point)", "B-spline"]) {
      expect(
        (screen.getByRole("tab", { name }) as HTMLButtonElement).disabled,
      ).toBe(false);
    }
  });
});
