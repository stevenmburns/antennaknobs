// Workbench deep links (AK#1838): a URL that opens a design and selects one
// of its analyses in the chart's picker.
//
//   ?design=<family.design>[:<variant>]   the design, and optionally its variant
//   &analysis=<name>                      the chart's analysis (own or a study)
//   &view=<view id>                       the chart's view (Rx, Knobs, Smith, …)
//   &run=1                                press Run once it is selected
//   ?deck=<z>&name=<file name>            an opened deck (lib/decks.ts): the
//                                         file's text, compressed, in place
//                                         of `design`
//   &dialect=nec2|nec4|nec5               the dialect the deck is read in,
//                                         when chosen (absent: detected)
//
// React-free, so the grammar and the resolution are tested alone. The
// session (DesignSession) applies a parsed link in stages and reports what it
// could not resolve by name; nothing here touches the page.

import type { AnalysisEntry } from "./analyses";
import { DECK_NS, isDialect, shareable, type DeckPayload } from "./decks";
import type { ExampleDescriptor } from "./params";

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
  /** What went wrong opening the link's deck, for the link notice. */
  problem?: string | null;
};

/** The query parameters a link owns; any other is left as it is. */
export const LINK_PARAMS = ["design", "analysis", "view", "run", "deck", "name", "dialect"] as const;

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
  const link: DeepLink = {
    design,
    variant,
    analysis: param(q, "analysis"),
    view: param(q, "view"),
    run: q.get("run") === "1",
    ...(z === null
      ? {}
      : {
          deck: {
            z,
            name: param(q, "name") ?? "deck.nec",
            ...(isDialect(dialect) ? { dialect } : {}),
          },
        }),
  };
  return link.design || link.variant || link.analysis || link.view || link.run || link.deck
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
};

/** `search` with the link's parameters replaced by `state`'s (any other
 *  parameter kept, in its place), as `?…`, or "" when nothing is left. Never
 *  `run`: a link someone copies does not spend the visitor's solves. */
export function linkSearch(search: string, state: LinkState): string {
  const q = new URLSearchParams(search);
  for (const k of LINK_PARAMS) q.delete(k);
  if (state.deck && shareable(state.deck)) {
    // The deck itself: any browser that opens the link rebuilds the design
    // from it. (Too long to carry, the key stands in: this page still opens
    // it, and the session says the link cannot share it.)
    q.set("deck", state.deck.z);
    q.set("name", state.deck.name);
    if (state.deck.dialect) q.set("dialect", state.deck.dialect);
  } else {
    q.set("design", state.variant ? `${state.design}:${state.variant}` : state.design);
  }
  if (state.analysis) {
    q.set("analysis", state.analysis);
    if (state.view) q.set("view", state.view);
  }
  // URLSearchParams writes a space as "+" and escapes a colon and
  // parentheses; %20 and the bare characters (legal in a query) read the
  // same, and are what a person reading the link expects to see.
  const s = q
    .toString()
    .replace(/\+/g, "%20")
    .replace(/%3A/g, ":")
    .replace(/%28/g, "(")
    .replace(/%29/g, ")");
  return s ? `?${s}` : "";
}

/** The whole link for `state`, at this page's own origin and path. */
export function linkHref(loc: Pick<Location, "origin" | "pathname" | "search" | "hash">, state: LinkState): string {
  return `${loc.origin}${loc.pathname}${linkSearch(loc.search, state)}${loc.hash}`;
}
