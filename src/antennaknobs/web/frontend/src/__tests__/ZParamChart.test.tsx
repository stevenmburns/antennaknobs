// The Z-vs-parameter chart (docs/design/z-vs-param-view.md): what it draws,
// read through its data-* attributes (jsdom has no 2-D context), and its
// controls — the two y-axis range popovers and the lin/log x toggle.
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ZParamChart } from "../components/charts/ZParamChart";
import { nudgeClear } from "../lib/paramSweep";
import { SweepChart } from "../components/charts/SweepChart";
import type { ParamSweepData } from "../lib/paramSweep";

HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];

const DENSITY_SWEEP: ParamSweepData = {
  param: "n_per_wire",
  label: "N",
  values: [8, 12, 17, 24, 34, 48, 68],
  z_re: [70.72, 70.735, 70.75, 70.76, 70.77, 70.775, 70.78],
  z_im: [-10.3, -10.16, -10.0, -9.9, -9.8, -9.75, -9.7],
  z_re_extrap: 70.79,
  z_im_extrap: -9.6,
};

const KNOB_SWEEP: ParamSweepData = {
  param: "length_factor",
  label: "length factor",
  values: [0.9, 1.0, 1.1],
  z_re: [55, 70, 88],
  z_im: [-40, 0, 45],
  z_re_extrap: null,
  z_im_extrap: null,
};

type Props = Partial<React.ComponentProps<typeof ZParamChart>>;

function mount(p: Props = {}) {
  const props: React.ComponentProps<typeof ZParamChart> = {
    data: DENSITY_SWEEP,
    param: "n_per_wire",
    label: "N",
    total: 7,
    currentValue: 15,
    liveR: 70.745,
    liveX: -10.05,
    size: 400,
    running: false,
    xLog: true,
    ...p,
  };
  const r = render(<ZParamChart {...props} />);
  const canvas = () => r.container.querySelector("canvas.zparam") as HTMLElement;
  return { ...r, canvas };
}

describe("what the chart draws", () => {
  it("a density sweep: every point, log x, Z* on both axes", () => {
    const c = mount().canvas();
    expect(c.dataset.param).toBe("n_per_wire");
    expect(c.dataset.values).toBe("8,12,17,24,34,48,68");
    expect(c.dataset.r!.split(",")).toHaveLength(7);
    expect(c.dataset.xLog).toBe("1");
    expect(c.dataset.extrap).toBe("70.790,-9.600");
    // Each axis auto-fits its own trace (and Z*): R and X ranges are apart.
    expect(Number(c.dataset.rLo)).toBeGreaterThan(70);
    expect(Number(c.dataset.xHi)).toBeLessThan(0);
  });

  it("a knob sweep: no Z*, and the current value's guide", () => {
    const c = mount({
      data: KNOB_SWEEP,
      param: "length_factor",
      label: "length factor",
      total: 3,
      currentValue: 0.97,
      xLog: false,
    }).canvas();
    expect(c.dataset.extrap).toBe("");
    expect(c.dataset.xLog).toBe("0");
    expect(c.dataset.guide).toBe("0.97");
  });

  it("the guide follows the current value and drops off outside the sweep", () => {
    const r = mount({ currentValue: 15 });
    expect(r.canvas().dataset.guide).toBe("15");
    r.rerender(
      <ZParamChart
        data={DENSITY_SWEEP}
        param="n_per_wire"
        label="N"
        total={7}
        currentValue={100}
        liveR={70}
        liveX={-10}
        size={400}
        running={false}
        xLog
      />,
    );
    expect(r.canvas().dataset.guide).toBe("");
    // The points are the same points: the guide moved, the sweep did not.
    expect(r.canvas().dataset.values).toBe("8,12,17,24,34,48,68");
  });

  it("a sweep of another parameter is not drawn under this one's name", () => {
    const c = mount({ param: "length_factor", label: "length factor" }).canvas();
    expect(c.dataset.points).toBe("0");
    expect(c.dataset.status).toBe("no sweep yet — length factor");
  });

  it("counts the points in while streaming", () => {
    const c = mount({
      data: { ...DENSITY_SWEEP, values: [8, 12], z_re: [1, 2], z_im: [1, 2] },
      running: true,
    }).canvas();
    expect(c.dataset.status).toBe("sweeping N 2/7…");
  });

  it("a fixed range is drawn as given", () => {
    const c = mount({ rAxis: { kind: "fixed", lo: 70, hi: 71 } }).canvas();
    expect(c.dataset.rLo).toBe("70.0000");
    expect(c.dataset.rHi).toBe("71.0000");
  });

  it("hover reads the nearest point", () => {
    const c = mount().canvas();
    c.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 400, height: 400 }) as DOMRect;
    // The plot spans x 46…354; its left edge is the first point.
    // jsdom has no PointerEvent: a MouseEvent of the pointer type carries
    // the coordinates React reads.
    const move = (clientX: number) =>
      fireEvent(c, new MouseEvent("pointermove", { clientX, clientY: 100, bubbles: true }));
    move(46);
    expect(c.dataset.hover).toBe("0");
    move(354);
    expect(c.dataset.hover).toBe("6");
    fireEvent.pointerLeave(c);
    expect(c.dataset.hover).toBe("");
  });
});

describe("the chart's controls", () => {
  it("a thumbnail (no callbacks) has none", () => {
    mount();
    expect(screen.queryByRole("button", { name: "R range" })).toBeNull();
    expect(screen.queryByRole("button", { name: /lin x|log x/ })).toBeNull();
  });

  it("each y axis opens its own range popover: Auto, or a custom min/max", async () => {
    const user = userEvent.setup();
    const onAxisChange = vi.fn();
    mount({ onAxisChange });
    await user.click(screen.getByRole("button", { name: "X range" }));
    const dialog = screen.getByRole("dialog", { name: "X range" });
    expect(dialog).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Auto" }));
    expect(onAxisChange).toHaveBeenLastCalledWith("x", { kind: "auto" });
    const [lo] = screen.getAllByRole("spinbutton");
    await user.clear(lo);
    await user.type(lo, "-12");
    expect(onAxisChange).toHaveBeenLastCalledWith(
      "x",
      expect.objectContaining({ kind: "fixed", lo: -12 }),
    );
  });

  it("toggles lin/log x, and refuses log over a span that reaches zero", async () => {
    const user = userEvent.setup();
    const onXLogChange = vi.fn();
    const r = mount({ onXLogChange });
    await user.click(screen.getByRole("button", { name: "log x" }));
    expect(onXLogChange).toHaveBeenCalledWith(false);
    r.unmount();
    mount({
      data: { ...KNOB_SWEEP, param: "offset", values: [-1, 0, 1] },
      param: "offset",
      label: "offset",
      xLog: true,
      onXLogChange,
    });
    const btn = screen.getByRole("button", { name: "lin x" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});

// Steve, 2026-09-26: at 125 % zoom the X axis's popover opened mostly off
// screen. A narrow viewport and a click at the right-hand axis: the box must
// land wholly inside the viewport.
describe("the range popovers stay inside the viewport", () => {
  const W = 360;
  const H = 600;
  const BOX = { width: 220, height: 150 };
  function narrow() {
    vi.stubGlobal("innerWidth", W);
    vi.stubGlobal("innerHeight", H);
    // jsdom lays nothing out: every element measures as the popover would.
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
      this: HTMLElement,
    ) {
      const left = parseFloat(this.style.left) || 0;
      const top = parseFloat(this.style.top) || 0;
      return {
        left, top, x: left, y: top, width: BOX.width, height: BOX.height,
        right: left + BOX.width, bottom: top + BOX.height, toJSON: () => ({}),
      } as DOMRect;
    });
  }
  const inside = (el: HTMLElement) => {
    const left = parseFloat(el.style.left);
    const top = parseFloat(el.style.top);
    expect(left).toBeGreaterThanOrEqual(0);
    expect(left + BOX.width).toBeLessThanOrEqual(W);
    expect(top).toBeGreaterThanOrEqual(0);
    expect(top + BOX.height).toBeLessThanOrEqual(H);
  };

  it("the X (right) axis popover, clicked at the viewport's right edge", () => {
    narrow();
    mount({ onAxisChange: vi.fn() });
    fireEvent.click(screen.getByRole("button", { name: "X range" }), { clientX: W - 4, clientY: H - 20 });
    inside(screen.getByRole("dialog", { name: "X range" }));
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("the R (left) axis popover, in a window narrower than the box's reach", () => {
    narrow();
    mount({ onAxisChange: vi.fn() });
    fireEvent.click(screen.getByRole("button", { name: "R range" }), { clientX: W - 100, clientY: 10 });
    inside(screen.getByRole("dialog", { name: "R range" }));
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("the VSWR chart's popover (#1738) shares the placement", () => {
    narrow();
    render(
      <SweepChart
        mode="vswr"
        r={50}
        x={0}
        z0={50}
        size={300}
        sweep={null}
        measFreqMhz={14}
        running={false}
        multiFeed={false}
        onAxisChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "VSWR range and SWR threshold" }), {
      clientX: W - 4,
      clientY: H - 4,
    });
    inside(screen.getByRole("dialog", { name: "VSWR range" }));
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });
});

describe("value boxes never stack", () => {
  it("a box landing on a placed one moves below it, or above when below has no room", () => {
    const placed = [{ x: 10, y: 100, w: 80, h: 28 }];
    expect(nudgeClear(105, { x: 20, w: 80, h: 28 }, placed, 0, 400)).toBe(130);
    // No room below: above instead.
    expect(nudgeClear(105, { x: 20, w: 80, h: 28 }, placed, 0, 110)).toBe(70);
    // Clear already, or side by side: unchanged.
    expect(nudgeClear(200, { x: 20, w: 80, h: 28 }, placed, 0, 400)).toBe(200);
    expect(nudgeClear(100, { x: 200, w: 80, h: 28 }, placed, 0, 400)).toBe(100);
  });
});

// Steve, 2026-09-26: the two lines that matter are R = Z0 and X = 0.
describe("the reference lines", () => {
  const SPANNING: ParamSweepData = {
    ...KNOB_SWEEP,
    z_re: [40, 50, 65],
    z_im: [-20, 5, 30],
  };
  const knob = { param: "length_factor", label: "length factor", total: 3, currentValue: 1, xLog: false };

  it("R = Z0 and X = 0 are drawn at their heights when inside the ranges", () => {
    const c = mount({ data: SPANNING, ...knob, z0: 50 }).canvas();
    const r = { lo: Number(c.dataset.rLo), hi: Number(c.dataset.rHi) };
    const x = { lo: Number(c.dataset.xLo), hi: Number(c.dataset.xHi) };
    expect(Number(c.dataset.refR)).toBeCloseTo((50 - r.lo) / (r.hi - r.lo), 3);
    expect(Number(c.dataset.refX)).toBeCloseTo((0 - x.lo) / (x.hi - x.lo), 3);
  });

  it("out of range they become edge markers, and the auto ranges are not widened", () => {
    const c = mount().canvas(); // R ≈ 70.7, X ≈ −10: Z0 = 50 below, 0 above
    expect(c.dataset.refR).toBe("below");
    expect(c.dataset.refX).toBe("above");
    expect(Number(c.dataset.rLo)).toBeGreaterThan(70);
    expect(Number(c.dataset.xHi)).toBeLessThan(0);
  });

  it("R's line follows Z0", () => {
    const at50 = Number(mount({ data: SPANNING, ...knob, z0: 50 }).canvas().dataset.refR);
    const c75 = mount({ data: SPANNING, ...knob, z0: 75 }).canvas();
    expect(c75.dataset.z0).toBe("75");
    expect(c75.dataset.refR).toBe("above");
    expect(at50).toBeGreaterThan(0);
  });

  it("the R popover's preset takes in Z0", async () => {
    const user = userEvent.setup();
    const onAxisChange = vi.fn();
    mount({ onAxisChange, z0: 50 });
    await user.click(screen.getByRole("button", { name: "R range" }));
    await user.click(screen.getByRole("button", { name: "take in Z0" }));
    const [, c] = onAxisChange.mock.calls.at(-1)!;
    expect(c.kind).toBe("fixed");
    expect(c.lo).toBeLessThan(50);
    expect(c.hi).toBeGreaterThan(70.78);
  });
});
