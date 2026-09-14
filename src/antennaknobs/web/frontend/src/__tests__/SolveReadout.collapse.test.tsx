// The stage readout's minimize control: a "–" on the full card collapses it to
// a one-line R · X · SWR pill, the pill expands it again, and a readout wired
// with no handler (the mobile Info screen) has neither.
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { SolveReadout } from "../components/results/SolveReadout";
import type { SolveResponse } from "../lib/api";

function fakeResult(extra: Partial<SolveResponse> = {}): SolveResponse {
  return {
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
    z_in_re: 44,
    z_in_im: -4,
    design_freq_mhz: 28.47,
    measurement_freq_mhz: 28.47,
    solve_ms: 1.0,
    z0_ohms: 50,
    ...extra,
  } as SolveResponse;
}

function renderReadout({
  result = fakeResult(),
  collapsed,
  onCollapsedChange,
}: {
  result?: SolveResponse | null;
  collapsed?: boolean;
  onCollapsedChange?: (c: boolean) => void;
}) {
  return render(
    <SolveReadout
      result={result}
      rttMs={null}
      currentExample={undefined}
      effectiveMultiFeed={false}
      normCheck={null}
      normCheckEnabled={false}
      className="stage-readout"
      collapsed={collapsed}
      onCollapsedChange={onCollapsedChange}
    />,
  );
}

describe("readout minimize", () => {
  it("offers no control without a handler, and ignores `collapsed` (the mobile Info screen)", () => {
    renderReadout({ collapsed: true });
    expect(screen.queryByRole("button", { name: /minimize the solve readout/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /show the full solve readout/i })).toBeNull();
    expect(screen.getByText("44.00 Ω")).toBeTruthy();
  });

  it("the full card's – button asks to collapse", () => {
    const onChange = vi.fn();
    renderReadout({ onCollapsedChange: onChange });
    fireEvent.click(screen.getByRole("button", { name: /minimize the solve readout/i }));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("collapsed, it is one pill carrying R, X and SWR, and clicking it asks to expand", () => {
    const onChange = vi.fn();
    const { container } = renderReadout({ collapsed: true, onCollapsedChange: onChange });
    const pill = screen.getByRole("button", { name: /show the full solve readout/i });
    expect(pill.textContent).toContain("R 44.00 Ω");
    expect(pill.textContent).toContain("X -4.00 Ω");
    expect(pill.textContent).toMatch(/SWR \d/);
    expect(pill.classList.contains("stage-readout")).toBe(true);
    // The full card's rows are not rendered behind it.
    expect(container.querySelectorAll(".row")).toHaveLength(0);
    fireEvent.click(pill);
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it("collapsed before any solve, the pill shows dashes", () => {
    renderReadout({ result: null, collapsed: true, onCollapsedChange: () => {} });
    const pill = screen.getByRole("button", { name: /show the full solve readout/i });
    expect(pill.textContent).toContain("R —");
    expect(pill.textContent).toContain("SWR —");
  });

  it("an open feed reads as open once, not twice", () => {
    renderReadout({
      result: fakeResult({ z_in_re: 1e9, z_in_im: 0 }),
      collapsed: true,
      onCollapsedChange: () => {},
    });
    const pill = screen.getByRole("button", { name: /show the full solve readout/i });
    expect(pill.textContent?.match(/∞ \(open\)/g)).toHaveLength(1);
  });
});
