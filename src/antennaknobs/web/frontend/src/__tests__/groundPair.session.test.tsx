// AK#1854 through a real <DesignSession>: one line names the solver x ground
// pair (the strips are independent, never paired by column), and switching
// the active solver to NEC-5, which has no refl-coef, marks the refl-coef
// ground tab refused (AK#1856; nec5RefusesReflCoef.session.test.tsx has the
// way out and the chart).
import { describe, it, expect, afterEach } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { mountReady } from "./designSessionHarness";
import { NEC5_REFL_COEF_REFUSAL, ROSTER_WITH_NEC5, SERVED_SLOT_SEEDS } from "./backendFixtures";

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
    expect(pair()).toMatch(/^solving on A \(B-spline d=2\) × X \(Sommerfeld/);
    await user.click(groundTab("Z"));
    expect(pair()).toMatch(/× Z \(refl-coef/);
    await user.click(solverTab("B"));
    expect(pair()).toMatch(/^solving on B \(B-spline d=1\) × Z/);
  });

  it("under NEC-5 the refl-coef ground tab carries the refusal mark (AK#1856)", async () => {
    const user = userEvent.setup();
    await mountReady({ roster: ROSTER_WITH_NEC5, slotSeeds: SEEDS });
    // Slot Z is the stock refl-coef ground (AK#1856).
    expect(groundTab("Z").getAttribute("aria-label")).toMatch(/^Ground slot Z: refl-coef(?! ⊘)/);
    expect(groundTab("Z").dataset.refused).toBe("0");
    await user.click(solverTab("C"));
    expect(groundTab("Z").getAttribute("aria-label")).toMatch(/^Ground slot Z: refl-coef ⊘/);
    expect(groundTab("Z").dataset.refused).toBe("1");
    expect(groundTab("Z").getAttribute("title")).toContain(
      `refused on NEC-5. ${NEC5_REFL_COEF_REFUSAL}`,
    );
    // No arrow anywhere: NEC-5 no longer runs refl-coef as Sommerfeld.
    expect(groundTab("Z").getAttribute("aria-label")).not.toMatch(/→/);
    // A Sommerfeld slot is NEC-5's own ground, and free space is no finite one.
    expect(groundTab("X").dataset.refused).toBe("0");
    expect(groundTab("X").getAttribute("aria-label")).not.toMatch(/⊘|→/);
    expect(groundTab("Y").getAttribute("aria-label")).toBe("Ground slot Y: free space");
    // Back on a momwire slot the mark goes.
    await user.click(solverTab("A"));
    expect(groundTab("Z").dataset.refused).toBe("0");
    expect(within(groundTab("Z")).queryByText(/⊘/)).toBeNull();
  });
});
