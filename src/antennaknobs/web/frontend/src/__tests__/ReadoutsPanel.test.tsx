// The generic server-driven readouts contract (issue #712). The feature's
// whole promise is that a NEW design idea reaches the workbench with zero
// TypeScript, so these rows are deliberately synthetic and look nothing
// like the rigging rows that motivated the feature — if this file ever
// needs to know what a row MEANS, the guarantee is gone.
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  ReadoutsPanel,
  formatReadoutValue,
} from "../components/results/ReadoutsPanel";
import { SolveReadout } from "../components/results/SolveReadout";
import type { ReadoutRow, SolveResponse } from "../lib/api";

function rowText(label: string): string {
  // The value sits in the row's second span, beside its label.
  const labelEl = screen.getByText(label);
  return labelEl.parentElement?.querySelector(".val")?.textContent ?? "";
}

describe("ReadoutsPanel", () => {
  it("renders every value type from rows it has never seen before", () => {
    const rows: ReadoutRow[] = [
      { label: "flux capacitance", value: 1.21, unit: "GW", group: null },
      { label: "coolant", value: "liquid nitrogen", unit: null, group: "plumbing" },
      { label: "leak rate", value: 0.5, unit: "mL/h", group: "plumbing" },
      { label: "spare hose", value: null, unit: "m", group: "plumbing" },
    ];
    render(<ReadoutsPanel rows={rows} />);

    expect(rowText("flux capacitance")).toBe("1.21 GW");
    // A string value is printed verbatim — no unit, no reformatting.
    expect(rowText("coolant")).toBe("liquid nitrogen");
    expect(rowText("leak rate")).toBe("0.5 mL/h");
    // A null value is an em-dash and drops its unit (no "— m").
    expect(rowText("spare hose")).toBe("—");
    // Group heading rendered once for the three rows that share it.
    expect(screen.getAllByText("plumbing")).toHaveLength(1);
  });

  it("clusters rows by group, ungrouped first, order preserved", () => {
    const rows: ReadoutRow[] = [
      { label: "b-first", value: 1, unit: null, group: "beta" },
      { label: "loose", value: 2, unit: null, group: null },
      { label: "a-only", value: 3, unit: null, group: "alpha" },
      { label: "b-second", value: 4, unit: null, group: "beta" },
    ];
    const { container } = render(<ReadoutsPanel rows={rows} />);
    const labels = Array.from(
      container.querySelectorAll(".readout-row > span:first-child"),
    ).map((el) => el.textContent);
    // Ungrouped leads; each group keeps first-appearance order, and rows
    // stay in the order the server sent them within their group.
    expect(labels).toEqual(["loose", "b-first", "b-second", "a-only"]);
  });

  it("renders nothing at all when there are no rows", () => {
    for (const rows of [undefined, null, [] as ReadoutRow[]]) {
      const { container } = render(<ReadoutsPanel rows={rows} />);
      expect(container.innerHTML).toBe("");
    }
  });

  it("formats numbers to fixed significant digits, trimming float dust", () => {
    expect(formatReadoutValue(1234.5678)).toBe("1235");
    expect(formatReadoutValue(0.00123456)).toBe("0.001235");
    expect(formatReadoutValue(64.08740188881157)).toBe("64.09");
    expect(formatReadoutValue(22.53)).toBe("22.53");
    expect(formatReadoutValue(0)).toBe("0");
    expect(formatReadoutValue(-1.0 / 3.0)).toBe("-0.3333");
    expect(formatReadoutValue(null)).toBe("—");
  });
});

describe("SolveReadout's readouts section", () => {
  function fakeResult(extra: Partial<SolveResponse> = {}): SolveResponse {
    return {
      geometry: "dipoles.invvee_catenary",
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
      z_in_re: 44,
      z_in_im: -4,
      design_freq_mhz: 28.47,
      measurement_freq_mhz: 28.47,
      solve_ms: 1.0,
      z0_ohms: 50,
      ...extra,
    } as SolveResponse;
  }

  function renderReadout(result: SolveResponse | null) {
    return render(
      <SolveReadout
        result={result}
        rttMs={null}
        currentExample={undefined}
        effectiveMultiFeed={false}
        normCheck={null}
        normCheckEnabled={false}
      />,
    );
  }

  it("shows the solve's rows inside the readout HUD", () => {
    renderReadout(
      fakeResult({
        readouts: [
          { label: "wire sag", value: 64.087, unit: "mm", group: "rigging" },
        ],
      }),
    );
    expect(screen.getByText("rigging")).toBeTruthy();
    expect(rowText("wire sag")).toBe("64.09 mm");
  });

  it("is absent for a solve that carries no readouts", () => {
    renderReadout(fakeResult());
    expect(screen.queryByText("rigging")).toBeNull();
    expect(document.querySelectorAll(".readout-row")).toHaveLength(0);
  });
});
