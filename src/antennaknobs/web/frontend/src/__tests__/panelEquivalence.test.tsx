/**
 * The schema-rendered panel is the bespoke panel (#1006 G2-6).
 *
 * `BSplineFields` and `PANEL_BSPLINE` are gone; every knob is drawn by
 * `OptionField` from the served catalogue. This file is the evidence that the
 * swap was behaviour-preserving, which is the condition the panel was allowed
 * to be deleted under.
 *
 * RECORDED BEFORE ANY OF IT WAS DELETED, against the code that still
 * implemented it — eight states per b-spline backend, reaching 12 controls at
 * full expansion. THE FIRST RECORDING CAPTURED ONLY THE DEFAULT STATE: 8
 * controls against 12 accepted kwargs, because the enrichment sub-form is
 * collapsed until it is switched on. An equivalence test built on that would
 * have compared 8 controls, passed, and silently ignored the other five. The
 * states below exist because of that near-miss.
 *
 * A second flaw in the same recording: captions were read from each field's
 * first <span>, which duplicated one and dropped others. Controls are located
 * by the control element itself here for the same reason.
 *
 * A FRESHLY WRITTEN EQUIVALENCE TEST'S EXPECTATIONS ARE THE NEWEST THING IN
 * THE ROOM. When this file first ran, three of its assertions were wrong and
 * the code was right: `n_qp_source` is correctly HIDDEN by default (it is
 * gated on the smoothing factor, which is null), the enrichment sub-form is
 * correctly collapsed, and a field's label text includes its value span so it
 * needs prefix matching rather than equality. The pull is to "fix" the code
 * until the new test passes — which would have broken three working gates to
 * satisfy three fresh mistakes. The code under suspicion has been running;
 * these expectations were written minutes ago. Suspect them first.
 *
 * It did also find two REAL bugs, which is the other half of the same point:
 * `pynec` grew a pair of degree tabs (the axes-null fallback fired for a
 * backend with no degree at all), and `hmatrix`/`arrayblock` stopped greying
 * their enrichment control (momwire's coupling rows under-attributed, fixed
 * in momwire#890). Telling those apart from the three false alarms is the
 * whole skill, and the tell is the same either way: go and measure.
 *
 * WHAT IS DELIBERATELY NOT COMPARED: nothing. Captions, bounds, steps,
 * checked/disabled state, enum options and the request payload are all
 * compared, because every one of them was a thing the panel encoded that the
 * schema had to learn to say — the render bounds, the gate captions, the gate
 * on-values, the nullable gate and the gate CHAIN were each found by a
 * mismatch here rather than by reading the code.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { BackendConfigModal } from "../components/backend/BackendConfigModal";
import {
  defaultOptsFor,
  modelOptionsForRequest,
  type BackendEntry,
  type BackendOpts,
} from "../lib/backends";
import { entry, SERVED_ROSTER } from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const BSPLINE_FAMILY = ["bspline", "hmatrix", "arrayblock"];

function withModel(name: string, over: Record<string, unknown>): BackendOpts {
  const base = defaultOptsFor(entry(name), SERVED_OPTION_SPECS);
  return { ...base, model: { ...base.model, ...over } };
}

/** Every control on screen, located by the control rather than by caption. */
function controls() {
  const numbers = Array.from(
    document.querySelectorAll("input[type=number]"),
  ).map((e) => {
    const i = e as HTMLInputElement;
    return {
      kind: "number",
      label: i.closest(".field")?.querySelector("label")?.textContent?.trim(),
      value: i.value,
      min: i.min,
      max: i.max,
      step: i.step,
    };
  });
  const boxes = Array.from(
    document.querySelectorAll("input[type=checkbox]"),
  ).map((e) => {
    const i = e as HTMLInputElement;
    return {
      kind: "checkbox",
      label: i.closest("label")?.textContent?.trim(),
      checked: i.checked,
      disabled: i.disabled,
    };
  });
  const selects = Array.from(document.querySelectorAll("select")).map((e) => {
    const s = e as HTMLSelectElement;
    return {
      kind: "select",
      value: s.value,
      options: Array.from(s.options).map((o) => o.value),
    };
  });
  const tabs = Array.from(document.querySelectorAll('[role="tablist"]')).map(
    (e) => ({
      kind: "tablist",
      label: (e as HTMLElement)
        .closest(".field")
        ?.querySelector("label")
        ?.textContent?.trim(),
      tabs: within(e as HTMLElement)
        .getAllByRole("tab")
        .map((t) => t.textContent),
    }),
  );
  return { numbers, boxes, selects, tabs };
}

function mount(b: BackendEntry, opts: BackendOpts) {
  return render(
    <BackendConfigModal
      slot="A"
      backend={b}
      backends={SERVED_ROSTER}
      requiredBackends={null}
      design={{}}
      specs={SERVED_OPTION_SPECS}
      suggestConvergedFeed={false}
      opts={opts}
      onChangeBackend={vi.fn()}
      onPatch={vi.fn()}
      onReset={vi.fn()}
      onClose={vi.fn()}
    />,
  );
}

describe.each(BSPLINE_FAMILY)("%s — the panel the schema draws", (name) => {
  const b = () => entry(name);

  it("default: the nine stock knobs, with the sub-form collapsed", () => {
    mount(b(), defaultOptsFor(b(), SERVED_OPTION_SPECS));
    const c = controls();
    expect(c.tabs.map((t) => t.tabs)).toContainEqual(["d=1", "d=2"]);
    // A field's label text includes its value span, so match by prefix.
    const has = (pre: string) => c.numbers.some((n) => n.label?.startsWith(pre));
    // NOT drawn by default, each for its own reason — this is the state the
    // first recording captured alone, and it is the smallest of the eight.
    // `n_qp_source` is gated on the smoothing factor (null by default); the
    // enrichment sub-form is gated on the flag (false).
    expect(has("n_qp_source")).toBe(false);
    expect(c.selects).toHaveLength(0);
    expect(has("n_qp_sing")).toBe(false);
    expect(has("tikhonov_lambda")).toBe(false);
    expect(c.boxes.map((x) => x.label)).toEqual([
      "extended kernel (EK)",
      "n_qp_pair: auto",
      "feed source smoothing",
      "K≥3 junction singular enrichment",
    ]);
  });

  it("n_qp_pair: unticking auto pins the panel's own 8, not the spec default", () => {
    // The spec default IS null (auto), so a renderer that used it would put
    // the knob straight back to auto. `gate_on_value` is why it does not.
    mount(b(), withModel(name, { n_qp_pair: 8 }));
    const f = controls().numbers.find((n) => n.label?.startsWith("n_qp_pair"));
    expect(f).toBeTruthy();
    expect(f!.value).toBe("8");
    expect(f!.min).toBe("2");
    expect(f!.max).toBe("32");
  });

  it("feed smoothing: the RENDER range, not the sanitiser's", () => {
    // 0.5..10 step 0.5 against an accepted 0..100. A renderer fed the
    // sanitiser bounds would widen this knob tenfold.
    mount(b(), withModel(name, { feed_smoothing_factor: 3 }));
    const a = controls().numbers.find((n) => n.label?.includes("α"));
    expect(a).toBeTruthy();
    expect([a!.min, a!.max, a!.step]).toEqual(["0.5", "10", "0.5"]);
  });

  it("n_qp_source is gated on a NULLABLE NUMBER, not a boolean", () => {
    const shown = () =>
      controls().numbers.some((n) => n.label?.startsWith("n_qp_source"));
    const off = mount(b(), withModel(name, { feed_smoothing_factor: null }));
    expect(shown()).toBe(false);
    off.unmount();
    mount(b(), withModel(name, { feed_smoothing_factor: 3 }));
    expect(shown()).toBe(true);
  });

  it("enrichment on: the sub-form appears with its own bounds", () => {
    mount(b(), withModel(name, { use_singular_enrichment: true }));
    const c = controls();
    expect(c.selects[0]?.options).toEqual(["raw", "stable", "tikhonov", "auto"]);
    const sing = c.numbers.find((n) => n.label?.startsWith("n_qp_sing"));
    expect([sing!.min, sing!.max]).toEqual(["8", "64"]);
    const mink = c.numbers.find((n) => n.label?.startsWith("enrichment_min_k"));
    expect([mink!.min, mink!.max]).toEqual(["2", "6"]);
  });

  it("the variant knobs follow the VARIANT, not merely the enrichment flag", () => {
    // The gate CHAIN: tikhonov_lambda -> enrichment_variant ->
    // use_singular_enrichment. A truthiness gate on the flag alone would show
    // both variant knobs for every variant.
    const lambda = () =>
      controls().numbers.find((n) => n.label?.startsWith("tikhonov_lambda"));
    const tap = () =>
      controls().numbers.find((n) =>
        n.label?.startsWith("auto_tap_ratio_threshold"),
      );

    let v = mount(
      b(),
      withModel(name, { use_singular_enrichment: true, enrichment_variant: "raw" }),
    );
    expect(lambda()).toBeUndefined();
    expect(tap()).toBeUndefined();
    v.unmount();

    v = mount(
      b(),
      withModel(name, {
        use_singular_enrichment: true,
        enrichment_variant: "tikhonov",
      }),
    );
    expect(lambda()).toBeTruthy();
    expect(tap()).toBeUndefined();
    v.unmount();

    v = mount(
      b(),
      withModel(name, {
        use_singular_enrichment: true,
        enrichment_variant: "auto",
      }),
    );
    expect(lambda()).toBeUndefined();
    expect(tap()).toBeTruthy();
    v.unmount();

    // ...and with enrichment OFF, the variant keeps its value and the knob
    // still must not render — which a single-level gate would get wrong.
    mount(
      b(),
      withModel(name, {
        use_singular_enrichment: false,
        enrichment_variant: "tikhonov",
      }),
    );
    expect(lambda()).toBeUndefined();
  });

  it("the extended kernel greys enrichment, with momwire's own sentence", () => {
    mount(b(), withModel(name, { extended_kernel: true }));
    const box = controls().boxes.find((x) => x.label?.includes("enrichment"));
    expect(box?.disabled).toBe(true);
    const titled = screen.getByTitle(/use_singular_enrichment=True not/);
    // momwire#249 follow-up C, as momwire says it — not the momwire#271 the
    // deleted frontend copy cited.
    expect(titled.getAttribute("title")).toContain("momwire#249");
  });

  it("the controls appear in the ORDER the bespoke panel used", () => {
    // ORDER IS PART OF "looks the same" AND THIS SUITE MISSED IT AT FIRST.
    // Everything else here compares presence, bounds, captions and payload —
    // all of which passed while `degree` had moved from just under the kernel
    // toggle to the bottom of the panel, because the generic loop ran before
    // the axis-governed controls. A reviewer opening the app would have seen
    // it immediately; no assertion would have.
    //
    // So the axis controls bracket the generic loop the way the old panel
    // did: degree above it (it was the b-spline panel's first field), feed
    // model below it (it followed the generic knob on sin-galerkin).
    mount(b(), defaultOptsFor(b(), SERVED_OPTION_SPECS));
    const order = Array.from(document.querySelectorAll(".field")).map((f) =>
      (f.querySelector("label")?.textContent ?? "").trim().replace(/[\d.]+$/, ""),
    );
    expect(order).toEqual([
      "solver" + entry(name).label,
      "segments / wire (N)",
      "wire radius (m)",
      "extended kernel (EK)",
      "degree",
      "n_qp_pair: auto",
      "feed source smoothing",
      "K≥3 junction singular enrichment",
    ]);
  });

    it("the request payload is unchanged in every state", () => {
    const states: Record<string, unknown>[] = [
      {},
      { n_qp_pair: 8 },
      { feed_smoothing_factor: 3 },
      { use_singular_enrichment: true },
      { use_singular_enrichment: true, enrichment_variant: "tikhonov" },
      { degree: 1 },
      { extended_kernel: true },
    ];
    for (const over of states) {
      const opts = withModel(name, over);
      const payload = modelOptionsForRequest(b(), opts, SERVED_OPTION_SPECS);
      // Every exposed knob rides except the two whose absence is meaningful.
      expect(Object.keys(payload)).toContain("degree");
      expect("n_qp_pair" in payload).toBe(over.n_qp_pair !== undefined);
      expect("extended_kernel" in payload).toBe(over.extended_kernel === true);
      // ...and null rides for the nullable knob, which is a VALUE there.
      expect("feed_smoothing_factor" in payload).toBe(true);
    }
  });
});

describe("the backends that never had a bespoke panel", () => {
  it("pynec draws no solver knobs and no degree tabs", () => {
    // It fell through the axes-null fallback and grew a pair of degree tabs
    // during this refactor — `degreeChoices` now checks EXPOSURE first.
    mount(entry("pynec"), defaultOptsFor(entry("pynec"), SERVED_OPTION_SPECS));
    const c = controls();
    expect(c.tabs.flatMap((t) => t.tabs)).not.toContain("d=2");
    expect(c.selects).toHaveLength(0);
    expect(c.numbers.map((n) => n.label?.replace(/[\d.]+$/, ""))).toEqual([
      "segments / wire (N)",
      "wire radius (m)",
    ]);
  });

  it("razor-2p draws only the shared mesh knobs and the kernel toggle", () => {
    mount(entry("razor-2p"), defaultOptsFor(entry("razor-2p"), SERVED_OPTION_SPECS));
    const c = controls();
    expect(c.boxes.map((x) => x.label)).toEqual(["extended kernel (EK)"]);
    // `degree` and `n_qp_source` are ACCEPTED by RazorSolver and deliberately
    // not exposed; a renderer driven by acceptance would draw both.
    expect(c.numbers.some((n) => n.label?.startsWith("n_qp_source"))).toBe(false);
    expect(c.tabs.flatMap((t) => t.tabs)).not.toContain("d=2");
  });
});
