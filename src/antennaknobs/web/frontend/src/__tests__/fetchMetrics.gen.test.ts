// /pattern_metrics is a full momwire solve on the server (AK#1712). The live
// design's fetch must carry the channel's generation, so a newer solve
// supersedes it on the session's lane, and must be abortable, so a result
// that moved on stops it. A pinned row sends no generation: a knob drag must
// not cancel a frozen snapshot's metrics.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchMetrics } from "../components/session/contexts";
import type { SolveRequest } from "../lib/api";

const REQ = { geometry: "x", _session: "tab-1" } as unknown as SolveRequest;

function stubFetch() {
  const calls: { body: Record<string, unknown>; signal: AbortSignal | null | undefined }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init: RequestInit) => {
      calls.push({ body: JSON.parse(String(init.body)), signal: init.signal });
      return { json: async () => ({ available: true, metrics: { peak_gain_dbi: 1 } }) };
    }),
  );
  return calls;
}

describe("fetchMetrics", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("stamps the live design's generation and passes the abort signal", async () => {
    const calls = stubFetch();
    const ctrl = new AbortController();
    await fetchMetrics(REQ, { gen: 7, signal: ctrl.signal });
    expect(calls[0].body._gen).toBe(7);
    expect(calls[0].body._session).toBe("tab-1");
    expect(calls[0].signal).toBe(ctrl.signal);
  });

  it("sends no generation for a pinned row", async () => {
    const calls = stubFetch();
    await fetchMetrics(REQ);
    expect("_gen" in calls[0].body).toBe(false);
  });

  it("answers null when aborted", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new DOMException("aborted", "AbortError");
      }),
    );
    expect(await fetchMetrics(REQ, { gen: 1 })).toBeNull();
  });
});
