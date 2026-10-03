// An analysis chart's crosses (AK#1757, sweep-framework step 5 unit 4):
// which solver slots and ground slots a chart compares, the analysis's own
// crosses over measurement planes, designs and a family (unit 4b), the
// curves (cells) their product makes, what each cell is called in the
// legend, and which cells are refused and why. React-free, so the rules are
// tested alone.
//
// The rules, from the step-5 design note's rulings and the CLI's
// `analysis_run.cells`:
//  - a chart's engines are a non-empty subset of the solver slots and its
//    grounds a non-empty subset of the ground slots, as checkboxes; both
//    default to the ACTIVE slot only, which is the chart as it was before
//    crosses, and follow the active slot until the viewer ticks a box;
//  - slot ids are open-ended (engines A…E, grounds X, Y, Z, U…): everything here
//    reads the ids it is handed and never assumes three;
//  - an analysis's listed engines and grounds (its `.py`) preselect the
//    slots that hold them, and no slot is ever rewritten to hold one. A
//    listed ENGINE no slot holds is SKIPPED (Steve, 2026-10-01: "just skip
//    those engines listed in the analysis that are not in slots"): no cell,
//    no curve, only the legend's note naming it (`skippedNote`). If every
//    listed engine is skipped the chart would be empty, so the pick ticks
//    every slot instead and the note says so. A listed GROUND no slot holds
//    is still a REFUSED cell, named in the legend with its reason, and so is
//    a cell refused for any other reason (a slot that cannot draw the
//    design, an engine that cannot feed it): those are cells the viewer has,
//    not engines they lack. The CLI's `analyze` runs exactly what is listed;
//    the skip is the workbench's, about the viewer's slots;
//  - its crosses over planes, designs and a family come from the analysis
//    alone (they are not session slots, so there are no checkboxes): one
//    cell per plane, per design and per step value, as /analyses serves
//    them, refused by name where the server says so;
//  - the cells are the product of every axis, in the order the analysis
//    writes its crosses, then the engine and ground axes it does not cross
//    (engines before grounds), capped at CURVE_CAP curves (the CLI's cap,
//    analyses.CURVE_CAP); over the cap the whole chart is refused with the
//    CLI's wording, never truncated;
//  - a cell's label names what varies, the parts joined by ", " in that
//    same order, as the CLI's cells do: each engine as the analysis spells
//    it when it listed it, a listed ground in the ground tabs' words
//    (`groundSpecWords`: the spec `finite:13,0.005` names the soil but
//    not the model, and Sommerfeld against refl-coef is a ~3 dB split on
//    a low vertical, AK#1867; the CLI words it alike,
//    `analysis_run.ground_words`), a plane and a design by name,
//    a state by its name (after its design when it names one), and a
//    family's `knob = value` as the server labels it;
//  - a state (AK#1757 step 7) is one cell per named knob setting, set over
//    its design's DEFAULTS: one naming a design is that design's cell, and
//    an unnamed one beside a designs cross is set on each of them, refused
//    per design where the server says (`on`);
//  - listed cells (`cells=`, step 7 unit 4) are a UNION, not a product: one
//    curve per listed cell, in order, each on the slot and ground slot that
//    hold ITS engine and ground (else the analysis's, else the active
//    ones). A cell whose engine no slot holds is skipped as a listed
//    engine is; if every cell is, and the cells say nothing else that
//    tells them apart (no state, one ground, one plane), they are only an
//    engine list and the chart draws the slots instead (`cellsFallback`);
//    otherwise the chart draws nothing but the note. A cell whose ground no
//    slot holds is refused by name. The checkboxes do not multiply them.
//  - a cell whose engine refuses its ground (AK#1856: NEC-5 has no refl-coef)
//    is refused in the roster's served sentence, as the CLI refuses
//    `--engine nec5 --ground finite-fast`, never drawn on other physics.

import type { BackendEntry } from "./backends";
import { type SoilParams, type SoilPresetSchema, soilSummaryLabel } from "./ground";
import { type GroundSlot, METHOD_LABEL } from "./groundSlots";

/** The most curves one chart draws: the CLI's `analyses.CURVE_CAP`. */
export const CURVE_CAP = 6;

/** What a chart compares. Null follows the session's active slot (the
 *  default: one curve, the chart as it always was); a list is the viewer's
 *  or a pick's own choice. */
export type ChartCross = {
  slots: string[] | null;
  grounds: string[] | null;
};

/** The kinds of cross an analysis writes (analyses._CROSS_KINDS). */
export type CrossKind = "engines" | "grounds" | "planes" | "designs" | "states" | "cells" | "step";

/** A plane cell as /analyses serves it: refused (in the CLI's words) where
 *  the design does not offer it. */
export type PlaneCross = { name: string; refused: string | null };
/** A design cell: refused where the catalog lacks it or its sweep does not
 *  resolve there; a knob sweep's parameter and values as that design
 *  resolves them (null for a frequency sweep); a frequency sweep's spacing
 *  and exact grid on that design's own band (null for a knob sweep). */
export type DesignCross = {
  name: string;
  refused: string | null;
  param: string | null;
  values: number[] | null;
  spacing?: "lin" | "log" | null;
  freqs?: number[] | null;
  /** A MetricPlot's reference cell (AK#1828): the cell its `relative_to`
   *  names. `fixed`: solved once at its own setting (its `values` the one
   *  value of the swept knob it sets), drawn flat. */
  reference?: boolean;
  fixed?: boolean;
};
/** A scalar knob value: a number, a bool or a string. */
export type ScalarKnob = number | boolean | string;
/** A knob value a state sets: what the design's knob holds, a group knob's
 *  (fan_dipole's `bands`, unit 4) a list of its entries. */
export type KnobValue = ScalarKnob | Record<string, ScalarKnob>[];
/** A state (AK#1757 step 7): a named knob setting over its design's
 *  defaults, as /analyses serves it. `design` null is the session's design
 *  (at its variant's defaults, never its live knobs); `label` is the CLI's
 *  label part. The cell's sweep and refusal are served as a design cell's
 *  are; beside a designs cross an unnamed state is set on each design, and
 *  `on` holds one such entry per design (the top-level ones then null). */
export type StateCross = Omit<DesignCross, "name"> & {
  name: string;
  design: string | null;
  /** The variant whose defaults it is set over (unit 4), or null: the
   *  design's default (the session's own variant for an unnamed state). */
  variant?: string | null;
  knobs: Record<string, KnobValue>;
  label: string;
  on: DesignCross[] | null;
};
/** What a state cell sets: its knobs over its design's defaults (its
 *  `variant`'s, when it names one). */
export type CellState = { label: string; knobs: Record<string, KnobValue>; variant?: string };
/** A listed cell (`cells=`, AK#1757 step 7 unit 4), as /analyses serves
 *  it: its label, its state (null: the session's design as the chart runs
 *  it), its own engine, ground and plane specs (null: the analysis's, else
 *  the active slot's), and its sweep and refusal as a design cell's. */
export type ListedCell = Omit<DesignCross, "name"> & {
  label: string;
  state: {
    name: string;
    design: string | null;
    variant: string | null;
    knobs: Record<string, KnobValue>;
    label: string;
  } | null;
  engine: string | null;
  ground: string | null;
  plane: string | null;
};

/** A family: the knob each cell sets, its values, and each cell's label. */
export type StepCross = { knob: string; values: number[]; labels: string[] };

/** What the picked analysis lists (lib/analyses.ts): the engines and
 *  grounds it names, or null where it names none, and its other crosses,
 *  absent or null where it has none. `axes` is the order its crosses are
 *  written in. */
export type ListedCross = {
  engines: string[] | null;
  grounds: string[] | null;
  axes?: CrossKind[];
  planes?: PlaneCross[] | null;
  designs?: DesignCross[] | null;
  states?: StateCross[] | null;
  cells?: ListedCell[] | null;
  step?: StepCross | null;
};

export const FOLLOW_ACTIVE: ChartCross = { slots: null, grounds: null };
export const NOTHING_LISTED: ListedCross = { engines: null, grounds: null };

/** The slots a cross can draw from, as the session holds them. */
export type CrossEnv = {
  /** The solver slots in id order: a slot's label for the legend, whether
   *  it holds an engine spec, and why it cannot draw this design (or null). */
  slots: { id: string; label: string; holds: (spec: string) => boolean; refusal: string | null }[];
  activeSlot: string;
  grounds: { id: string; label: string; holds: (spec: string) => boolean }[];
  activeGround: string;
  /** The session's design. A slot's refusal is about it, so it refuses the
   *  cells of that design only; another design's cell is the server's to
   *  refuse. Absent: every cell is the session's design. */
  design?: string;
  /** Why solver slot `slot` refuses ground slot `ground`, or null (AK#1856:
   *  NEC-5 on a refl-coef slot, in the roster's served words). About the
   *  pair, not the design, so it refuses that pair's cells on every design.
   *  Absent: no pair is refused. */
  groundRefusal?: (slot: string, ground: string) => string | null;
  /** The soil presets a listed ground's soil is named by ("average");
   *  absent, its numbers. */
  soilPresets?: readonly SoilPresetSchema[];
};

/** `env.groundRefusal` for a cell's pair, or null when either is unset. */
function pairRefusal(env: CrossEnv, slot: string | null, ground: string | null): string | null {
  return slot !== null && ground !== null ? (env.groundRefusal?.(slot, ground) ?? null) : null;
}

/** One entry on an axis: a slot, or a listed ground no slot holds. */
export type AxisEntry = { id: string | null; label: string; refused: string | null };

/** One curve: its legend label, the slot and ground slot it solves on, the
 *  plane, design, state and family step it sets (absent: the session's),
 *  and why it cannot be drawn (then `slot` / `ground` may be null). */
export type ChartCell = {
  key: string;
  label: string;
  slot: string | null;
  ground: string | null;
  plane?: string;
  design?: string;
  state?: CellState;
  step?: { knob: string; value: number };
  /** Which listed cell it is (`cells=`), its index in `ListedCross.cells`. */
  listed?: number;
  refused: string | null;
};

export type CrossPlan = {
  engines: AxisEntry[];
  grounds: AxisEntry[];
  /** Every cell of the product, refused ones included; empty over the cap. */
  cells: ChartCell[];
  /** The CLI's over-cap refusal, or null. */
  capRefusal: string | null;
  /** The listed engine specs no slot holds, skipped: no cell, no curve,
   *  named once each in the analysis's order (`skippedNote`). */
  skipped: string[];
  /** Every listed engine (or listed cell) was skipped, so the chart draws
   *  the ticked slots in their place (a pick ticks every slot). */
  fallback: boolean;
};

/** The ids ticked on one axis: the cross's list (those that still exist,
 *  in id order), else the active one; never empty. */
function ticked(list: string[] | null, ids: string[], active: string): string[] {
  const out = list ? ids.filter((id) => list.includes(id)) : [];
  return out.length > 0 ? out : [active];
}

export function checkedSlots(cross: ChartCross, env: CrossEnv): string[] {
  return ticked(cross.slots, env.slots.map((s) => s.id), env.activeSlot);
}

export function checkedGrounds(cross: ChartCross, env: CrossEnv): string[] {
  return ticked(cross.grounds, env.grounds.map((g) => g.id), env.activeGround);
}

/** One axis: each listed spec in the analysis's order (the ticked slot that
 *  holds it; for a ground no slot holds, a refused entry naming it; for an
 *  engine, nothing, the spec skipped), then the ticked slots no listed spec
 *  claimed, in id order. A listed spec whose slot the viewer unticked is
 *  left out; it is not refused, the viewer chose. */
function axis(
  listed: string[] | null,
  slots: { id: string; label: string; holds: (spec: string) => boolean }[],
  checked: string[],
  what: "solver" | "ground",
  skipped: string[],
  words: (spec: string) => string = (spec) => spec,
): AxisEntry[] {
  const out: AxisEntry[] = [];
  const used = new Set<string>();
  for (const spec of listed ?? []) {
    const slot = slots.find((s) => !used.has(s.id) && s.holds(spec));
    if (!slot) {
      if (what === "solver") {
        if (!skipped.includes(spec)) skipped.push(spec);
      } else {
        out.push({ id: null, label: words(spec), refused: `no ${what} slot holds ${spec}` });
      }
      continue;
    }
    used.add(slot.id);
    if (checked.includes(slot.id)) out.push({ id: slot.id, label: words(spec), refused: null });
  }
  for (const s of slots) {
    if (checked.includes(s.id) && !used.has(s.id)) {
      out.push({ id: s.id, label: s.label, refused: null });
    }
  }
  return out;
}

/** The slots a pick preselects: those holding the analysis's listed specs
 *  (null when it lists none, so the chart follows the active slot). A pick
 *  that lists specs no slot holds still selects what it can. One whose
 *  every listed engine is skipped selects EVERY solver slot (the chart
 *  draws the viewer's slots in their place), and so does a `cells=` pick
 *  whose every cell is skipped and says nothing but its engine
 *  (`cellsFallback`); a ground pick that selects nothing leaves the active
 *  ground slot beside the refused cells. */
export function preselect(listed: ListedCross, env: CrossEnv): ChartCross {
  const pick = (specs: string[] | null, slots: CrossEnv["slots"] | CrossEnv["grounds"]) => {
    if (specs === null) return null;
    const used: string[] = [];
    for (const spec of specs) {
      const s = slots.find((x) => !used.includes(x.id) && x.holds(spec));
      if (s) used.push(s.id);
    }
    return used;
  };
  const all = env.slots.map((s) => s.id);
  let slots = pick(listed.engines, env.slots);
  if (listed.cells) {
    if (cellsFallback(listed, listed.cells, env)) slots = all;
  } else if (slots !== null && slots.length === 0 && (listed.engines?.length ?? 0) > 0) {
    slots = all;
  }
  return { slots, grounds: pick(listed.grounds, env.grounds) };
}

/** A `cells=` list's engine specs, one per cell: its own, else the
 *  analysis's one engine, else null (the chart's slot). */
function cellEngines(listed: ListedCross, cells: ListedCell[]): (string | null)[] {
  const oneEngine = listed.engines && listed.engines.length === 1 ? listed.engines[0] : null;
  return cells.map((c) => c.engine ?? oneEngine);
}

/** Whether a `cells=` list falls back to the viewer's slots: every cell
 *  names an engine no slot holds (so every one is skipped), and the cells
 *  say nothing else that tells them apart — no state, one ground and one
 *  plane among them — so they are an engine list written as cells, and the
 *  slots in their place keep what they say. A list whose cells carry a
 *  state, or differ in ground or plane, has no slot each cell would go on:
 *  it falls back to nothing, and the chart draws only the note. */
export function cellsFallback(listed: ListedCross, cells: ListedCell[], env: CrossEnv): boolean {
  if (cells.length === 0) return false;
  const specs = cellEngines(listed, cells);
  if (!specs.every((s) => s !== null && !env.slots.some((x) => x.holds(s)))) return false;
  return (
    cells.every((c) => c.state === null) &&
    new Set(cells.map((c) => c.ground)).size === 1 &&
    new Set(cells.map((c) => c.plane)).size === 1
  );
}

// An engine spec as the note names it: the engine's own name, a momwire
// basis by its basis (the analysis's spelling for anything else).
const ENGINE_NAMES: Record<string, string> = {
  nec5: "NEC-5",
  nec2: "NEC-2",
  pynec: "PyNEC",
  momwire: "B-spline",
  "momwire:bspline": "B-spline",
  "momwire:bspline-d1": "B-spline d=1",
  "momwire:razor-nec5": "razor-2p",
};
export function engineSpecName(spec: string): string {
  const named = ENGINE_NAMES[spec];
  if (named) return named;
  return spec.startsWith("momwire:") ? spec.slice("momwire:".length) : spec;
}

/** The legend's note for the skipped engines, or null when none was:
 *  "skipped: razor-2p, NEC-5, which no slot holds. Put one in a slot to
 *  include it.", and when every one was, that the chart draws the slots in
 *  their place. A note, not a refusal: the viewer lacks the engine, which
 *  is no fault of the cell. */
export function skippedNote(plan: Pick<CrossPlan, "skipped" | "fallback">): string | null {
  const n = plan.skipped.length;
  if (n === 0) return null;
  const names = [...new Set(plan.skipped.map(engineSpecName))].join(", ");
  const instead = plan.fallback ? ", so the chart draws your slots instead" : "";
  const put = n === 1 ? "Put it in a slot to include it." : "Put one in a slot to include it.";
  return `skipped: ${names}, which no slot holds${instead}. ${put}`;
}

/** One axis of the product, for the cap's wording: its size and kind. */
export type CapAxis = { n: number; kind: CrossKind };

/** The CLI's over-cap refusal (analyses.problems): each axis's size in the
 *  product's order, a family's as "values", then the product. */
export function capRefusal(axes: readonly CapAxis[]): string | null {
  const n = axes.reduce((p, a) => p * a.n, 1);
  if (n <= CURVE_CAP) return null;
  const sizes = axes.map((a) => `${a.n} ${a.kind === "step" ? "values" : a.kind}`).join(" x ");
  return `REFUSED: ${sizes} = ${n} curves, over the cap of ${CURVE_CAP}`;
}

/** The kinds of the product's axes, in order: the analysis's crosses as it
 *  writes them, then the engine and ground axes it does not cross. */
export function axisOrder(listed: ListedCross): CrossKind[] {
  const present = (k: CrossKind) =>
    k === "engines" || k === "grounds" || (listed[k] !== undefined && listed[k] !== null);
  const order = (listed.axes ?? []).filter((k, i, all) => present(k) && all.indexOf(k) === i);
  for (const k of ["engines", "grounds"] as const) if (!order.includes(k)) order.push(k);
  return order;
}

// One value on one axis of the product: its label part, why it is refused,
// and what it sets on the cell.
type Part = {
  label: string;
  refused: string | null;
  key: string;
  set: Partial<Pick<ChartCell, "slot" | "ground" | "plane" | "design" | "state" | "step">>;
};

/** The served entry a cell's sweep and refusal come from: its state's (the
 *  per-design one beside a designs cross), else its design's, else none
 *  (the session's design, as the chart runs it). */
export function servedCell(
  c: Pick<ChartCell, "design" | "state" | "listed">,
  listed: ListedCross,
): DesignCross | StateCross | ListedCell | null {
  if (c.listed !== undefined) return listed.cells?.[c.listed] ?? null;
  if (c.state) {
    const st = listed.states?.find((s) => s.label === c.state!.label);
    if (!st) return null;
    if (st.on) return st.on.find((d) => d.name === c.design) ?? null;
    return st;
  }
  if (c.design === undefined) return null;
  return listed.designs?.find((d) => d.name === c.design) ?? null;
}

/** The chart's curves: the product of its axes (axisOrder), each labelled
 *  by the axes that vary (or that the analysis listed), refused where any
 *  of its parts is, or where its slot cannot draw this design. */
export function crossPlan(cross: ChartCross, listed: ListedCross, env: CrossEnv): CrossPlan {
  const skipped: string[] = [];
  const engines = axis(listed.engines, env.slots, checkedSlots(cross, env), "solver", skipped);
  const grounds = axis(listed.grounds, env.grounds, checkedGrounds(cross, env), "ground", [], (spec) =>
    groundSpecWords(spec, env.soilPresets ?? []),
  );
  if (listed.cells) return listedPlan(cross, listed, listed.cells, env, engines, grounds);
  // Every listed engine skipped: the engine axis is the ticked slots alone
  // (the pick ticked them all), which the note says.
  const fallback = skipped.length > 0 && skipped.length === new Set(listed.engines ?? []).size;
  const order = axisOrder(listed);
  const crossed = new Set(listed.axes ?? []);
  const parts = (kind: CrossKind): Part[] => {
    switch (kind) {
      case "engines":
        return engines.map((e) => ({
          label: e.label,
          refused: e.refused,
          key: e.id ?? `?${e.label}`,
          set: { slot: e.id },
        }));
      case "grounds":
        return grounds.map((g) => ({
          label: g.label,
          refused: g.refused,
          key: g.id ?? `?${g.label}`,
          set: { ground: g.id },
        }));
      case "planes":
        return (listed.planes ?? []).map((p) => ({
          label: p.name,
          refused: p.refused,
          key: `p:${p.name}`,
          set: { plane: p.name },
        }));
      case "designs":
        return (listed.designs ?? []).map((d) => ({
          label: d.name,
          refused: d.refused,
          key: `d:${d.name}`,
          set: { design: d.name },
        }));
      case "states":
        return (listed.states ?? []).map((s) => ({
          label: s.label,
          refused: s.refused,
          key: `st:${s.label}`,
          set: {
            state: {
              label: s.label,
              knobs: s.knobs,
              ...(s.variant ? { variant: s.variant } : {}),
            },
            ...(s.design !== null ? { design: s.design } : {}),
          },
        }));
      case "cells":
        // Listed cells are a union (listedPlan), never an axis of a product.
        return [];
      case "step": {
        const st = listed.step;
        if (!st) return [];
        return st.values.map((value, k) => ({
          label: st.labels[k] ?? `${st.knob} = ${value}`,
          refused: null,
          key: `s:${value}`,
          set: { step: { knob: st.knob, value } },
        }));
      }
    }
  };
  const axes = order.map((kind) => ({ kind, parts: parts(kind) }));
  // The cap names every cross the analysis writes and every other axis
  // with more than one value: the CLI's wording when nothing is ticked
  // beyond the analysis.
  const over = capRefusal(
    axes
      .filter((a) => crossed.has(a.kind) || a.parts.length > 1)
      .map((a) => ({ n: a.parts.length, kind: a.kind })),
  );
  if (over) return { engines, grounds, cells: [], capRefusal: over, skipped, fallback };
  // Which axes a label names: a plane, a design or a family always; an
  // engine or ground when there are several or the analysis listed them.
  const named = (kind: CrossKind, n: number) =>
    kind === "engines"
      ? n > 1 || listed.engines !== null
      : kind === "grounds"
        ? n > 1 || listed.grounds !== null
        : true;
  let combos: Part[][] = [[]];
  for (const a of axes) combos = combos.flatMap((c) => a.parts.map((p) => [...c, p]));
  const cells = combos.map((combo) => {
    const set: Part["set"] = Object.assign({}, ...combo.map((p) => p.set));
    const labels = combo.filter((_, k) => named(axes[k].kind, axes[k].parts.length)).map((p) => p.label);
    const engineLabel = combo[order.indexOf("engines")]?.label ?? "";
    const slot = set.slot ?? null;
    const ownDesign = set.design === undefined || env.design === undefined || set.design === env.design;
    const slotRefusal = slot && ownDesign ? (env.slots.find((s) => s.id === slot)?.refusal ?? null) : null;
    // An unnamed state beside a designs cross: refused on the designs the
    // server refused it on (a knob that design lacks, say).
    const onDesign =
      set.state && set.design !== undefined ? (servedCell(set, listed)?.refused ?? null) : null;
    // The 4a key (slot|ground) leads, so an engine x ground cell keeps it.
    const key = [
      combo[order.indexOf("engines")].key,
      combo[order.indexOf("grounds")].key,
      ...combo.filter((_, k) => axes[k].kind !== "engines" && axes[k].kind !== "grounds").map((p) => p.key),
    ].join("|");
    const cell: ChartCell = {
      key,
      label: labels.length > 0 ? labels.join(", ") : engineLabel,
      slot,
      ground: set.ground ?? null,
      ...(set.plane !== undefined ? { plane: set.plane } : {}),
      ...(set.design !== undefined ? { design: set.design } : {}),
      ...(set.step !== undefined ? { step: set.step } : {}),
      refused:
        combo.find((p) => p.refused)?.refused ??
        onDesign ??
        slotRefusal ??
        pairRefusal(env, slot, set.ground ?? null),
    };
    if (set.state !== undefined) cell.state = set.state;
    return cell;
  });
  return { engines, grounds, cells, capRefusal: null, skipped, fallback };
}

/** A listed cell's served label (`an.Cell.label`: its parts, the ground as
 *  the spec spells it, joined by ", ") with that ground part in the ground
 *  tabs' words, as a product cell's is (AK#1867). A spec has no ", " in it,
 *  so it is one part; the last match is the ground's, after any state. */
function listedLabel(c: ListedCell, env: CrossEnv): string {
  if (!c.ground) return c.label;
  const parts = c.label.split(", ");
  const at = parts.lastIndexOf(c.ground);
  if (at < 0) return c.label;
  parts[at] = groundSpecWords(c.ground, env.soilPresets ?? []);
  return parts.join(", ");
}

/** A `cells=` chart (unit 4): one cell per listed cell, a union. Each is
 *  on the slot holding its engine spec (else the analysis's one engine,
 *  else the first ticked slot) and the ground slot holding its ground spec
 *  (likewise). A cell whose engine no slot holds is skipped (no cell, named
 *  in the note); one whose ground no slot holds is refused by name. Every
 *  cell skipped and nothing else told apart (`cellsFallback`): one cell per
 *  ticked slot instead, on the cells' one ground and plane. The checkboxes
 *  pick the slots a cell that names nothing draws on, and multiply
 *  nothing. */
function listedPlan(
  cross: ChartCross,
  listed: ListedCross,
  cells: ListedCell[],
  env: CrossEnv,
  engines: AxisEntry[],
  grounds: AxisEntry[],
): CrossPlan {
  if (cells.length > CURVE_CAP) {
    return {
      engines,
      grounds,
      cells: [],
      capRefusal: `REFUSED: ${cells.length} cells = ${cells.length} curves, over the cap of ${CURVE_CAP}`,
      skipped: [],
      fallback: false,
    };
  }
  const oneGround = listed.grounds && listed.grounds.length === 1 ? listed.grounds[0] : null;
  const pick = (
    spec: string | null,
    slots: { id: string; holds: (spec: string) => boolean }[],
    fallback: string,
    what: "solver" | "ground",
  ): { id: string | null; refused: string | null } => {
    if (spec === null) return { id: fallback, refused: null };
    const s = slots.find((x) => x.holds(spec));
    return s ? { id: s.id, refused: null } : { id: null, refused: `no ${what} slot holds ${spec}` };
  };
  const specs = cellEngines(listed, cells);
  const skipped: string[] = [];
  const out: ChartCell[] = [];
  cells.forEach((c, k) => {
    const spec = specs[k];
    if (spec !== null && !env.slots.some((x) => x.holds(spec))) {
      if (!skipped.includes(spec)) skipped.push(spec);
      return;
    }
    const e = pick(spec, env.slots, checkedSlots(cross, env)[0], "solver");
    const g = pick(c.ground ?? oneGround, env.grounds, checkedGrounds(cross, env)[0], "ground");
    const design = c.state?.design ?? undefined;
    const ownDesign = design === undefined || env.design === undefined || design === env.design;
    const slotRefusal = e.id && ownDesign ? (env.slots.find((s) => s.id === e.id)?.refusal ?? null) : null;
    const cell: ChartCell = {
      key: `${e.id ?? "?"}|${g.id ?? "?"}|cell:${k}`,
      label: listedLabel(c, env) || (env.slots.find((s) => s.id === e.id)?.label ?? ""),
      slot: e.id,
      ground: g.id,
      ...(c.plane !== null ? { plane: c.plane } : {}),
      ...(design !== undefined ? { design } : {}),
      listed: k,
      refused: e.refused ?? g.refused ?? c.refused ?? slotRefusal ?? pairRefusal(env, e.id, g.id),
    };
    if (c.state) {
      cell.state = {
        label: c.state.label,
        knobs: c.state.knobs,
        ...(c.state.variant !== null ? { variant: c.state.variant } : {}),
      };
    }
    out.push(cell);
  });
  // Every cell skipped, and they are only an engine list: the ticked slots
  // in their place, on the cells' one ground and plane.
  const fallback = out.length === 0 && cellsFallback(listed, cells, env);
  if (fallback) {
    const g = pick(cells[0].ground ?? oneGround, env.grounds, checkedGrounds(cross, env)[0], "ground");
    const plane = cells[0].plane;
    for (const id of checkedSlots(cross, env)) {
      const s = env.slots.find((x) => x.id === id);
      out.push({
        key: `${id}|${g.id ?? "?"}|cells`,
        label: s?.label ?? id,
        slot: id,
        ground: g.id,
        ...(plane !== null ? { plane } : {}),
        refused: g.refused ?? s?.refusal ?? pairRefusal(env, id, g.id),
      });
    }
  }
  return { engines, grounds, cells: out, capRefusal: null, skipped, fallback };
}

/** Whether a solver slot holds an engine spec, as `--engine` spells one
 *  (cli.parse_engine_spec): "pynec", "nec5", "nec2", or "momwire[:basis]".
 *  A bare "momwire" is the CLI's default, the B-spline basis; "bspline-d1"
 *  is B-spline at degree 1, and "razor-nec5" the old spelling of
 *  "razor-2p". `degree` is the slot's B-spline degree, where it has one. */
export function engineSpecHeld(
  spec: string,
  b: Pick<BackendEntry, "kind" | "name">,
  degree: number | null | undefined,
): boolean {
  const [name, basis = ""] = spec.split(":", 2);
  if (name !== "momwire") return basis === "" && b.kind === name;
  if (b.kind !== "momwire") return false;
  if (basis === "" || basis === "bspline") return b.name === "bspline" && degree !== 1;
  if (basis === "bspline-d1") return b.name === "bspline" && degree === 1;
  if (basis === "razor-nec5") return b.name === "razor-2p";
  return b.name === basis;
}

// The CLI's ground kinds (cli.parse_ground) and the finite method each one
// means in a ground slot.
const GROUND_KINDS: Record<string, GroundSlot["method"]> = {
  "finite-fast": "fast",
  finite: "sommerfeld",
  mininec: "mininec",
};
// cli.parse_ground's soil when a spec gives none.
const CLI_SOIL: SoilParams = { eps_r: 13.0, sigma: 0.005 };

const close = (a: number, b: number) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));

/** A ground spec as the ground tabs word what a slot holds
 *  (groundSlotLabel): "Sommerfeld · average" for `finite:13,0.005`,
 *  "refl-coef · εr 5, σ 0.001 S/m" for `finite-fast:5,0.001`, "free space",
 *  "PEC". A spec the CLI would not parse reads as written. */
export function groundSpecWords(spec: string, presets: readonly SoilPresetSchema[] = []): string {
  if (spec === "free") return "free space";
  if (spec === "pec") return "PEC";
  const [kind, soilText] = spec.split(":", 2);
  const method = GROUND_KINDS[kind];
  if (!method) return spec;
  let soil = CLI_SOIL;
  if (soilText !== undefined) {
    const nums = soilText.split(",").map(Number);
    if (nums.length !== 2 || !nums.every(Number.isFinite)) return spec;
    soil = { eps_r: nums[0], sigma: nums[1] };
  }
  return `${METHOD_LABEL[method]} · ${soilSummaryLabel(soil, [...presets])}`;
}

/** Whether a ground slot holds a ground spec, as `--ground` spells one
 *  (cli.parse_ground): "free", "pec", or "finite" / "finite-fast" /
 *  "mininec", each optionally ":<eps_r>,<sigma>". A slot whose soil is not
 *  known yet reads as `defaultSoil`. A terrain slot holds no spec (the CLI
 *  has none). */
export function groundSpecHeld(
  spec: string,
  g: Pick<GroundSlot, "enabled" | "type" | "method" | "soil">,
  defaultSoil: SoilParams | null,
): boolean {
  if (spec === "free") return !g.enabled;
  if (spec === "pec") return g.enabled && g.type === "pec";
  const [kind, soilText] = spec.split(":", 2);
  const method = GROUND_KINDS[kind];
  if (!method || !g.enabled || g.type !== "finite" || g.method !== method) return false;
  let want = CLI_SOIL;
  if (soilText !== undefined) {
    const nums = soilText.split(",").map(Number);
    if (nums.length !== 2 || !nums.every(Number.isFinite)) return false;
    want = { eps_r: nums[0], sigma: nums[1] };
  }
  const soil = g.soil ?? defaultSoil;
  return !!soil && close(soil.eps_r, want.eps_r) && close(soil.sigma, want.sigma);
}

/** The cap refusal or the refused cells, as the lines the chart's legend
 *  names them by: "label: reason". */
export function refusedLines(plan: CrossPlan): string[] {
  if (plan.capRefusal) return [plan.capRefusal];
  return plan.cells.filter((c) => c.refused).map((c) => `${c.label}: ${c.refused}`);
}

/** A curve's server error as a refused cell's reason, or null when it is
 *  some other failure. The server reports a point it could not solve as
 *  "<ExceptionType>: <message>"; an engine declining the design (NEC-2 and
 *  a vertex feed) raises ValueError or NotImplementedError, which is
 *  exactly what `antennaknobs analyze` reports as a refused cell, in the
 *  message's own words (analysis_run.run). */
export function engineRefusal(error: string | null | undefined): string | null {
  const m = error ? /^(?:ValueError|NotImplementedError): ([\s\S]+)$/.exec(error) : null;
  return m ? m[1] : null;
}
