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
import { fireEvent, screen } from "@testing-library/react";
import type { ExampleDescriptor } from "../lib/params";
import { HARNESS_EXAMPLE, mountReady, stageChart, sweepIdle } from "./designSessionHarness";

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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a measurement-frequency change inside the band", () => {
  it("sends no new /sweep request", async () => {
    const sweeps: { meas: number | undefined; lo: number; hi: number }[] = [];
    await mountReady({
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
    // The deck's sweep has run and the runner is idle (the Smith chart, in
    // the rail, publishes its phase): nothing queued, nothing streaming.
    const smith = document.querySelector<HTMLElement>("canvas.smith") ?? stageChart("canvas.smith")!;
    await sweepIdle(smith);
    expect(sweeps.length).toBeGreaterThan(0);
    expect(sweeps[sweeps.length - 1].lo).toBeCloseTo(14, 9);
    const before = sweeps.length;
    const at = Number(dial().getAttribute("aria-valuenow"));
    for (let i = 0; i < 4; i++) fireEvent.keyDown(dial(), { key: "ArrowUp" });
    expect(Number(dial().getAttribute("aria-valuenow"))).toBeGreaterThan(at);
    // The runner decided on these steps inside their act: still idle means
    // no sweep is queued, so none will follow.
    expect(smith.dataset.phase).toBe("idle");
    expect(sweeps.slice(before)).toEqual([]);
  });
});
