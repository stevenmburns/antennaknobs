// The Z-vs-parameter chart on a phone (AK#1757, Steve's phone review of
// units 4a/4b): the Z∞ readout's reason behind an ⓘ, and small per-point dots.
// The canvas has no 2-D context in jsdom, so the drawn choices are read from
// data-* attributes set from the very values the drawing uses.
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { ZParamChart } from "../components/charts/ZParamChart";
import { traceDotRadius } from "../lib/paramSweep";
import type { ParamSweepData } from "../lib/paramSweep";
import type { ExtraCurve } from "../components/charts/curves";

HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];

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

describe("the per-point dots", () => {
  it("the rule", () => {
    expect(traceDotRadius(true, 1)).toBe(2);
    expect(traceDotRadius(false, 1)).toBe(2.6);
    expect(traceDotRadius(false, 2)).toBe(2.6);
    expect(traceDotRadius(false, 3)).toBe(2);
  });

  it("a phone draws small dots even for one curve", () => {
    stubMedia(true);
    expect(mount(KNOB).dataset.dotR).toBe("2");
  });

  it("the live marker keeps full size on a phone and with many curves", () => {
    stubMedia(true);
    const c = mount(KNOB, { curves: [curve("a"), curve("b"), curve("c")] });
    expect(c.dataset.dotR).toBe("2");
    expect(c.dataset.liveR).toBe("4");
  });

  it("desktop: full size for one curve, small from three curves", () => {
    stubMedia(false);
    expect(mount(KNOB).dataset.dotR).toBe("2.6");
    cleanupAll();
    expect(mount(KNOB, { curves: [curve("a")] }).dataset.dotR).toBe("2.6");
    cleanupAll();
    expect(mount(KNOB, { curves: [curve("a"), curve("b")] }).dataset.dotR).toBe("2");
  });
});

function cleanupAll() {
  document.body.innerHTML = "";
}
