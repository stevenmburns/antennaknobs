import type { SolveRequest } from "./api";

// Client-side twin of the server's cache key (web/server.py::
// _CACHE_KEY_BLOCKLIST) — the same idea at the other end of the wire:
// every request field is load-bearing unless explicitly exempted. Keying
// the background-analysis effects on this signature flips the invalidation
// polarity (issue #692): a new SolveRequest field invalidates every
// analysis by default, and opting *out* takes an exemption entry — the
// safe failure mode. (The old polarity — nothing invalidates unless
// hand-listed — is how the measurement plane was forgotten in #652 c.)
//
// These are the pure-metadata fields: scheduling identity, zero physics.
// Kept in lockstep with the server blocklist's metadata entries.
const METADATA_EXEMPT = [
  "_request_id",
  "_client_ts",
  "_seq",
  "_session",
  "_gen",
  "_approved",
  // Adaptive refinement's lane-kind marker (issue #744) — scheduling, not
  // physics. Never reaches a signature today (it is attached to the sweep
  // BODY, not to buildRequest's output), but the two blocklists are kept in
  // lockstep on purpose: the next field to travel both paths should not
  // have to rediscover this.
  "_refine",
] as const;

/** Stable stringification of a solve request minus the metadata fields and
 *  a per-caller exemption list — the one physics dependency an analysis
 *  effect needs. Keys are sorted recursively so the signature doesn't
 *  depend on construction order (the server hashes with sort_keys=True for
 *  the same reason), and exempt keys are dropped at every nesting level,
 *  matching the server's quantise() walk. */
export function solveSignature(
  req: SolveRequest,
  opts: { exempt?: readonly string[] } = {},
): string {
  const drop = new Set<string>([...METADATA_EXEMPT, ...(opts.exempt ?? [])]);
  const strip = (x: unknown): unknown => {
    if (Array.isArray(x)) return x.map(strip);
    if (x !== null && typeof x === "object") {
      const rec = x as Record<string, unknown>;
      return Object.fromEntries(
        Object.keys(rec)
          .filter((k) => !drop.has(k))
          .sort()
          .map((k) => [k, strip(rec[k])]),
      );
    }
    return x;
  };
  return JSON.stringify(strip(req));
}
