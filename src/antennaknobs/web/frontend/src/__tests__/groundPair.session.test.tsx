// AK#1854 through a real <DesignSession>: one line names the solver x ground
// pair (the strips are independent, never paired by column), and switching
// the active solver to NEC-5, which has no refl-coef, relabels the refl-coef
// ground tab to say what NEC-5 solves it as.
import { describe, it, expect, afterEach } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { mountReady } from "./designSessionHarness";
import { ROSTER_WITH_NEC5, SERVED_SLOT_SEEDS } from "./backendFixtures";

// Slot C holds NEC-5 (the served roster carries its row on a NEC-5 machine).
const SEEDS = SERVED_SLOT_SEEDS.map((s) =>
  s.slot === "C" ? { ...s, backend: "nec5", n_per_wire: null, model: {} } : s,
);

const pair = () => screen.getByTestId("solve-pair").textContent;
const groundTab = (id: string) =>
  screen.getByRole("tab", { name: new RegExp(`^Ground slot ${id}:`) });
const solverTab = (id: string) =>
  screen.getByRole("tab", { name: new RegExp(`^Solver slot ${id}:`) });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the solver x ground pair (AK#1854)", () => {
  it("names the active pair and follows both strips", async () => {
    const user = userEvent.setup();
    await mountReady({ roster: ROSTER_WITH_NEC5, slotSeeds: SEEDS });
    expect(pair()).toMatch(/^solving on A \(B-spline d=2\) × X \(refl-coef/);
    await user.click(groundTab("Z"));
    expect(pair()).toMatch(/× Z \(Sommerfeld/);
    await user.click(solverTab("B"));
    expect(pair()).toMatch(/^solving on B \(B-spline d=1\) × Z/);
  });

  it("under NEC-5 the refl-coef ground tab says it is solved as Sommerfeld", async () => {
    const user = userEvent.setup();
    await mountReady({ roster: ROSTER_WITH_NEC5, slotSeeds: SEEDS });
    expect(groundTab("X").getAttribute("aria-label")).toMatch(/^Ground slot X: refl-coef(?! →)/);
    await user.click(solverTab("C"));
    expect(groundTab("X").getAttribute("aria-label")).toMatch(
      /^Ground slot X: refl-coef → Sommerfeld/,
    );
    expect(groundTab("X").getAttribute("title")).toMatch(/solved as Sommerfeld on NEC-5/);
    // A Sommerfeld slot needs no arrow, and free space none either.
    expect(groundTab("Z").getAttribute("aria-label")).not.toMatch(/→/);
    expect(groundTab("Y").getAttribute("aria-label")).toBe("Ground slot Y: free space");
    expect(pair()).toMatch(/^solving on C \(NEC-5\) × X \(refl-coef → Sommerfeld/);
    // Back on a momwire slot the arrow goes.
    await user.click(solverTab("A"));
    expect(within(groundTab("X")).queryByText(/→/)).toBeNull();
  });
});
