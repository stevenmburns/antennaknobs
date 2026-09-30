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
//  - slot ids are open-ended (engines A…E, grounds 1…5): everything here
//    reads the ids it is handed and never assumes three;
//  - an analysis's listed engines and grounds (its `.py`) preselect the
//    slots that hold them; one no slot holds is a REFUSED cell, named in the
//    legend with its reason, and no slot is ever rewritten to hold it;
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
//    same order, as the CLI's cells do: each engine and ground as the
//    analysis spells it when it listed it, a plane and a design by name,
//    a state by its name (after its design when it names one), and a
//    family's `knob = value` as the server labels it;
//  - a state (AK#1757 step 7) is one cell per named knob setting, set over
//    its design's DEFAULTS: one naming a design is that design's cell, and
//    an unnamed one beside a designs cross is set on each of them, refused
//    per design where the server says (`on`).

import type { BackendEntry } from "./backends";
import type { SoilParams } from "./ground";
import type { GroundSlot } from "./groundSlots";

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
export type CrossKind = "engines" | "grounds" | "planes" | "designs" | "states" | "step";

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
};
/** A knob value a state sets: what the design's knob holds. */
export type KnobValue = number | boolean | string;
/** A state (AK#1757 step 7): a named knob setting over its design's
 *  defaults, as /analyses serves it. `design` null is the session's design
 *  (at its variant's defaults, never its live knobs); `label` is the CLI's
 *  label part. The cell's sweep and refusal are served as a design cell's
 *  are; beside a designs cross an unnamed state is set on each design, and
 *  `on` holds one such entry per design (the top-level ones then null). */
export type StateCross = Omit<DesignCross, "name"> & {
  name: string;
  design: string | null;
  knobs: Record<string, KnobValue>;
  label: string;
  on: DesignCross[] | null;
};
/** What a state cell sets: its knobs over its design's defaults. */
export type CellState = { label: string; knobs: Record<string, KnobValue> };

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
};

/** One entry on an axis: a slot, or a listed spec no slot holds. */
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
  refused: string | null;
};

export type CrossPlan = {
  engines: AxisEntry[];
  grounds: AxisEntry[];
  /** Every cell of the product, refused ones included; empty over the cap. */
  cells: ChartCell[];
  /** The CLI's over-cap refusal, or null. */
  capRefusal: string | null;
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
 *  holds it, or a refused entry naming it), then the ticked slots no listed
 *  spec claimed, in id order. A listed spec whose slot the viewer unticked
 *  is left out; it is not refused, the viewer chose. */
function axis(
  listed: string[] | null,
  slots: { id: string; label: string; holds: (spec: string) => boolean }[],
  checked: string[],
  what: "solver" | "ground",
): AxisEntry[] {
  const out: AxisEntry[] = [];
  const used = new Set<string>();
  for (const spec of listed ?? []) {
    const slot = slots.find((s) => !used.has(s.id) && s.holds(spec));
    if (!slot) {
      out.push({ id: null, label: spec, refused: `no ${what} slot holds ${spec}` });
      continue;
    }
    used.add(slot.id);
    if (checked.includes(slot.id)) out.push({ id: slot.id, label: spec, refused: null });
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
 *  that lists specs no slot holds still selects what it can, and if it can
 *  select nothing, the active slot draws beside the refused cells. */
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
  return { slots: pick(listed.engines, env.slots), grounds: pick(listed.grounds, env.grounds) };
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
  c: Pick<ChartCell, "design" | "state">,
  listed: ListedCross,
): DesignCross | StateCross | null {
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
  const engines = axis(listed.engines, env.slots, checkedSlots(cross, env), "solver");
  const grounds = axis(listed.grounds, env.grounds, checkedGrounds(cross, env), "ground");
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
            state: { label: s.label, knobs: s.knobs },
            ...(s.design !== null ? { design: s.design } : {}),
          },
        }));
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
  if (over) return { engines, grounds, cells: [], capRefusal: over };
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
      refused: combo.find((p) => p.refused)?.refused ?? onDesign ?? slotRefusal,
    };
    if (set.state !== undefined) cell.state = set.state;
    return cell;
  });
  return { engines, grounds, cells, capRefusal: null };
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
