// Workbench deep links (AK#1838): a URL that opens a design and selects one
// of its analyses in the chart's picker.
//
//   ?design=<family.design>[:<variant>]   the design, and optionally its variant
//   &analysis=<name>                      the chart's analysis (own or a study)
//   &view=<view id>                       the chart's view (Rx, Knobs, Smith, …)
//   &family=<knob>:<from>:<to>:<points>[:log]
//                                         a pattern family's knob and range
//                                         (AK#1935), beside a pattern `view`
//   &cut=<degrees>                        that family's cut angle (AK#1950):
//                                         the bearing of an Elevation view,
//                                         the elevation of an Azimuth view;
//                                         absent, the view's own (0° az,
//                                         10° el), as every link before it
//   &run=1                                press Run once it is selected
//   ?deck=<z>&name=<file name>            an opened deck (lib/decks.ts): the
//                                         file's text, compressed, in place
//                                         of `design`
//   &dialect=nec2|nec4|nec5               the dialect the deck is read in,
//                                         when chosen (absent: detected)
//   &analyses=<z>                         analyses for the deck or design
//                                         (AK#2045): the stylized Python a
//                                         design's build_analyses() returns,
//                                         compressed as the deck is; listed
//                                         in the chart's picker, and
//                                         `analysis=` selects one by name.
//                                         Read by the server, never run.
//                                         Beside `deck` it rides the deck
//                                         (part of its key); beside `design`
//                                         the session sends it with /analyses.
//                                         Copy link writes the listed link
//                                         and built analyses here, at most
//                                         MAX_SHARE_CHARS packed
//   &knobs=<knob>:<value>[:<min>:<max>],…
//                                         knob values (AK#2045), set on the
//                                         knob panel before `analysis` is
//                                         picked or run; each entry a knob
//                                         name (an identifier: an SY knob is
//                                         sy_<name>), a value, and optionally
//                                         a range. Numbers are decimal
//                                         (sign, point, exponent; nothing
//                                         else, never evaluated). A range is
//                                         for an opened deck's knob, which
//                                         has none of its own: it is sent
//                                         with the deck (`ranges`), is part
//                                         of its key, and becomes the knob's
//                                         min/max on the server, so a hold
//                                         on it can run. On a catalog design
//                                         a range is refused by name (the
//                                         design's own stands) and the value
//                                         still applies. The writer writes a
//                                         knob moved off its default, and
//                                         every knob the deck has a range
//                                         for; at most MAX_LINK_KNOBS
//                                         entries, MAX_LINK_KNOBS_CHARS
//                                         characters
//
// React-free, so the grammar and the resolution are tested alone. The
// session (DesignSession) applies a parsed link in stages and reports what it
// could not resolve by name; nothing here touches the page.

import type { AnalysisEntry } from "./analyses";
import { DECK_NS, isDialect, shareable, type DeckPayload } from "./decks";
import { isGroup, type ExampleDescriptor, type SchemaItem, type SchemaParamSpec } from "./params";
import { MIN_POINTS, type ParamSweepSpec } from "./paramSweep";

/** A family's spec as a link carries it: its knob, range, count and spacing
 *  (never an analysis's explicit `values`: a family's are its range's). */
export type LinkFamily = Pick<ParamSweepSpec, "param" | "lo" | "hi" | "points" | "log">;

/** `knob:from:to:points[:log]`, or null when it is not that. The knob name
 *  holds no colon; `points` is a whole number of at least MIN_POINTS. */
export function parseFamily(raw: string): LinkFamily | null {
  const f = raw.split(":");
  if ((f.length !== 4 && f.length !== 5) || (f.length === 5 && f[4] !== "log")) return null;
  const [param, lo, hi, points] = [f[0].trim(), Number(f[1]), Number(f[2]), Number(f[3])];
  if (param === "" || !Number.isFinite(lo) || !Number.isFinite(hi)) return null;
  if (!Number.isInteger(points) || points < MIN_POINTS) return null;
  return { param, lo, hi, points, log: f.length === 5 };
}

/** The family as `parseFamily` reads it back. */
export function familyParam(f: LinkFamily): string {
  return [f.param, f.lo, f.hi, f.points, ...(f.log ? ["log"] : [])].join(":");
}

/** At most this many `knobs=` entries, and this many characters of them: a
 *  deck has a few dozen knobs at most (the server's own bounds,
 *  `decks.MAX_RANGES` / `MAX_RANGES_CHARS`). */
export const MAX_LINK_KNOBS = 32;
export const MAX_LINK_KNOBS_CHARS = 2000;

/** One `knobs=` entry: a knob's value, and the range the link gives it. */
export type LinkKnob = { name: string; value: number; min?: number; max?: number };

const KNOB_NAME = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;
const LINK_NUMBER = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;

/** `raw` as a link's number: decimal, finite; else null. `Number` alone
 *  would also take "", " 1", "0x10", "Infinity". */
export function linkNumber(raw: string): number | null {
  if (!LINK_NUMBER.test(raw)) return null;
  const v = Number(raw);
  return Number.isFinite(v) ? v : null;
}

/** A `knobs=` value read strictly: the entries that read, and each one that
 *  did not, refused by name (the rest stand). Over MAX_LINK_KNOBS entries or
 *  MAX_LINK_KNOBS_CHARS characters, none are read. */
export function parseKnobs(raw: string): { knobs: LinkKnob[]; problems: string[] } {
  if (raw.length > MAX_LINK_KNOBS_CHARS) {
    return { knobs: [], problems: [`knobs: ${raw.length} characters, over the ${MAX_LINK_KNOBS_CHARS} a link may carry`] };
  }
  const entries = raw.split(",");
  if (entries.length > MAX_LINK_KNOBS) {
    return { knobs: [], problems: [`knobs: ${entries.length} entries, over the ${MAX_LINK_KNOBS} a link may carry`] };
  }
  const knobs: LinkKnob[] = [];
  const problems: string[] = [];
  const seen = new Set<string>();
  for (const entry of entries) {
    const f = entry.split(":");
    const shown = entry.length <= 80 ? entry : `${entry.slice(0, 77)}...`;
    if ((f.length !== 2 && f.length !== 4) || !KNOB_NAME.test(f[0])) {
      problems.push(`knobs: "${shown}" is not <knob>:<value>[:<min>:<max>]`);
      continue;
    }
    const [name, ...nums] = f;
    const v = nums.map(linkNumber);
    if (v.some((x) => x === null)) {
      problems.push(`knobs: ${name}'s "${shown}" has a value that is not a finite decimal number`);
    } else if (seen.has(name)) {
      problems.push(`knobs: ${name} is given twice`);
    } else if (v.length === 3 && !(v[1]! < v[2]!)) {
      problems.push(`knobs: ${name}'s range ${nums[1]}:${nums[2]} does not have min < max`);
    } else if (v.length === 3 && (v[0]! < v[1]! || v[0]! > v[2]!)) {
      problems.push(`knobs: ${name}'s value ${nums[0]} is outside its range ${nums[1]}:${nums[2]}`);
    } else {
      seen.add(name);
      knobs.push(v.length === 3 ? { name, value: v[0]!, min: v[1]!, max: v[2]! } : { name, value: v[0]! });
    }
  }
  return { knobs, problems };
}

/** The entries as `parseKnobs` reads them back. */
export function knobsParam(knobs: readonly LinkKnob[]): string {
  return knobs
    .map((k) => (k.min !== undefined && k.max !== undefined ? `${k.name}:${k.value}:${k.min}:${k.max}` : `${k.name}:${k.value}`))
    .join(",");
}

/** The ranges alone, `<knob>:<min>:<max>,…`, as /deck takes them (the
 *  values are the panel's, never the deck's key's); "" for none. */
export function knobRanges(knobs: readonly LinkKnob[]): string {
  return knobs
    .filter((k) => k.min !== undefined && k.max !== undefined)
    .map((k) => `${k.name}:${k.min}:${k.max}`)
    .join(",");
}

/** `/deck`'s `ranges` read back into `{name: [min, max]}` (the page wrote
 *  them, so they read; anything that does not is skipped). */
export function rangesOf(ranges: string | undefined): Map<string, [number, number]> {
  const out = new Map<string, [number, number]>();
  for (const e of (ranges ?? "").split(",")) {
    const f = e.split(":");
    if (f.length !== 3) continue;
    const [lo, hi] = [linkNumber(f[1]), linkNumber(f[2])];
    if (lo !== null && hi !== null) out.set(f[0], [lo, hi]);
  }
  return out;
}

/** A design's flat numeric knob by name (a group's leaves are not link
 *  knobs). */
function numericKnob(schema: readonly SchemaItem[], name: string): SchemaParamSpec | undefined {
  return schema.find((x): x is SchemaParamSpec => !isGroup(x) && x.name === name);
}

const fmt = (v: number | null) => (v === null ? "?" : String(v));

/** The link's knob values as the panel takes them on this design
 *  (`schema`, the variant's), and each that it does not, by name:
 *
 *  - a knob the design lacks, or one that is not a number, is refused;
 *  - an integer knob takes a whole number only;
 *  - a range is an opened deck's (`deck`): the server made it the knob's
 *    min/max when it opened the deck. On a catalog design it is refused by
 *    name and the design's own range stands; the value still applies;
 *  - a value outside a range the design declares (the deck's, from the
 *    link) is refused. A knob whose range is only the app's own window
 *    (`auto_range`) takes any value, as its number field does. */
export function linkKnobValues(
  knobs: readonly LinkKnob[],
  schema: readonly SchemaItem[],
  opts: { deck: boolean },
): { values: Record<string, number>; problems: string[] } {
  const values: Record<string, number> = {};
  const problems: string[] = [];
  for (const k of knobs) {
    const spec = numericKnob(schema, k.name);
    if (!spec) {
      problems.push(`knobs: this design has no knob "${k.name}"`);
      continue;
    }
    if (spec.kind !== "float" && spec.kind !== "int") {
      problems.push(`knobs: "${k.name}" is not a numeric knob`);
      continue;
    }
    if (spec.kind === "int" && !Number.isInteger(k.value)) {
      problems.push(`knobs: "${k.name}" takes a whole number, not ${k.value}`);
      continue;
    }
    if (k.min !== undefined && !opts.deck) {
      problems.push(
        `knobs: ${k.name}'s range ${k.min}:${k.max} is not applied: a link gives a range only to an ` +
          `opened deck's knob, and this design's own (${fmt(spec.min)} to ${fmt(spec.max)}) stands`,
      );
    }
    const declared = spec.auto_range !== true && spec.min !== null && spec.max !== null;
    if (declared && (k.value < spec.min! || k.value > spec.max!)) {
      problems.push(`knobs: ${k.name}'s value ${k.value} is outside its range ${spec.min} to ${spec.max}`);
      continue;
    }
    values[k.name] = k.value;
  }
  return { values, problems };
}

/** What a link writes of a design's knobs (`knobs=`): every flat numeric
 *  knob moved off its default (`defaults`, the variant's), and every knob
 *  the opened deck has a link range for (`ranges`), with its range, in the
 *  schema's order. */
export function linkKnobsOf(
  schema: readonly SchemaItem[],
  values: Readonly<Record<string, unknown>>,
  defaults: Readonly<Record<string, unknown>>,
  ranges: ReadonlyMap<string, [number, number]>,
): LinkKnob[] {
  const out: LinkKnob[] = [];
  for (const item of schema) {
    if (isGroup(item) || (item.kind !== "float" && item.kind !== "int")) continue;
    const v = values[item.name];
    if (typeof v !== "number" || !Number.isFinite(v)) continue;
    const r = ranges.get(item.name);
    if (r) out.push({ name: item.name, value: v, min: r[0], max: r[1] });
    else if (v !== defaults[item.name]) out.push({ name: item.name, value: v });
  }
  return out;
}

/** A parsed link. Every field is optional: an absent one is not part of the
 *  link. `run` is true only for `run=1`. */
export type DeepLink = {
  design: string | null;
  variant: string | null;
  analysis: string | null;
  view: string | null;
  run: boolean;
  /** An opened deck the link carries (`deck` + `name`); the shell opens it
   *  and sets `design` to its key before the session reads the link. */
  deck?: DeckPayload | null;
  /** A pattern family's knob and range, to be applied beside `view`. */
  family?: LinkFamily | null;
  /** What was wrong with the link's `family`, for the link notice. */
  familyProblem?: string | null;
  /** The family's cut angle (AK#1950), a whole number of degrees; whether
   *  it suits the view is the session's to judge (`cutAngleProblem`). */
  cut?: number | null;
  /** What was wrong with the link's `cut`, for the link notice. */
  cutProblem?: string | null;
  /** What went wrong opening the link's deck, for the link notice. */
  problem?: string | null;
  /** The knob values (and ranges) the link sets (AK#2045, `knobs=`); the
   *  ranges also ride the deck (`deck.ranges`) when there is one. */
  knobs?: LinkKnob[] | null;
  /** The `knobs=` entries that did not read, by name, for the link notice. */
  knobsProblems?: string[] | null;
  /** A catalog design's `analyses=` (AK#2045), packed: the session lists
   *  them with /analyses. A deck's ride the deck (`deck.analyses`). */
  analyses?: string | null;
};

/** The query parameters a link owns; any other is left as it is. */
export const LINK_PARAMS = [
  "design",
  "analysis",
  "view",
  "run",
  "deck",
  "name",
  "dialect",
  "analyses",
  "knobs",
  "family",
  "cut",
] as const;

/** A non-empty, trimmed parameter, else null. */
function param(q: URLSearchParams, k: string): string | null {
  const v = q.get(k)?.trim() ?? "";
  return v === "" ? null : v;
}

/** `location.search` as a link, or null when it names none of the link's
 *  parameters (a plain visit). `design=a.b:v` splits at the first colon:
 *  a design name never holds one. */
export function parseDeepLink(search: string): DeepLink | null {
  const q = new URLSearchParams(search);
  const raw = param(q, "design");
  let design: string | null = null;
  let variant: string | null = null;
  if (raw !== null) {
    const at = raw.indexOf(":");
    design = at < 0 ? raw : raw.slice(0, at).trim() || null;
    variant = at < 0 ? null : raw.slice(at + 1).trim() || null;
  }
  const z = param(q, "deck");
  // A dialect the workbench does not know is dropped: the deck opens detected.
  const dialect = param(q, "dialect");
  const analyses = param(q, "analyses");
  const rawFamily = param(q, "family");
  const family = rawFamily === null ? null : parseFamily(rawFamily);
  // A whole number here; its range is the view's (a bearing wraps, an
  // elevation is 1–89), which only the session knows.
  const rawKnobs = param(q, "knobs");
  const parsedKnobs = rawKnobs === null ? null : parseKnobs(rawKnobs);
  const ranges = parsedKnobs ? knobRanges(parsedKnobs.knobs) : "";
  const rawCut = param(q, "cut");
  const cut = rawCut !== null && /^-?\d+$/.test(rawCut) ? Number(rawCut) : null;
  const link: DeepLink = {
    design,
    variant,
    analysis: param(q, "analysis"),
    view: param(q, "view"),
    run: q.get("run") === "1",
    ...(family ? { family } : {}),
    ...(rawFamily !== null && family === null
      ? { familyProblem: `family "${rawFamily}" is not knob:from:to:points[:log]` }
      : {}),
    ...(cut !== null ? { cut } : {}),
    ...(rawCut !== null && cut === null ? { cutProblem: `cut "${rawCut}" is not a whole number of degrees` } : {}),
    ...(z === null
      ? {}
      : {
          deck: {
            z,
            name: param(q, "name") ?? "deck.nec",
            ...(isDialect(dialect) ? { dialect } : {}),
            ...(analyses !== null ? { analyses } : {}),
            ...(ranges ? { ranges } : {}),
          },
        }),
    ...(parsedKnobs && parsedKnobs.knobs.length > 0 ? { knobs: parsedKnobs.knobs } : {}),
    ...(parsedKnobs && parsedKnobs.problems.length > 0 ? { knobsProblems: parsedKnobs.problems } : {}),
    ...(z === null && analyses !== null ? { analyses } : {}),
  };
  return link.design ||
    link.variant ||
    link.analysis ||
    link.view ||
    link.run ||
    link.deck ||
    link.family ||
    link.familyProblem ||
    link.cut !== undefined ||
    link.cutProblem ||
    link.knobs ||
    link.knobsProblems ||
    link.analyses
    ? link
    : null;
}

/** What a link resolves to, or why it does not, in words the UI shows. */
export type Resolved<T> = { ok: true; value: T } | { ok: false; problem: string };

const USER_NS = "user.";

/** The design a link names in the catalog: its full name, or a bare design
 *  name that exactly one catalog family holds (as the CLI's `--design moxon`
 *  resolves; a bare name never reaches a user design, so none can shadow a
 *  catalog one). */
export function resolveDesign(name: string, examples: readonly ExampleDescriptor[]): Resolved<string> {
  if (examples.some((e) => e.name === name)) return { ok: true, value: name };
  if (!name.includes(".")) {
    const hits = examples.filter(
      (e) => !e.name.startsWith(USER_NS) && e.name.slice(e.name.lastIndexOf(".") + 1) === name,
    );
    if (hits.length === 1) return { ok: true, value: hits[0].name };
    if (hits.length > 1) {
      return {
        ok: false,
        problem: `design "${name}" is ambiguous: give one of ${hits.map((e) => `"${e.name}"`).join(", ")}`,
      };
    }
  }
  if (name.startsWith(USER_NS)) {
    return {
      ok: false,
      problem: `design "${name}" is not here: a user design opens only on the machine that has it`,
    };
  }
  if (name.startsWith(DECK_NS)) {
    return {
      ok: false,
      problem:
        `design "${name}" is an opened deck this page does not hold: its link was too long ` +
        "to carry the deck, so open the file again",
    };
  }
  return { ok: false, problem: `no design "${name}" in this workbench's catalog` };
}

/** A variant the design has, by its name. */
export function resolveVariant(variant: string, example: ExampleDescriptor): Resolved<string> {
  const have = example.variants ?? [];
  if (have.includes(variant)) return { ok: true, value: variant };
  return {
    ok: false,
    problem:
      `design "${example.name}" has no variant "${variant}"` +
      (have.length > 1 ? `; its variants: ${have.join(", ")}` : ""),
  };
}

/** The analysis a link names among the ones the design's picker lists (POST
 *  /analyses: its own, and the studies that include it, each a study by its
 *  full `source:name`). The order is `studies.find`'s, the rule `analyze
 *  --study` resolves a name by, over this picker's entries: the full name
 *  (an own analysis's name is its full name), then a source that holds one
 *  study, then a study's own short name when one study has it. A rule that
 *  matches more than one entry names them and resolves nothing. */
export function resolveAnalysis(name: string, entries: readonly AnalysisEntry[]): Resolved<AnalysisEntry> {
  const studies = entries.filter((e) => e.study);
  const rules = [
    entries.filter((e) => e.name === name),
    studies.filter((e) => e.study!.source === name),
    studies.filter((e) => e.study!.name === name),
  ];
  for (const hits of rules) {
    if (hits.length === 1) return { ok: true, value: hits[0] };
    if (hits.length > 1) {
      return {
        ok: false,
        problem: `analysis "${name}" is ambiguous: give one of ${hits.map((e) => `"${e.name}"`).join(", ")}`,
      };
    }
  }
  return {
    ok: false,
    problem:
      entries.length === 0
        ? `no analysis "${name}": this design lists none`
        : `no analysis "${name}" on this design; it lists ${entries.map((e) => `"${e.name}"`).join(", ")}`,
  };
}

/** A view the chart can draw what it shows, by its id. */
export function resolveView<V extends string>(view: string, views: readonly V[]): Resolved<V> {
  const hit = views.find((v) => v === view);
  return hit !== undefined
    ? { ok: true, value: hit }
    : { ok: false, problem: `no view "${view}" on this chart; it draws ${views.join(", ")}` };
}

/** What the URL records of a tab: its design and variant (null: the
 *  design's first, which the link then leaves out), and the chart's analysis
 *  and view (the view only beside an analysis). */
export type LinkState = {
  design: string;
  variant: string | null;
  analysis: string | null;
  view: string | null;
  /** The opened deck the design is, when it is one: the link carries it in
   *  place of the design's key, when it fits (`decks.shareable`). */
  deck?: DeckPayload | null;
  /** The pattern family the chart draws (AK#1935): its knob and range,
   *  beside its pattern `view`; no analysis names it. */
  family?: LinkFamily | null;
  /** That family's cut angle (AK#1950), only where it is not the view's
   *  own (`chartLinkCut`); written only beside a `family`. */
  cut?: number | null;
  /** The knob values the link carries (AK#2045): a knob moved off its
   *  default, and every knob the deck has a range for (with it). */
  knobs?: readonly LinkKnob[] | null;
  /** A catalog design's analyses (AK#2045, packed): written beside the
   *  design. A deck's are its payload's (`deck.analyses`). */
  analyses?: string | null;
};

/** `search` with the link's parameters replaced by `state`'s (any other
 *  parameter kept, in its place), as `?…`, or "" when nothing is left. Never
 *  `run`: a link someone copies does not spend the visitor's solves. */
export function linkSearch(search: string, state: LinkState): string {
  const q = new URLSearchParams(search);
  for (const k of LINK_PARAMS) q.delete(k);
  const carried = !!state.deck && shareable(state.deck);
  if (state.deck && carried) {
    // The deck itself: any browser that opens the link rebuilds the design
    // from it. (Too long to carry, the key stands in: this page still opens
    // it, and the session says the link cannot share it.)
    q.set("deck", state.deck.z);
    q.set("name", state.deck.name);
    if (state.deck.dialect) q.set("dialect", state.deck.dialect);
    if (state.deck.analyses) q.set("analyses", state.deck.analyses);
  } else {
    q.set("design", state.variant ? `${state.design}:${state.variant}` : state.design);
    if (state.analyses && !state.deck) q.set("analyses", state.analyses);
  }
  if (state.knobs && state.knobs.length > 0) {
    // A range rides only beside the deck it was opened with: the key alone
    // (the deck too long to carry) already holds it.
    const knobs = carried ? state.knobs : state.knobs.map((k) => ({ name: k.name, value: k.value }));
    q.set("knobs", knobsParam(knobs));
  }
  if (state.analysis) {
    q.set("analysis", state.analysis);
    if (state.view) q.set("view", state.view);
  } else if (state.family) {
    q.set("family", familyParam(state.family));
    if (state.view) q.set("view", state.view);
    if (state.view && state.cut !== null && state.cut !== undefined) q.set("cut", String(state.cut));
  }
  // URLSearchParams writes a space as "+" and escapes a colon, a comma and
  // parentheses; %20 and the bare characters (legal in a query) read the
  // same, and are what a person reading the link expects to see.
  const s = q
    .toString()
    .replace(/\+/g, "%20")
    .replace(/%3A/g, ":")
    .replace(/%2C/g, ",")
    .replace(/%28/g, "(")
    .replace(/%29/g, ")");
  return s ? `?${s}` : "";
}

/** The whole link for `state`, at this page's own origin and path. */
export function linkHref(loc: Pick<Location, "origin" | "pathname" | "search" | "hash">, state: LinkState): string {
  return `${loc.origin}${loc.pathname}${linkSearch(loc.search, state)}${loc.hash}`;
}
