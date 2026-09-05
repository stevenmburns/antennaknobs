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
import { entry, ROSTER_WITH_NEC5, SERVED_ROSTER,
  SERVED_VOCAB,
} from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const BURIED = { buried: true, has_stepped_radius_junction: false };
const ABOVE = { buried: false, has_stepped_radius_junction: false };

/** The served capability, as momwire reports it — or, for AK's own wrappers
 *  since #1167, as AK measured it. */
const withBuried = (
  name: string,
  buried: boolean | null,
  reason: string | null,
  issue?: string | null,
) =>
  ({
    ...entry(name),
    buried,
    buried_refusal: reason,
    ...(issue === undefined ? {} : { buried_issue: issue }),
  }) as BackendEntry;

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
    // #1103's rule, and the one answer that must never be inferred. `nec5` is
    // still null — nobody has measured it. (`pynec` was too until #1167
    // measured it; the entry here is a null one whatever the roster now says,
    // because what is under test is the null HANDLING.)
    // `nec5` lives only in the with-NEC5 roster: the default served shape
    // omits it, absence being the hosted-simulator state.
    const nec5 = {
      ...entry("nec5", ROSTER_WITH_NEC5),
      buried: null,
      buried_refusal: null,
    } as BackendEntry;
    expect(capabilityRefusal(nec5, BURIED)).toBeNull();
  });

  it("says nothing when the capability is false but no prose came with it", () => {
    // A gate with no sentence would have to invent one, and an invented
    // refusal is worse than an ungated solve: the user is told something
    // nobody measured.
    expect(capabilityRefusal(withBuried("razor-2p", false, null), BURIED)).toBeNull();
  });
});

describe("capabilityRefusal cites the right issue (#1167)", () => {
  it("carries a wrapper's own issue rather than momwire's", () => {
    // PyNEC's buried limitation is not described by momwire#553, and sending
    // a user there for it is the same class of error as inventing the reason
    // — quieter, and just as wrong.
    const pynec = withBuried(
      "pynec",
      false,
      "PyNEC cannot model a conductor below the ground plane…",
      "antennaknobs#1167",
    );
    expect(capabilityRefusal(pynec, BURIED)!.issue).toBe("antennaknobs#1167");
  });

  it("still cites momwire#553 for a row that serves no issue", () => {
    // Every momwire row predates the field, so the fallback is load-bearing
    // rather than defensive.
    const razor = withBuried("razor-2p", false, "RazorSolver has no buried fill…");
    expect(capabilityRefusal(razor, BURIED)!.issue).toBe("momwire#553");
  });

  it("falls back when the server explicitly sends null", () => {
    const razor = withBuried(
      "razor-2p",
      false,
      "RazorSolver has no buried fill…",
      null,
    );
    expect(capabilityRefusal(razor, BURIED)!.issue).toBe("momwire#553");
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
        restrictionReason={null}
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

describe("the tooltip on a RESTRICTED tab is the served sentence", () => {
  // #1153 measured the frontend's single `RESTRICTED_BACKEND_REASON` already
  // FALSE for a vertex-port design: it claims "only the B-spline and
  // sinusoidal-Galerkin solvers" while such a design allows five, including
  // NEC-5. The overlay was switched to the served per-cause sentence then;
  // this tooltip was not — so the falsehood survived exactly where a user
  // hovers to find out why a tab is off. Found in review.
  it("prefers the served reason over the local constant", () => {
    render(
      <BackendConfigModal
        slot="A"
        backend={entry("bspline")}
        backends={SERVED_ROSTER}
        requiredBackends={["bspline", "sinusoidal-galerkin"]}
        design={{}}
        restrictionReason="this design drives a vertex port, which five solvers implement"
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
    const off = screen.getByRole("tab", { name: "PyNEC" }) as HTMLButtonElement;
    expect(off.disabled).toBe(true);
    expect(off.title).toContain("five solvers");
    // ...and not the constant it replaced.
    expect(off.title).not.toContain("only the B-spline and sinusoidal-Galerkin");
  });

  it("falls back to the constant when the server sent no reason", () => {
    // A third restriction cause that forgets a sentence gets generic copy,
    // which is a worse message rather than a false one (#1153's rule).
    render(
      <BackendConfigModal
        slot="A"
        backend={entry("bspline")}
        backends={SERVED_ROSTER}
        requiredBackends={["bspline"]}
        design={{}}
        restrictionReason={null}
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
    const off = screen.getByRole("tab", { name: "PyNEC" }) as HTMLButtonElement;
    expect(off.title.length).toBeGreaterThan(20);
  });
});
