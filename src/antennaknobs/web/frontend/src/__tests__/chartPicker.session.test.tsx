// Steve's phone (2026-09-29), findings 4 and 5 on the Sweep chart:
//   4. "you can change the knob you are sweeping but you can't actually draw
//      a graph": choosing a knob in the chart's parameter list armed nothing
//      (a knob sweep's dwell switch starts off, and unit 2 made a knob choice
//      wait for Run), so the chart said "no sweep yet" beside a small "run"
//      among the wrapped controls. A choice of what to sweep is a pick, and
//      a pick runs;
//   5. "no sweep item to choose, a lot of greyed-out analyses": the picker
//      now leads with what runs here (the chart's own frequency sweep, the
//      runnable analyses, and ONE "Sweep a knob" entry, which runs the knob
//      in the chart's parameter list, the last knob swept, else the design's
//      first, through the knob menu's "Sweep this knob…" path), and puts the
//      analyses the workbench cannot run yet last, in their own group,
//      disabled. One entry, not one per knob (Steve): a design can have
//      twenty knobs, and the parameter list already chooses among them.
// Both at a phone's width (the mobile tree) and on a desktop.
//
// Before the fix (run by hand, 2026-09-29): the pre-fix header, a knob
// choice that arms nothing, fails "choosing a knob in the header draws it"
// on both widths (no /param_sweep for length_factor: the runner stays idle),
// and zparamView's pick test with it; the picker tests fail without the
// "Sweep a knob" entry, and with its handler unwired the draw test fails on
// both widths.
import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 20_000 });

const knob = (name: string, label: string, d: number): SchemaParamSpec => ({
  name,
  label,
  default: d,
  kind: "float",
  min: 0.5 * d,
  max: 1.5 * d,
  step: 0.01,
  precision: 2,
  unit: null,
  visible_when: null,
});

// The inverted V's knobs, as dipoles.invvee serves them.
const INVVEE: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "dipoles.invvee",
  param_schema: [knob("base", "base", 7), knob("length_factor", "length_factor", 0.97), knob("angle_deg", "angle", 31.7)],
};

const HOLD = "hold (optimise at each point): not in the workbench yet (sweep-framework step 6)";
const ANALYSES = {
  geometry: INVVEE.name,
  analyses: [
    { name: "convergence", summary: "", code: "", problems: [], workbench: { runs: true, kind: "knob", param: "n_per_wire", values: [8, 12, 17, 24, 34, 48, 68], log: true, note: null } },
    { name: "height", summary: "", code: "", problems: [], workbench: { runs: true, kind: "knob", param: "base", values: [5, 6, 7, 8, 9], log: false, note: null } },
    { name: "tuning family", summary: "", code: "", problems: [], workbench: { runs: false, why: "a family: sweep-framework step 5 unit 4" } },
    { name: "match vs height", summary: "", code: "", problems: [], workbench: { runs: false, why: HOLD } },
    {
      name: "band SWR",
      summary: "",
      code: "",
      problems: [],
      workbench: { runs: true, kind: "frequency", note: null, views: ["Swr"], range: null, level: "policy", points: null, swr: { scale: null, threshold: 2 } },
    },
  ],
};

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

async function mount(mobile: boolean) {
  const bodies: { param: string; values: number[] }[] = [];
  const r = await mountReady({
    mobile,
    examples: [INVVEE],
    pinned: ["zparam", "antenna"],
    routes: {
      "/analyses": () => ({ ok: true, status: 200, json: async () => ANALYSES }) as unknown as Response,
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as { param: string; values: number[] };
        bodies.push(b);
        const lines = b.values.map((v) =>
          JSON.stringify({ param: b.param, value: v, z_re: 60 + 10 * v, z_im: -20 + 5 * v, solver: "momwire" }),
        );
        lines.push(JSON.stringify({ done: true, solver: "momwire" }));
        return ndjson(lines);
      },
    },
  });
  // Put the chart on the stage (a desktop; a phone's first page is it).
  if (!mobile) fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
  const picker = await untilDom(
    () => screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null,
  );
  await untilDom(() => [...picker.options].some((o) => o.value === "height") || null);
  return { ...r, picker, bodies };
}

const stageChart = () =>
  [...document.querySelectorAll<HTMLElement>("canvas.zparam")].find((c) => !c.closest(".thumbstrip"));

// The picker as a reader sees it: top-level entries, then each group.
function outline(select: HTMLSelectElement) {
  return [...select.children].map((c) =>
    c.tagName === "OPTGROUP"
      ? {
          group: (c as HTMLOptGroupElement).label,
          options: [...c.children].map((o) => `${o.textContent}${(o as HTMLOptionElement).disabled ? " [off]" : ""}`),
        }
      : `${c.textContent}${(c as HTMLOptionElement).disabled ? " [off]" : ""}`,
  );
}

for (const mobile of [false, true]) {
  const width = mobile ? "at a phone's width" : "on a desktop";

  describe(`the Sweep chart's picker, ${width}`, () => {
    afterEach(() => vi.unstubAllGlobals());

    it("leads with what runs here, then 'Sweep a knob', then what cannot run yet, disabled", async () => {
      const { picker } = await mount(mobile);
      expect(outline(picker)).toEqual([
        "freq sweep (the design's band)",
        "convergence",
        "height",
        "band SWR",
        "Sweep a knob",
        {
          group: "Not in the workbench yet",
          options: ["tuning family (not here yet) [off]", "match vs height (not here yet) [off]"],
        },
      ]);
      const hold = [...picker.options].find((o) => o.textContent?.startsWith("match vs height"))!;
      expect(hold.title).toBe(HOLD);
      // The new chart shows the first entry.
      expect(picker.selectedIndex).toBe(0);
    });

    it("'Sweep a knob' runs the first knob and draws; the parameter list then re-runs for length_factor", async () => {
      const user = userEvent.setup();
      const { bodies } = await mount(mobile);
      // The header is the kind's own (frequency or knob), so the picker is
      // a new element after a switch: ask for it each time.
      const picker = () => screen.getByRole("combobox", { name: "Analysis" }) as HTMLSelectElement;
      const knobEntry = () => [...picker().options].find((o) => o.textContent === "Sweep a knob")!.value;
      fireEvent.change(picker(), { target: { value: knobEntry() } });
      // No knob swept yet this session: the design's first, over its range.
      await untilDom(() => bodies.some((b) => b.param === "base") || null);
      const base = bodies.find((b) => b.param === "base")!;
      expect(base.values[0]).toBeCloseTo(3.5, 6);
      expect(base.values[base.values.length - 1]).toBeCloseTo(10.5, 6);
      await untilDom(
        () => (stageChart()?.dataset.param === "base" && Number(stageChart()!.dataset.points) === base.values.length) || null,
      );
      expect(screen.getByRole("group", { name: "Analysis chart" }).dataset.chartKind).toBe("knob");
      expect(picker().selectedOptions[0].textContent).toBe("Sweep a knob");
      // The knob selector: length_factor, a pick, re-runs and draws.
      await user.selectOptions(screen.getByRole("combobox", { name: "Parameter" }), "length_factor");
      await untilDom(() => bodies.some((b) => b.param === "length_factor") || null);
      const lf = bodies.find((b) => b.param === "length_factor")!;
      expect(lf.values[0]).toBeCloseTo(0.485, 6);
      await untilDom(() => (stageChart()?.dataset.param === "length_factor" && stageChart()!.dataset.points === "11") || null);
      // Back to the frequency sweep, then "Sweep a knob" again: the last knob.
      fireEvent.change(picker(), { target: { value: picker().options[0].value } });
      await untilDom(() => screen.getByRole("group", { name: "Analysis chart" }).dataset.chartKind === "frequency" || null);
      const n = bodies.length;
      fireEvent.change(picker(), { target: { value: knobEntry() } });
      await untilDom(() => bodies.length > n || null);
      expect(bodies[n].param).toBe("length_factor");
    });

    it("choosing a knob in the header's parameter list draws it too (a pick runs)", async () => {
      const user = userEvent.setup();
      const { picker, bodies } = await mount(mobile);
      fireEvent.change(picker, { target: { value: "height" } });
      await untilDom(() => bodies.some((b) => b.param === "base") || null);
      await user.selectOptions(screen.getByRole("combobox", { name: "Parameter" }), "length_factor");
      await untilDom(() => bodies.some((b) => b.param === "length_factor") || null);
      await untilDom(() => (stageChart()?.dataset.param === "length_factor" && stageChart()!.dataset.points === "11") || null);
      // Run is there to run it again.
      expect(screen.getByRole("button", { name: /· run$|^run$/ })).toBeTruthy();
    });
  });
}
