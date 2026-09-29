// The Z-vs-parameter chart on a phone (AK#1757, Steve's phone review of
// units 4a/4b): the Z∞ readout's reason behind an ⓘ, and small per-point dots.
// The canvas has no 2-D context in jsdom, so the drawn choices are read from
// data-* attributes set from the very values the drawing uses.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ZParamChart } from "../components/charts/ZParamChart";
import { traceDotRadius } from "../lib/paramSweep";
import type { ParamSweepData } from "../lib/paramSweep";
import type { ExtraCurve } from "../components/charts/curves";

HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];

const REASON = ": fed segment 100.0→33.3 mm at N 65→95";
const ROUGH: ParamSweepData = {
  param: "n_per_wire",
  label: "N",
  values: [8, 12, 17, 24],
  z_re: [70.7, 70.73, 70.75, 70.76],
  z_im: [-10.3, -10.1, -10.0, -9.9],
  z_re_extrap: 70.79,
  z_im_extrap: -9.6,
  z_extrap_status: "rough",
  z_extrap_reason: REASON,
};
const KNOB: ParamSweepData = {
  param: "length_factor",
  label: "length factor",
  values: [0.9, 1.0, 1.1],
  z_re: [55, 70, 88],
  z_im: [-40, 0, 45],
  z_re_extrap: null,
  z_im_extrap: null,
};

function stubMedia(mobile: boolean) {
  vi.stubGlobal("matchMedia", () => ({
    matches: mobile,
    addEventListener() {},
    removeEventListener() {},
  }));
}
afterEach(() => vi.unstubAllGlobals());

function mount(data: ParamSweepData, p: Partial<React.ComponentProps<typeof ZParamChart>> = {}) {
  const r = render(
    <ZParamChart
      data={data}
      param={data.param}
      label={data.label}
      total={data.values.length}
      currentValue={data.values[1]}
      liveR={70}
      liveX={0}
      size={300}
      running={false}
      xLog={false}
      {...p}
    />,
  );
  return r.container.querySelector("canvas.zparam") as HTMLElement;
}

const curve = (key: string): ExtraCurve => ({ key, color: "#f00", paramSweep: KNOB });

describe("the Z∞ readout's reason on a phone", () => {
  it("phone: a short line and an ⓘ that shows the full sentence on tap", () => {
    stubMedia(true);
    const c = mount(ROUGH);
    expect(c.dataset.zinfLine).toBe("short");
    expect(screen.queryByRole("note")).toBeNull();
    const btn = screen.getByRole("button", { name: "Show the Z∞ note" });
    // One DOM row: the short text, then the ⓘ right after it, so the button
    // can never sit on top of the value (Steve's phone, second pass).
    const line = document.querySelector(".zinf-line") as HTMLElement;
    expect(line).not.toBeNull();
    const text = line.querySelector(".zinf-text") as HTMLElement;
    expect(text.textContent).toBe("Z∞ ≈ 70.79 − j9.60 Ω · rough");
    expect(text.nextElementSibling).toBe(btn);
    fireEvent.click(btn);
    const note = screen.getByRole("note", { name: "Z∞ note" });
    expect(note.textContent).toContain("Z∞ ≈ 70.79 − j9.60 Ω · rough");
    expect(note.textContent).toContain(REASON);
    fireEvent.click(screen.getByRole("button", { name: "Hide the Z∞ note" }));
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("phone: no reason, no ⓘ", () => {
    stubMedia(true);
    mount({ ...ROUGH, z_extrap_reason: null });
    expect(screen.queryByRole("button", { name: /Z∞ note/ })).toBeNull();
  });

  it("desktop: the full line on the canvas and no ⓘ", () => {
    stubMedia(false);
    const c = mount(ROUGH);
    expect(c.dataset.zinfLine).toBe("full");
    expect(c.dataset.extrapReason).toBe(REASON);
    expect(screen.queryByRole("button", { name: /Z∞ note/ })).toBeNull();
    expect(document.querySelector(".zinf-line")).toBeNull();
  });
});

describe("the per-point dots", () => {
  it("the rule", () => {
    expect(traceDotRadius(true, 1)).toBe(1.2);
    expect(traceDotRadius(false, 1)).toBe(2.6);
    expect(traceDotRadius(false, 2)).toBe(2.6);
    expect(traceDotRadius(false, 3)).toBe(1.2);
  });

  it("a phone draws small dots even for one curve", () => {
    stubMedia(true);
    expect(mount(KNOB).dataset.dotR).toBe("1.2");
  });

  it("the live marker keeps full size on a phone and with many curves", () => {
    stubMedia(true);
    const c = mount(KNOB, { curves: [curve("a"), curve("b"), curve("c")] });
    expect(c.dataset.dotR).toBe("1.2");
    expect(c.dataset.liveR).toBe("4");
  });

  it("desktop: full size for one curve, small from three curves", () => {
    stubMedia(false);
    expect(mount(KNOB).dataset.dotR).toBe("2.6");
    cleanupAll();
    expect(mount(KNOB, { curves: [curve("a")] }).dataset.dotR).toBe("2.6");
    cleanupAll();
    expect(mount(KNOB, { curves: [curve("a"), curve("b")] }).dataset.dotR).toBe("1.2");
  });
});

function cleanupAll() {
  document.body.innerHTML = "";
}
