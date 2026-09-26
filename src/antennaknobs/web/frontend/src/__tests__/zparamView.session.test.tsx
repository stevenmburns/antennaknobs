// The Z-vs-parameter view through a real <DesignSession>
// (docs/design/z-vs-param-view.md):
//   - "Sweep this knob" in the knob menu opens the view and asks
//     /param_sweep for that knob over its own range, on the slot's request;
//   - dragging the swept knob moves the chart's guide and re-sweeps nothing
//     (every point overrides it), while any OTHER knob re-sweeps;
//   - a density sweep is the old convergence sweep: with the switch on and
//     the Smith chart on screen, the same ladder, trail and Z* as before.
import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HARNESS_EXAMPLE, mountDesignSession } from "./designSessionHarness";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";

const T = { timeout: 5000 };

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
  name: "gap",
  label: "Gap",
  default: 0.25,
  kind: "float",
  min: 0,
  max: 1,
  step: 0.05,
  precision: 2,
  unit: null,
  visible_when: null,
  ...over,
});

const EXAMPLE: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  param_schema: [
    knob({}),
    knob({ name: "height", label: "Height", default: 7, min: 1, max: 16, step: 1, precision: 0, unit: "m" }),
  ],
};

type Body = Record<string, unknown> & { param: string; values: number[] };

// A /param_sweep route that records each request and streams one record per
// value (Z moving as 1/N for a density sweep, so Richardson has a limit).
function paramSweepRoute(bodies: Body[]) {
  return (_url: string, init?: RequestInit) => {
    const b = JSON.parse(String(init?.body ?? "{}")) as Body;
    bodies.push(b);
    const lines = b.values.map((v) =>
      JSON.stringify({
        param: b.param,
        value: v,
        // Density: Z = 70 + 10/N − j(10 − 5/N), a 1/N approach. A knob:
        // a line through its range.
        z_re: b.param === "n_per_wire" ? 70 + 10 / v : 60 + 20 * v,
        z_im: b.param === "n_per_wire" ? -10 + 5 / v : -30 + 60 * v,
        solver: "momwire",
      }),
    );
    lines.push(JSON.stringify({ done: true, solver: "momwire" }));
    const chunks = [new TextEncoder().encode(lines.join("\n") + "\n")];
    return {
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: async () =>
            chunks.length > 0
              ? { done: false, value: chunks.shift() }
              : { done: true, value: undefined },
        }),
      },
    } as unknown as Response;
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a knob sweep", () => {
  it("Sweep this knob opens the view and sweeps the knob over its range", async () => {
    const user = userEvent.setup();
    const bodies: Body[] = [];
    const { container } = mountDesignSession({
      examples: [EXAMPLE],
      routes: { "/param_sweep": paramSweepRoute(bodies) },
    });
    const gap = await screen.findByRole("slider", { name: "Gap" });
    fireEvent.contextMenu(gap);
    await user.click(await screen.findByRole("button", { name: "Sweep this knob…" }));
    // The view is on the stage with its header.
    await waitFor(() => expect(container.querySelector("canvas.zparam")).not.toBeNull(), T);
    expect((screen.getByRole("combobox", { name: "Parameter" }) as HTMLSelectElement).value).toBe("gap");
    await waitFor(() => expect(bodies.some((b) => b.param === "gap")).toBe(true), T);
    const b = bodies.find((x) => x.param === "gap")!;
    // Its own min…max, 11 linear points.
    expect(b.values).toHaveLength(11);
    expect(b.values[0]).toBe(0);
    expect(b.values[10]).toBe(1);
    // An ordinary solve request otherwise: the slot's engine, the knob's own
    // current value (overridden per point on the server), the measurement
    // frequency untouched.
    expect(b.geometry).toBe(EXAMPLE.name);
    expect(b.solver).toBeTruthy();
    expect(b.gap).toBe(0.25);
    expect(typeof b.measurement_freq_mhz).toBe("number");
    // The chart drew it, with the guide at the knob's value.
    const chart = () => container.querySelector("canvas.zparam") as HTMLElement;
    await waitFor(() => expect(chart().dataset.points).toBe("11"), T);
    expect(chart().dataset.param).toBe("gap");
    expect(chart().dataset.guide).toBe("0.25");
  });

  it("dragging the swept knob moves the guide and re-sweeps nothing; another knob re-sweeps", async () => {
    const user = userEvent.setup();
    const bodies: Body[] = [];
    const { container } = mountDesignSession({
      examples: [EXAMPLE],
      pinned: ["antenna", "zparam"],
      routes: { "/param_sweep": paramSweepRoute(bodies) },
    });
    const gap = await screen.findByRole("slider", { name: "Gap" });
    fireEvent.contextMenu(gap);
    await user.click(await screen.findByRole("button", { name: "Sweep this knob…" }));
    const chart = () => container.querySelector("canvas.zparam") as HTMLElement;
    await waitFor(() => expect(chart()?.dataset.points).toBe("11"), T);
    await new Promise((r) => setTimeout(r, 800));
    const before = bodies.length;

    for (let i = 0; i < 3; i++) fireEvent.keyDown(gap, { key: "ArrowUp" });
    await waitFor(() => expect(chart().dataset.guide).not.toBe("0.25"), T);
    // Past the 500 ms dwell, with margin: no new sweep, the same points.
    await new Promise((r) => setTimeout(r, 1200));
    expect(bodies.slice(before)).toEqual([]);
    expect(chart().dataset.points).toBe("11");

    // Another knob is physics for every point: it re-sweeps.
    fireEvent.keyDown(screen.getByRole("slider", { name: "Height" }), { key: "ArrowUp" });
    await waitFor(() => expect(bodies.length).toBeGreaterThan(before), T);
    expect(bodies[bodies.length - 1].param).toBe("gap");
  });
});

describe("a density sweep is the old convergence sweep", () => {
  it("the switch on, the Smith chart up: the same ladder, trail and Z*", async () => {
    const bodies: Body[] = [];
    const { container } = mountDesignSession({
      examples: [EXAMPLE],
      routes: { "/param_sweep": paramSweepRoute(bodies) },
      uiDefaults: {
        path: "/x/settings.toml",
        exists: false,
        writable: true,
        switches: {
          live: true,
          freq_sweep: false,
          convergence_sweep: true,
          pattern_renorm: true,
          refine: true,
          heatmap_currents: true,
          current_waveforms: false,
          wire_labels: false,
          feed_labels: true,
        },
        switches_set: [],
        antenna_view: { orientation: "iso" },
        ground: null,
        problems: [],
      },
    });
    await waitFor(() => expect(bodies.length).toBeGreaterThan(0), T);
    expect(bodies[0].param).toBe("n_per_wire");
    expect(bodies[0].values).toEqual([8, 12, 17, 24, 34, 48, 68]);
    const smith = () => container.querySelector("canvas.smith") as HTMLElement;
    await waitFor(() => expect(smith().dataset.trail).toBe("n_per_wire:8→68:7"), T);
    // Z = 70 + 10/N − j(10 − 5/N): Richardson in 1/N recovers the limit.
    expect(smith().dataset.extrap).toBe("70.000,-10.000");
  });
});

describe("the server's refusal is shown, not clamped to", () => {
  it("a hosted 413 appears in the view in its own words", async () => {
    const detail =
      "A parameter sweep of 600 points is over the live limit of 500. Reduce the point count.";
    const { container } = mountDesignSession({
      examples: [EXAMPLE],
      pinned: ["antenna", "zparam"],
      routes: {
        "/param_sweep": () =>
          ({
            ok: false,
            status: 413,
            json: async () => ({ detail }),
          }) as unknown as Response,
      },
    });
    const thumb = await waitFor(() => {
      const c = container.querySelector(".thumbstrip canvas.zparam");
      expect(c).not.toBeNull();
      return c as HTMLElement;
    }, T);
    fireEvent.click(thumb);
    expect((await screen.findByRole("alert", {}, T)).textContent).toBe(detail);
    const chart = [...container.querySelectorAll("canvas.zparam")].find(
      (c) => !c.closest(".thumbstrip"),
    ) as HTMLElement;
    expect(chart.dataset.error).toBe(detail);
  });
});

// A /param_sweep that streams one record every 120 ms and honours the
// request's AbortSignal the way fetch does: the reader rejects with an
// AbortError once the signal trips.
function slowRoute(bodies: Body[], signals: AbortSignal[]) {
  return (_url: string, init?: RequestInit) => {
    const b = JSON.parse(String(init?.body ?? "{}")) as Body;
    bodies.push(b);
    const signal = init?.signal as AbortSignal;
    signals.push(signal);
    let i = 0;
    return {
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: async () => {
            await new Promise((r) => setTimeout(r, 120));
            if (signal.aborted) throw new DOMException("aborted", "AbortError");
            if (i >= b.values.length) return { done: true, value: undefined };
            const v = b.values[i++];
            const line = JSON.stringify({ param: b.param, value: v, z_re: 60 + v, z_im: v, solver: "momwire" });
            return { done: false, value: new TextEncoder().encode(line + "\n") };
          },
        }),
      },
    } as unknown as Response;
  };
}

describe("Stop", () => {
  it("aborts, keeps the partial points, and re-solves nothing until a parameter changes or Run", async () => {
    const user = userEvent.setup();
    const bodies: Body[] = [];
    const signals: AbortSignal[] = [];
    const { container } = mountDesignSession({
      examples: [EXAMPLE],
      pinned: ["antenna", "zparam"],
      routes: { "/param_sweep": slowRoute(bodies, signals) },
    });
    const gap = await screen.findByRole("slider", { name: "Gap" });
    fireEvent.contextMenu(gap);
    await user.click(await screen.findByRole("button", { name: "Sweep this knob…" }));
    const chart = () =>
      [...container.querySelectorAll("canvas.zparam")].find(
        (c) => !c.closest(".thumbstrip"),
      ) as HTMLElement;
    await waitFor(() => expect(Number(chart()?.dataset.points)).toBeGreaterThanOrEqual(3), T);
    const n = bodies.length;
    await user.click(screen.getByRole("button", { name: /· stop$/ }));
    expect(signals[signals.length - 1].aborted).toBe(true);
    const kept = Number(chart().dataset.points);
    expect(kept).toBeGreaterThanOrEqual(3);
    expect(kept).toBeLessThan(11);
    expect(chart().dataset.partial).toBe("1");
    // Past the dwell, with margin: nothing restarted, the points stayed.
    await new Promise((r) => setTimeout(r, 1200));
    expect(bodies.length).toBe(n);
    expect(Number(chart().dataset.points)).toBe(kept);
    expect(screen.getByRole("button", { name: `${kept}/11 · run` })).toBeTruthy();

    // A parameter change is a new request: it sweeps again.
    fireEvent.keyDown(screen.getByRole("slider", { name: "Height" }), { key: "ArrowUp" });
    await waitFor(() => expect(bodies.length).toBe(n + 1), T);
    await user.click(await screen.findByRole("button", { name: /· stop$/ }, T));
    const m = bodies.length;
    // ...and so does Run, at once.
    // (Stopped before a point landed: the button reads a bare "run".)
    await user.click(screen.getByRole("button", { name: /run$/ }));
    await waitFor(() => expect(bodies.length).toBe(m + 1), T);
  }, 15000);
});

describe("R = Z0 follows the session's Zo (AK#1735)", () => {
  it("the design's own Zo from the preview, then the Zo field's override", async () => {
    const { container } = mountDesignSession({
      pinned: ["antenna", "zparam"],
      routes: {
        "/geometry": () =>
          ({
            ok: true,
            status: 200,
            json: async () => ({
              geometry: HARNESS_EXAMPLE.name,
              wires: [],
              z0_ohms: 75,
              design_z0_ohms: 75,
            }),
          }) as unknown as Response,
      },
    });
    const chart = () =>
      [...container.querySelectorAll("canvas.zparam")].find(
        (c) => !c.closest(".thumbstrip"),
      ) as HTMLElement | undefined;
    const thumb = await waitFor(() => {
      const c = container.querySelector(".thumbstrip canvas.zparam");
      expect(c).not.toBeNull();
      return c as HTMLElement;
    }, T);
    fireEvent.click(thumb);
    await waitFor(() => expect(chart()?.dataset.z0).toBe("75"), T);
    fireEvent.click(screen.getByLabelText("Optimisation method"));
    const zo = screen.getByLabelText("Reference impedance Zo, ohms") as HTMLInputElement;
    fireEvent.change(zo, { target: { value: "60" } });
    fireEvent.keyDown(zo, { key: "Enter" });
    await waitFor(() => expect(chart()?.dataset.z0).toBe("60"), T);
    localStorage.clear();
  });
});
