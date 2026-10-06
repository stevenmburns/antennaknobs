// Analysis groups in the picker (AK#1907): a design listing more than three
// analyses in more than one group shows each group under its heading (an
// <optgroup>), in the served order; three or fewer, or one group, show none.
// The order within a group is the served order.
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { AnalysisSelect } from "../components/results/AnalysisPicker";
import {
  analysisGroups,
  parseAnalyses,
  type AnalysisEntry,
  type AnalysisWorkbench,
} from "../lib/analyses";

const RUNS = { runs: true, kind: "knob", param: "base", values: [1, 2], log: false, note: null };

const entry = (name: string, group?: string, study = false): AnalysisEntry => ({
  name,
  summary: "",
  code: "",
  problems: [],
  workbench: RUNS as AnalysisWorkbench,
  study: study ? { source: "studies.x", name } : null,
  ...(group ? { group } : {}),
});

// The invvee as /analyses serves it: grouped, the generic one last.
const INVVEE = [
  entry("tuning family", "Tuning"),
  entry("tuning map", "Tuning"),
  entry("resonance vs angle", "Tuning"),
  entry("match vs height", "Tuning"),
  entry("height", "Height & ground"),
  entry("height states", "Height & ground"),
  entry("height patterns", "Height & ground"),
  entry("convergence", "Accuracy"),
  entry("band SWR", "General"),
];

function optgroups() {
  return screen.queryAllByRole("group").map((g) => ({
    label: g.getAttribute("label"),
    options: within(g)
      .getAllByRole("option")
      .map((o) => o.textContent),
  }));
}

describe("analysisGroups", () => {
  it("groups a long list by heading, keeping the served order", () => {
    const got = analysisGroups(INVVEE).map((g) => [g.group, g.entries.map((a) => a.name)]);
    expect(got).toEqual([
      ["Tuning", ["tuning family", "tuning map", "resonance vs angle", "match vs height"]],
      ["Height & ground", ["height", "height states", "height patterns"]],
      ["Accuracy", ["convergence"]],
      ["General", ["band SWR"]],
    ]);
  });

  it("shows no headings for three analyses or fewer", () => {
    const three = [entry("convergence", "General"), entry("band SWR", "General"), entry("height", "X")];
    expect(analysisGroups(three)).toEqual([{ group: null, entries: three }]);
  });

  it("shows no headings for one group, or from an older server", () => {
    const general = ["a", "b", "c", "d"].map((n) => entry(n, "General"));
    expect(analysisGroups(general).map((g) => g.group)).toEqual([null]);
    const old = ["a", "b", "c", "d"].map((n) => entry(n));
    expect(analysisGroups(old).map((g) => g.group)).toEqual([null]);
  });

  it("counts the design's whole list, not only what runs here", () => {
    // Three run, but the design lists five: the headings stay.
    const runnable = INVVEE.slice(0, 3);
    expect(analysisGroups(runnable, INVVEE.slice(0, 5)).map((g) => g.group)).toEqual(["Tuning"]);
  });

  it("parses the served group, and leaves it out when absent", () => {
    const body = {
      analyses: [
        { name: "a", group: "Tuning", workbench: { runs: false, why: "no" } },
        { name: "b", workbench: { runs: false, why: "no" } },
      ],
    };
    const [a, b] = parseAnalyses(body);
    expect(a.group).toBe("Tuning");
    expect("group" in b).toBe(false);
  });
});

describe("AnalysisSelect headings", () => {
  it("draws each group as an optgroup, in order, the Studies group after", () => {
    render(
      <AnalysisSelect
        entries={[...INVVEE, entry("vs the dipole", "Tuning", true)]}
        current={null}
        blocked={() => null}
        onPick={() => {}}
      />,
    );
    expect(optgroups()).toEqual([
      {
        label: "Tuning",
        options: ["tuning family", "tuning map", "resonance vs angle", "match vs height"],
      },
      { label: "Height & ground", options: ["height", "height states", "height patterns"] },
      { label: "Accuracy", options: ["convergence"] },
      { label: "General", options: ["band SWR"] },
      { label: "Studies", options: ["vs the dipole"] },
    ]);
  });

  it("draws no headings for a design with three analyses", () => {
    render(
      <AnalysisSelect
        entries={[entry("convergence", "General"), entry("band SWR", "General"), entry("height", "General")]}
        current={null}
        blocked={() => null}
        onPick={() => {}}
      />,
    );
    expect(optgroups()).toEqual([]);
    const names = screen.getAllByRole("option").map((o) => o.textContent);
    expect(names).toEqual(["pick…", "convergence", "band SWR", "height"]);
  });

  it("keeps what cannot run here in its own group, out of the headings", () => {
    const blocked = (a: AnalysisEntry) => (a.name === "tuning map" ? "a map" : null);
    render(
      <AnalysisSelect entries={INVVEE} current={null} blocked={blocked} onPick={() => {}} />,
    );
    const groups = optgroups();
    expect(groups[0]).toEqual({
      label: "Tuning",
      options: ["tuning family", "resonance vs angle", "match vs height"],
    });
    expect(groups.at(-1)).toEqual({
      label: "Not in the workbench yet",
      options: ["tuning map (not here yet)"],
    });
  });
});
