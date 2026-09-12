// AK#1432 — a file design's own ground seeds the switch, end to end through
// a real <DesignSession>. Dan's Example 2 (`GE 0`, a dipole at z = 0) opened
// under the app's default finite ground and NEC-5 refused the wire in the
// plane; the deck said free space and nothing read it. The descriptor now
// carries `ground_seed` (+ `ground_medium`) and the session seeds ground
// enabled/type/method/soil from it on selection, the ground panel says so,
// and the slot label reads "deck's own" because the deck's counts are what
// the solvers honour.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { mountDesignSession, HARNESS_EXAMPLE } from "./designSessionHarness";
import type { ExampleDescriptor } from "../lib/params";

const FREE: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "user.n20Example2",
  label: "Example2",
  ground_seed: "free",
  fixed_segment_counts: true,
};
const PEC: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "user.pecdeck",
  label: "PEC deck",
  ground_seed: "pec",
  fixed_segment_counts: true,
};
const GN2: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "user.gn2deck",
  label: "GN 2 deck",
  ground_seed: "sommerfeld",
  ground_medium: { eps_r: 20, sigma: 0.02 },
  fixed_segment_counts: true,
};
const GN0: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "user.gn0deck",
  label: "GN 0 deck",
  ground_seed: "fast",
  ground_medium: { eps_r: 5, sigma: 0.001 },
  fixed_segment_counts: true,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

const groundBox = () =>
  screen.getByRole("checkbox", { name: /ground plane/ }) as HTMLInputElement;

describe("ground seed from a file design (AK#1432)", () => {
  it("GE 0: the ground plane comes up OFF, the panel says why, the slot label reads deck's own", async () => {
    mountDesignSession({ examples: [FREE] });
    await screen.findByText(/from the file: free space \(GE 0\)/);
    await waitFor(() => expect(groundBox().checked).toBe(false));
    expect(screen.getByText(/N=deck's own/)).toBeTruthy();
  });

  it("GE 1 / GN 1: ground on with the PEC type", async () => {
    mountDesignSession({ examples: [PEC] });
    await screen.findByText(/from the file: perfect ground/);
    await waitFor(() => expect(groundBox().checked).toBe(true));
    expect(
      (screen.getByRole("radio", { name: /perfect|pec/i }) as HTMLInputElement).checked,
    ).toBe(true);
  });

  it("GN 2: ground on, finite, Sommerfeld, with the card's medium in the notice", async () => {
    mountDesignSession({ examples: [GN2] });
    await screen.findByText(/from the file: finite ground, Sommerfeld \(GN 2\), εr 20, σ 0.02 S\/m/);
    await waitFor(() => expect(groundBox().checked).toBe(true));
    expect(
      (screen.getByRole("radio", { name: "Sommerfeld" }) as HTMLInputElement).checked,
    ).toBe(true);
    expect(
      (screen.getByRole("radio", { name: /finite/ }) as HTMLInputElement).checked,
    ).toBe(true);
  });

  it("GN 0: ground on, finite, the reflection-coefficient method", async () => {
    mountDesignSession({ examples: [GN0] });
    await screen.findByText(/from the file: finite ground, reflection coefficients \(GN 0\)/);
    await waitFor(() => {
      expect(
        (screen.getByRole("radio", { name: /refl-coef/ }) as HTMLInputElement).checked,
      ).toBe(true);
    });
  });

  it("a catalog design (no seed) keeps the defaults, no notice, a numeric N", async () => {
    mountDesignSession({ examples: [HARNESS_EXAMPLE] });
    await screen.findByRole("radiogroup", { name: "Finite-ground solve method" });
    expect(screen.queryByText(/from the file:/)).toBeNull();
    expect(screen.queryByText(/N=deck's own/)).toBeNull();
    expect(screen.getByText(/· N=\d+/)).toBeTruthy();
  });
});
