import { useEffect, useState } from "react";
import type { PatternCuts, SolveResponse } from "../../lib/api";
import { cutDbiTop, refineCutAngles } from "../../lib/refine";
import { tunedInt } from "../../lib/tuning";
import type { FarFieldCut } from "./types";

// --- Server-side polar cuts (issue #547) -----------------------------------
// The per-direction cut physics lives in server.py (_pattern_cuts); every
// solve response arrives with `cuts` attached at the request's angles, and
// new angles come from the stateless POST /cuts endpoint. The pieces below
// cache those fetches so the azimuth + elevation charts (and thumbnails)
// sharing a solve don't duplicate round trips.

// Identity for solve-response objects (immutable snapshots), used to key the
// cuts cache. WeakMap so ids die with their solves.
let cutsIdSeq = 0;
const cutsIds = new WeakMap<SolveResponse, number>();
// Resolved /cuts responses by `${solveId}:${azElev}:${elevAz}`. Insertion-
// ordered and capped — a long session of slider drags would otherwise grow
// it without bound.
const cutsCache = new Map<string, PatternCuts>();
const CUTS_CACHE_MAX = 256;
// In-flight fetch dedup — both chart instances ask for the same key at once.
const cutsInFlight = new Map<string, Promise<PatternCuts | null>>();
// Freshest trace known per solve, at whatever angles — drawn while the fetch
// for the current angles is in flight so drags never blank the chart.
const cutsLatest = new WeakMap<SolveResponse, PatternCuts>();

function cutsKey(
  result: SolveResponse,
  azElevDeg: number,
  elevAzDeg: number,
): string {
  let id = cutsIds.get(result);
  if (id === undefined) {
    id = ++cutsIdSeq;
    cutsIds.set(result, id);
  }
  return `${id}:${azElevDeg}:${elevAzDeg}`;
}

// The cuts for a solve at exactly these angles, or null if not yet known.
// The cache is consulted BEFORE the solve's attached cuts: a refinement pass
// (issue #744) writes its densified trace back under the same key, and it is
// the same cut at the same angles — only sampled better — so it must win
// over the uniform copy the solve arrived with.
function cachedCuts(
  result: SolveResponse,
  azElevDeg: number,
  elevAzDeg: number,
): PatternCuts | null {
  const cached = cutsCache.get(cutsKey(result, azElevDeg, elevAzDeg));
  if (cached) return cached;
  const attached = result.cuts;
  if (
    attached &&
    attached.az_elev_deg === azElevDeg &&
    attached.elev_az_deg === elevAzDeg
  ) {
    return attached;
  }
  return null;
}

// Cuts over the live /ws socket (issue #551): when the socket is open it
// doubles as the cuts transport — a ~100-byte {_kind:"cuts", solve_id}
// message replaces the full-body POST (warm ws measured ~2× cheaper than
// HTTP through a tunnel, and the server answers from its cuts-source
// cache). The socket effect registers a sender here on open and clears it
// on close; fetchCuts falls back to HTTP when it's absent or doesn't
// answer.
export let cutsWsSend: ((msg: string) => boolean) | null = null;
// Setter for App.tsx's websocket effect: ESM live bindings let an importer
// READ an exported `let` but not assign to it (issue #642 seam 3 move).
export function setCutsWsSend(send: ((msg: string) => boolean) | null): void {
  cutsWsSend = send;
}
// Outcome of a ws cuts round trip. "miss" (server says unknown id) skips
// the pointless HTTP id retry — the same cache would 404 — and goes
// straight to the full-body backstop; "unavailable" (no socket, timeout,
// socket died) still tries the tiny HTTP id request first.
type CutsWsReply =
  | { status: "ok"; cuts: PatternCuts }
  | { status: "miss" }
  | { status: "unavailable" };
const cutsWsPending = new Map<string, (reply: CutsWsReply) => void>();
// Generous vs the ~100 ms worst-case big-mesh cut compute: a timeout only
// fires when the socket is wedged, and the HTTP fallback then still
// delivers — slower, never wrong.
const CUTS_WS_TIMEOUT_MS = 1500;

/** Explicit per-cut sampling angles for a refinement request (issue #744).
 *  Absent on a plain dial request, which keeps the uniform circle. */
type CutAngles = { az_angles_deg?: number[]; elev_angles_deg?: number[] };

const isRefined = (extra: CutAngles | undefined): boolean =>
  !!(extra?.az_angles_deg || extra?.elev_angles_deg);

// The refined flag is part of the pending key (and echoed by the server):
// a refinement and a dial request can be in flight for the same solve at
// the same angles, and answering one with the other's trace would either
// throw the densified samples away or hand them to a caller expecting the
// uniform circle.
function cutsWsPendingKey(
  solveId: string,
  az: number,
  el: number,
  refined: boolean,
): string {
  return `${solveId}:${az}:${el}:${refined ? 1 : 0}`;
}

function requestCutsViaWs(
  solveId: string,
  azElevDeg: number,
  elevAzDeg: number,
  extra?: CutAngles,
): Promise<CutsWsReply> {
  const send = cutsWsSend;
  if (!send) return Promise.resolve({ status: "unavailable" });
  const key = cutsWsPendingKey(solveId, azElevDeg, elevAzDeg, isRefined(extra));
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      cutsWsPending.delete(key);
      resolve({ status: "unavailable" });
    }, CUTS_WS_TIMEOUT_MS);
    cutsWsPending.set(key, (reply) => {
      window.clearTimeout(timer);
      cutsWsPending.delete(key);
      resolve(reply);
    });
    if (
      !send(
        JSON.stringify({
          _kind: "cuts",
          solve_id: solveId,
          az_elev_deg: azElevDeg,
          elev_az_deg: elevAzDeg,
          ...(extra ?? {}),
        }),
      )
    ) {
      window.clearTimeout(timer);
      cutsWsPending.delete(key);
      resolve({ status: "unavailable" });
    }
  });
}

/** Server cuts message arriving on the /ws socket — routed here by the
 *  socket effect's onmessage before any solve handling. */
export type CutsWsMessage = {
  _kind: "cuts";
  solve_id: string;
  az_elev_deg: number;
  elev_az_deg: number;
  /** Server echo of "this reply carries an explicitly-sampled cut" (issue
   *  #744). Absent from a pre-#744 server, which only ever sent uniform
   *  cuts — so undefined reads as false, the right answer for it. */
  refined?: boolean;
  ok: boolean;
  cuts?: PatternCuts;
};

export function resolveCutsWsMessage(data: CutsWsMessage): void {
  const key = cutsWsPendingKey(
    data.solve_id,
    data.az_elev_deg,
    data.elev_az_deg,
    !!data.refined,
  );
  const pending = cutsWsPending.get(key);
  if (!pending) return; // timed out / superseded — fallback already running
  pending(data.ok && data.cuts ? { status: "ok", cuts: data.cuts } : { status: "miss" });
}

/** Socket died: nothing pending will ever be answered on it. Resolving as
 *  "unavailable" sends every waiter down the HTTP path immediately instead
 *  of eating the full timeout. (A rare pending riding a *newer* socket gets
 *  flushed too — it just falls back to HTTP: slower, never wrong.) */
export function flushCutsWsPending(): void {
  for (const pending of Array.from(cutsWsPending.values())) {
    pending({ status: "unavailable" });
  }
}

function cacheCuts(key: string, cuts: PatternCuts): void {
  if (cutsCache.size >= CUTS_CACHE_MAX) {
    // Evict the oldest half (Maps iterate in insertion order).
    let drop = CUTS_CACHE_MAX >> 1;
    for (const k of Array.from(cutsCache.keys())) {
      if (drop-- <= 0) break;
      cutsCache.delete(k);
    }
  }
  cutsCache.set(key, cuts);
}

/** One cuts round trip down the transport ladder (issue #551): ws id →
 *  HTTP id → HTTP full body. Every rung is strictly a fallback of the one
 *  above; the full-body POST remains the correctness backstop (it's how
 *  pre-#551 responses and pins from dead server sessions resolve).
 *  `extra` carries a refinement's explicit angles (issue #744) — it rides
 *  every rung, so a refined cut resolves even for a pin whose server
 *  session is long gone. */
function requestCuts(
  result: SolveResponse,
  azElevDeg: number,
  elevAzDeg: number,
  extra?: CutAngles,
): Promise<PatternCuts | null> {
  const postCuts = (body: object): Promise<Response> =>
    fetch("/cuts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...body,
        az_elev_deg: azElevDeg,
        elev_az_deg: elevAzDeg,
        ...(extra ?? {}),
      }),
    });
  return (async (): Promise<PatternCuts | null> => {
    const solveId = result.solve_id;
    if (solveId) {
      const viaWs = await requestCutsViaWs(solveId, azElevDeg, elevAzDeg, extra);
      if (viaWs.status === "ok") return viaWs.cuts;
      if (viaWs.status === "unavailable") {
        const r = await postCuts({ solve_id: solveId });
        if (r.ok) return (await r.json()) as PatternCuts;
        if (r.status !== 404) return null; // 400: cuts genuinely unsupported
      }
      // ws said "miss" (or HTTP id 404'd): the server lost this solve —
      // only the full body can answer now.
    }
    const r = await postCuts({ solve: result });
    return r.ok ? ((await r.json()) as PatternCuts) : null;
  })().catch(() => null);
}

function fetchCuts(
  result: SolveResponse,
  azElevDeg: number,
  elevAzDeg: number,
): Promise<PatternCuts | null> {
  const key = cutsKey(result, azElevDeg, elevAzDeg);
  const inFlight = cutsInFlight.get(key);
  if (inFlight) return inFlight;
  const p = requestCuts(result, azElevDeg, elevAzDeg)
    .then((cuts) => {
      if (cuts) cacheCuts(key, cuts);
      return cuts;
    })
    .finally(() => cutsInFlight.delete(key));
  cutsInFlight.set(key, p);
  return p;
}

// --- Adaptive cut refinement (issue #744) ----------------------------------
// Extra sample angles where the POLAR trace corners, once the cut dials have
// settled. Deliberately NOT on the solve lane, unlike sweep refinement: the
// cuts-source cache (issue #551) holds the moment set, so extra angles are
// the EXISTING solve's pattern re-evaluated at more directions — no solve to
// serialize, and the same no-lane latest-wins channel a dial drag uses.

// Master switch, set by DesignSession from the same "adaptive resolution"
// setting the sweep side reads as a prop. A module flag rather than plumbing
// through FarFieldChart's props because everything else about refinement
// already lives at this module's scope (caches, in-flight maps).
let cutRefineEnabled = true;
export function setCutRefineEnabled(v: boolean): void {
  cutRefineEnabled = v;
}

// Which cut charts are on screen right now. A chart's useCutTraces registers
// its own cut while mounted; refinement consults this PER ROUND so it only
// buys angles for a cut somebody can see — the polar charts are one view
// each, and "show only the azimuth cut" used to densify the elevation cut
// anyway. Ref-counted so a transient double-mount (layout switches) can't
// unregister a cut the other instance still shows.
const mountedCutCharts = new Map<FarFieldCut, number>();
function registerCutChart(cut: FarFieldCut): () => void {
  mountedCutCharts.set(cut, (mountedCutCharts.get(cut) ?? 0) + 1);
  return () => {
    const n = (mountedCutCharts.get(cut) ?? 1) - 1;
    if (n <= 0) mountedCutCharts.delete(cut);
    else mountedCutCharts.set(cut, n);
  };
}
const wantedCuts = () => ({
  az: mountedCutCharts.has("xy"),
  elev: mountedCutCharts.has("yz"),
});

/** Total extra angles per cut, summed across rounds. 180 uniform + 120
 *  refined stays well under the server's 720-angle ceiling, and a far-field
 *  evaluation at 300 directions is still ~1 ms on a typical mesh. */
// Overridable without a rebuild (lib/tuning.ts); capped under the server's
// 720-angle request ceiling with the 180-point base already inside it.
export const CUT_REFINE_BUDGET = tunedInt(
  "antennaknobs.cutRefineBudget",
  120,
  500,
);
export const CUT_REFINE_ROUND_BUDGET = 40;
/** Dwell after the cuts for the current dial angles resolve. A dial drag
 *  must not spend evaluations on angles the user is about to leave. */
const CUT_REFINE_DWELL_MS = 400;

// Both polar charts share one solve, so both would otherwise start the same
// refinement chain. Keyed like cutsInFlight.
const cutsRefineInFlight = new Map<string, Promise<void>>();
// Keys whose refinement has run to completion (or its budget), so a
// re-render never restarts it. Bounded like cutsCache: a long session of
// dial drags mints a key per angle pair per solve, and a key whose cached
// trace has already been evicted is worth nothing anyway.
const cutsRefineDone = new Set<string>();
function markRefineDone(key: string): void {
  if (cutsRefineDone.size >= CUTS_CACHE_MAX) {
    let drop = CUTS_CACHE_MAX >> 1;
    for (const k of Array.from(cutsRefineDone)) {
      if (drop-- <= 0) break;
      cutsRefineDone.delete(k);
    }
  }
  cutsRefineDone.add(key);
}

function peakOf(dbi: readonly number[]): number {
  let peak = -Infinity;
  for (const d of dbi) if (d > peak) peak = d;
  return peak;
}

const mergeAngles = (
  held: readonly number[] | undefined,
  n: number,
  added: readonly number[],
): number[] =>
  [
    ...(held ?? Array.from({ length: n }, (_, i) => (360 * i) / n)),
    ...added,
  ].sort((a, b) => a - b);

/** Densify the ON-SCREEN cuts of one solve where the polar trace corners,
 *  in rounds, writing each round back under the plain cuts key so the
 *  charts pick it up. Which cuts to buy angles for comes from the mounted-
 *  chart registry, re-read per round — a cut whose chart nobody shows gets
 *  no angles (and gets its own pass later if its chart mounts, because the
 *  done-marker records WHAT was refined, not just that something was). Any
 *  failure just stops — the uniform trace stays on screen. */
function refineCuts(
  result: SolveResponse,
  azElevDeg: number,
  elevAzDeg: number,
): Promise<void> {
  const key = cutsKey(result, azElevDeg, elevAzDeg);
  const running = cutsRefineInFlight.get(key);
  if (running) return running;
  const wantKey = (w: { az: boolean; elev: boolean }) =>
    `${key}|${w.az ? "az" : ""}${w.elev ? "el" : ""}`;
  if (cutsRefineDone.has(wantKey(wantedCuts()))) return Promise.resolve();
  const p = (async () => {
    let cur = cachedCuts(result, azElevDeg, elevAzDeg);
    let spent = 0;
    let want = wantedCuts();
    while (cur && spent < CUT_REFINE_BUDGET && cutRefineEnabled) {
      want = wantedCuts();
      const budget = Math.min(
        CUT_REFINE_ROUND_BUDGET,
        CUT_REFINE_BUDGET - spent,
      );
      const azAdd = want.az
        ? refineCutAngles(
            cur.azimuth,
            cur.az_angles_deg,
            cutDbiTop([peakOf(cur.azimuth)]),
            budget,
          )
        : [];
      const elAdd = want.elev
        ? refineCutAngles(
            cur.elevation,
            cur.elev_angles_deg,
            cutDbiTop([peakOf(cur.elevation)]),
            budget,
          )
        : [];
      if (azAdd.length === 0 && elAdd.length === 0) break;
      spent += Math.max(azAdd.length, elAdd.length);
      // A cut getting no new angles keeps what it already has: its held
      // refined list travels unchanged, and a still-uniform cut is OMITTED
      // from the request entirely — "absent means uniform" is the wire
      // contract, and forcing an explicit list would make the response
      // (and every cached copy of it) carry 180 angles for nothing.
      const extra: CutAngles = {};
      if (azAdd.length > 0 || cur.az_angles_deg) {
        extra.az_angles_deg = mergeAngles(
          cur.az_angles_deg,
          cur.azimuth.length,
          azAdd,
        );
      }
      if (elAdd.length > 0 || cur.elev_angles_deg) {
        extra.elev_angles_deg = mergeAngles(
          cur.elev_angles_deg,
          cur.elevation.length,
          elAdd,
        );
      }
      const next = await requestCuts(result, azElevDeg, elevAzDeg, extra);
      if (!next) break;
      cacheCuts(key, next);
      cur = next;
    }
    markRefineDone(wantKey(want));
  })().finally(() => cutsRefineInFlight.delete(key));
  cutsRefineInFlight.set(key, p);
  return p;
}

// Resolve the cut traces for a list of solves (live + pinned ghosts) at the
// current angles. Synchronous when a solve already carries or has cached the
// right angles; otherwise the freshest known trace is returned immediately
// (stale-while-refetch) and a debounced POST /cuts brings the real one — the
// debounce eats the flood of intermediate angles a slider drag produces.
//
// `cut` is which polar chart this hook instance serves; while mounted it
// registers that cut so refinement (below) buys angles only for cuts that
// are actually on screen.
export function useCutTraces(
  cut: FarFieldCut,
  results: readonly (SolveResponse | null)[],
  azElevDeg: number,
  elevAzDeg: number,
): (PatternCuts | null)[] {
  const [, setFetchTick] = useState(0); // re-render when a fetch lands
  useEffect(() => registerCutChart(cut), [cut]);
  const wantKey = results
    .map((r) => (r ? cutsKey(r, azElevDeg, elevAzDeg) : "-"))
    .join("|");
  useEffect(() => {
    const missing = results.filter(
      (r): r is SolveResponse => !!r && !cachedCuts(r, azElevDeg, elevAzDeg),
    );
    const live = results[0] ?? null;
    let cancelled = false;
    let refineTimer: number | null = null;
    // Adaptive refinement (issue #744) of the LIVE trace only. Pinned
    // ghosts are dashed comparison references, and refining each of them
    // would multiply the far-field evaluations by the pin count for a line
    // nobody reads geometry off. The dwell is what makes this
    // scrub-safe: a cut-dial drag re-fires this effect, the cleanup below
    // clears the pending timer, and no refinement request is ever issued
    // for an angle the user passed through.
    const scheduleRefine = () => {
      if (!live || !cutRefineEnabled) return;
      refineTimer = window.setTimeout(() => {
        refineCuts(live, azElevDeg, elevAzDeg).then(() => {
          if (!cancelled) setFetchTick((t) => t + 1);
        });
      }, CUT_REFINE_DWELL_MS);
    };
    if (missing.length === 0) {
      // Already drawable at these angles (the solve shipped with them, or a
      // previous fetch cached them) — straight to the refinement dwell.
      scheduleRefine();
      return () => {
        cancelled = true;
        if (refineTimer) window.clearTimeout(refineTimer);
      };
    }
    // When every missing trace can go over the ws id path (~100 bytes, and
    // the server squashes per-solve latest-wins), a much tighter debounce
    // makes cut drags feel live; the original 120 ms guard stays for the
    // full-body HTTP fallback, whose requests are 10 KB–300 KB (issue #551).
    const delay =
      cutsWsSend && missing.every((r) => r.solve_id) ? 30 : 120;
    const h = window.setTimeout(() => {
      Promise.all(missing.map((r) => fetchCuts(r, azElevDeg, elevAzDeg))).then(
        () => {
          if (cancelled) return;
          setFetchTick((t) => t + 1);
          scheduleRefine();
        },
      );
    }, delay);
    return () => {
      cancelled = true;
      window.clearTimeout(h);
      if (refineTimer) window.clearTimeout(refineTimer);
    };
    // results/azElevDeg/elevAzDeg are read but not listed: wantKey is their
    // exact string encoding (see its definition above), the same stable-
    // signature idiom used elsewhere in this codebase (e.g. currentValuesKey)
    // — listing the raw inputs too would just re-fire on every render, since
    // `results` is a fresh array from the caller each time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantKey]);
  return results.map((r) => {
    if (!r) return null;
    const exact = cachedCuts(r, azElevDeg, elevAzDeg);
    if (exact) {
      cutsLatest.set(r, exact);
      return exact;
    }
    return cutsLatest.get(r) ?? r.cuts ?? null;
  });
}

// One chart's trace from a cuts payload: the dBi samples for the requested
// cut, their explicit angles when the cut was refined (issue #744), and
// their peak (for the adaptive radial scale and the annotation). Null when
// there's nothing to draw (no cuts, or everything at the floor).
export function traceFor(
  cuts: PatternCuts | null,
  cut: FarFieldCut,
): { dbi: number[]; anglesDeg?: number[]; peakDbi: number } | null {
  if (!cuts) return null;
  const dbi = cut === "xy" ? cuts.azimuth : cuts.elevation;
  const anglesDeg = cut === "xy" ? cuts.az_angles_deg : cuts.elev_angles_deg;
  let peak = -Infinity;
  for (const d of dbi) if (d > peak) peak = d;
  if (!(peak > cuts.floor_dbi)) return null;
  // A mismatched angle list is a server/client disagreement, not something
  // to draw through: fall back to the uniform parameterisation rather than
  // index past the end of it.
  return {
    dbi,
    ...(anglesDeg && anglesDeg.length === dbi.length ? { anglesDeg } : {}),
    peakDbi: peak,
  };
}
