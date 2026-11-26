// The station rail's chain, as the page holds it and posts it back
// (docs/design/block-builder.md, "The station rail"; the server's model is
// src/antennaknobs/station_rail.py, which is the authority on what a chain
// may hold). The page keeps rails as JSON-shaped data, A and optionally B,
// and the server renders, solves and checks them.
//
// What is checked here is the SHAPE a chain must have before it is posted:
// a version, a rig name, a list of items each with a kind and plain values.
// Whether a cable exists or a tuner's values make sense is the server's
// call, so the two sides cannot drift on the component table.

import type { SolveRequest } from "./api";
import { apiFetch } from "./pin";

export const CHAIN_VERSION = 1;

/** One component record: its kind, its values (numbers or text), and the
 *  names it resolved to (`name` its instance, `node` the node on its rig
 *  side), which the server writes so an edit renames nothing else. */
export type StationItem = {
  kind: string;
  name?: string;
  node?: string;
  [value: string]: string | number | undefined;
};

export type StationChain = {
  version: number;
  rig: string;
  items: StationItem[];
};

export class StationChainError extends Error {}

const IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;

function checkItem(raw: unknown, where: string): StationItem {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new StationChainError(`${where}: a component is an object`);
  }
  const rec = raw as Record<string, unknown>;
  if (typeof rec.kind !== "string" || !rec.kind) {
    throw new StationChainError(`${where}: a component names its kind`);
  }
  const out: StationItem = { kind: rec.kind };
  for (const key of Object.keys(rec).sort()) {
    if (key === "kind") continue;
    const v = rec[key];
    if (v === null || v === undefined) continue;
    if (key === "name" || key === "node") {
      if (typeof v !== "string" || !IDENT.test(v)) {
        throw new StationChainError(`${where}: ${key} ${JSON.stringify(v)} is not an identifier`);
      }
      out[key] = v;
    } else if (typeof v === "number") {
      if (!Number.isFinite(v)) throw new StationChainError(`${where}: ${key} must be finite`);
      out[key] = v;
    } else if (typeof v === "string") {
      out[key] = v;
    } else {
      throw new StationChainError(`${where}: ${key} must be a number or text`);
    }
  }
  return out;
}

/** A chain from parsed JSON, shape-checked; StationChainError says why not. */
export function chainFromData(data: unknown): StationChain {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new StationChainError("a chain is an object");
  }
  const rec = data as Record<string, unknown>;
  for (const key of Object.keys(rec)) {
    if (!["version", "rig", "items"].includes(key)) {
      throw new StationChainError(`a chain has no field ${JSON.stringify(key)}`);
    }
  }
  const version = rec.version ?? CHAIN_VERSION;
  if (version !== CHAIN_VERSION) {
    throw new StationChainError(`chain version ${String(version)}; this rail reads ${CHAIN_VERSION}`);
  }
  const rig = rec.rig ?? "rig";
  if (typeof rig !== "string" || !IDENT.test(rig)) {
    throw new StationChainError(`rig ${JSON.stringify(rig)} is not an identifier`);
  }
  const items = rec.items ?? [];
  if (!Array.isArray(items)) throw new StationChainError("a chain's items are a list");
  return { version: CHAIN_VERSION, rig, items: items.map((it, i) => checkItem(it, `item ${i}`)) };
}

/** A chain from its JSON text. */
export function chainFromJson(text: string): StationChain {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (e) {
    throw new StationChainError(`not JSON: ${(e as Error).message}`);
  }
  return chainFromData(data);
}

/** A chain as JSON text: fields in a fixed order (version, rig, items; each
 *  item's kind first, then its other keys sorted), so one chain always
 *  writes the same text and two texts compare as two chains do. */
export function chainToJson(chain: StationChain): string {
  const c = chainFromData(chain);
  return JSON.stringify({
    version: c.version,
    rig: c.rig,
    items: c.items.map((it) => {
      const rec: Record<string, string | number> = { kind: it.kind };
      for (const key of Object.keys(it).sort()) {
        const v = it[key];
        if (key !== "kind" && v !== undefined) rec[key] = v;
      }
      return rec;
    }),
  });
}

export function sameChain(a: StationChain | null, b: StationChain | null): boolean {
  if (a === null || b === null) return a === b;
  return chainToJson(a) === chainToJson(b);
}

/** The chain with item `i` removed. */
export function withoutItem(chain: StationChain, i: number): StationChain {
  return { ...chain, items: chain.items.filter((_it, k) => k !== i) };
}

// --- the server's answers ----------------------------------------------------------

export type ZRow = { z_re: number | null; z_im: number | null; swr: number | null };
export type Probe = ZRow & { node: string | null; at: string };
export type Chip = {
  label: string;
  kind: string;
  series: boolean;
  a: string;
  b: string | null;
  name: string | null;
};
export type RailResult = ZRow & {
  chain: StationChain;
  python: string;
  changed: number[];
  chips: Chip[];
  nodes: string[];
  advisories: string[];
  loss_db: number | null;
  p_ant_w: number;
  probes: Probe[];
  budget: { label: string; watts: number }[];
  tuner: { label: string; value: string; unit: string | null }[];
  tuner_advisories: string[];
  svg?: string | null;
  svg_reason?: string | null;
};
export type StationAntenna = {
  design: string;
  module: string;
  feed: string;
  form: "wire" | "port" | "cut";
  balanced: boolean | null;
  replaced: number;
  freq_mhz: number;
  z_ref: number;
  origin?: "design" | "default";
  notice?: string;
};
export type RenderResponse = {
  antenna: StationAntenna;
  starting_chain: StationChain;
  rails: RailResult[];
  antenna_solves: number;
  ms: number;
};
export type GalleryCard = ZRow & {
  pos: number;
  where: string;
  chain: StationChain;
  advisories: string[];
  loss_db: number | null;
  p_ant_w: number;
  svg: string | null;
  current: boolean;
  diff: string[];
};
export type GalleryResponse = {
  component: string;
  refusal: string | null;
  cards: GalleryCard[];
  antenna_solves: number;
};
export type PaletteResponse = {
  palette: Record<string, { label: string; kind: string }>;
  cables: string[];
};
export type ReadResponse =
  | { chain: StationChain; antenna: { module: string; form: string; feed: string } }
  | { refusal: string };

/** A refusal or failure from the rail's endpoints, with the server's reason. */
export class StationRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const init: RequestInit = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  if (signal) init.signal = signal;
  const r = await apiFetch(path, init);
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const j = (await r.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      // not JSON: keep the status line
    }
    throw new StationRequestError(detail, r.status);
  }
  return (await r.json()) as T;
}

export function renderRails(
  request: SolveRequest,
  rails: (StationChain | null)[],
  prevPython: (string | null)[],
  signal?: AbortSignal,
): Promise<RenderResponse> {
  return post("/station/render", { request, rails, prev_python: prevPython }, signal);
}

export function galleryFor(
  request: SolveRequest,
  chain: StationChain,
  what: { add: string } | { move: number },
  signal?: AbortSignal,
): Promise<GalleryResponse> {
  return post("/station/gallery", { request, chain, ...what }, signal);
}

export function readFile(request: SolveRequest, text: string): Promise<ReadResponse> {
  return post("/station/read", { request, text });
}

export async function fetchPalette(): Promise<PaletteResponse> {
  const r = await apiFetch("/station/palette");
  if (!r.ok) throw new StationRequestError(`${r.status} ${r.statusText}`, r.status);
  return (await r.json()) as PaletteResponse;
}

// --- formatting ----------------------------------------------------------------

export function fmtZ(row: ZRow): string {
  if (row.z_re === null || row.z_im === null) return "—";
  const sign = row.z_im < 0 ? "−" : "+";
  return `${row.z_re.toFixed(1)} ${sign} j${Math.abs(row.z_im).toFixed(1)} Ω`;
}

export function fmtSwr(swr: number | null): string {
  if (swr === null) return "∞";
  return swr >= 100 ? "> 99" : swr.toFixed(2);
}
