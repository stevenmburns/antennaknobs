// The solver advisory channel's rendering (antennaknobs#1144).
//
// The channel's failure modes are both about VOLUME, in opposite directions,
// so every presence assertion is paired with an absence one:
//
//   too little — an advisory the user needed is collapsed away or suppressed
//   too much   — an advisory that fires on every solve trains the eye to skip
//                the channel, and takes the deck-specific ones with it
//
// And one about tone: nothing here was refused or remeshed, so a rendering
// that reads as an error sends the user looking for a broken antenna.
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SolverAdvisories } from "../components/results/SolverAdvisories";

const SURFACE = {
  category: "SurfaceRadialHeight",
  text: "a conductor lies within a few radii of the ground: 4 near-ground wire(s) at h = 1.05 mm, h/a = 2.1.",
};
const FARMESH = {
  category: "RazorFarMeshClass",
  text: "razor-2p is first order in the far mesh: its default-mesh answer is not converged.",
};
const COARSE = {
  category: "CoarseCrossingNode",
  text: "a crossing junction's node region is unresolved for its convergence class.",
};

describe("SolverAdvisories", () => {
  it("renders nothing at all when there are none", () => {
    // The no-noise half. An empty channel must leave no chrome behind — a
    // heading over an empty list is still something to learn to ignore.
    const { container } = render(<SolverAdvisories advisories={[]} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing when the field is absent", () => {
    // Geometry-preview responses carry no advisories key at all.
    const { container } = render(<SolverAdvisories />);
    expect(container.innerHTML).toBe("");
  });

  it("shows a deck-conditional advisory in full, with its own numbers", () => {
    render(<SolverAdvisories advisories={[SURFACE]} />);
    expect(screen.getByText(/h\/a = 2\.1/)).toBeTruthy();
  });

  it("labels it as advisory, not as an error", () => {
    // Nothing was refused and nothing was remeshed. The styling carries this
    // too (muted `.design-note`, never `.examples-error`), but the word is
    // what a user actually reads.
    const { container } = render(<SolverAdvisories advisories={[SURFACE]} />);
    expect(screen.getByText("Advisory")).toBeTruthy();
    expect(container.querySelector(".examples-error")).toBeNull();
    expect(container.querySelector(".solver-advisory")).not.toBeNull();
  });

  it("collapses the unconditional far-mesh one behind a count", () => {
    // It fires on EVERY razor-2p solve by momwire's design — no solve-free
    // predictor of the error correlates, so there is no honest threshold.
    render(<SolverAdvisories advisories={[FARMESH]} />);
    expect(screen.queryByText(/first order in the far mesh/)).toBeNull();
    expect(screen.getByRole("button", { name: /convergence advisory/ })).toBeTruthy();
  });

  it("expands the collapsed one on request — hidden, not withheld", () => {
    render(<SolverAdvisories advisories={[FARMESH]} />);
    return userEvent
      .click(screen.getByRole("button", { name: /convergence advisory/ }))
      .then(() => {
        expect(screen.getByText(/first order in the far mesh/)).toBeTruthy();
      });
  });

  it("never collapses a deck-conditional one alongside it", () => {
    // The whole ranking exists for this case: on a razor-2p solve of a
    // surface deck, the unconditional advisory must not bury the one that
    // says something about THIS deck.
    render(<SolverAdvisories advisories={[FARMESH, SURFACE]} />);
    expect(screen.getByText(/h\/a = 2\.1/)).toBeTruthy();
    expect(screen.queryByText(/first order in the far mesh/)).toBeNull();
  });

  it("shows an UNKNOWN category in full rather than hiding it", () => {
    // The collapse list is a presentation choice about one known-unconditional
    // advisory, not a filter on what counts. A category momwire adds later
    // shows until someone decides otherwise: over-showing is visible and gets
    // fixed, quiet suppression is neither.
    render(
      <SolverAdvisories
        advisories={[{ category: "SomethingNewMomwireAdded", text: "a new advisory" }]}
      />,
    );
    expect(screen.getByText(/a new advisory/)).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows several deck-conditional advisories at once", () => {
    render(<SolverAdvisories advisories={[SURFACE, COARSE]} />);
    expect(screen.getByText(/h\/a = 2\.1/)).toBeTruthy();
    expect(screen.getByText(/node region is unresolved/)).toBeTruthy();
  });
});
