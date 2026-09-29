// An analysis chart's engine and ground crosses (AK#1757, sweep-framework
// step 5 unit 4): which solver slots and ground slots a chart compares, the
// curves (cells) their product makes, what each cell is called in the
// legend, and which cells are refused and why. React-free, so the rules are
// tested alone.
//
// The rules, from the step-5 design note's rulings:
//  - a chart's engines are a non-empty subset of the solver slots and its
//    grounds a non-empty subset of the ground slots, as checkboxes; both
//    default to the ACTIVE slot only, which is the chart as it was before
//    crosses, and follow the active slot until the viewer ticks a box;
//  - slot ids are open-ended (engines A…E, grounds 1…5): everything here
//    reads the ids it is handed and never assumes three;
//  - an analysis's listed engines and grounds (its `.py`) preselect the
//    slots that hold them; one no slot holds is a REFUSED cell, named in the
//    legend with its reason, and no slot is ever rewritten to hold it;
//  - engines × grounds is the cross, capped at CURVE_CAP curves (the CLI's
//    cap, analyses.CURVE_CAP); over the cap the whole chart is refused with
//    the CLI's wording, never truncated;
//  - a cell's label names what varies, the parts joined by ", ", as the
//    CLI's cells do (analysis_run.cells): the engine, then the ground, each
//    as the analysis spells it when it listed it.

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

/** The engines and grounds the picked analysis lists (lib/analyses.ts), or
 *  null where it names none. */
export type ListedCross = {
  engines: string[] | null;
  grounds: string[] | null;
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
};

/** One entry on an axis: a slot, or a listed spec no slot holds. */
export type AxisEntry = { id: string | null; label: string; refused: string | null };

/** One curve: its legend label, the slot and ground slot it solves on, and
 *  why it cannot be drawn (then `slot` / `ground` may be null). */
export type ChartCell = {
  key: string;
  label: string;
  slot: string | null;
  ground: string | null;
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

/** The CLI's over-cap refusal (analyses.problems), sized by this chart's
 *  two axes. */
export function capRefusal(nEngines: number, nGrounds: number): string | null {
  const n = nEngines * nGrounds;
  if (n <= CURVE_CAP) return null;
  return `REFUSED: ${nEngines} engines x ${nGrounds} grounds = ${n} curves, over the cap of ${CURVE_CAP}`;
}

/** The chart's curves: engines × grounds, engine-major, each labelled by
 *  the axes that vary (or that the analysis listed), refused where its
 *  engine or ground is, or where its slot cannot draw this design. */
export function crossPlan(cross: ChartCross, listed: ListedCross, env: CrossEnv): CrossPlan {
  const engines = axis(listed.engines, env.slots, checkedSlots(cross, env), "solver");
  const grounds = axis(listed.grounds, env.grounds, checkedGrounds(cross, env), "ground");
  const over = capRefusal(engines.length, grounds.length);
  if (over) return { engines, grounds, cells: [], capRefusal: over };
  const nameEngine = engines.length > 1 || listed.engines !== null;
  const nameGround = grounds.length > 1 || listed.grounds !== null;
  const cells: ChartCell[] = [];
  for (const e of engines) {
    for (const g of grounds) {
      const parts = [
        ...(nameEngine ? [e.label] : []),
        ...(nameGround ? [g.label] : []),
      ];
      const slotRefusal = e.id ? (env.slots.find((s) => s.id === e.id)?.refusal ?? null) : null;
      cells.push({
        key: `${e.id ?? `?${e.label}`}|${g.id ?? `?${g.label}`}`,
        label: parts.length > 0 ? parts.join(", ") : e.label,
        slot: e.id,
        ground: g.id,
        refused: e.refused ?? g.refused ?? slotRefusal,
      });
    }
  }
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
