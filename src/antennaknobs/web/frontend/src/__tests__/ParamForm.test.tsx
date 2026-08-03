// Pins the schema-driven rendering matrix of ParamForm (src/components/
// params/ParamForm.tsx, issue #673): per-kind rendering (float/int knob,
// bool checkbox, enum select), the missing-value default fallback, the
// on_change_set sibling side effect, applyVisibility gating (including its
// permissive fallback when the controlling value is absent — see
// lib/params.ts applyVisibility, pinned directly at params.test.ts too, but
// re-asserted here at the render level since a missing `applyVisibility`
// call is a plausible regression this component alone can introduce), group
// instancing (repeat_count vs. actual instance-array length), the nested
// group onChange path, range_from_enum_option, and the top-level optimiser
// (`opt`) integration. Every conditional-presence assertion is paired with
// an absence assertion on the case that must NOT show/fire.
import type { ComponentProps } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ParamForm } from "../components/params/ParamForm";
import type {
  ParamValueBag,
  SchemaItem,
  SchemaParamGroupSpec,
  SchemaParamSpec,
} from "../lib/params";

// --- fixture factories -------------------------------------------------
// Local, minimal, fully-typed — modeled on params.test.ts's factories but
// redefined here rather than imported (importing a test module re-registers
// its suites).

function makeParam(overrides: Partial<SchemaParamSpec> = {}): SchemaParamSpec {
  return {
    name: "p",
    label: "P",
    default: 0,
    kind: "float",
    min: 0,
    max: 10,
    step: 1,
    precision: 2,
    unit: null,
    visible_when: null,
    ...overrides,
  };
}

function makeGroup(overrides: Partial<SchemaParamGroupSpec> = {}): SchemaParamGroupSpec {
  return {
    kind: "group",
    name: "g",
    label_template: "G {i}",
    repeat_count: "n_g",
    max_repeats: 2,
    params: [],
    default_overrides: [{}, {}],
    ...overrides,
  };
}

// --- render harness ------------------------------------------------------
// onChange is always the spy (spread after overrides), so a test can never
// end up asserting on a spy the component didn't actually receive.
type FormOverrides = Partial<
  Omit<ComponentProps<typeof ParamForm>, "schema" | "values" | "onChange">
>;

function renderForm(
  schema: SchemaItem[],
  values: ParamValueBag,
  overrides: FormOverrides = {},
) {
  const onChange = vi.fn();
  const view = render(
    <ParamForm schema={schema} values={values} {...overrides} onChange={onChange} />,
  );
  return { ...view, onChange, user: userEvent.setup() };
}

describe("ParamForm — scalar float/int knob", () => {
  it("renders label, slider aria bounds/value, and the toFixed(precision)+unit value text", () => {
    const schema: SchemaItem[] = [
      makeParam({
        name: "len",
        label: "Length",
        kind: "float",
        default: 0,
        min: 0,
        max: 10,
        step: 0.5,
        precision: 2,
        unit: "m",
      }),
    ];
    renderForm(schema, { len: 3.456 });
    const slider = screen.getByRole("slider", { name: "Length" });
    expect(slider.getAttribute("aria-valuenow")).toBe("3.456");
    expect(slider.getAttribute("aria-valuemin")).toBe("0");
    expect(slider.getAttribute("aria-valuemax")).toBe("10");
    expect(slider.getAttribute("data-knob-id")).toBe("len");
    const field = slider.closest(".field-knob");
    expect(field).not.toBeNull();
    expect(within(field as HTMLElement).getByText("Length")).toBeTruthy();
    expect((field as HTMLElement).querySelector(".knob-value")?.textContent).toBe("3.46m");
  });

  it("renders an int knob's value display Math.round'd, Knob precision 0", () => {
    const schema: SchemaItem[] = [
      makeParam({
        name: "n",
        label: "N",
        kind: "int",
        default: 0,
        min: 0,
        max: 10,
        step: 1,
        precision: 2, // item.precision itself is irrelevant to int display
        unit: null,
      }),
    ];
    renderForm(schema, { n: 4.7 });
    const slider = screen.getByRole("slider", { name: "N" });
    // Knob receives precision=0 for an int kind, so its own formatted text
    // (aria-valuetext) rounds too, even though aria-valuenow stays the raw
    // unrounded value.
    expect(slider.getAttribute("aria-valuenow")).toBe("4.7");
    expect(slider.getAttribute("aria-valuetext")).toBe("5");
    const field = slider.closest(".field-knob") as HTMLElement;
    expect(field.querySelector(".knob-value")?.textContent).toBe("5");
  });

  it("falls back to Number(item.default) when the value bag lacks the param", () => {
    const schema: SchemaItem[] = [
      makeParam({ name: "len", label: "Length", default: 7, min: 0, max: 20, precision: 1, unit: null }),
    ];
    renderForm(schema, {});
    const slider = screen.getByRole("slider", { name: "Length" });
    expect(slider.getAttribute("aria-valuenow")).toBe("7");
    const field = slider.closest(".field-knob") as HTMLElement;
    expect(field.querySelector(".knob-value")?.textContent).toBe("7.0");
  });
});

describe("ParamForm — bool", () => {
  it("reflects the current value and fires onChange([name], true) when checked on", async () => {
    const schema: SchemaItem[] = [makeParam({ name: "flag", label: "Flag", kind: "bool", default: false })];
    const { user, onChange } = renderForm(schema, { flag: false });
    const box = screen.getByRole("checkbox", { name: "Flag" });
    expect(box).toHaveProperty("checked", false);
    await user.click(box);
    expect(onChange).toHaveBeenCalledWith(["flag"], true);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("fires onChange([name], false) when unchecked off", async () => {
    const schema: SchemaItem[] = [makeParam({ name: "flag", label: "Flag", kind: "bool", default: true })];
    const { user, onChange } = renderForm(schema, { flag: true });
    const box = screen.getByRole("checkbox", { name: "Flag" });
    expect(box).toHaveProperty("checked", true);
    await user.click(box);
    expect(onChange).toHaveBeenCalledWith(["flag"], false);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("disabledFields disables the input and marks the label field-disabled", () => {
    const schema: SchemaItem[] = [makeParam({ name: "flag", label: "Flag", kind: "bool", default: true })];
    renderForm(schema, { flag: true }, { disabledFields: new Set(["flag"]) });
    const box = screen.getByRole("checkbox", { name: "Flag" });
    expect(box).toHaveProperty("disabled", true);
    expect(box.closest("label")?.className.includes("field-disabled")).toBe(true);
  });

  it("is enabled with no field-disabled class when disabledFields doesn't name it", () => {
    const schema: SchemaItem[] = [makeParam({ name: "flag", label: "Flag", kind: "bool", default: true })];
    renderForm(schema, { flag: true });
    const box = screen.getByRole("checkbox", { name: "Flag" });
    expect(box).toHaveProperty("disabled", false);
    expect(box.closest("label")?.className.includes("field-disabled")).toBe(false);
  });
});

describe("ParamForm — enum", () => {
  it("renders options from enum_options and fires onChange([name], value) on change", async () => {
    const schema: SchemaItem[] = [
      makeParam({
        name: "mode",
        label: "Mode",
        kind: "enum",
        default: "a",
        enum_options: [
          { value: "a", label: "A" },
          { value: "b", label: "B" },
        ],
      }),
    ];
    const { user, onChange } = renderForm(schema, { mode: "a" });
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["a", "b"]);
    await user.selectOptions(select, "b");
    expect(onChange).toHaveBeenCalledWith(["mode"], "b");
    // Adversarial: no on_change_set declared, so exactly one call.
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("on_change_set also fires a second onChange for the sibling, in order", async () => {
    const schema: SchemaItem[] = [
      makeParam({
        name: "band",
        label: "Band",
        kind: "enum",
        default: "b10",
        enum_options: [
          { value: "b10", label: "10 m", bandFreq: 28.5 },
          { value: "b12", label: "12 m", bandFreq: 24.94 },
        ],
        on_change_set: { set: "freq", from_enum_key: "bandFreq" },
      }),
      makeParam({ name: "freq", label: "Freq", kind: "float", default: 28.5, min: 0, max: 30, precision: 2, unit: "MHz" }),
    ];
    const { user, onChange } = renderForm(schema, { band: "b10", freq: 28.5 });
    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "b12");
    expect(onChange).toHaveBeenNthCalledWith(1, ["band"], "b12");
    expect(onChange).toHaveBeenNthCalledWith(2, ["freq"], 24.94);
    expect(onChange).toHaveBeenCalledTimes(2);
  });
});

describe("ParamForm — visibility (applyVisibility)", () => {
  const controlled = makeParam({
    name: "extra",
    label: "Extra",
    kind: "float",
    default: 1,
    min: 0,
    max: 5,
    precision: 1,
    unit: null,
    visible_when: { name: "ctrl", op: "gt", value: 0 },
  });

  it("renders when the controlling value satisfies the condition", () => {
    renderForm([controlled], { ctrl: 1, extra: 2 });
    expect(screen.queryByRole("slider", { name: "Extra" })).not.toBeNull();
  });

  it("does not render when the controlling value fails the condition", () => {
    renderForm([controlled], { ctrl: 0, extra: 2 });
    expect(screen.queryByRole("slider", { name: "Extra" })).toBeNull();
  });

  it("renders when the controlling value is absent from the value bag (permissive fallback)", () => {
    renderForm([controlled], { extra: 2 }); // no "ctrl" key at all
    expect(screen.queryByRole("slider", { name: "Extra" })).not.toBeNull();
  });
});

describe("ParamForm — groups", () => {
  const groupSchema = makeGroup({
    name: "bag",
    label_template: "Bag {i}",
    repeat_count: "count",
    max_repeats: 3,
    params: [makeParam({ name: "p", label: "P", kind: "float", default: 1, min: 0, max: 10, step: 1, precision: 0, unit: null })],
    default_overrides: [{}, {}, {}],
  });

  it("renders one .param-group-instance per count, with the {i}-substituted header", () => {
    const { container } = renderForm([groupSchema], { count: 2, bag: [{ p: 1 }, { p: 2 }] });
    const instances = container.querySelectorAll(".param-group-instance");
    expect(instances).toHaveLength(2);
    expect(instances[0].querySelector(".param-group-header")?.textContent).toBe("Bag 0");
    expect(instances[1].querySelector(".param-group-header")?.textContent).toBe("Bag 1");
  });

  it("renders only `count` instances when count is less than the instance-bag length", () => {
    const { container } = renderForm([groupSchema], { count: 1, bag: [{ p: 1 }, { p: 2 }] });
    expect(container.querySelectorAll(".param-group-instance")).toHaveLength(1);
  });

  it("clamps to the instance-bag length when count exceeds it (Math.min, not count alone)", () => {
    // count=5 with only 2 real instance bags: a bare `count` (dropping the
    // Math.min clamp) would try to render instances[2..4], which are
    // undefined — either a crash or 5 instances, never the correct 2.
    const { container } = renderForm([groupSchema], { count: 5, bag: [{ p: 1 }, { p: 2 }] });
    expect(container.querySelectorAll(".param-group-instance")).toHaveLength(2);
  });

  it("renders nothing for the group when its instances value isn't an array", () => {
    const { container } = renderForm([groupSchema], { count: 2, bag: "oops" });
    expect(container.querySelector(".param-group")).toBeNull();
  });

  it("routes a nested knob's onChange through the group/index/param path", () => {
    const { container, onChange } = renderForm([groupSchema], {
      count: 2,
      bag: [{ p: 1 }, { p: 5 }],
    });
    const instance1 = container.querySelectorAll(".param-group-instance")[1] as HTMLElement;
    const slider = within(instance1).getByRole("slider", { name: "P" });
    fireEvent.keyDown(slider, { key: "ArrowUp" });
    expect(onChange).toHaveBeenCalledWith(["bag", 1, "p"], 6);
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

describe("ParamForm — range_from_enum_option", () => {
  const schema: SchemaItem[] = [
    makeParam({
      name: "band",
      label: "Band",
      kind: "enum",
      default: "b1",
      enum_options: [
        { value: "b1", label: "B1", freqMin: 10, freqMax: 20 },
        { value: "b2", label: "B2" }, // no freqMin/freqMax -> item.min/max fallback
      ],
    }),
    makeParam({
      name: "freq",
      label: "Freq",
      kind: "float",
      default: 15,
      min: 0,
      max: 100,
      step: 1,
      precision: 1,
      unit: "MHz",
      range_from_enum_option: { param: "band", min_key: "freqMin", max_key: "freqMax" },
    }),
  ];

  it("takes min/max from the selected option's keys", () => {
    renderForm(schema, { band: "b1", freq: 15 });
    const slider = screen.getByRole("slider", { name: "Freq" });
    expect(slider.getAttribute("aria-valuemin")).toBe("10");
    expect(slider.getAttribute("aria-valuemax")).toBe("20");
  });

  it("falls back to item.min/max when the selected option lacks those keys", () => {
    renderForm(schema, { band: "b2", freq: 15 });
    const slider = screen.getByRole("slider", { name: "Freq" });
    expect(slider.getAttribute("aria-valuemin")).toBe("0");
    expect(slider.getAttribute("aria-valuemax")).toBe("100");
  });
});

describe("ParamForm — opt integration", () => {
  const schema: SchemaItem[] = [
    makeParam({ name: "len", label: "Len", kind: "float", default: 5, min: 0, max: 10, step: 0.5, precision: 2, unit: null }),
  ];

  it("marks the field is-opt-var and the knob's aria bounds use dispMin/dispMax", () => {
    const opt = {
      settings: { len: { vary: true, optMin: 0, optMax: 10, dispMin: 2, dispMax: 8, step: 0.1 } },
      onContext: vi.fn(),
      onToggleVary: vi.fn(),
    };
    renderForm(schema, { len: 5 }, { opt });
    const slider = screen.getByRole("slider", { name: "Len" });
    const field = slider.closest(".field-knob") as HTMLElement;
    expect(field.className.includes("is-opt-var")).toBe(true);
    expect(slider.getAttribute("aria-valuemin")).toBe("2");
    expect(slider.getAttribute("aria-valuemax")).toBe("8");
  });

  it("fires opt.onContext(name, event) on contextmenu over the field", () => {
    const opt = {
      settings: {},
      onContext: vi.fn(),
      onToggleVary: vi.fn(),
    };
    renderForm(schema, { len: 5 }, { opt });
    const field = screen.getByRole("slider", { name: "Len" }).closest(".field-knob") as HTMLElement;
    fireEvent.contextMenu(field);
    expect(opt.onContext).toHaveBeenCalledTimes(1);
    const [name, evt] = opt.onContext.mock.calls[0];
    expect(name).toBe("len");
    expect((evt as Event).type).toBe("contextmenu");
  });

  it("'o' on the focused knob fires opt.onToggleVary(name)", () => {
    const opt = { settings: {}, onContext: vi.fn(), onToggleVary: vi.fn() };
    renderForm(schema, { len: 5 }, { opt });
    const slider = screen.getByRole("slider", { name: "Len" });
    fireEvent.keyDown(slider, { key: "o" });
    expect(opt.onToggleVary).toHaveBeenCalledWith("len");
    expect(opt.onToggleVary).toHaveBeenCalledTimes(1);
  });

  it("ctrl+'o' does not fire opt.onToggleVary (reserved for other shortcuts)", () => {
    const opt = { settings: {}, onContext: vi.fn(), onToggleVary: vi.fn() };
    renderForm(schema, { len: 5 }, { opt });
    const slider = screen.getByRole("slider", { name: "Len" });
    fireEvent.keyDown(slider, { key: "o", ctrlKey: true });
    expect(opt.onToggleVary).not.toHaveBeenCalled();
  });

  it("without opt: no is-opt-var, and contextmenu over the field doesn't throw", () => {
    renderForm(schema, { len: 5 });
    const field = screen.getByRole("slider", { name: "Len" }).closest(".field-knob") as HTMLElement;
    expect(field.className.includes("is-opt-var")).toBe(false);
    expect(() => fireEvent.contextMenu(field)).not.toThrow();
  });
});
