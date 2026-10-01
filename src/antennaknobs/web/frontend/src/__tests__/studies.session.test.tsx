// Studies in the analysis picker (AK#1757, sweep-framework step 7 unit 1),
// through a real <DesignSession>.
//
// /analyses serves, after a design's own analyses, the studies that cross
// that design (a study is an analysis over several designs, from a
// module-level build_studies()). The stub here answers as the server does:
// the study is in the listing exactly when the request's geometry is one of
// its designs. So E7 shows on both of its designs' tabs and on no other,
// under a "Studies" group, by its short name; and picking it runs its design
// cross as picking a design analysis with that cross does: one /param_sweep
// per design and engine, each design at its own defaults.
//
// Mutation notes (run by hand, 2026-09-30; each reverted after):
//   - the picker ignoring `study` (studies listed with the design's own):
//     "shows the Studies group…" fails, there is no optgroup "Studies";
//   - a study option valued by its short name, not its full one: both
//     fail, the value is not E7's name and the pick finds no entry to run.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountReady, switchDesign, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
  name: "len",
  label: "Length",
  default: 1,
  kind: "float",
  min: 0.5,
  max: 1.5,
  step: 0.01,
  precision: 2,
  unit: null,
  visible_when: null,
  ...over,
});

const design = (name: string, label: string): ExampleDescriptor => ({
  ...HARNESS_EXAMPLE,
  name,
  label,
  param_schema: [knob({})],
});

const INVVEE = design("dipoles.invvee", "Inverted vee");
const APEX = design("dipoles.invvee_apex", "Inverted vee, apex fed");
const OTHER = design("dipoles.ocf_dipole", "OCF dipole");

const LADDER = [8, 12, 17];
const E7_NAME = "dipoles.apex_feed_on_invvee:feed spelling (E7)";

const knobEntry = (name: string, over: Record<string, unknown>) => ({
  name,
  summary: name,
  code: "an.convergence()",
  problems: [],
  workbench: {
    runs: true,
    kind: "knob",
    param: "n_per_wire",
    values: LADDER,
    log: true,
    engines: null,
    grounds: null,
    axes: [],
    planes: null,
    designs: null,
    step: null,
    note: null,
    ...over,
  },
});

const E7 = {
  ...knobEntry(E7_NAME, {
    engines: ["momwire:bspline", "momwire:razor-2p"],
    axes: ["designs", "engines"],
    designs: [
      { name: INVVEE.name, refused: null, param: "n_per_wire", values: LADDER },
      { name: APEX.name, refused: null, param: "n_per_wire", values: LADDER },
    ],
  }),
  summary: "density; 4 curves (2 designs x 2 engines)",
  study: { source: "dipoles.apex_feed_on_invvee", name: "feed spelling (E7)" },
};
const E7_DESIGNS = [INVVEE.name, APEX.name];

class EchoWebSocket {
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    setTimeout(() => {
      this.readyState = EchoWebSocket.OPEN;
      this.onopen?.();
    }, 0);
  }
  send(payload: string) {
    const req = JSON.parse(payload) as Record<string, unknown>;
    if (!("geometry" in req) || typeof req._seq !== "number") return;
    const reply = {
      ...invveeShape,
      feeds: undefined,
      geometry: req.geometry,
      _seq: req._seq,
      z_in_re: 50,
      z_in_im: -10,
      z0_ohms: 50,
    };
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(reply) } as MessageEvent), 0);
  }
  close() {}
}

function ndjson(lines: string[]): Response {
  const chunks = [new TextEncoder().encode(lines.join("\n") + "\n")];
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () =>
          chunks.length > 0 ? { done: false, value: chunks.shift() } : { done: true, value: undefined },
      }),
    },
  } as unknown as Response;
}

type Body = Record<string, unknown>;

const UI_DEFAULTS = {
  path: "/x/settings.toml",
  exists: false,
  writable: true,
  switches: {
    live: true,
    freq_sweep: true,
    convergence_sweep: true,
    pattern_renorm: false,
    refine: false,
    heatmap_currents: true,
    current_waveforms: false,
    wire_labels: false,
    feed_labels: true,
  },
  switches_set: ["refine"],
  antenna_view: { orientation: "iso" },
  ground: null,
  problems: [],
};

async function mount(examples: ExampleDescriptor[]) {
  const params: Body[] = [];
  const listed: string[] = [];
  const r = await mountReady({
    // A pick starts its analysis, as before [workbench.run_on_pick] (AC6LA #179).
    pickRuns: true,
    examples,
    pinned: ["antenna", "zparam"],
    uiDefaults: UI_DEFAULTS,
    routes: {
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as Body & { values: number[] };
        params.push(body);
        const lines = body.values.map((v) =>
          JSON.stringify({ param: body.param, value: v, z_re: 50 + v, z_im: -10 }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/analyses": (_url: string, init?: RequestInit) => {
        // The server's rule: the design's own, then the studies crossing it.
        const geometry = String((JSON.parse(String(init?.body ?? "{}")) as Body).geometry);
        listed.push(geometry);
        const analyses = [
          knobEntry("convergence", {}),
          ...(E7_DESIGNS.includes(geometry) ? [E7] : []),
        ];
        return { ok: true, status: 200, json: async () => ({ analyses }) } as unknown as Response;
      },
    },
  });
  return { ...r, params, listed };
}

async function chartOnStage(r: { container: HTMLElement }) {
  // eslint-disable-next-line testing-library/no-node-access -- the rail's thumbnail is a bare canvas, with no role to find it by
  fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
  await untilDom(() => screen.queryByRole("button", { name: "Engines and grounds" }));
}

/** The picker, once it lists the design's own analyses. */
async function picker(): Promise<HTMLSelectElement> {
  return untilDom(() => {
    const b = screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null;
    return b && [...b.options].some((o) => o.value === "convergence") ? b : null;
  });
}

const groupOf = (box: HTMLSelectElement, label: string) =>
  within(box).queryByRole("group", { name: label });

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

/** The picker's Studies group once it has listed ``geometry``'s analyses:
 *  its options as [text, value, disabled], or null with no group. */
async function studiesOn(r: { listed: string[] }, geometry: string) {
  await untilDom(() => (r.listed.includes(geometry) ? true : null));
  const box = await picker();
  const group = groupOf(box, "Studies");
  return group
    ? within(group)
        .getAllByRole("option")
        .map((o) => [o.textContent, (o as HTMLOptionElement).value, (o as HTMLOptionElement).disabled])
    : null;
}

describe("studies in the analysis picker", () => {
  it("shows the Studies group on each design's tab that a study crosses, and on no other", async () => {
    const user = userEvent.setup();
    // The catalog opens on dipoles.invvee.
    const r = await mount([INVVEE, APEX, OTHER]);
    await chartOnStage(r);
    const e7Row = [["feed spelling (E7)", E7_NAME, false]];
    // By its short name, keyed by its full one.
    expect(await studiesOn(r, INVVEE.name)).toEqual(e7Row);
    const box = await picker();
    const e7 = [...box.options].find((o) => o.value === E7_NAME) as HTMLOptionElement;
    expect(e7.title).toContain("a study in dipoles.apex_feed_on_invvee");
    // Below the design's own analyses.
    const all = [...box.options].map((o) => o.value);
    expect(all.indexOf(E7_NAME)).toBeGreaterThan(all.indexOf("convergence"));

    await switchDesign(user, APEX.label, APEX.name);
    expect(await studiesOn(r, APEX.name)).toEqual(e7Row);

    await switchDesign(user, OTHER.label, OTHER.name);
    expect(await studiesOn(r, OTHER.name)).toBeNull();
    expect([...(await picker()).options].map((o) => o.value)).not.toContain(E7_NAME);
  });

  it("picking E7 runs its design cross, each design at its own defaults, as a design analysis does", async () => {
    const r = await mount([INVVEE, APEX, OTHER]);
    await chartOnStage(r);
    const box = await picker();
    fireEvent.change(box, { target: { value: E7_NAME } });
    // One ladder per design of the cross: both designs are solved.
    const geometries = await untilDom(() => {
      const got = new Set(r.params.filter((b) => b.param === "n_per_wire").map((b) => String(b.geometry)));
      return E7_DESIGNS.every((g) => got.has(g)) ? got : null;
    });
    expect([...geometries].sort()).toEqual([...E7_DESIGNS].sort());
    for (const b of r.params.filter((p) => p.param === "n_per_wire")) {
      expect(b.values).toEqual(LADDER);
    }
    // The picker reads the study as the running pick.
    expect((await picker()).value).toBe(E7_NAME);
    // The session's design is untouched.
    // eslint-disable-next-line testing-library/no-node-access -- the session's loaded design is a data attribute, the harness's own readiness signal
    expect(document.querySelector<HTMLElement>(".app[data-ready]")?.dataset.ready).toMatch(
      /^dipoles\.invvee#/,
    );
  });
});
