// Keeping what you built (AK#1757, sweep-framework step 7, unit 4): "copy as
// analysis" and "keep as study", from an analysis chart, from the pinned
// sweeps and from the pinned patterns. React-free, so the rules are tested
// alone.
//
// The page never writes Python itself. It sends DATA to POST /keep (the
// clipboard text) or POST /studies/save (a file in the studies folder, a
// local workbench only), and the server builds a spec value from it and
// prints that (antennaknobs.keep):
//  - a chart sends the analysis /analyses served (`spec`, as data), the
//    tab's own request (`tab`: a study names the tab's design and its knobs),
//    the requests its curves were solved with (`cells`: the engines and
//    grounds it drew), and its x values when the viewer edited the range;
//  - a pin sends the request its curve was solved with (`req`), which is the
//    whole of what it says: its design, variant, knobs, engine, ground and
//    plane are read off it server-side, so the page and the server cannot
//    disagree about what a pin was. A sweep pin adds what it sweeps and the
//    x values it was solved at.

import type { SolveRequest } from "./api";

export type KeepOrigin = "chart" | "sweep pins" | "pattern pins";
export type KeepForm = "analysis" | "study";

/** A solve request as a keep sends it: plain data, without the fields that
 *  are the session's plumbing rather than the solve (its lane, stream and
 *  generation, the poor-match approval, the tracker's drag) or display-only
 *  (the cut dials stay: a pattern pin's views are drawn at them). */
export type KeepRequest = Record<string, unknown>;

const PLUMBING = new Set(["_session", "_stream", "_gen", "_approved", "_track", "z0_ohms"]);

export function keepRequest(req: SolveRequest | KeepRequest): KeepRequest {
  const out: KeepRequest = {};
  for (const [k, v] of Object.entries(req)) if (!PLUMBING.has(k) && v !== undefined) out[k] = v;
  return out;
}

/** What a sweep pin keeps: its request, what it sweeps and at which x. */
export type SweepPinKeep = {
  req: KeepRequest;
  x: { kind: "frequency" | "knob" | "density"; name: string };
  xs: number[];
  label: string;
};

/** What a pattern pin keeps: its request (the cut dials ride in it). */
export type PatternPinKeep = { req: KeepRequest; label: string };

/** The body of a keep request (POST /keep, and /studies/save with a path). */
export type KeepBody =
  | {
      origin: "chart";
      form: KeepForm;
      name?: string;
      spec: unknown;
      tab: KeepRequest;
      cells?: KeepRequest[];
      values?: number[];
    }
  | { origin: "sweep pins"; form: "study"; name?: string; pins: SweepPinKeep[] }
  | { origin: "pattern pins"; form: "study"; name?: string; pins: PatternPinKeep[] };

/** Why a set of sweep pins cannot be kept as one study, or null: a study
 *  sweeps one thing, so every pin must sweep the same x (kind and, for a
 *  knob, name), and it is one curve per pin under the chart's cap. */
export function sweepPinsBlocked(
  pins: readonly Pick<SweepPinKeep, "x">[],
  cap: number,
): string | null {
  if (pins.length === 0) return "No pins to keep: pin a chart's curves first";
  const xs = new Set(pins.map((p) => (p.x.kind === "knob" ? `knob:${p.x.name}` : p.x.kind)));
  if (xs.size > 1) return "The shown pins sweep different things: a study sweeps one; hide the others";
  if (pins.length > cap) return `${pins.length} pins is over the cap of ${cap} curves: hide some`;
  return null;
}

/** The shown pinned patterns as a keep (AK#1757 step 7 unit 4): each the
 *  request its pattern was solved with, and why they cannot be kept (none
 *  shown, one pinned before pins kept their request, over the cap), or null. */
export function patternPinsKeep(
  pins: readonly { enabled: boolean; label: string; req?: KeepRequest }[],
  cap: number,
): { pins: PatternPinKeep[]; blocked: string | null } {
  const shown = pins.filter((p) => p.enabled);
  const kept = shown.flatMap((p) => (p.req ? [{ req: p.req, label: p.label }] : []));
  const blocked =
    shown.length === 0
      ? "No shown pin to keep: show one"
      : kept.length < shown.length
        ? "A shown pin has no solve request to keep: pin it again"
        : shown.length > cap
          ? `${shown.length} pins is over the cap of ${cap} patterns: hide some`
          : null;
  return { pins: kept, blocked };
}

/** What POST /keep answers: the text, the analysis's name, its problems on
 *  the tab's design, and why it could not be kept as a study (or null). */
export type KeepText = {
  code: string;
  name: string;
  problems: string[];
  studyRefusal: string | null;
};

// The server's refusal in its own words, else the status.
async function detail(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return body.detail;
  } catch {
    /* no JSON body */
  }
  return `the server answered ${resp.status}`;
}

/** POST /keep: the text a keep puts on the clipboard, or an Error naming
 *  why it cannot be kept. */
export async function fetchKeep(body: KeepBody, signal?: AbortSignal): Promise<KeepText> {
  const resp = await fetch("/keep", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    ...(signal ? { signal } : {}),
  });
  if (!resp.ok) throw new Error(await detail(resp));
  const o = (await resp.json()) as Record<string, unknown>;
  return {
    code: typeof o.code === "string" ? o.code : "",
    name: typeof o.name === "string" ? o.name : "",
    problems: Array.isArray(o.problems) ? o.problems.filter((p): p is string => typeof p === "string") : [],
    studyRefusal: typeof o.study_refusal === "string" ? o.study_refusal : null,
  };
}

/** What a save wrote: the file, its study source and the study's full name
 *  (as the picker's Studies group and `analyze --study` take it). */
export type SavedStudy = { path: string; source: string; name: string };

/** A save refused because the file is there already (409): the dialog
 *  offers to replace it. */
export class StudyExistsError extends Error {}

/** POST /studies/save: write the study file at `path` under the studies
 *  folder (subfolders are name parts), trusted with edits allowed. */
export async function saveStudy(
  body: KeepBody,
  path: string,
  overwrite: boolean,
): Promise<SavedStudy> {
  const resp = await fetch("/studies/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, form: "study", path, overwrite }),
  });
  if (resp.status === 409) throw new StudyExistsError(await detail(resp));
  if (!resp.ok) throw new Error(await detail(resp));
  const o = (await resp.json()) as Record<string, unknown>;
  return {
    path: typeof o.path === "string" ? o.path : "",
    source: typeof o.source === "string" ? o.source : "",
    name: typeof o.name === "string" ? o.name : "",
  };
}

/** A study file's suggested path under the studies folder: the name as one
 *  plain part (letters, digits, `_` and `-`), which the server's own rule
 *  accepts; the viewer may add folders ("feeds/e7"). */
export function suggestedPath(name: string): string {
  const part = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, 64);
  return part || "study";
}
