// The ground-requirement seed, end to end through a real <DesignSession>
// (the v0.61.0 buried-wire wave). The unit pins live in GroundPanel.test.tsx
// (notice rendering); what those cannot show is the seeding effect actually
// seeding: a design whose /examples descriptor declares
// ground_requirement: "sommerfeld" must mount with the finite ground type
// AND the Sommerfeld method selected — which momwire needs for conductors
// below z = 0 — and say so in a notice, while an ordinary design keeps the
// session default (Sommerfeld too since AK#1856) with no notice.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { mountReady, HARNESS_EXAMPLE, groundSettings } from "./designSessionHarness";
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

const checked = (name: string | RegExp) =>
  (within(groundSettings()).getByRole("radio", { name }) as HTMLInputElement).checked;

// Synchronous after mountReady: the seed runs in the render that loads the
// design (AK#1762), and the session's readiness is past that render — so
// the ordinary design's absences below are about the LOADED design, not the
// moment before the catalog arrived.
describe("ground-requirement seeding (buried designs)", () => {
  it("seeds finite + Sommerfeld and shows the notice for a sommerfeld-requiring design", async () => {
    await mountReady({ examples: [BURIED_EXAMPLE] });
    expect(screen.getByText(NOTICE)).toBeTruthy();
    expect(checked("Sommerfeld")).toBe(true);
    expect(checked(/finite/)).toBe(true);
    expect(checked(/refl-coef/)).toBe(false);
  });

  it("leaves the session default (and no notice) on an ordinary design", async () => {
    await mountReady({ examples: [HARNESS_EXAMPLE] });
    expect(screen.queryByText(NOTICE)).toBeNull();
    // The default is Sommerfeld since AK#1856, so the method alone no longer
    // tells seeded from default: the notice is what says it was seeded.
    expect(checked("Sommerfeld")).toBe(true);
    expect(checked(/refl-coef/)).toBe(false);
  });
});
