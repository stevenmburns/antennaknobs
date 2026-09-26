/**
 * Moving the measurement frequency slides the dot along the sweep; it does
 * not re-sweep (Steve, 2026-09-26). Through a real <DesignSession>: the
 * request the session builds carries measurement_freq_mhz, and the freq
 * sweep's invalidation signature used to include it, so every dial step
 * blanked the VSWR / S11 / Smith trails and re-requested the SAME band.
 * Every engine's sweep overrides the measurement frequency per point, so
 * the field never changes a swept impedance.
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { ExampleDescriptor } from "../lib/params";
import { HARNESS_EXAMPLE, mountDesignSession } from "./designSessionHarness";

// A deck: no design frequency, so the dial is never locked to one, and a
// fixed file sweep range, so the band cannot follow the dial.
const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [
    { key: "14.175 MHz", label: "14.175 MHz", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 },
  ],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  sweep_range: { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" },
};

const T = { timeout: 5000 };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a measurement-frequency change inside the band", () => {
  it("sends no new /sweep request", async () => {
    const sweeps: { meas: number | undefined; lo: number; hi: number }[] = [];
    mountDesignSession({
      examples: [DECK],
      routes: {
        "/sweep": (_url: string, init?: RequestInit) => {
          const b = JSON.parse(String(init?.body ?? "{}"));
          const f = b.freqs_mhz as number[];
          sweeps.push({ meas: b.measurement_freq_mhz, lo: f[0], hi: f[f.length - 1] });
          return {
            ok: true,
            status: 200,
            body: { getReader: () => ({ read: async () => ({ done: true, value: undefined }) }) },
          } as unknown as Response;
        },
      },
    });
    const dial = () => screen.getByRole("slider", { name: "measurement frequency" });
    // The deck's own band has been swept (the session may sweep a default
    // window first, before /examples lands).
    await waitFor(() => {
      expect(sweeps.length).toBeGreaterThan(0);
      expect(sweeps[sweeps.length - 1].lo).toBeCloseTo(14, 9);
    }, T);
    // Let any trailing request settle, then count.
    await new Promise((r) => setTimeout(r, 800));
    const before = sweeps.length;
    const at = Number(dial().getAttribute("aria-valuenow"));
    for (let i = 0; i < 4; i++) fireEvent.keyDown(dial(), { key: "ArrowUp" });
    await waitFor(() => expect(Number(dial().getAttribute("aria-valuenow"))).toBeGreaterThan(at), T);
    // Past the sweep's 500 ms debounce, with margin.
    await new Promise((r) => setTimeout(r, 1200));
    expect(sweeps.slice(before)).toEqual([]);
  });
});
