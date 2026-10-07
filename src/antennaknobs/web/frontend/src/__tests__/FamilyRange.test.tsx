// The family's knob select leaves out a density-role knob and says why
// (AK#1935 follow-up): a family over the mesh density is refused by
// `analyze`, so the chart does not offer it to solve and fail.
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { FamilyRange } from "../components/results/FamilyRange";
import type { ParamSweepSpec } from "../lib/paramSweep";

const SPEC: ParamSweepSpec = { param: "base", lo: 4, hi: 14, points: 3, log: false };
const props = {
  spec: SPEC,
  values: [4, 9, 14],
  onSpec: () => {},
  onParam: () => {},
  onReset: () => {},
  isDefault: true,
};

describe("the family's knob select", () => {
  it("offers no density knob, and its title says why", () => {
    render(
      <FamilyRange
        {...props}
        knobs={[{ name: "base", label: "Base" }, { name: "freq", label: "frequency (MHz)" }]}
        skipped={[{ name: "nseg", label: "Segments" }]}
      />,
    );
    const select = screen.getByLabelText("Parameter") as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["base", "freq"]);
    expect(select.title).toMatch(/Segments.*mesh density.*refused/);
  });

  it("carries no note when nothing was left out", () => {
    render(<FamilyRange {...props} knobs={[{ name: "base", label: "Base" }]} />);
    expect((screen.getByLabelText("Parameter") as HTMLSelectElement).title).toBe("");
  });
});
