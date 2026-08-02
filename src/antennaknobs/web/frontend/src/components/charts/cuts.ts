import { useEffect, useState } from "react";
import type { PatternCuts, SolveResponse } from "../../lib/api";
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
function cachedCuts(
  result: SolveResponse,
  azElevDeg: number,
  elevAzDeg: number,
): PatternCuts | null {
  const attached = result.cuts;
  if (
    attached &&
    attached.az_elev_deg === azElevDeg &&
    attached.elev_az_deg === elevAzDeg
  ) {
    return attached;
  }
  return cutsCache.get(cutsKey(result, azElevDeg, elevAzDeg)) ?? null;
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

function cutsWsPendingKey(solveId: string, az: number, el: number): string {
  return `${solveId}:${az}:${el}`;
}

function requestCutsViaWs(
  solveId: string,
  azElevDeg: number,
  elevAzDeg: number,
): Promise<CutsWsReply> {
  const send = cutsWsSend;
  if (!send) return Promise.resolve({ status: "unavailable" });
  const key = cutsWsPendingKey(solveId, azElevDeg, elevAzDeg);
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
  ok: boolean;
  cuts?: PatternCuts;
};

export function resolveCutsWsMessage(data: CutsWsMessage): void {
  const key = cutsWsPendingKey(data.solve_id, data.az_elev_deg, data.elev_az_deg);
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

function fetchCuts(
  result: SolveResponse,
  azElevDeg: number,
  elevAzDeg: number,
): Promise<PatternCuts | null> {
  const key = cutsKey(result, azElevDeg, elevAzDeg);
  const inFlight = cutsInFlight.get(key);
  if (inFlight) return inFlight;
  const postCuts = (body: object): Promise<Response> =>
    fetch("/cuts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...body,
        az_elev_deg: azElevDeg,
        elev_az_deg: elevAzDeg,
      }),
    });
  const p = (async (): Promise<PatternCuts | null> => {
    // Transport ladder (issue #551): ws id → HTTP id → HTTP full body.
    // Every rung is strictly a fallback of the one above; the full-body
    // POST remains the correctness backstop (it's how pre-#551 responses
    // and pins from dead server sessions resolve).
    const solveId = result.solve_id;
    if (solveId) {
      const viaWs = await requestCutsViaWs(solveId, azElevDeg, elevAzDeg);
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
  })()
    .then((cuts) => {
      if (cuts) {
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
      return cuts;
    })
    .catch(() => null)
    .finally(() => cutsInFlight.delete(key));
  cutsInFlight.set(key, p);
  return p;
}

// Resolve the cut traces for a list of solves (live + pinned ghosts) at the
// current angles. Synchronous when a solve already carries or has cached the
// right angles; otherwise the freshest known trace is returned immediately
// (stale-while-refetch) and a debounced POST /cuts brings the real one — the
// debounce eats the flood of intermediate angles a slider drag produces.
export function useCutTraces(
  results: readonly (SolveResponse | null)[],
  azElevDeg: number,
  elevAzDeg: number,
): (PatternCuts | null)[] {
  const [, setFetchTick] = useState(0); // re-render when a fetch lands
  const wantKey = results
    .map((r) => (r ? cutsKey(r, azElevDeg, elevAzDeg) : "-"))
    .join("|");
  useEffect(() => {
    const missing = results.filter(
      (r): r is SolveResponse => !!r && !cachedCuts(r, azElevDeg, elevAzDeg),
    );
    if (missing.length === 0) return;
    let cancelled = false;
    // When every missing trace can go over the ws id path (~100 bytes, and
    // the server squashes per-solve latest-wins), a much tighter debounce
    // makes cut drags feel live; the original 120 ms guard stays for the
    // full-body HTTP fallback, whose requests are 10 KB–300 KB (issue #551).
    const delay =
      cutsWsSend && missing.every((r) => r.solve_id) ? 30 : 120;
    const h = window.setTimeout(() => {
      Promise.all(missing.map((r) => fetchCuts(r, azElevDeg, elevAzDeg))).then(
        () => {
          if (!cancelled) setFetchTick((t) => t + 1);
        },
      );
    }, delay);
    return () => {
      cancelled = true;
      window.clearTimeout(h);
    };
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
// cut plus their peak (for the adaptive radial scale and the annotation).
// Null when there's nothing to draw (no cuts, or everything at the floor).
export function traceFor(
  cuts: PatternCuts | null,
  cut: FarFieldCut,
): { dbi: number[]; peakDbi: number } | null {
  if (!cuts) return null;
  const dbi = cut === "xy" ? cuts.azimuth : cuts.elevation;
  let peak = -Infinity;
  for (const d of dbi) if (d > peak) peak = d;
  if (!(peak > cuts.floor_dbi)) return null;
  return { dbi, peakDbi: peak };
}
