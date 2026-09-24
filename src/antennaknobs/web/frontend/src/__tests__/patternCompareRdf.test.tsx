import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PatternCompareTable } from "../components/results/PatternCompareTable";
import type { PatternMetrics } from "../components/charts/types";

// AK#1707: the compare table carries the receiving directivity factor beside
// F/B, and a row whose metrics predate the field shows a dash, not "NaN".
const BASE: PatternMetrics = {
  peak_gain_dbi: -9.1,
  takeoff_deg: 30,
  azimuth_deg: 0,
  front_to_back_db: 18.4,
  az_beamwidth_deg: 65,
  el_beamwidth_deg: 41,
};

describe("PatternCompareTable RDF column", () => {
  it("shows the RDF to one decimal", () => {
    render(
      <PatternCompareTable
        live={{ ...BASE, rdf_db: 11.94 }}
        liveLabel="beverage"
        pinned={[]}
        onRemove={() => {}}
        onToggle={() => {}}
      />,
    );
    expect(screen.getByText("RDF")).toBeTruthy();
    expect(screen.getByText("11.9")).toBeTruthy();
  });

  it("shows a dash when the server sent no RDF", () => {
    render(
      <PatternCompareTable
        live={BASE}
        liveLabel="old pin"
        pinned={[]}
        onRemove={() => {}}
        onToggle={() => {}}
      />,
    );
    const cells = screen.getAllByRole("cell").map((c) => c.textContent);
    // design, peak, takeoff, F/B, az bw, RDF, (remove)
    expect(cells[5]).toBe("—");
  });
});
