// The Z-vs-parameter chart (docs/design/z-vs-param-view.md): what it draws,
// read through its data-* attributes (jsdom has no 2-D context), and its
// controls — the two y-axis range popovers and the lin/log x toggle.
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ZParamChart } from "../components/charts/ZParamChart";
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
