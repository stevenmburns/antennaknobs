// The Z-vs-parameter view through a real <DesignSession>
// (docs/design/z-vs-param-view.md):
//   - "Sweep this knob" in the knob menu opens the view and asks
//     /param_sweep for that knob over its own range, on the slot's request;
//   - dragging the swept knob moves the chart's guide and re-sweeps nothing
//     (every point overrides it), while any OTHER knob re-sweeps;
//   - a density sweep is the old convergence sweep: picked in the analysis
//     chart and drawn on its Smith view, the same ladder, trail and Z* as
//     the Smith view's "param sweep" switch drew (AK#1757 step 5 unit 3,
//     which folded that view and switch into the chart).
// Since unit 3 a new chart is a frequency sweep, so a knob sweep here starts
// from "Sweep this knob…" (or a knob analysis), never from the chart opening.
import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HARNESS_EXAMPLE, mountDesignSession, mountReady, sessionReady, untilDom } from "./designSessionHarness";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";


// The file's budget (AK#1762). "dragging…" and "Stop" are correct, long
// tests: a cold mount, a streamed sweep, a knob change and a re-run, each
// awaited on its cause. On a loaded box that is more than vitest's default
// 5 s; this says so, rather than any wait inside them guessing a clock.
vi.setConfig({ testTimeout: 15_000 });

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
// value. Density: each record carries the achieved segment count
// n_seg = 10·2^i at the i-th rung (a doubling ladder, unlike N), and Z moves
// as 1/n_seg, so Z∞ is exact and asymptotic ONLY when the view extrapolates
// against n_seg, as the CLI does (AK#1781).
function paramSweepRoute(bodies: Body[]) {
  return (_url: string, init?: RequestInit) => {
    const b = JSON.parse(String(init?.body ?? "{}")) as Body;
    bodies.push(b);
    const lines = b.values.map((v, i) =>
      JSON.stringify({
        param: b.param,
        value: v,
        // Density: Z = 70 + 10/n − j(10 − 5/n), n = n_seg. A knob: a line
        // through its range.
        ...(b.param === "n_per_wire" ? { n_seg: 10 * 2 ** i } : {}),
        z_re: b.param === "n_per_wire" ? 70 + 10 / (10 * 2 ** i) : 60 + 20 * v,
        z_im: b.param === "n_per_wire" ? -10 + 5 / (10 * 2 ** i) : -30 + 60 * v,
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
    const { container } = await mountReady({
      examples: [EXAMPLE],
      routes: { "/param_sweep": paramSweepRoute(bodies) },
    });
    // mountReady waited for the design's load path, so the knob and its
    // menu are live: everything below is synchronous.
    const gap = screen.getByRole("slider", { name: "Gap" });
    fireEvent.contextMenu(gap);
    await user.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    // The view is on the stage with its header.
    expect(container.querySelector("canvas.zparam")).not.toBeNull();
    expect((screen.getByRole("combobox", { name: "Parameter" }) as HTMLSelectElement).value).toBe("gap");
    await untilDom(() => bodies.some((b) => b.param === "gap") === true);
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
    await untilDom(() => chart().dataset.points === "11");
    expect(chart().dataset.param).toBe("gap");
    expect(chart().dataset.guide).toBe("0.25");
  });

  it("dragging the swept knob moves the guide; another knob marks it stale; Run re-runs", async () => {
    const user = userEvent.setup();
    const bodies: Body[] = [];
    const { container } = await mountReady({
      examples: [EXAMPLE],
      pinned: ["antenna", "zparam"],
      routes: { "/param_sweep": paramSweepRoute(bodies) },
    });
    // mountReady waited for the design's load path, so the knob and its
    // menu are live: everything below is synchronous.
    const gap = screen.getByRole("slider", { name: "Gap" });
    fireEvent.contextMenu(gap);
    await user.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    const chart = () =>
      [...container.querySelectorAll("canvas.zparam")].find(
        (c) => !c.closest(".thumbstrip"),
      ) as HTMLElement;
    // The sweep landed and the runner is idle: nothing queued, nothing out.
    await untilDom(() => chart()?.dataset.points === "11" && chart().dataset.phase === "idle");
    const before = bodies.length;

    for (let i = 0; i < 3; i++) fireEvent.keyDown(gap, { key: "ArrowUp" });
    await untilDom(() => chart().dataset.guide !== "0.25");
    // The runner decided on this change already (effects ran inside the
    // event's act): idle means no sweep is queued, so none will follow.
    expect(chart().dataset.phase).toBe("idle");
    expect(bodies.slice(before)).toEqual([]);
    expect(chart().dataset.points).toBe("11");

    // Another knob changes every point, but a knob sweep re-runs only when
    // asked: the old trace stays, dimmed as stale, and "re-run?" is offered.
    fireEvent.keyDown(screen.getByRole("slider", { name: "Height" }), { key: "ArrowUp" });
    await untilDom(() => chart().dataset.stale === "1");
    expect(chart().dataset.phase).toBe("idle");
    expect(bodies.slice(before)).toEqual([]);
    expect(chart().dataset.points).toBe("11");
    await user.click(screen.getByRole("button", { name: "run · re-run?" }));
    await untilDom(() => bodies.length === before + 1);
    expect(bodies[bodies.length - 1].param).toBe("gap");
    await untilDom(() => chart().dataset.stale === "0");
  });
});

// The design's generic convergence analysis, as /analyses serves it: the
// density ladder the old convergence sweep ran.
const CONVERGENCE = {
  geometry: EXAMPLE.name,
  analyses: [
    {
      name: "convergence",
      summary: "density 8..68, 7 points; 1 curve; views Rx, Smith",
      code: "an.convergence()",
      problems: [],
      workbench: {
        runs: true,
        kind: "knob",
        param: "n_per_wire",
        values: [8, 12, 17, 24, 34, 48, 68],
        log: true,
        note: null,
      },
    },
  ],
};

describe("a density sweep is the old convergence sweep", () => {
  it("picked in the chart and shown on its Smith view: the same ladder, trail and Z*", async () => {
    const bodies: Body[] = [];
    const { container } = await mountReady({
      examples: [EXAMPLE],
      pinned: ["antenna", "zparam"],
      routes: {
        "/param_sweep": paramSweepRoute(bodies),
        "/analyses": () =>
          ({ ok: true, status: 200, json: async () => CONVERGENCE }) as unknown as Response,
      },
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
    // The chart opens on a frequency sweep: nothing goes to /param_sweep.
    fireEvent.click(container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
    const select = await untilDom(
      () => screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null,
    );
    await untilDom(() => [...select.options].some((o) => o.value === "convergence") || null);
    expect(bodies).toEqual([]);
    fireEvent.change(select, { target: { value: "convergence" } });
    await untilDom(() => bodies.length > 0);
    expect(bodies[0].param).toBe("n_per_wire");
    expect(bodies[0].values).toEqual([8, 12, 17, 24, 34, 48, 68]);
    // convergence_sweep = true seeds a knob chart's dwell switch on.
    expect(
      (screen.getByRole("checkbox", { name: "auto re-run" }) as HTMLInputElement).checked,
    ).toBe(true);
    // The knob sweep's views: R/X, its trail on the Smith chart, and the
    // numbers (the Table, AK#1757 step 5 unit 5).
    const view = screen.getByRole("combobox", { name: "Chart view" }) as HTMLSelectElement;
    expect([...view.options].map((o) => o.value)).toEqual(["Rx", "Smith", "Table"]);
    fireEvent.change(view, { target: { value: "Smith" } });
    const smith = () =>
      [...container.querySelectorAll<HTMLElement>("canvas.smith")].find(
        (c) => !c.closest(".thumbstrip"),
      ) as HTMLElement;
    await untilDom(() => smith()?.dataset.trail === "n_per_wire:8→68:7" || null);
    expect(bodies).toHaveLength(1);
    // Z = 70 + 10/n − j(10 − 5/n) in the achieved count n: the estimator,
    // run against n_seg, sees an exact first order and recovers the limit.
    expect(smith().dataset.extrap).toBe("70.000,-10.000");
    expect(smith().dataset.extrapStatus).toBe("asymptotic");
  });
});

describe("the server's refusal is shown, not clamped to", () => {
  it("a hosted 413 appears in the view in its own words", async () => {
    const detail =
      "A parameter sweep of 600 points is over the live limit of 500. Reduce the point count.";
    const { container } = await mountReady({
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
    // A knob sweep on the chart (a new chart is a frequency sweep, unit 3).
    fireEvent.contextMenu(screen.getByRole("slider", { name: "Gap" }));
    fireEvent.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    expect((await untilDom(() => screen.queryByRole("alert")))!.textContent).toBe(detail);
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
    const { container } = await mountReady({
      examples: [EXAMPLE],
      pinned: ["antenna", "zparam"],
      routes: { "/param_sweep": slowRoute(bodies, signals) },
    });
    // mountReady waited for the design's load path, so the knob and its
    // menu are live: everything below is synchronous.
    const gap = screen.getByRole("slider", { name: "Gap" });
    fireEvent.contextMenu(gap);
    await user.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    const chart = () =>
      [...container.querySelectorAll("canvas.zparam")].find(
        (c) => !c.closest(".thumbstrip"),
      ) as HTMLElement;
    await untilDom(() => Number(chart()?.dataset.points) >= 3);
    const n = bodies.length;
    await user.click(screen.getByRole("button", { name: /· stop$/ }));
    expect(signals[signals.length - 1].aborted).toBe(true);
    const kept = Number(chart().dataset.points);
    expect(kept).toBeGreaterThanOrEqual(3);
    expect(kept).toBeLessThan(11);
    expect(chart().dataset.partial).toBe("1");
    // Nothing restarted (the runner is idle), and the points stayed.
    expect(chart().dataset.phase).toBe("idle");
    expect(bodies.length).toBe(n);
    expect(Number(chart().dataset.points)).toBe(kept);
    expect(screen.getByRole("button", { name: `${kept}/11 · run` })).toBeTruthy();

    // Another knob does not restart a knob sweep either (it waits to be
    // asked): it goes stale. Run is what re-runs it.
    fireEvent.keyDown(screen.getByRole("slider", { name: "Height" }), { key: "ArrowUp" });
    await untilDom(() => chart().dataset.stale === "1");
    expect(chart().dataset.phase).toBe("idle");
    expect(bodies.length).toBe(n);
    await user.click(screen.getByRole("button", { name: "run · re-run?" }));
    await untilDom(() => bodies.length === n + 1);
  });
});

describe("R = Z0 follows the session's Zo (AK#1735)", () => {
  it("the design's own Zo from the preview, then the Zo field's override", async () => {
    const { container } = await mountReady({
      examples: [EXAMPLE],
      pinned: ["antenna", "zparam"],
      routes: {
        "/param_sweep": paramSweepRoute([]),
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
    // The knob sweep's R/X plot draws the R = Z0 line.
    fireEvent.contextMenu(screen.getByRole("slider", { name: "Gap" }));
    fireEvent.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    await untilDom(() => chart()?.dataset.z0 === "75");
    fireEvent.click(screen.getByLabelText("Optimisation method"));
    const zo = screen.getByLabelText("Reference impedance Zo, ohms") as HTMLInputElement;
    fireEvent.change(zo, { target: { value: "60" } });
    fireEvent.keyDown(zo, { key: "Enter" });
    await untilDom(() => chart()?.dataset.z0 === "60");
    localStorage.clear();
  });
});

// Steve, 2026-09-26: a length_factor sweep must not start on his next design
// unless he asks. Since unit 3 the chart starts over on the design's own
// frequency sweep, so no knob or density sweep runs by itself.
const VARIANTS: ExampleDescriptor = {
  ...EXAMPLE,
  variants: ["default", "other"],
  variant_values: { default: {}, other: {} },
};

describe("a knob sweep runs only when asked (a pick, Run, or its own range)", () => {
  it("a design switch starts the chart over on the frequency sweep; no knob sweep follows", async () => {
    const user = userEvent.setup();
    const bodies: Body[] = [];
    const { container } = await mountReady({
      examples: [VARIANTS],
      pinned: ["antenna", "zparam"],
      routes: { "/param_sweep": paramSweepRoute(bodies) },
    });
    // mountReady waited for the design's load path, so the knob and its
    // menu are live: everything below is synchronous.
    const gap = screen.getByRole("slider", { name: "Gap" });
    fireEvent.contextMenu(gap);
    await user.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    await untilDom(() => bodies.some((b) => b.param === "gap") === true);
    const n = bodies.length;
    // Another variant is another design.
    await user.selectOptions(screen.getByRole("combobox", { name: "variant" }), "other");
    const head = screen.getByRole("group", { name: "Analysis chart" });
    expect(head.dataset.chartKind).toBe("frequency");
    expect(screen.queryByRole("combobox", { name: "Parameter" })).toBeNull();
    // The Smith chart on the stage, its sweep decided (it has no /sweep
    // route here, so it ends idle), and nothing more went to /param_sweep.
    const smith = await untilDom(() =>
      [...container.querySelectorAll<HTMLElement>("canvas.smith")].find(
        (c) => !c.closest(".thumbstrip"),
      ) ?? null,
    );
    await untilDom(() => smith.dataset.phase === "idle" || null);
    expect(bodies.length).toBe(n);
  });

  it("picking a knob in the header is a pick: it runs, and draws", async () => {
    // Steve's phone, 2026-09-29: choosing length_factor here left "no sweep
    // yet" and a small "run" he never found. Unit 2 made a knob choice wait
    // for Run; the rulings say a pick runs, and choosing what to sweep is one.
    const user = userEvent.setup();
    const bodies: Body[] = [];
    await mountReady({
      examples: [EXAMPLE],
      pinned: ["antenna", "zparam"],
      routes: { "/param_sweep": paramSweepRoute(bodies) },
    });
    fireEvent.contextMenu(screen.getByRole("slider", { name: "Height" }));
    await user.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    await untilDom(() => bodies.some((b) => b.param === "height") === true);
    const n = bodies.length;
    await user.selectOptions(screen.getByRole("combobox", { name: "Parameter" }), "gap");
    const stage = () =>
      [...document.querySelectorAll<HTMLElement>("canvas.zparam")].find((c) => !c.closest(".thumbstrip"))!;
    // Decided inside the pick's act: queued (after the usual dwell).
    expect(stage().dataset.phase).toBe("queued");
    await untilDom(() => bodies.length === n + 1);
    expect(bodies[n].param).toBe("gap");
    await untilDom(() => (stage().dataset.param === "gap" && stage().dataset.points === "11") || null);
  });

  it("an edit to the knob sweep's own range runs it", async () => {
    const user = userEvent.setup();
    const bodies: Body[] = [];
    await mountReady({
      examples: [EXAMPLE],
      pinned: ["antenna", "zparam"],
      routes: { "/param_sweep": paramSweepRoute(bodies) },
    });
    fireEvent.contextMenu(screen.getByRole("slider", { name: "Height" }));
    await user.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    await untilDom(() => bodies.some((b) => b.param === "height") === true);
    await user.selectOptions(screen.getByRole("combobox", { name: "Parameter" }), "gap");
    const n = bodies.length;
    const pts = screen.getByLabelText("points") as HTMLInputElement;
    await user.clear(pts);
    await user.type(pts, "5{Enter}");
    await untilDom(() => bodies.length === n + 1);
    expect(bodies[n]).toMatchObject({ param: "gap" });
    expect(bodies[n].values).toHaveLength(5);
  });
});

// The flake's cause, pinned (2026-09-26): the design's knobs render in the
// commit that selects it, and the design-load reset used to run in an effect
// AFTER that commit — so a right-click landing in between opened the menu
// and the late reset wiped it. A MutationObserver fires in that gap (a
// microtask after the DOM changes, before React's passive effects), so this
// right-click lands there every time. With the menu keyed to its design the
// click is kept; with the old effect it is lost, deterministically.
describe("a right-click the moment the knobs appear", () => {
  it("opens the knob menu, not a menu the design-load reset then wipes", async () => {
    mountDesignSession({ examples: [EXAMPLE] });
    const gap = await untilDom(() =>
      document.querySelector<HTMLElement>('[role="slider"][aria-label="Gap"]'),
    );
    fireEvent.contextMenu(gap);
    await sessionReady(document.body);
    expect(screen.getByRole("button", { name: "Sweep this knob…" })).toBeTruthy();
  });
});

describe("a knob sweep on the chart's Smith view is the old param-sweep trail", () => {
  it("the same sweep draws as R/X or as the Smith trail, with no second run", async () => {
    // Steve, 2026-09-28 (unit 3): the Smith view's "param sweep" switch
    // folded into the chart, whose Smith view draws its knob sweep's trail.
    // Before, the switch decided whether the Smith chart drew a sweep the
    // Z-vs-parameter view had run; now the chart's view is the choice.
    const user = userEvent.setup();
    const bodies: Body[] = [];
    const { container } = await mountReady({
      examples: [EXAMPLE],
      pinned: ["smith", "zparam"],
      routes: { "/param_sweep": paramSweepRoute(bodies) },
    });
    // Both stored pins are the one chart now.
    expect(container.querySelectorAll(".thumbstrip .thumb-label").length).toBeLessThanOrEqual(1);
    const gap = screen.getByRole("slider", { name: "Gap" });
    fireEvent.contextMenu(gap);
    await user.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    const onStage = (sel: string) =>
      [...container.querySelectorAll(sel)].find((c) => !c.closest(".thumbstrip")) as
        | HTMLElement
        | undefined;
    await untilDom(() => onStage("canvas.zparam")?.dataset.points === "11");
    expect(onStage("canvas.smith")).toBeUndefined();
    const before = bodies.length;
    const view = screen.getByRole("combobox", { name: "Chart view" }) as HTMLSelectElement;
    fireEvent.change(view, { target: { value: "Smith" } });
    await untilDom(() => onStage("canvas.smith")?.dataset.trail === "gap:0→1:11" || null);
    expect(onStage("canvas.zparam")).toBeUndefined();
    expect(bodies.length).toBe(before);
    // No param-sweep switch anywhere, the Tools menu included.
    expect(screen.queryAllByRole("checkbox", { name: "param sweep" })).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Tools menu" }));
    expect(screen.queryAllByRole("checkbox", { name: "param sweep" })).toEqual([]);
    // And back to R/X: the same data.
    fireEvent.change(view, { target: { value: "Rx" } });
    await untilDom(() => onStage("canvas.zparam")?.dataset.points === "11" || null);
    expect(bodies.length).toBe(before);
  });
});
