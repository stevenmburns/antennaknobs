// The ground-requirement seed, end to end through a real <DesignSession>
// (the v0.61.0 buried-wire wave). The unit pins live in GroundPanel.test.tsx
// (notice rendering); what those cannot show is the seeding effect actually
// seeding: a design whose /examples descriptor declares
// ground_requirement: "sommerfeld" must mount with the finite ground type
// AND the Sommerfeld method selected — not the "fast" refl-coef default,
// which momwire refuses by name for conductors below z = 0 — while an
// ordinary design keeps the refl-coef default untouched.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { mountDesignSession, HARNESS_EXAMPLE } from "./designSessionHarness";
import type { ExampleDescriptor } from "../lib/params";

const BURIED_EXAMPLE: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "verticals.buried_probe",
  label: "Buried probe",
  ground_requirement: "sommerfeld",
};

const NOTICE = "buried design — Sommerfeld ground selected automatically";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ground-requirement seeding (buried designs)", () => {
  it("seeds finite + Sommerfeld and shows the notice for a sommerfeld-requiring design", async () => {
    mountDesignSession({ examples: [BURIED_EXAMPLE] });

    // The catalog resolves, the design auto-selects, and the seeding effect
    // lands: the notice renders and the Sommerfeld method radio is checked.
    await screen.findByText(NOTICE);
    await waitFor(() => {
      expect(
        (screen.getByRole("radio", { name: "Sommerfeld" }) as HTMLInputElement)
          .checked,
      ).toBe(true);
    });
    expect(
      (
        screen.getByRole("radio", {
          name: /finite/,
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    expect(
      (screen.getByRole("radio", { name: /refl-coef/ }) as HTMLInputElement)
        .checked,
    ).toBe(false);
  });

  it("leaves the refl-coef default (and no notice) on an ordinary design", async () => {
    mountDesignSession({ examples: [HARNESS_EXAMPLE] });

    // Same settling point as above without depending on the notice: the
    // finite-method radiogroup is present once the catalog resolves.
    await screen.findByRole("radiogroup", {
      name: "Finite-ground solve method",
    });
    expect(screen.queryByText(NOTICE)).toBeNull();
    expect(
      (screen.getByRole("radio", { name: /refl-coef/ }) as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByRole("radio", { name: "Sommerfeld" }) as HTMLInputElement)
        .checked,
    ).toBe(false);
  });
});
