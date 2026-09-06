// The engine-timing fields during an optimizer run (#1007).
//
// `solve` and `rtt` both came off the /ws channel, and the optimiser POSTs
// /optimize with its own fetch and reads an SSE stream — so both froze for the
// whole of a run, which is exactly when the engine is busiest. A reactive run
// is 40+ full solves showing the timings of whatever interactive solve
// happened before it started.
//
// `rtt` is deliberately NOT reused as the same quantity. The interactive
// number is one request/response pair; during a run the honest figure is the
// gap between progress frames — what the user is actually waiting through —
// so it gets its own label rather than quietly meaning something else in the
// same slot.
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { SolveReadout } from "../components/results/SolveReadout";
import type { SolveResponse } from "../lib/api";

function fakeResult(): SolveResponse {
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
    solve_ms: 12.5,
    z0_ohms: 50,
  } as SolveResponse;
}

type Live = { solveMs: number | null; intervalMs: number | null; nSolves: number | null };

function show(live: Live | null) {
  return render(
    <SolveReadout
      result={fakeResult()}
      rttMs={31.0}
      live={live}
      currentExample={undefined}
      effectiveMultiFeed={false}
      normCheck={null}
      normCheckEnabled={false}
    />,
  );
}

function rowValue(label: string): string | null {
  const el = Array.from(document.querySelectorAll(".row")).find(
    (r) => r.firstElementChild?.textContent === label,
  );
  return el?.querySelector(".val")?.textContent ?? null;
}

describe("engine timing outside a run", () => {
  it("shows the interactive solve time and the /ws round trip", () => {
    show(null);
    expect(rowValue("solve")).toBe("12.5 ms");
    expect(rowValue("rtt")).toBe("31.0 ms");
    expect(rowValue("solves")).toBeNull();   // no run, no count
    expect(rowValue("per eval")).toBeNull();
  });
});

describe("engine timing during a run (#1007)", () => {
  const LIVE = { solveMs: 88.4, intervalMs: 102.7, nSolves: 43 };

  it("shows the run's own solve time, not the pre-run one", () => {
    show(LIVE);
    expect(rowValue("solve")).toBe("88.4 ms");
  });

  it("replaces rtt with the frame interval, and RELABELS it", () => {
    show(LIVE);
    // The label changes because the quantity changes: the optimiser's request
    // never makes the interactive round trip.
    expect(rowValue("per eval")).toBe("102.7 ms");
    expect(rowValue("rtt")).toBeNull();
  });

  it("says how many solves the run has paid for", () => {
    show(LIVE);
    // "a run that did 43 solves should say so rather than looking like one"
    expect(rowValue("solves")).toBe("43");
  });

  it("falls back per field when the server sent no figure", () => {
    // An older server, or the first frame of a run before any solve landed.
    show({ solveMs: null, intervalMs: null, nSolves: null });
    expect(rowValue("solve")).toBe("12.5 ms");
    expect(rowValue("rtt")).toBe("31.0 ms");
    expect(rowValue("solves")).toBeNull();
  });
});
