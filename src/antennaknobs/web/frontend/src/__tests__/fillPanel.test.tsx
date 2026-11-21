// The Fill view (AK#2327): every state momwire's report can be in reads as
// what it is, and the map can be read without colour.
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { FillPanel } from "../components/results/FillPanel";
import {
  compression,
  type FillReport,
  type FillReuse,
  type FillReuseMap,
  fillShare,
  reuseCellText,
  reuseNote,
} from "../lib/fillReport";

const REUSE: FillReuse = {
  state: "served",
  declined: null,
  pairs: 100,
  computed: 40,
  reused: 50,
  near: 10,
  kernel_evals: 50,
  families: {
    direct: { pairs: 60, computed: 20, reused: 35, near: 5, kernel_evals: 25 },
    "a-family-nobody-named-yet": { pairs: 40, computed: 20, reused: 15, near: 5, kernel_evals: 25 },
  },
  uncounted: [],
  plan_bytes: 0,
  census_peak_bytes: null,
};

const MAP: FillReuseMap = {
  kind: "reuse",
  rows: [
    { label: "driver", first: 0, last: 0, wires: 1, segments: 5 },
    { label: "wire 2", first: 1, last: 1, wires: 1, segments: 5 },
  ],
  computed: [[10, 10], [10, 10]],
  reused: [[10, 15], [15, 10]],
  near: [[5, 0], [0, 5]],
};

function report(over: Partial<FillReport> = {}): FillReport {
  return {
    version: 1,
    scope: "solve",
    source: "fresh",
    solved_at: 1_800_000_000,
    solver: "RazorSolver",
    fills: 1,
    frequencies: 1,
    times: { fill_s: 0.75, factor_s: 0.25, census_s: 0.1 },
    no_fill: false,
    points_cached: 0,
    route: "dense",
    reuse_asked: true,
    reuse: REUSE,
    sector: null,
    map: MAP,
    ...over,
  };
}

function show(r: FillReport | null, extra: { refusal?: FillReport; sweep?: FillReport } = {}) {
  return render(
    <FillPanel report={r} refusal={extra.refusal ?? null} sweep={extra.sweep ?? null} size={800} fill />,
  );
}

describe("the numbers", () => {
  it("compression is pairs over computed plus near", () => {
    expect(compression(REUSE)).toBeCloseTo(2);
  });
  it("the fill's share is of fill plus factor", () => {
    expect(fillShare(report())).toBeCloseTo(0.75);
  });
  it("a cell's detail adds up to its pairs", () => {
    expect(reuseCellText(MAP, 0, 1)).toContain("driver × wire 2: 25 pairs");
  });
});

describe("the readout", () => {
  it("labels compression as not being time saved, and says what the fill is of the solve", () => {
    show(report());
    expect(screen.getByText(/It is not the time saved/)).toBeTruthy();
    expect(screen.getByText(/The fill is 75% of the fill and factor time/)).toBeTruthy();
    expect(screen.getByText(/Pair reuse shortens the fill only/)).toBeTruthy();
  });
  it("draws a family it has never heard of", () => {
    show(report());
    expect(screen.getByText("a-family-nobody-named-yet")).toBeTruthy();
  });
  it("says reuse is off, with the times still shown", () => {
    show(report({ reuse: null, reuse_asked: false, map: null }));
    expect(screen.getByText("Fill reuse is off for this solve.")).toBeTruthy();
    expect(screen.getByText("750 ms")).toBeTruthy();
  });
  it("gives a decline's reason", () => {
    const declined = { ...REUSE, state: "declined" as const, declined: "too few segments", pairs: null };
    expect(reuseNote(report({ reuse: declined }))).toBe("Fill reuse declined: too few segments.");
  });
  it("names what a partial fill left out", () => {
    const partial = { ...REUSE, state: "partial" as const, declined: "the image family" };
    show(report({ reuse: partial }));
    expect(screen.getByText(/Left out: the image family/)).toBeTruthy();
  });
  it("never shows an uncounted family as zero", () => {
    show(report({ reuse: { ...REUSE, uncounted: ["remainder"] } }));
    expect(screen.getByText(/Not counted by this fill: remainder\./)).toBeTruthy();
  });
  it("over a ground, keeps the free-space term apart from the ground terms", () => {
    const bspline = { ...REUSE, families: { direct: REUSE.families.direct }, uncounted: ["image", "remainder"] };
    show(report({ reuse: bspline }));
    expect(screen.getByText("Without ground terms: the free-space (direct) term")).toBeTruthy();
    expect(screen.getByText("Ground terms")).toBeTruthy();
    expect(screen.getByText(/Not counted by this fill: image, remainder\./)).toBeTruthy();
    // with a term uncounted there is no all-terms total to read as the whole fill
    expect(screen.queryByText("All terms")).toBeNull();
  });
  it("shows each counted ground term in its own row, and the all-terms total", () => {
    const razor = {
      ...REUSE,
      families: { direct: REUSE.families.direct, remainder: { pairs: 40, computed: 30, reused: 10, near: 0, kernel_evals: 30 } },
    };
    show(report({ reuse: razor }));
    expect(screen.getByText("remainder")).toBeTruthy();
    expect(screen.getByText("All terms")).toBeTruthy();
  });
  it("has no ground section in free space", () => {
    show(report({ reuse: { ...REUSE, families: { direct: REUSE.families.direct } } }));
    expect(screen.queryByText("Ground terms")).toBeNull();
  });
  it("says a cached answer's numbers are an earlier solve's", () => {
    show(report({ source: "cached" }));
    expect(screen.getByText(/came from the solve cache/)).toBeTruthy();
  });
  it("shows no times or counts when the matrix came from memory", () => {
    show(report({ no_fill: true, fills: 0, reuse: null, map: null, route: null }));
    expect(screen.getByText(/already in memory/)).toBeTruthy();
    expect(screen.queryByText("fill")).toBeNull();
  });
  it("says what a sweep's totals cover", () => {
    show(report(), { sweep: report({ scope: "sweep", frequencies: 21, points_cached: 3 }) });
    expect(screen.getByText(/totals over 21 solved frequencies/)).toBeTruthy();
    expect(screen.getByText(/3 more came from the sweep cache/)).toBeTruthy();
  });
  it("shows a refusal's sentence with no report", () => {
    const refusal = report({
      source: "refused",
      sector: { n_sectors: null, axial: null, blocks: [], computed_pairs: null, pairs: null, declined: "no axis." },
    });
    show(null, { refusal });
    expect(screen.getByRole("status").textContent).toBe("no axis.");
  });
  it("says so when the engine has no report", () => {
    show(null);
    expect(screen.getByText("The engine on this tab does not report its fill.")).toBeTruthy();
  });
  it("offers no advice", () => {
    const { container } = show(report());
    expect(container.textContent).not.toMatch(/\b(try|should|consider|recommend)\b/i);
  });
});

describe("the sector route", () => {
  const sector = report({
    route: "sector",
    reuse: null,
    reuse_asked: false,
    sector: {
      n_sectors: 4,
      axial: 1,
      blocks: [{ size: 52, count: 3 }],
      computed_pairs: 5616,
      pairs: 13689,
      declined: null,
    },
    map: {
      kind: "sector",
      rows: [
        { label: "wire 1", first: 0, last: 0, wires: 1, segments: 9, sector_first: 0, sector_last: 0, role: "computed" },
        { label: "wire 2", first: 1, last: 1, wires: 1, segments: 9, sector_first: 1, sector_last: 1, role: "rotation" },
      ],
    },
  });
  it("gives sectors, blocks and entries, and that the factor shortens too", () => {
    show(sector);
    expect(screen.getByText("3 × 52")).toBeTruthy();
    expect(screen.getByText("5,616 of 13,689")).toBeTruthy();
    expect(screen.getByText(/shortens the fill and the factor/)).toBeTruthy();
  });
  it("labels each row with its sector", () => {
    const { container } = show(sector);
    const labels = [...container.querySelectorAll(".fill-axis")].map((t) => t.textContent);
    expect(labels).toContain("1 wire 1 · sector 1");
    expect(labels).toContain("2 wire 2 · sector 2");
    expect(container.querySelectorAll(".fill-sector-edge")).toHaveLength(1);
  });
  it("marks computed rows and rotated rows in words in its table", () => {
    show(sector);
    fireEvent.click(screen.getByRole("button", { name: "Show as table" }));
    expect(screen.getByText("computed")).toBeTruthy();
    expect(screen.getByText("follows from rotation")).toBeTruthy();
  });
});

describe("the map without colour", () => {
  it("names each mark's pattern in the key", () => {
    show(report());
    expect(screen.getByText("reused (hatched)")).toBeTruthy();
    expect(screen.getByText("near (dotted)")).toBeTruthy();
  });
  it("reads a block by keyboard", () => {
    show(report());
    fireEvent.keyDown(screen.getByRole("img"), { key: "ArrowRight" });
    expect(screen.getByText(/driver × wire 2: 25 pairs/)).toBeTruthy();
  });
  it("gives every block as a table", () => {
    show(report());
    fireEvent.click(screen.getByRole("button", { name: "Show as table" }));
    expect(screen.getByRole("table", { name: "Pairs per wire block" })).toBeTruthy();
  });
});

describe("a large map", () => {
  it("draws 32 × 32 grouped blocks as three marks, not a node per cell", () => {
    const n = 32;
    const grid = Array.from({ length: n }, () => Array.from({ length: n }, () => 7));
    const big: FillReuseMap = {
      kind: "reuse",
      rows: Array.from({ length: n }, (_, i) => ({
        label: `wire ${i * 13 + 1} – wire ${i * 13 + 13}`,
        first: i * 13,
        last: i * 13 + 12,
        wires: 13,
        segments: 117,
      })),
      computed: grid,
      reused: grid,
      near: grid,
    };
    const { container } = show(report({ map: big }));
    expect(container.querySelectorAll(".fill-grid path")).toHaveLength(3);
    expect(container.querySelectorAll(".fill-grid rect").length).toBeLessThan(10);
    expect(screen.getByText(/Wires are grouped/)).toBeTruthy();
  });
});
