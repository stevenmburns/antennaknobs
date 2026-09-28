// The range popover while it is open (Steve, 2026-09-26): "you don't see
// what you are getting until you commit to it". Two halves:
//   - the y-axis button (over the tick labels) never fills when hovered,
//     focused or open, so the ticks stay readable — it had filled with
//     --accent-soft, an opaque tint in the light theme;
//   - a choice applies to the chart at once, with the popover still open.
import { useState } from "react";
import { describe, it, expect } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { SweepChart } from "../components/charts/SweepChart";
import type { SweepData } from "../lib/api";
import { RECIPROCAL, RHO, type SweepAxisChoice } from "../lib/sweepAxis";
import stylesSrc from "../styles.css?raw";

HTMLCanvasElement.prototype.getContext = (() =>
  null) as unknown as HTMLCanvasElement["getContext"];

describe("the axis button never hides the tick labels", () => {
  // Every rule in styles.css whose selector names the axis button.
  const rules = [...stylesSrc.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .map((m) => ({ selector: m[1].trim(), body: m[2] }))
    .filter((r) => r.selector.includes(".sweep-axis-btn"));

  it("styles its hover, focus and open states", () => {
    const states = rules.map((r) => r.selector).join(" ");
    expect(states).toContain('.sweep-axis-btn[aria-expanded="true"]');
    expect(states).toContain(".sweep-axis-btn:focus-visible");
    expect(states).toContain(".sweep-axis-btn:hover");
  });

  it("with no fill: any background it declares is transparent", () => {
    // Themes redefine the tokens, not these rules, so this covers dark too.
    for (const r of rules) {
      for (const m of r.body.matchAll(
        /background(?:-color)?\s*:\s*([^;]+);/g,
      )) {
        expect(m[1].trim(), r.selector).toBe("transparent");
      }
    }
  });
});

// A resonance whose band edges reach SWR ~18.
const FREQS = Array.from({ length: 21 }, (_, i) => 13.7 + i * 0.05);
const SWEEP: SweepData = {
  freqs_mhz: FREQS,
  z_re: FREQS.map(() => 50),
  z_im: FREQS.map((f) => 400 * (f - 14.2)),
};

// The session's part, reduced to state: the chart's choice lives above it.
function Stateful({ start }: { start: SweepAxisChoice }) {
  const [axis, setAxis] = useState<SweepAxisChoice>(start);
  return (
    <SweepChart
      mode="vswr"
      r={0}
      x={0}
      z0={50}
      size={236}
      sweep={SWEEP}
      measFreqMhz={14.2}
      running={false}
      multiFeed={false}
      axis={axis}
      onAxisChange={setAxis}
    />
  );
}

const canvas = () =>
  document.querySelector("canvas.sweep") as HTMLCanvasElement;
const dialogOpen = () =>
  screen.queryByRole("dialog", { name: "VSWR range" }) !== null;

describe("a choice applies while the popover stays open", () => {
  it("presets and 1–∞ redraw the axis at once", () => {
    render(<Stateful start={RECIPROCAL} />);
    fireEvent.click(
      screen.getByRole("button", { name: "VSWR range and SWR threshold" }),
    );
    expect(canvas().dataset.ticks).toBe("1,1.5,2,3,5,10,∞");
    fireEvent.click(screen.getByRole("button", { name: "1–3" }));
    expect(dialogOpen()).toBe(true);
    expect(canvas().dataset.yHi).toBe("3");
    expect(canvas().dataset.ticks).toBe("1,1.5,2,2.5,3");
    fireEvent.click(screen.getByRole("button", { name: "1–∞" }));
    expect(dialogOpen()).toBe(true);
    expect(canvas().dataset.axis).toBe("reciprocal");
  });

  it("a custom max applies on each valid edit, as typed", () => {
    render(<Stateful start={{ kind: "fixed", lo: 1, hi: 2 }} />);
    fireEvent.click(
      screen.getByRole("button", { name: "VSWR range and SWR threshold" }),
    );
    const [, maxField] = screen.getAllByRole("spinbutton");
    fireEvent.change(maxField, { target: { value: "4" } });
    expect(dialogOpen()).toBe(true);
    expect(canvas().dataset.yHi).toBe("4");
    // An invalid edit (max below min) is refused and leaves the chart be.
    fireEvent.change(maxField, { target: { value: "0.5" } });
    expect(canvas().dataset.yHi).toBe("4");
  });
});

// Dan, QRZ #170 fig 8: with ρ (EZNEC) selected the min/max fields read 1 / 10,
// a range the whole-range scale does not draw. On 1–∞ and ρ they now read a
// greyed 1 / ∞. ∞ is not a linear top, so the bottom cannot change while the
// top is ∞: min is disabled, and a typed max switches to the linear range
// from 1, after which min is editable like any finite range.
describe("min / max on the whole-range scales", () => {
  for (const [name, start] of [
    ["ρ (EZNEC)", RHO],
    ["1–∞", RECIPROCAL],
  ] as const) {
    it(`${name}: a greyed 1 / ∞, min disabled; a max makes it linear from 1`, () => {
      render(<Stateful start={start} />);
      fireEvent.click(
        screen.getByRole("button", { name: "VSWR range and SWR threshold" }),
      );
      const [minField, maxField] = screen.getAllByRole(
        "spinbutton",
      ) as HTMLInputElement[];
      expect([minField.value, maxField.value]).toEqual(["", ""]);
      expect([minField.placeholder, maxField.placeholder]).toEqual(["1", "∞"]);
      expect(minField.disabled).toBe(true);
      expect(maxField.disabled).toBe(false);

      fireEvent.change(maxField, { target: { value: "12" } });
      expect(canvas().dataset.axis).toBe("fixed");
      expect([canvas().dataset.yLo, canvas().dataset.yHi]).toEqual(["1", "12"]);

      // Now finite: the fields say what it is, and the bottom is editable.
      const [lo, hi] = screen.getAllByRole("spinbutton") as HTMLInputElement[];
      expect([lo.value, hi.value]).toEqual(["1", "12"]);
      expect(lo.disabled).toBe(false);
      fireEvent.change(lo, { target: { value: "3" } });
      expect([canvas().dataset.yLo, canvas().dataset.yHi]).toEqual(["3", "12"]);
    });
  }

  it("clearing the greyed max puts ∞ back, not an error", () => {
    render(<Stateful start={RHO} />);
    fireEvent.click(
      screen.getByRole("button", { name: "VSWR range and SWR threshold" }),
    );
    const [, maxField] = screen.getAllByRole(
      "spinbutton",
    ) as HTMLInputElement[];
    fireEvent.change(maxField, { target: { value: "" } });
    expect(maxField.value).toBe("");
    expect(maxField.getAttribute("aria-invalid")).toBeNull();
    expect(canvas().dataset.axis).toBe("rho");
  });

  it("a fixed range still shows its own numbers, both editable", () => {
    render(<Stateful start={{ kind: "fixed", lo: 1, hi: 3 }} />);
    fireEvent.click(
      screen.getByRole("button", { name: "VSWR range and SWR threshold" }),
    );
    const [minField, maxField] = screen.getAllByRole(
      "spinbutton",
    ) as HTMLInputElement[];
    expect([minField.value, maxField.value]).toEqual(["1", "3"]);
    expect(minField.placeholder).toBe("");
    expect(minField.disabled).toBe(false);
  });
});
