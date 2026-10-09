// AK#1955: under the MININEC-type ground the norm check ships no radiated
// fraction (currents over a perfect ground, soil in the pattern only: no
// ledger), and the readout row says so instead of printing a percentage that
// read 117 % on a near-ground deck. A real ground keeps its number.
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SolveReadout } from "../components/results/SolveReadout";
import { NO_LEDGER_MININEC } from "../lib/api";
import type { NormCheckData, SolveResponse } from "../lib/api";

const result = {
  geometry: "dipoles.invvee",
  wires: [
    {
      label: "w",
      knot_positions: [[0, 0, 0]],
      knot_currents_re: [0],
      knot_currents_im: [0],
    },
  ],
  feed_wire_index: 0,
  feed_knot_index: 0,
  z_in_re: 68.55,
  z_in_im: 6.08,
  design_freq_mhz: 1.83,
  measurement_freq_mhz: 1.83,
  solve_ms: 1.0,
  z0_ohms: 50,
} as SolveResponse;

function check(
  method: string,
  radiated_fraction: number | null,
): NormCheckData {
  return {
    directivity_norm: 1,
    pattern_norm: 1,
    method,
    delta_db: 0,
    radiated_fraction,
    radiation_efficiency: 1,
  };
}

function radiatedRow(normCheck: NormCheckData) {
  render(
    <SolveReadout
      result={result}
      rttMs={null}
      currentExample={undefined}
      effectiveMultiFeed={false}
      normCheck={normCheck}
      normCheckEnabled={true}
    />,
  );
  return screen
    .getByText("radiated (incl. ground)")
    .closest(".row") as HTMLElement;
}

describe("radiated fraction under the MININEC-type ground", () => {
  it("shows a dash and the reason, never a percentage", () => {
    const row = radiatedRow(check("no_ledger_mininec", null));
    expect(row.textContent).toContain("—");
    expect(row.textContent).not.toContain("%");
    expect(row.getAttribute("title")).toBe(NO_LEDGER_MININEC);
  });

  it("a real ground keeps its percentage", () => {
    const row = radiatedRow(check("grid_45x90", 0.327));
    expect(row.textContent).toContain("33%");
    expect(row.getAttribute("title")).not.toBe(NO_LEDGER_MININEC);
  });
});
