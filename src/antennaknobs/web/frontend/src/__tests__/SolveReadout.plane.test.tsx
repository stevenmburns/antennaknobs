// The measurement-plane picker (issue #652 c) in the solve readout: shown
// exactly when the solve offers >1 plane AND the session wired a handler;
// paired presence/absence pins in the repo's matrix style.
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SolveReadout } from "../components/results/SolveReadout";
import type { SolveResponse } from "../lib/api";

function fakeResult(extra: Partial<SolveResponse> = {}): SolveResponse {
  return {
    geometry: "dipoles.invvee_coax_station",
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

function renderReadout(
  result: SolveResponse | null,
  onPlaneChange?: (p: string) => void,
) {
  return render(
    <SolveReadout
      result={result}
      rttMs={null}
      currentExample={undefined}
      effectiveMultiFeed={false}
      normCheck={null}
      normCheckEnabled={false}
      onPlaneChange={onPlaneChange}
    />,
  );
}

describe("measurement-plane picker", () => {
  it("offers the solve's planes and reports a pick", () => {
    const onPlaneChange = vi.fn();
    renderReadout(
      fakeResult({ plane: "rig", planes: ["rig", "feed"] }),
      onPlaneChange,
    );
    const select = screen.getByLabelText(
      "measurement plane",
    ) as HTMLSelectElement;
    expect(select.value).toBe("rig");
    fireEvent.change(select, { target: { value: "feed" } });
    expect(onPlaneChange).toHaveBeenCalledWith("feed");
  });

  it("reflects the plane the solve actually ran at", () => {
    renderReadout(
      fakeResult({ plane: "feed", planes: ["rig", "feed"] }),
      vi.fn(),
    );
    expect(
      (screen.getByLabelText("measurement plane") as HTMLSelectElement).value,
    ).toBe("feed");
  });

  it("is absent when the design has no planes to offer", () => {
    renderReadout(fakeResult(), vi.fn());
    expect(screen.queryByLabelText("measurement plane")).toBeNull();
  });

  it("is absent when there is only the natural plane", () => {
    renderReadout(fakeResult({ plane: "feed", planes: ["feed"] }), vi.fn());
    expect(screen.queryByLabelText("measurement plane")).toBeNull();
  });

  it("is absent when no handler is wired, whatever the solve offers", () => {
    renderReadout(fakeResult({ plane: "rig", planes: ["rig", "feed"] }));
    expect(screen.queryByLabelText("measurement plane")).toBeNull();
  });
});
